import json
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
        self.assertEqual("TRANSCRIPT_FALLBACK", result["evaluation"]["mode"])

    @patch("src.speaking_service.subprocess.run")
    @patch("src.speaking_service.requests.post")
    def test_assess_uses_direct_audio_scores(self, post, run):
        def create_wav(command, **kwargs):
            Path(command[-1]).write_bytes(b"RIFF-audio")
            return Mock()

        run.side_effect = create_wav
        transcription = Mock()
        transcription.json.return_value = {"text": "Locks protect shared state."}
        audio_evaluation = Mock()
        audio_evaluation.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "pronunciationScore": 90,
                                "fluencyScore": 86,
                                "intonationScore": 80,
                                "pacingScore": 84,
                                "relevanceScore": 92,
                                "grammarScore": 88,
                                "vocabularyScore": 82,
                                "summary": "Clear and relevant.",
                                "strengths": ["Clear consonants"],
                                "improvements": ["Vary sentence stress"],
                                "practicePlan": ["Shadow the model answer"],
                            }
                        )
                    }
                }
            ]
        }
        post.side_effect = [transcription, audio_evaluation]
        service = SpeakingAssessmentService("openai", "deepseek")

        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "answer.m4a"
            audio.write_bytes(b"audio")
            result = service.assess(audio, "Explain locking.")

        self.assertEqual("AUDIO_AND_TRANSCRIPT", result["evaluation"]["mode"])
        self.assertEqual(90, result["evaluation"]["pronunciationScore"])
        self.assertEqual(result["evaluation"]["overallScore"], result["score"])
