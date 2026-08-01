import unittest
from unittest.mock import Mock

from src.provider_router import ProviderRouter


class ProviderRouterTest(unittest.TestCase):
    def test_falls_back_when_first_provider_fails(self):
        first = Mock()
        first.api_key = "first-key"
        first.model = "first-model"
        first.generate_lesson.side_effect = RuntimeError("provider unavailable")
        second = Mock()
        second.api_key = "second-key"
        second.model = "second-model"
        second.generate_lesson.return_value = {"title": "Fallback lesson"}
        router = ProviderRouter([("first", first), ("second", second)])

        result = router.generate_lesson(
            "prompt",
            metadata={"uuid": "00000000-0000-0000-0000-000000000000"},
        )

        self.assertEqual("Fallback lesson", result["title"])
        self.assertEqual(1, first.generate_lesson.call_count)
        self.assertEqual(1, second.generate_lesson.call_count)
        first.generate_lesson.assert_called_once_with(
            "prompt",
            metadata={"uuid": "00000000-0000-0000-0000-000000000000"},
            max_retries=1,
        )

    def test_deepseek_gets_second_json_attempt_before_fallback(self):
        deepseek = Mock()
        deepseek.api_key = "deepseek-key"
        deepseek.model = "deepseek-chat"
        deepseek.generate_lesson.return_value = {"title": "Recovered JSON"}
        router = ProviderRouter([("deepseek", deepseek)])

        result = router.generate_lesson(
            "prompt",
            metadata={"uuid": "lesson-1"},
        )

        self.assertEqual("Recovered JSON", result["title"])
        deepseek.generate_lesson.assert_called_once_with(
            "prompt",
            metadata={"uuid": "lesson-1"},
            max_retries=2,
        )


if __name__ == "__main__":
    unittest.main()
