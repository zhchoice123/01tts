import itertools
import unittest

from src.lesson_review import generate_lesson_review_report


GENERATED_AT = "2026-08-01T07:00:00Z"
CLIENT_ID = "00000000-0000-0000-0000-000000000001"
CONTENT_UUID = "00000000-0000-0000-0000-000000000002"


def progress(**changes):
    payload = {"clientId": CLIENT_ID, "contentUuid": CONTENT_UUID}
    payload.update(changes)
    return payload


def report(learning_progress=None, vocabulary=(), evaluation=None):
    return generate_lesson_review_report(
        learning_progress=learning_progress or progress(),
        vocabulary_progress=vocabulary,
        speaking_evaluation=evaluation,
        generated_at=GENERATED_AT,
    )


class LessonReviewReportTest(unittest.TestCase):
    def test_no_data_marks_every_dimension_and_does_not_create_weaknesses(self):
        result = report()

        self.assertEqual(0, result["overallScore"])
        self.assertEqual(
            ["listening", "comprehension", "vocabulary", "speaking"],
            [item["key"] for item in result["dimensions"]],
        )
        self.assertTrue(
            all(
                item["score"] is None and item["status"] == "NO_DATA"
                for item in result["dimensions"]
            )
        )
        self.assertEqual([], result["weakPoints"])
        self.assertEqual(GENERATED_AT, result["generatedAt"])

    def test_full_scores_are_strong(self):
        vocabulary = [
            {"contentUuid": CONTENT_UUID, "word": "latency", "status": "KNOWN"},
            {"contentUuid": CONTENT_UUID, "word": "throughput", "status": "KNOWN"},
        ]
        result = report(
            progress(
                listeningDone=True,
                quizCorrect=5,
                quizTotal=5,
                speakingScore=100,
            ),
            vocabulary,
        )

        self.assertEqual(100, result["overallScore"])
        self.assertEqual(
            [100, 100, 100, 100],
            [dimension["score"] for dimension in result["dimensions"]],
        )
        self.assertTrue(all(d["status"] == "STRONG" for d in result["dimensions"]))
        self.assertEqual([], result["weakPoints"])

    def test_partial_data_excludes_missing_speaking_from_overall(self):
        vocabulary = [
            {"word": "cache", "status": "KNOWN"},
            {"word": "backpressure", "status": "LEARNING"},
        ]
        result = report(
            progress(positionMs=50, durationMs=100, quizCorrect=3, quizTotal=4),
            vocabulary,
        )

        dimensions = {item["key"]: item for item in result["dimensions"]}
        self.assertEqual(58, result["overallScore"])
        self.assertEqual(50, dimensions["listening"]["score"])
        self.assertEqual(75, dimensions["comprehension"]["score"])
        self.assertEqual(50, dimensions["vocabulary"]["score"])
        self.assertIsNone(dimensions["speaking"]["score"])
        self.assertEqual("NO_DATA", dimensions["speaking"]["status"])

    def test_zero_quiz_total_is_no_data_not_zero_score(self):
        result = report(progress(quizCorrect=0, quizTotal=0))
        comprehension = result["dimensions"][1]

        self.assertIsNone(comprehension["score"])
        self.assertEqual("NO_DATA", comprehension["status"])
        self.assertFalse(
            any(
                point["kind"] == "COMPREHENSION"
                for point in result["weakPoints"]
            )
        )

    def test_no_vocabulary_is_no_data(self):
        result = report(progress(listeningDone=True), [])
        vocabulary = result["dimensions"][2]

        self.assertEqual(100, result["overallScore"])
        self.assertIsNone(vocabulary["score"])
        self.assertEqual("NO_DATA", vocabulary["status"])

    def test_low_speaking_uses_evaluation_and_its_real_improvement(self):
        result = report(
            progress(speakingScore=95),
            evaluation={
                "overallScore": 42,
                "improvements": ["Slow down before stressed words."],
            },
        )
        speaking = result["dimensions"][3]
        weakness = next(p for p in result["weakPoints"] if p["kind"] == "SPEAKING")

        self.assertEqual(42, speaking["score"])
        self.assertEqual("NEEDS_WORK", speaking["status"])
        self.assertEqual("Slow down before stressed words.", weakness["detail"])

    def test_scores_are_clamped_to_zero_and_one_hundred(self):
        high = report(
            progress(
                positionMs=250,
                durationMs=100,
                quizCorrect=9,
                quizTotal=3,
                speakingScore=500,
            )
        )
        low = report(progress(positionMs=-10, durationMs=100, speakingScore=-30))

        high_dimensions = {item["key"]: item["score"] for item in high["dimensions"]}
        low_dimensions = {item["key"]: item["score"] for item in low["dimensions"]}
        self.assertEqual(100, high_dimensions["listening"])
        self.assertEqual(100, high_dimensions["comprehension"])
        self.assertEqual(100, high_dimensions["speaking"])
        self.assertEqual(0, low_dimensions["listening"])
        self.assertEqual(0, low_dimensions["speaking"])

    def test_aggregate_quiz_score_does_not_invent_a_specific_wrong_answer(self):
        result = report(progress(quizCorrect=1, quizTotal=4))
        weakness = next(
            point for point in result["weakPoints"] if point["kind"] == "COMPREHENSION"
        )

        self.assertEqual("Review lesson comprehension", weakness["title"])
        self.assertIn("Quiz accuracy is 25%", weakness["detail"])
        self.assertNotIn("question", weakness["detail"].lower())
        self.assertNotIn("answer", weakness["detail"].lower())

    def test_vocabulary_weak_points_are_limited_and_deterministic(self):
        vocabulary = [
            {"word": "Zulu", "status": "NEW"},
            {"word": "alpha", "status": "LEARNING"},
            {"word": "Echo", "status": "LEARNING"},
            {"word": "bravo", "status": "NEW"},
            {"word": "delta", "status": "NEW"},
            {"word": "charlie", "status": "NEW"},
            {"word": "foxtrot", "status": "NEW"},
            {"word": "ignored", "status": "KNOWN", "contentUuid": "another-course"},
        ]
        expected = None
        for permutation in itertools.islice(itertools.permutations(vocabulary), 12):
            current = report(progress(), permutation)
            if expected is None:
                expected = current
            else:
                self.assertEqual(expected, current)

        word_points = [
            item for item in expected["weakPoints"] if item["kind"] == "VOCABULARY_WORD"
        ]
        self.assertEqual(5, len(word_points))
        self.assertEqual(
            ["alpha", "Echo", "bravo", "charlie", "delta"],
            [item["title"] for item in word_points],
        )

    def test_required_ids_are_validated(self):
        with self.assertRaisesRegex(ValueError, "clientId and contentUuid"):
            report({"clientId": CLIENT_ID})


if __name__ == "__main__":
    unittest.main()
