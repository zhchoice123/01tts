import json
import logging
import os
import re
import time
from typing import Any

import requests

from src.schema_validator import validate_and_repair_lesson_content

LOGGER = logging.getLogger("tts-worker.deepseek")

DIALOGUE_TARGET_MIN_WORDS = 800
DIALOGUE_TARGET_MAX_WORDS = 950
DIALOGUE_ACCEPT_MIN_WORDS = 700
DIALOGUE_ACCEPT_MAX_WORDS = 1050
DIALOGUE_TARGET_MIN_TURNS = 12
DIALOGUE_TARGET_MAX_TURNS = 20
DIALOGUE_ACCEPT_MIN_TURNS = 10
DIALOGUE_ACCEPT_MAX_TURNS = 24
# Long scripts need variety; schema validation and retries guard the JSON.
DIALOGUE_TEMPERATURE = 0.7
LONG_LESSON_TEMPERATURE = 0.6

LESSON_SYSTEM_PROMPT = """Return JSON only adhering strictly to the LessonContent schema:
{
  "title": "Short Title",
  "level": "B1",
  "passage": "50-150 English words paragraph.",
  "simplifiedPassage": "Simplified version of passage.",
  "vocabulary": [
    {
      "word": "concurrency",
      "phonetic": "/kənˈkʌr.ən.si/",
      "definition": "simultaneous execution",
      "meaningZh": "并发；同时发生",
      "example": "Concurrency improves throughput.",
      "collocations": ["handle concurrency", "concurrency control"],
      "usageNotes": "Usually used as an uncountable noun in software contexts."
    }
  ],
  "questions": [
    {
      "type": "INFERENCE",
      "prompt": "What is the main topic?",
      "options": ["A. Concurrency", "B. Databases", "C. CSS", "D. Hardware"],
      "answer": "A. Concurrency",
      "explanation": "The text focuses on concurrency."
    }
  ],
  "speakingPrompts": ["Summarize the main idea in your own words."],
  "writingPrompts": ["Write 80-120 words explaining how you would use this idea."]
}
Do not wrap the object in Markdown. Use double-quoted property names and values.
Do not add comments or trailing commas. Keep every string on one JSON-safe line;
escape any double quote inside a value and never stop before the final closing brace.
Before responding, silently verify that the JSON parses and every required array exists.
"""

# Lessons are listened to, not read: write the script the way people speak.
SPOKEN_STYLE_RULES = """Write for the ear. Use contractions and mostly short sentences
(under 25 words). Use natural spoken signposts such as "So here's the thing",
"Right", "Let me put it another way", or "The catch is". Never read code, stack
traces, URLs, or file paths aloud: name the class or method and say in words what it
does. Write numbers, units, and percentiles the way an engineer says them, for example
"p ninety-nine latency" and "two hundred milliseconds". Avoid lists that only work on a
page; turn them into "first ... then ... finally" speech."""

LONG_LESSON_SYSTEM_PROMPT = """Return JSON only. Create a rigorous English lesson for
an experienced backend developer. The passage MUST contain 1200-1450 English words
(roughly ten minutes of narration) and use clear B1-B2 English. Structure the passage
around the requested concrete problem and learning objective. The requested objective
must determine the structure: diagnosis uses evidence to distinguish hypotheses;
verification gives reproducible steps, expected observations and pass/fail criteria;
recovery gives ordered mitigation, rollback triggers and recovery checks; design
compares alternatives under explicit constraints. Keep introductory definitions brief.
Include one concrete Java or Spring example, trade-offs, and a concise recap.
""" + SPOKEN_STYLE_RULES + """

Use the same LessonContent JSON schema as below:
{
  "title": "Specific technical title",
  "level": "B1 or B2",
  "passage": "1200-1450 English words",
  "simplifiedPassage": "A 180-260 word recap",
  "vocabulary": [{
    "word": "backpressure", "phonetic": "", "definition": "English definition",
    "meaningZh": "中文释义", "example": "Technical example sentence.",
    "collocations": ["apply backpressure"], "usageNotes": "Usage guidance."
  }],
  "questions": [{
    "type": "INFERENCE", "prompt": "Question", "options": ["A", "B", "C", "D"],
    "answer": "A", "explanation": "Explanation"
  }],
  "speakingPrompts": ["A practical spoken response task"],
  "writingPrompts": ["A 150-200 word engineering writing task"]
}
Include 12-18 vocabulary items, exactly 5 useful reading-comprehension questions,
at least 2 speaking prompts, and at least 1 writing prompt. Do not use Markdown
outside JSON. Do not invent claims about a supplied source; attribute and summarize it.
"""

DIALOGUE_LESSON_SYSTEM_PROMPT = """Return one complete, valid JSON object only. Create a natural technical
English podcast dialogue for an experienced backend developer. Use exactly two
speakers who alternate, beginning with HOST. HOST is curious and active: asks
follow-ups, pushes back, reacts briefly ("Wait, so the pool was full the whole
time?"), or restates an idea in plain words. EXPERT gives practical, technically
accurate answers and sometimes asks HOST a question back. Use 12-20 turns in total.
Vary the turn length the way real conversation does: some turns are a single short
sentence, the longest EXPERT turns reach about 110 words, and no two EXPERT turns in a
row have similar length. Total 800-950 spoken words, about 5-8 minutes of speech.
Use clear B1-B2 English. Do not put speaker labels inside the text value.
""" + SPOKEN_STYLE_RULES + """

Return this shape:
{
  "title": "Specific technical dialogue title",
  "level": "B1 or B2",
  "dialogue": [
    {"speaker": "HOST", "text": "Question or transition."},
    {"speaker": "EXPERT", "text": "Detailed answer with an example."}
  ],
  "simplifiedPassage": "A 120-180 word recap",
  "vocabulary": [{
    "word": "backpressure", "phonetic": "", "definition": "English definition",
    "meaningZh": "中文释义", "example": "Technical example sentence.",
    "collocations": ["apply backpressure"], "usageNotes": "Usage guidance."
  }],
  "questions": [{
    "type": "INFERENCE", "prompt": "Question", "options": ["A", "B", "C", "D"],
    "answer": "A", "explanation": "Explanation"
  }],
  "speakingPrompts": ["A practical spoken response task"],
  "writingPrompts": ["A 150-200 word engineering writing task"]
}
Organize the dialogue around the requested concrete problem and learning objective.
The objective overrides a generic architecture overview. For diagnosis, compare
hypotheses using concrete evidence. For verification, spend most turns on reproducible
experiment steps, failure injection, expected observations, and pass/fail criteria.
For recovery, give ordered mitigation, rollback triggers, and recovery checks. For a
design decision, compare two alternatives under explicit constraints. Include one
concrete Java or Spring example and keep foundational definitions brief. Label invented
production cases hypothetical. Do not present delivery guarantees as unconditional,
confuse a consumer inbox with a producer outbox, or catch a database constraint error
inside a transaction and assume that transaction can still commit. Close naturally,
for example with one practical takeaway, a short recap, or a question for the listener.
Include 8-12 vocabulary items, exactly 5 reading questions, at least 2 speaking
prompts, and at least 1 writing prompt. Do not include a passage field; it will be
constructed from the dialogue. Do not use Markdown outside JSON. Do not invent claims
about a supplied source. Keep every string JSON-safe: escape embedded double quotes,
do not use literal newlines inside strings, do not add trailing commas, and always emit
the final closing brace. Before responding, silently count the turns and spoken words
and verify that the object parses as JSON.
"""


def count_english_words(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z]+(?:['-][A-Za-z]+)*\b", text or ""))

def parse_model_json(content: str) -> dict[str, Any]:
    """Parse common provider JSON variants without weakening schema validation."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Model returned empty lesson content")

    text = content.strip().lstrip("\ufeff")
    candidates = [text]

    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())

    extracted = _extract_first_json_object(text)
    if extracted:
        candidates.append(extracted)

    errors = []
    for candidate in dict.fromkeys(candidates):
        for normalized in (candidate, _remove_trailing_commas(candidate)):
            try:
                parsed = json.loads(normalized, strict=False)
                if not isinstance(parsed, dict):
                    raise ValueError("Lesson content must be a JSON object")
                return parsed
            except (json.JSONDecodeError, ValueError) as error:
                errors.append(str(error))

    raise ValueError(f"Model returned malformed lesson JSON: {errors[-1]}")


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return text[start:]


def _remove_trailing_commas(text: str) -> str:
    output = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == ",":
            next_index = index + 1
            while next_index < len(text) and text[next_index].isspace():
                next_index += 1
            if next_index < len(text) and text[next_index] in "}]":
                index += 1
                continue
        output.append(char)
        index += 1
    return "".join(output)


class DeepSeekService:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str | None = None,
        timeout_seconds: float = 45,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        # Model precedence: config/env -> current fast generation model.
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        self.timeout_seconds = timeout_seconds

    def _thinking_control(self) -> dict[str, Any]:
        """Use deterministic non-thinking mode for schema-bound JSON generation."""
        if self.model.startswith("deepseek-v4"):
            return {"thinking": {"type": "disabled"}}
        return {}

    def generate_lesson(self, prompt: str, metadata: dict[str, Any] | None = None, max_retries: int = 3) -> dict[str, Any]:
        """
        Generate LessonContent JSON via the DeepSeek API.
        Executes schema validation and 1-pass auto-repair.
        """
        meta = metadata or {}
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                LOGGER.info("Calling AI completions API (Attempt %d/%d) model=%s", attempt, max_retries, self.model)
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        **self._thinking_control(),
                        "response_format": {"type": "json_object"},
                        "max_tokens": 4096,
                        "temperature": 0.2,
                        "messages": [
                            {"role": "system", "content": LESSON_SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                    },
                    timeout=(10, self.timeout_seconds),
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                raw_json = parse_model_json(content)

                # Validate and execute 1-pass repair if schema has flaws
                lesson = validate_and_repair_lesson_content(raw_json, metadata=meta)
                return lesson
            except Exception as e:
                LOGGER.warning("Lesson generation attempt %d failed: %s", attempt, e)
                last_error = e
                if attempt < max_retries:
                    time.sleep(1.5 * attempt)

        raise RuntimeError(f"Failed to generate valid LessonContent after {max_retries} attempts: {last_error}")

    def generate_long_lesson(
        self,
        prompt: str,
        metadata: dict[str, Any] | None = None,
        max_retries: int = 2,
    ) -> dict[str, Any]:
        """Generate and length-check a 1200-1450 word backend lesson."""
        meta = metadata or {}
        lesson = self._generate_with_prompt(
            prompt,
            LONG_LESSON_SYSTEM_PROMPT,
            meta,
            max_tokens=8192,
            max_retries=max_retries,
        )
        word_count = count_english_words(str(lesson.get("passage", "")))
        issues = self._long_lesson_issues(lesson)
        if issues:
            LOGGER.info("Refining long lesson issues=%s", issues)
            expansion_prompt = (
                f"The previous JSON lesson did not meet these requirements: {'; '.join(issues)}. "
                "Rewrite the COMPLETE JSON object so its passage contains 1200-1450 English "
                "words. Preserve the topic and source attribution. Add technical depth, "
                "a concrete Java or Spring example, trade-offs, operational advice, "
                "12-18 vocabulary items, exactly 5 questions, speaking and writing tasks. "
                "Previous lesson JSON:\n"
                + json.dumps(lesson, ensure_ascii=False)
            )
            lesson = self._generate_with_prompt(
                expansion_prompt,
                LONG_LESSON_SYSTEM_PROMPT,
                meta,
                max_tokens=8192,
                max_retries=max_retries,
            )
            word_count = count_english_words(str(lesson.get("passage", "")))
        remaining_issues = self._long_lesson_issues(lesson)
        if remaining_issues:
            raise ValueError("Invalid long lesson after refinement: " + "; ".join(remaining_issues))
        lesson["wordCount"] = word_count
        lesson["estimatedDurationSeconds"] = round(word_count / 130 * 60)
        return lesson

    def generate_dialogue_lesson(
        self,
        prompt: str,
        metadata: dict[str, Any] | None = None,
        max_retries: int = 2,
    ) -> dict[str, Any]:
        """Generate and validate a two-speaker 5-8 minute technical dialogue."""
        meta = metadata or {}
        dialogue = self._generate_dialogue_json(
            prompt,
            max_tokens=7200,
            max_retries=max_retries,
        )
        issues = self._dialogue_lesson_issues(dialogue)
        if issues:
            LOGGER.info("Refining dialogue lesson issues=%s", issues)
            previous_dialogue = json.dumps(dialogue, ensure_ascii=False)
            dialogue = self._generate_dialogue_json(
                (
                    "The first draft failed validation because: "
                    f"{'; '.join(issues)}. Rewrite the complete draft below while "
                    "preserving its accurate content. Use 12-20 alternating HOST/EXPERT "
                    "turns beginning with HOST, with naturally varied turn lengths. "
                    "Target 850-900 combined spoken English words. Expand or condense "
                    "the EXPERT explanations instead of adding extra turns. "
                    "Return one complete parseable JSON object and satisfy every schema "
                    "field.\nOriginal request:\n"
                    f"{prompt}\nPrevious draft:\n{previous_dialogue}"
                ),
                max_tokens=7200,
                max_retries=max_retries,
            )
        remaining_issues = self._dialogue_lesson_issues(dialogue)
        if remaining_issues:
            raise ValueError(
                "Invalid dialogue lesson after refinement: "
                + "; ".join(remaining_issues)
            )

        turns = dialogue["dialogue"]
        spoken_text = " ".join(str(turn["text"]) for turn in turns)
        dialogue["passage"] = "\n\n".join(
            f"{str(turn['speaker']).title()}: {str(turn['text']).strip()}"
            for turn in turns
        )
        lesson = validate_and_repair_lesson_content(dialogue, metadata=meta)
        lesson["dialogue"] = turns
        lesson["format"] = "DIALOGUE"
        lesson["wordCount"] = count_english_words(spoken_text)
        lesson["estimatedDurationSeconds"] = round(
            lesson["wordCount"] / 125 * 60
        )
        return lesson

    @staticmethod
    def _long_lesson_issues(lesson: dict[str, Any]) -> list[str]:
        word_count = count_english_words(str(lesson.get("passage", "")))
        vocabulary_count = len(lesson.get("vocabulary") or [])
        question_count = len(lesson.get("questions") or [])
        speaking_count = len(lesson.get("speakingPrompts") or [])
        writing_count = len(lesson.get("writingPrompts") or [])
        issues = []
        if not 1200 <= word_count <= 1450:
            issues.append(f"passage has {word_count} words")
        if not 12 <= vocabulary_count <= 18:
            issues.append(f"vocabulary has {vocabulary_count} items")
        if question_count != 5:
            issues.append(f"questions has {question_count} items")
        if speaking_count < 2:
            issues.append(f"speakingPrompts has {speaking_count} items")
        if writing_count < 1:
            issues.append("writingPrompts is empty")
        return issues

    @staticmethod
    def _dialogue_lesson_issues(lesson: dict[str, Any]) -> list[str]:
        turns = lesson.get("dialogue")
        if not isinstance(turns, list):
            return ["dialogue is not a list"]
        issues = []
        if not DIALOGUE_ACCEPT_MIN_TURNS <= len(turns) <= DIALOGUE_ACCEPT_MAX_TURNS:
            issues.append(f"dialogue has {len(turns)} turns")
        spoken_parts = []
        for index, turn in enumerate(turns):
            if not isinstance(turn, dict):
                issues.append(f"dialogue turn {index} is not an object")
                continue
            speaker = str(turn.get("speaker", "")).strip().upper()
            expected = "HOST" if index % 2 == 0 else "EXPERT"
            if speaker != expected:
                issues.append(
                    f"dialogue turn {index} speaker is {speaker or 'missing'}, expected {expected}"
                )
            text = str(turn.get("text", "")).strip()
            if not text:
                issues.append(f"dialogue turn {index} text is empty")
            spoken_parts.append(text)
        word_count = count_english_words(" ".join(spoken_parts))
        if not DIALOGUE_ACCEPT_MIN_WORDS <= word_count <= DIALOGUE_ACCEPT_MAX_WORDS:
            issues.append(f"dialogue has {word_count} spoken words")
        if len(lesson.get("vocabulary") or []) not in range(8, 13):
            issues.append(
                f"vocabulary has {len(lesson.get('vocabulary') or [])} items"
            )
        if len(lesson.get("questions") or []) != 5:
            issues.append(
                f"questions has {len(lesson.get('questions') or [])} items"
            )
        if len(lesson.get("speakingPrompts") or []) < 2:
            issues.append(
                f"speakingPrompts has {len(lesson.get('speakingPrompts') or [])} items"
            )
        if len(lesson.get("writingPrompts") or []) < 1:
            issues.append("writingPrompts is empty")
        return issues

    def _generate_dialogue_json(
        self,
        prompt: str,
        max_tokens: int,
        max_retries: int,
    ) -> dict[str, Any]:
        last_error = None
        attempt_limit = max(2, max_retries)
        for attempt in range(1, attempt_limit + 1):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        **self._thinking_control(),
                        "response_format": {"type": "json_object"},
                        "max_tokens": max_tokens,
                        "temperature": DIALOGUE_TEMPERATURE,
                        "messages": [
                            {
                                "role": "system",
                                "content": DIALOGUE_LESSON_SYSTEM_PROMPT,
                            },
                            {"role": "user", "content": prompt},
                        ],
                    },
                    timeout=(10, max(self.timeout_seconds, 120)),
                )
                response.raise_for_status()
                return parse_model_json(
                    response.json()["choices"][0]["message"]["content"]
                )
            except Exception as error:
                last_error = error
                LOGGER.warning(
                    "Dialogue generation attempt %d/%d failed: %s",
                    attempt,
                    attempt_limit,
                    error,
                )
                if attempt < attempt_limit:
                    time.sleep(1.5 * attempt)
        raise RuntimeError(f"Failed to generate dialogue lesson: {last_error}")

    def _generate_with_prompt(
        self,
        prompt: str,
        system_prompt: str,
        metadata: dict[str, Any],
        max_tokens: int,
        max_retries: int,
    ) -> dict[str, Any]:
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        **self._thinking_control(),
                        "response_format": {"type": "json_object"},
                        "max_tokens": max_tokens,
                        "temperature": LONG_LESSON_TEMPERATURE,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                    },
                    timeout=(10, max(self.timeout_seconds, 120)),
                )
                response.raise_for_status()
                raw = parse_model_json(
                    response.json()["choices"][0]["message"]["content"]
                )
                return validate_and_repair_lesson_content(raw, metadata=metadata)
            except Exception as error:
                last_error = error
                LOGGER.warning(
                    "Long lesson generation attempt %d/%d failed: %s",
                    attempt,
                    max_retries,
                    error,
                )
                if attempt < max_retries:
                    time.sleep(1.5 * attempt)
        raise RuntimeError(f"Failed to generate long lesson: {last_error}")
