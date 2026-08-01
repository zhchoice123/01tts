import unittest
from dataclasses import dataclass
from datetime import datetime, timezone

from src.review_queue import VocabularyProgress, build_review_queue


AS_OF = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def vocabulary(word, status, updated_at, content_uuid="course-1"):
    return {
        "contentUuid": content_uuid,
        "word": word,
        "status": status,
        "updatedAt": updated_at,
    }


class ReviewQueueTests(unittest.TestCase):
    def test_empty_input_has_zero_estimate(self):
        queue = build_review_queue("client-1", AS_OF, [])

        self.assertEqual("client-1", queue["clientId"])
        self.assertEqual("2026-08-01", queue["date"])
        self.assertEqual(0, queue["totalCount"])
        self.assertEqual(0, queue["estimatedMinutes"])
        self.assertEqual([], queue["items"])

    def test_status_intervals_only_return_due_items(self):
        rows = [
            vocabulary("new", "NEW", "2026-08-01T12:00:00Z"),
            vocabulary("learning-due", "LEARNING", "2026-07-31T12:00:00Z"),
            vocabulary("learning-future", "LEARNING", "2026-08-01T00:00:00Z"),
            vocabulary("known-due", "KNOWN", "2026-07-25T12:00:00Z"),
            vocabulary("known-future", "KNOWN", "2026-07-26T12:00:01Z"),
        ]

        queue = build_review_queue("client-1", AS_OF, rows)

        self.assertEqual(
            ["new", "learning-due", "known-due"],
            [item["word"] for item in queue["items"]],
        )
        self.assertEqual(
            ["2026-08-01T12:00:00Z"] * 3,
            [item["dueAt"] for item in queue["items"]],
        )

    def test_normalized_word_dedup_keeps_more_urgent_candidate(self):
        rows = [
            vocabulary("  Data   Race ", "KNOWN", "2026-07-20T00:00:00Z", "old"),
            vocabulary("data race", "NEW", "2026-08-01T10:00:00Z", "new"),
            vocabulary("ＤＡＴＡ RACE", "LEARNING", "2026-07-30T00:00:00Z", "wide"),
        ]

        queue = build_review_queue("client-1", AS_OF, rows)

        self.assertEqual(1, queue["totalCount"])
        self.assertEqual("new", queue["items"][0]["contentUuid"])
        self.assertEqual("NEW", queue["items"][0]["status"])
        self.assertEqual("REVIEW_WORD", queue["items"][0]["action"])

    def test_output_date_uses_as_of_timezone_and_due_at_is_utc(self):
        as_of = datetime.fromisoformat("2026-08-02T00:30:00+08:00")
        row = vocabulary("timezone", "LEARNING", "2026-08-01T00:30:00+08:00")

        queue = build_review_queue("client-1", as_of, [row])

        self.assertEqual("2026-08-02", queue["date"])
        self.assertEqual("2026-08-01T16:30:00Z", queue["items"][0]["dueAt"])

    def test_future_new_timestamp_is_not_due(self):
        row = vocabulary("clock-skew", "NEW", "2026-08-01T12:00:01Z")
        self.assertEqual(0, build_review_queue("client-1", AS_OF, [row])["totalCount"])

    def test_default_limit_is_ten_and_custom_limit_is_honored(self):
        rows = [
            vocabulary(f"word-{index:02d}", "NEW", "2026-07-30T00:00:00Z")
            for index in range(20)
        ]

        default_queue = build_review_queue("client-1", AS_OF, rows)
        short_queue = build_review_queue("client-1", AS_OF, rows, limit=3)

        self.assertEqual(10, default_queue["totalCount"])
        self.assertEqual(10, default_queue["estimatedMinutes"])
        self.assertEqual(3, short_queue["totalCount"])

    def test_estimate_is_capped_for_large_explicit_limit(self):
        rows = [
            vocabulary(f"word-{index:02d}", "NEW", "2026-07-30T00:00:00Z")
            for index in range(30)
        ]
        queue = build_review_queue("client-1", AS_OF, rows, limit=30)
        self.assertEqual(30, queue["totalCount"])
        self.assertEqual(15, queue["estimatedMinutes"])

    def test_sort_is_stable_across_input_order(self):
        rows = [
            vocabulary("beta", "LEARNING", "2026-07-30T12:00:00Z", "c2"),
            vocabulary("alpha", "LEARNING", "2026-07-30T12:00:00Z", "c1"),
        ]

        first = build_review_queue("client-1", AS_OF, rows)
        second = build_review_queue("client-1", AS_OF, reversed(rows))

        self.assertEqual(first, second)

    def test_invalid_status_and_invalid_timestamp_are_ignored(self):
        rows = [
            vocabulary("bad-status", "MASTERED", "2026-07-01T00:00:00Z"),
            vocabulary("bad-time", "NEW", "not-a-time"),
            vocabulary("good", "new", "2026-07-01T00:00:00Z"),
        ]
        queue = build_review_queue("client-1", AS_OF, rows)
        self.assertEqual(["good"], [item["word"] for item in queue["items"]])

    def test_dataclass_and_snake_case_attributes_are_supported(self):
        @dataclass
        class SnakeProgress:
            content_uuid: str
            word: str
            status: str
            updated_at: datetime

        rows = [
            VocabularyProgress("course-1", "typed", "NEW", AS_OF),
            SnakeProgress("course-2", "snake", "LEARNING", datetime(2026, 7, 30)),
        ]
        queue = build_review_queue("client-1", AS_OF, rows)
        self.assertEqual({"typed", "snake"}, {item["word"] for item in queue["items"]})

    def test_overdue_then_priority_then_due_time(self):
        rows = [
            vocabulary("known-old", "KNOWN", "2026-07-01T00:00:00Z"),
            vocabulary("new-recent", "NEW", "2026-08-01T11:00:00Z"),
            vocabulary("learning-older", "LEARNING", "2026-07-20T00:00:00Z"),
            vocabulary("new-now", "NEW", "2026-08-01T12:00:00Z"),
        ]
        queue = build_review_queue("client-1", AS_OF, rows)
        self.assertEqual(
            ["new-recent", "learning-older", "known-old", "new-now"],
            [item["word"] for item in queue["items"]],
        )

    def test_due_weak_lesson_is_mixed_with_vocabulary(self):
        rows = [vocabulary("known", "KNOWN", "2026-07-01T00:00:00Z")]
        weaknesses = [
            {
                "contentUuid": "lesson-1",
                "title": "Connection pools",
                "reason": "Listening score was below 60%.",
                "priority": 1,
                "dueAt": "2026-07-31T00:00:00Z",
            },
            {
                "contentUuid": "lesson-future",
                "title": "Not due",
                "priority": 1,
                "dueAt": "2026-08-02T00:00:00Z",
            },
        ]

        queue = build_review_queue("client-1", AS_OF, rows, weaknesses)

        self.assertEqual(["LESSON", "VOCABULARY"], [item["type"] for item in queue["items"]])
        lesson = queue["items"][0]
        self.assertEqual("NEEDS_REVIEW", lesson["status"])
        self.assertIsNone(lesson["word"])
        self.assertEqual("REVIEW_LESSON", lesson["action"])


if __name__ == "__main__":
    unittest.main()
