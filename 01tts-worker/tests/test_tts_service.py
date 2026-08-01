import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.tts_service import (
    _openai_voice,
    _post_speech,
    _split_text,
    generate_audio,
    generate_dialogue_audio,
)


class TtsServiceTest(unittest.IsolatedAsyncioTestCase):
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
                "en-US-AvaNeural",
                word_timings=timings,
                api_key="test-openai-key",
            )
            self.assertEqual(b"ID3-openai-audio", target.read_bytes())

        self.assertEqual(target, result)
        self.assertEqual(2, len(timings))
        self.assertEqual("nova", synthesize.call_args.kwargs["voice"])
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
                "nova",
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
    @patch("src.tts_service._synthesize_text")
    async def test_dialogue_audio_uses_two_voices_and_global_whisper_timeline(
        self,
        synthesize,
        probe_duration,
        concatenate,
        transcribe,
    ):
        def create_segment(text, output_path, **kwargs):
            output_path.write_bytes(b"segment")

        def create_output(segment_paths, output_path, work_dir):
            output_path.write_bytes(b"dialogue")

        synthesize.side_effect = create_segment
        concatenate.side_effect = create_output
        probe_duration.side_effect = [2100, 3900, 6000]
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
                api_key="test-openai-key",
            )
            self.assertEqual(b"dialogue", target.read_bytes())
            self.assertEqual(0, turns[0]["startMs"])
            self.assertEqual(2100, turns[0]["endMs"])
            self.assertEqual(2100, turns[1]["startMs"])
            self.assertEqual(6000, turns[1]["endMs"])
            self.assertEqual("What", turns[0]["words"][0]["text"])
            self.assertEqual(0, turns[0]["words"][0]["charStart"])
            self.assertEqual("A", turns[1]["words"][0]["text"])
            self.assertEqual(0, turns[1]["words"][0]["charStart"])

        self.assertEqual(target, result)
        self.assertEqual(
            ["nova", "onyx"],
            [call.kwargs["voice"] for call in synthesize.call_args_list],
        )
        self.assertEqual(
            [0.9, 0.9],
            [call.kwargs["speed"] for call in synthesize.call_args_list],
        )
        transcribe.assert_called_once()

    def test_splits_long_text_and_maps_legacy_voice_names(self):
        text = ("A" * 3600) + " sentence end. A short final sentence."
        chunks = _split_text(text)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(len(chunk) <= 3500 for chunk in chunks))
        self.assertEqual("nova", _openai_voice("en-US-AvaNeural"))
        self.assertEqual("onyx", _openai_voice("en-US-AndrewNeural"))
        self.assertEqual("shimmer", _openai_voice("shimmer"))
