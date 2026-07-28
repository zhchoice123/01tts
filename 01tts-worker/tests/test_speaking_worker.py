import unittest

from worker import SpeakingAnswerWorker


class SpeakingAnswerWorkerTest(unittest.TestCase):
    def test_extracts_speaking_question(self):
        raw = (
            '[{"type":"multiple_choice","question":"Choose."},'
            '{"type":"speaking","question":"Explain fairness."}]'
        )
        self.assertEqual(
            "Explain fairness.", SpeakingAnswerWorker._speaking_question(raw))
