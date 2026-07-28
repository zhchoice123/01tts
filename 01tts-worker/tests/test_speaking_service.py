import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.speaking_service import SpeakingAssessmentService


class SpeakingAssessmentServiceTest(unittest.TestCase):
    @patch("src.speaking_service.requests.post")
    def test_assess_transcribes_and_scores_recording(self, post):
        transcription = Mock()
        transcription.json.return_value = {"text": "Locks protect shared state."}
        scoring = Mock()
        scoring.json.return_value = {
            "choices": [
                {"message": {"content": '{"score": 82, "feedback": "Clear answer."}'}}
            ]
        }
        post.side_effect = [transcription, scoring]
        service = SpeakingAssessmentService("openai", "deepseek")

        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "answer.m4a"
            audio.write_bytes(b"audio")
            result = service.assess(audio, "Explain locking.")

        self.assertEqual(82, result["score"])
        self.assertEqual("Locks protect shared state.", result["transcript"])
