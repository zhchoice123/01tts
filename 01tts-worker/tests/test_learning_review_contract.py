import json
import unittest
from pathlib import Path

from src.lesson_review import generate_lesson_review_report
from src.review_queue import build_review_queue


CONTRACT_DIR = (
    Path(__file__).resolve().parents[2] / "contracts" / "learning_review"
)


def load_contract(name: str) -> dict:
    with (CONTRACT_DIR / name).open(encoding="utf-8") as contract_file:
        return json.load(contract_file)


class LearningReviewSharedContractTest(unittest.TestCase):
    def test_lesson_review_matches_shared_contract_exactly(self):
        contract = load_contract("lesson_review_case.json")
        inputs = contract["inputs"]

        actual = generate_lesson_review_report(
            learning_progress=inputs["learningProgress"],
            vocabulary_progress=inputs["vocabularyProgress"],
            speaking_evaluation=inputs["speakingEvaluation"],
            generated_at=inputs["generatedAt"],
        )

        self.assertEqual(contract["expected"], actual)

    def test_review_queue_matches_shared_contract_exactly(self):
        contract = load_contract("review_queue_case.json")
        inputs = contract["inputs"]

        actual = build_review_queue(
            client_id=inputs["clientId"],
            as_of=inputs["asOf"],
            vocabulary_progress=inputs["vocabularyProgress"],
            course_weaknesses=inputs["courseWeaknesses"],
            limit=inputs["limit"],
        )

        self.assertEqual(contract["expected"], actual)


if __name__ == "__main__":
    unittest.main()
