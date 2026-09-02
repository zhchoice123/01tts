import json
import unittest
from unittest.mock import Mock, patch

from src.deepseek_service import DeepSeekService, count_english_words, parse_model_json


class DeepSeekServiceTest(unittest.TestCase):
    def test_count_english_words_handles_hyphenated_terms(self):
        self.assertEqual(5, count_english_words("A cloud-native service isn't fragile."))

    def test_parse_model_json_repairs_markdown_and_trailing_commas(self):
        content = """
        Here is the lesson:
        ```json
        {
          "title": "Generated lesson",
          "vocabulary": [
            {"word": "record", "definition": "data carrier",},
          ],
        }
        ```
        """

        parsed = parse_model_json(content)

        self.assertEqual("Generated lesson", parsed["title"])
        self.assertEqual("record", parsed["vocabulary"][0]["word"])

    def test_parse_model_json_preserves_commas_inside_strings(self):
        parsed = parse_model_json(
            '{"title":"Records, classes, and data", "passage":"Use }, in text",}'
        )

        self.assertEqual("Records, classes, and data", parsed["title"])
        self.assertEqual("Use }, in text", parsed["passage"])

    @patch("src.deepseek_service.time.sleep")
    @patch("src.deepseek_service.requests.post")
    def test_deepseek_dialogue_retries_malformed_json_once(
        self,
        mock_post,
        mock_sleep,
    ):
        malformed = Mock()
        malformed.raise_for_status.return_value = None
        malformed.json.return_value = {
            "choices": [{"message": {"content": '{"dialogue": ['}}]
        }
        valid = Mock()
        valid.raise_for_status.return_value = None
        valid.json.return_value = {
            "choices": [{"message": {"content": '{"dialogue": []}'}}]
        }
        mock_post.side_effect = [malformed, valid]

        result = DeepSeekService(api_key="test-key")._generate_dialogue_json(
            "Create a dialogue",
            max_tokens=6000,
            max_retries=1,
        )

        self.assertEqual([], result["dialogue"])
        self.assertEqual(2, mock_post.call_count)
        mock_sleep.assert_called_once()

    @patch("src.deepseek_service.requests.post")
    def test_generate_lesson_valid_schema(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "title": "Concurrency in Java",
                                "level": "B2",
                                "passage": "Virtual threads enable high-throughput concurrent applications.",
                                "simplifiedPassage": "Virtual threads help applications run faster.",
                                "vocabulary": [
                                    {
                                        "word": "concurrency",
                                        "phonetic": "",
                                        "definition": "executing simultaneously",
                                        "example": "Java uses threads for concurrency.",
                                    }
                                ],
                                "questions": [
                                    {
                                        "type": "INFERENCE",
                                        "prompt": "What do virtual threads enable?",
                                        "options": ["A. High throughput", "B. Slow code"],
                                        "answer": "A",
                                        "explanation": "Stated in passage.",
                                    }
                                ],
                                "speakingPrompts": ["Summarize virtual threads."],
                            }
                        )
                    }
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        service = DeepSeekService(api_key="test-key")
        lesson = service.generate_lesson("Explain virtual threads")

        self.assertEqual("Concurrency in Java", lesson["title"])
        self.assertEqual("B2", lesson["level"])
        self.assertEqual(1, len(lesson["vocabulary"]))
        self.assertEqual(1, len(lesson["questions"]))
        request_body = mock_post.call_args.kwargs["json"]
        self.assertEqual(4096, request_body["max_tokens"])
        self.assertEqual(0.2, request_body["temperature"])
        self.assertEqual({"type": "disabled"}, request_body["thinking"])

    @patch("src.deepseek_service.requests.post")
    def test_long_lesson_expands_short_response_and_uses_large_token_budget(self, mock_post):
        def lesson_json(word_count):
            return json.dumps(
                {
                    "title": "Reliable Backends",
                    "level": "B2",
                    "passage": " ".join(["backend"] * word_count),
                    "simplifiedPassage": "A reliable backend handles failure.",
                    "vocabulary": [
                        {"word": f"resilience{i}", "definition": "ability to recover"}
                        for i in range(12)
                    ],
                    "questions": [
                        {"type": "INFERENCE", "prompt": f"Why recover {i}?", "options": ["A"], "answer": "A", "explanation": "Reliability."}
                        for i in range(5)
                    ],
                    "speakingPrompts": ["Explain resilience.", "Describe a failure."],
                    "writingPrompts": ["Write about a recovery plan."],
                }
            )

        first = Mock()
        first.raise_for_status.return_value = None
        first.json.return_value = {"choices": [{"message": {"content": lesson_json(300)}}]}
        second = Mock()
        second.raise_for_status.return_value = None
        second.json.return_value = {"choices": [{"message": {"content": lesson_json(1250)}}]}
        mock_post.side_effect = [first, second]

        lesson = DeepSeekService(api_key="test-key").generate_long_lesson(
            "Explain resilient services", max_retries=1
        )

        self.assertEqual(1250, lesson["wordCount"])
        self.assertEqual(2, mock_post.call_count)
        self.assertEqual(8192, mock_post.call_args_list[0].kwargs["json"]["max_tokens"])
        self.assertIn("previous JSON lesson", mock_post.call_args_list[1].kwargs["json"]["messages"][1]["content"])

    @patch("src.deepseek_service.requests.post")
    def test_dialogue_lesson_builds_passage_from_alternating_turns(self, mock_post):
        turns = [
            {
                "speaker": "HOST" if index % 2 == 0 else "EXPERT",
                "text": " ".join(["backend"] * 50),
            }
            for index in range(16)
        ]
        payload = {
            "title": "Production Database Latency",
            "level": "B1",
            "dialogue": turns,
            "simplifiedPassage": "A host and expert discuss database latency.",
            "vocabulary": [
                {
                    "word": f"term{i}",
                    "phonetic": "",
                    "definition": "technical term",
                    "meaningZh": "技术术语",
                    "example": "The team uses this term.",
                    "collocations": [],
                    "usageNotes": "",
                }
                for i in range(10)
            ],
            "questions": [
                {
                    "type": "INFERENCE",
                    "prompt": f"Question {i}",
                    "options": ["A", "B", "C", "D"],
                    "answer": "A",
                    "explanation": "Because of the evidence.",
                }
                for i in range(5)
            ],
            "speakingPrompts": ["Explain the incident.", "Suggest a fix."],
            "writingPrompts": ["Write an incident review."],
        }
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(payload)}}]
        }
        mock_post.return_value = response

        lesson = DeepSeekService(api_key="test-key").generate_dialogue_lesson(
            "Discuss production database latency",
            metadata={"uuid": "dialogue-1", "sourceType": "TEXT"},
            max_retries=1,
        )

        self.assertEqual("DIALOGUE", lesson["format"])
        self.assertEqual(800, lesson["wordCount"])
        self.assertIn("Host:", lesson["passage"])
        self.assertIn("Expert:", lesson["passage"])
        self.assertEqual(16, len(lesson["dialogue"]))
        self.assertEqual(
            7200,
            mock_post.call_args.kwargs["json"]["max_tokens"],
        )

    @patch("src.deepseek_service.requests.post")
    def test_dialogue_refinement_reuses_short_draft_with_exact_turn_budget(self, mock_post):
        def payload(words_per_turn):
            return {
                "title": "Reliable Queues",
                "level": "B1",
                "dialogue": [
                    {
                        "speaker": "HOST" if index % 2 == 0 else "EXPERT",
                        "text": " ".join(["queue"] * words_per_turn),
                    }
                    for index in range(16)
                ],
                "simplifiedPassage": "A queue discussion.",
                "vocabulary": [
                    {"word": f"term{i}", "definition": "definition"}
                    for i in range(10)
                ],
                "questions": [
                    {"prompt": f"Question {i}", "options": ["A"], "answer": "A"}
                    for i in range(5)
                ],
                "speakingPrompts": ["Explain queues.", "Describe a retry."],
                "writingPrompts": ["Write a runbook."],
            }

        responses = []
        for lesson in (payload(25), payload(50)):
            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "choices": [{"message": {"content": json.dumps(lesson)}}]
            }
            responses.append(response)
        mock_post.side_effect = responses

        lesson = DeepSeekService(api_key="test-key").generate_dialogue_lesson(
            "Explain reliable queues",
            max_retries=1,
        )

        self.assertEqual(800, lesson["wordCount"])
        refinement_prompt = mock_post.call_args_list[1].kwargs["json"]["messages"][1]["content"]
        self.assertIn("Previous draft", refinement_prompt)
        self.assertIn("exactly 16", refinement_prompt)


if __name__ == "__main__":
    unittest.main()
