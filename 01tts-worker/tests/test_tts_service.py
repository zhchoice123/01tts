import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.tts_service import (
    _concat_mp3,
    _probe_duration_ms,
    _tts_provider_voice,
    _openai_voice,
    _post_speech,
    _split_text,
    generate_audio,
    generate_dialogue_audio,
)


class TtsServiceTest(unittest.IsolatedAsyncioTestCase):
    def test_provider_prefixed_voice_is_parsed(self):
        self.assertEqual(
            _tts_provider_voice("aliyun:loongdavid_v2"),
            ("aliyun", "loongdavid_v2"),
        )
        self.assertEqual(_tts_provider_voice("openai:nova"), ("openai", "nova"))

    @patch.dict("os.environ", {}, clear=True)
    def test_unprefixed_voice_defaults_to_aliyun(self):
        self.assertEqual(("aliyun", "loongdavid_v2"), _tts_provider_voice(""))

    @patch.dict("os.environ", {}, clear=True)
    def test_legacy_voices_keep_gender_and_accent_on_aliyun(self):
        # Regression: Ava and Andrew used to swap genders, so dialogue HOST and
        # EXPERT were voiced opposite to their configured voices.
        expected = {
            "en-US-AvaNeural": "loongabby_v2",
            "en-US-AndrewNeural": "loongdavid_v2",
            "en-GB-SoniaNeural": "loongemily_v2",
            "en-GB-RyanNeural": "loongeric_v2",
        }
        for legacy, aliyun in expected.items():
            with self.subTest(legacy=legacy):
                self.assertEqual(("aliyun", aliyun), _tts_provider_voice(legacy))

    @patch("src.tts_service._transcribe_word_timings")
    @patch("src.tts_service._synthesize_text")
    async def test_generate_audio_uses_openai_speech_and_whisper(
        self,
        synthesize,
        transcribe,
    ):
        def create_audio(text, output_path, **kwargs):
            output_path.write_bytes(b"ID3-openai-audio")

        synthesize.side_effect = create_audio
        transcribe.return_value = [
            {
                "text": "Hello",
                "startMs": 120,
                "endMs": 420,
                "charStart": 0,
                "charEnd": 5,
            },
            {
                "text": "world",
                "startMs": 450,
                "endMs": 700,
                "charStart": 7,
                "charEnd": 12,
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "sample.mp3"
            timings = []
            result = await generate_audio(
                "Hello, world!",
                target,
                "openai:nova",
                word_timings=timings,
                api_key="test-openai-key",
            )
            self.assertEqual(b"ID3-openai-audio", target.read_bytes())

        self.assertEqual(target, result)
        self.assertEqual(2, len(timings))
        self.assertEqual("openai:nova", synthesize.call_args.kwargs["voice"])
        self.assertEqual("tts-1-hd", synthesize.call_args.kwargs["model"])
        self.assertEqual(
            "whisper-1",
            transcribe.call_args.kwargs["model"],
        )
        self.assertEqual("test-openai-key", transcribe.call_args.kwargs["api_key"])

    @patch("src.tts_service._probe_duration_ms", return_value=4_000)
    @patch("src.tts_service._transcribe_word_timings", side_effect=RuntimeError("timeout"))
    @patch("src.tts_service._synthesize_text")
    async def test_generate_audio_keeps_mp3_with_estimated_timings_when_whisper_fails(
        self,
        synthesize,
        transcribe,
        probe_duration,
    ):
        synthesize.side_effect = lambda text, output_path, **kwargs: output_path.write_bytes(b"ID3")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "fallback.mp3"
            timings = []
            await generate_audio(
                "Retrying audio keeps the lesson playable.",
                target,
                "openai:nova",
                word_timings=timings,
                api_key="test-key",
            )

            self.assertEqual(b"ID3", target.read_bytes())
            self.assertTrue(timings)
            self.assertTrue(all(item["estimated"] for item in timings))
            self.assertEqual(0, timings[0]["startMs"])
            self.assertEqual(4_000, timings[-1]["endMs"])
        transcribe.assert_called_once()
        probe_duration.assert_called_once()

    @patch("src.tts_service.time.sleep")
    @patch("src.tts_service.requests.post")
    def test_speech_request_retries_transient_failure(self, post, sleep):
        success = Mock(status_code=200, content=b"ID3-success")
        post.side_effect = [RuntimeError("connection reset"), success]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "retry.mp3"
            _post_speech(
                "Reliable speech",
                target,
                api_key="test-key",
                model="tts-1-hd",
                voice="nova",
            )
            self.assertEqual(b"ID3-success", target.read_bytes())
        self.assertEqual(2, post.call_count)
        sleep.assert_called_once_with(1)

    @patch("src.tts_service._transcribe_word_timings")
    @patch("src.tts_service._concat_mp3")
    @patch("src.tts_service._probe_duration_ms")
    @patch("src.tts_service._synthesize_segments")
    async def test_dialogue_audio_uses_two_voices_and_global_whisper_timeline(
        self,
        synthesize,
        probe_duration,
        concatenate,
        transcribe,
    ):
        def create_segments(text, *, work_dir, **kwargs):
            work_dir.mkdir(parents=True, exist_ok=True)
            segment = work_dir / "speech-000.mp3"
            segment.write_bytes(b"segment")
            return [segment]

        def create_output(segment_paths, output_path, work_dir, gaps_ms):
            output_path.write_bytes(b"dialogue")

        synthesize.side_effect = create_segments
        concatenate.side_effect = create_output
        # Two turns of speech plus one 450 ms conversational pause.
        probe_duration.side_effect = [2100, 3900, 6450]
        transcribe.return_value = [
            {
                "text": "What",
                "startMs": 10,
                "endMs": 500,
                "charStart": 0,
                "charEnd": 4,
            },
            {
                "text": "A",
                "startMs": 2120,
                "endMs": 2250,
                "charStart": 24,
                "charEnd": 25,
            },
        ]

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "dialogue.mp3"
            turns = [
                {"speaker": "HOST", "text": "What caused the outage?"},
                {
                    "speaker": "EXPERT",
                    "text": "A database connection pool was exhausted.",
                },
            ]
            result = await generate_dialogue_audio(
                turns,
                target,
                host_voice="openai:nova",
                expert_voice="openai:onyx",
                api_key="test-openai-key",
            )
            self.assertEqual(b"dialogue", target.read_bytes())
            self.assertEqual(0, turns[0]["startMs"])
            self.assertEqual(2550, turns[0]["endMs"])
            self.assertEqual(2550, turns[1]["startMs"])
            self.assertEqual(6450, turns[1]["endMs"])
            self.assertEqual([450, 0], concatenate.call_args.args[3])
            self.assertEqual("What", turns[0]["words"][0]["text"])
            self.assertEqual(0, turns[0]["words"][0]["charStart"])
            self.assertEqual("A", turns[1]["words"][0]["text"])
            self.assertEqual(0, turns[1]["words"][0]["charStart"])

        self.assertEqual(target, result)
        self.assertEqual(
            ["openai:nova", "openai:onyx"],
            [call.kwargs["voice"] for call in synthesize.call_args_list],
        )
        # Slow playback belongs to the player; synthesis keeps natural prosody.
        self.assertTrue(
            all("speed" not in call.kwargs for call in synthesize.call_args_list)
        )
        transcribe.assert_called_once()

    @patch("src.tts_service.subprocess.run")
    def test_concat_normalizes_each_segment_and_inserts_gaps(self, run):
        paths = [Path("a.mp3"), Path("b.mp3"), Path("c.mp3")]
        _concat_mp3(paths, Path("out.mp3"), Path("."), [450, 150, 0])

        command = run.call_args.args[0]
        graph = command[command.index("-filter_complex") + 1]
        self.assertEqual(3, graph.count("loudnorm=I=-16"))
        self.assertIn("[0:a]aformat=channel_layouts=mono", graph)
        self.assertIn("apad=pad_dur=0.450[a0]", graph)
        self.assertIn("apad=pad_dur=0.150[a1]", graph)
        self.assertIn("aresample=24000[a2]", graph)
        self.assertIn("[a0][a1][a2]concat=n=3:v=0:a=1[out]", graph)
        self.assertNotIn("copy", command)

    def test_concat_rejects_mismatched_gaps(self):
        with self.assertRaises(ValueError):
            _concat_mp3([Path("a.mp3")], Path("out.mp3"), Path("."), [0, 0])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg not installed")
    def test_concat_output_length_includes_pauses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            segments = []
            for index, (frequency, rate) in enumerate(((440, 24000), (660, 44100))):
                segment = root / f"tone-{index}.mp3"
                subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                     "-i", f"sine=frequency={frequency}:sample_rate={rate}:duration=1",
                     "-c:a", "libmp3lame", str(segment)],
                    check=True,
                )
                segments.append(segment)
            output = root / "joined.mp3"
            _concat_mp3(segments, output, root, [500, 0])
            self.assertAlmostEqual(2500, _probe_duration_ms(output), delta=120)

    def test_splits_long_text_and_maps_legacy_voice_names(self):
        text = ("A" * 3600) + " sentence end. A short final sentence."
        chunks = _split_text(text)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(len(chunk) <= 3500 for chunk in chunks))
        self.assertEqual("nova", _openai_voice("en-US-AvaNeural"))
        self.assertEqual("onyx", _openai_voice("en-US-AndrewNeural"))
        self.assertEqual("shimmer", _openai_voice("shimmer"))

    def test_voice_validation_rejects_invalid_inputs(self):
        with self.assertRaises(ValueError):
            _tts_provider_voice("unsupported:voice")
        with self.assertRaises(ValueError):
            _tts_provider_voice("aliyun:invalid_voice")
        with self.assertRaises(ValueError):
            _tts_provider_voice("openai:invalid_voice")
        with self.assertRaises(ValueError):
            _tts_provider_voice("::")

    def test_voice_validation_accepts_valid_inputs(self):
        self.assertEqual(("aliyun", "loongdavid_v2"), _tts_provider_voice("aliyun:loongdavid_v2"))
        self.assertEqual(("openai", "nova"), _tts_provider_voice("openai:nova"))
        with self.assertRaisesRegex(ValueError, "provider:voice"):
            _tts_provider_voice("openai:openai:nova")
        with self.assertRaisesRegex(ValueError, "provider:voice"):
            _tts_provider_voice("openai:garbage:nova")
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                ("aliyun", "loongdavid_v2"),
                _tts_provider_voice("en-US-AndrewNeural"),
            )
