import unittest

from src.schema_validator import (
    SchemaValidationError,
    repair_lesson_content_once,
    validate_and_repair_lesson_content,
    validate_lesson_content,
)


class SchemaValidatorTest(unittest.TestCase):
    def test_valid_lesson_content_passes(self):
        data = {
            "uuid": "test-uuid-123",
            "title": "Understanding Concurrency",
            "sourceType": "TECH_DOC",
            "sourceUrl": "https://example.com/doc",
            "level": "B1",
            "passage": "Concurrency is the execution of multiple instruction sequences at the same time.",
            "simplifiedPassage": "Concurrency means doing multiple things at once.",
            "audioUrl": "https://example.com/audio.mp3",
            "vocabulary": [
                {
                    "word": "concurrency",
                    "phonetic": "/kənˈkʌr.ən.si/",
                    "definition": "simultaneous execution",
                    "example": "Java handles concurrency.",
                }
            ],
            "questions": [
                {
                    "type": "INFERENCE",
                    "prompt": "What does concurrency mean?",
                    "options": ["A. Doing multiple things at once", "B. Sequential code"],
                    "answer": "A",
                    "explanation": "Because multiple instruction sequences execute.",
                }
            ],
            "speakingPrompts": ["Summarize the passage."],
            "writingPrompts": ["Write three sentences about when concurrency is useful."],
        }
        is_valid, errors = validate_lesson_content(data)
        self.assertTrue(is_valid, f"Validation failed with errors: {errors}")

    def test_auto_repair_once_fixes_legacy_or_incomplete_dict(self):
        legacy_data = {
            "passage_text": "This is a passage with some legacy structure.",
            "questions": [
                {
                    "question": "What is this text about?",
                    "choices": ["Option 1", "Option 2"],
                    "answer": "Option 1",
                }
            ],
        }
        repaired = repair_lesson_content_once(legacy_data, metadata={"title": "Repaired Title", "sourceType": "URL"})
        is_valid, errors = validate_lesson_content(repaired)
        self.assertTrue(is_valid, f"Repaired content should be valid, got errors: {errors}")
        self.assertEqual("Repaired Title", repaired["title"])
        self.assertEqual("URL", repaired["sourceType"])
        self.assertIn("speakingPrompts", repaired)
        self.assertGreaterEqual(len(repaired["speakingPrompts"]), 1)

    def test_validate_and_repair_fails_if_still_invalid(self):
        hopeless_data = {
            "passage": "",  # Empty passage
        }
        with self.assertRaises(SchemaValidationError):
            validate_and_repair_lesson_content(hopeless_data)


if __name__ == "__main__":
    unittest.main()
