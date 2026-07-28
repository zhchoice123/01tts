import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.tts_service import generate_audio, generate_dialogue_audio


class TtsServiceTest(unittest.IsolatedAsyncioTestCase):
    @patch("src.tts_service.edge_tts.Communicate")
    async def test_generate_audio_delegates_to_edge_tts(self, communicate):
        communicate.return_value.save = AsyncMock()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "sample.mp3"
            result = await generate_audio("hello", target, "en-US-AvaNeural")
        self.assertEqual(target, result)
        communicate.return_value.save.assert_awaited_once_with(str(target))

    @patch("src.tts_service.subprocess.run")
    @patch("src.tts_service.edge_tts.Communicate")
    async def test_dialogue_audio_uses_alternating_voices_and_ffmpeg(
        self,
        communicate,
        run,
    ):
        async def save_segment(path):
            Path(path).write_bytes(b"segment")

        communicate.return_value.save = AsyncMock(side_effect=save_segment)

        def create_output(command, check):
            self.assertTrue(check)
            Path(command[-1]).write_bytes(b"dialogue")

        run.side_effect = create_output
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "dialogue.mp3"
            result = await generate_dialogue_audio(
                [
                    {"speaker": "HOST", "text": "What caused the outage?"},
                    {
                        "speaker": "EXPERT",
                        "text": "A database connection pool was exhausted.",
                    },
                ],
                target,
            )
            self.assertEqual(b"dialogue", target.read_bytes())

        self.assertEqual(target, result)
        self.assertEqual(
            ["en-US-AvaNeural", "en-US-AndrewNeural"],
            [
                call.kwargs["voice"]
                for call in communicate.call_args_list
            ],
        )
        self.assertTrue(
            all(
                call.kwargs["rate"] == "-5%"
                for call in communicate.call_args_list
            )
        )
        run.assert_called_once()
