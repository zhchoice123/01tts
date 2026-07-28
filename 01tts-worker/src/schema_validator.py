import uuid
from typing import Any

VALID_SOURCE_TYPES = {"TEXT", "URL", "NEWS", "TECH_DOC"}
VALID_QUESTION_TYPES = {"INFERENCE", "MULTIPLE_CHOICE", "VOCABULARY", "COMPREHENSION"}


class SchemaValidationError(ValueError):
    """Raised when LessonContent fails schema validation after repair attempt."""
    pass


def validate_lesson_content(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate LessonContent dictionary against cross-module contract schema."""
    errors = []

    if not isinstance(data, dict):
        return False, ["LessonContent must be a JSON object mapping"]

    # Required top-level string fields
    if not isinstance(data.get("uuid"), str) or not data.get("uuid"):
        errors.append("uuid must be a non-empty string")
    if not isinstance(data.get("title"), str) or not data.get("title"):
        errors.append("title must be a non-empty string")
    if data.get("sourceType") not in VALID_SOURCE_TYPES:
        errors.append(f"sourceType must be one of {VALID_SOURCE_TYPES}")
    if not isinstance(data.get("sourceUrl"), str):
        errors.append("sourceUrl must be a string")
    if not isinstance(data.get("level"), str) or not data.get("level"):
        errors.append("level must be a non-empty string")
    if not isinstance(data.get("passage"), str) or not data.get("passage"):
        errors.append("passage must be a non-empty string")
    if not isinstance(data.get("simplifiedPassage"), str):
        errors.append("simplifiedPassage must be a string")
    if not isinstance(data.get("audioUrl"), str):
        errors.append("audioUrl must be a string")

    # Vocabulary list validation
    vocab = data.get("vocabulary")
    if not isinstance(vocab, list):
        errors.append("vocabulary must be a list")
    else:
        for idx, item in enumerate(vocab):
            if not isinstance(item, dict):
                errors.append(f"vocabulary[{idx}] must be an object")
            else:
                for k in ["word", "phonetic", "definition", "example"]:
                    if not isinstance(item.get(k), str):
                        errors.append(f"vocabulary[{idx}].{k} must be a string")
                for k in ["meaningZh", "usageNotes"]:
                    if k in item and not isinstance(item.get(k), str):
                        errors.append(f"vocabulary[{idx}].{k} must be a string")
                if "collocations" in item and not isinstance(item.get("collocations"), list):
                    errors.append(f"vocabulary[{idx}].collocations must be a list")

    # Questions list validation
    questions = data.get("questions")
    if not isinstance(questions, list):
        errors.append("questions must be a list")
    else:
        for idx, item in enumerate(questions):
            if not isinstance(item, dict):
                errors.append(f"questions[{idx}] must be an object")
            else:
                q_type = str(item.get("type", "")).upper()
                if q_type not in VALID_QUESTION_TYPES:
                    errors.append(f"questions[{idx}].type must be one of {VALID_QUESTION_TYPES}")
                if not isinstance(item.get("prompt"), str) or not item.get("prompt"):
                    errors.append(f"questions[{idx}].prompt must be a non-empty string")
                if not isinstance(item.get("options"), list):
                    errors.append(f"questions[{idx}].options must be a list")
                if not isinstance(item.get("answer"), str):
                    errors.append(f"questions[{idx}].answer must be a string")
                if not isinstance(item.get("explanation"), str):
                    errors.append(f"questions[{idx}].explanation must be a string")

    # Speaking prompts list validation
    speaking = data.get("speakingPrompts")
    if not isinstance(speaking, list) or not all(isinstance(s, str) for s in speaking):
        errors.append("speakingPrompts must be a list of strings")

    writing = data.get("writingPrompts")
    if not isinstance(writing, list) or not all(isinstance(s, str) for s in writing):
        errors.append("writingPrompts must be a list of strings")

    return len(errors) == 0, errors


def repair_lesson_content_once(data: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Perform a single-pass deterministic repair on malformed or legacy lesson JSON.
    Fixes field names, supplies defaults, and normalizes types.
    """
    meta = metadata or {}
    repaired = dict(data) if isinstance(data, dict) else {}

    # Repair uuid
    repaired["uuid"] = str(repaired.get("uuid") or meta.get("uuid") or uuid.uuid4())

    # Repair title
    title = str(repaired.get("title") or meta.get("title") or "").strip()
    if not title:
        passage_snippet = str(repaired.get("passage") or repaired.get("passage_text") or meta.get("passage") or "").strip()
        title = passage_snippet.split("\n")[0][:50] if passage_snippet else "Lesson Article"
    repaired["title"] = title

    # Repair sourceType & sourceUrl
    st = str(repaired.get("sourceType") or meta.get("sourceType") or "TEXT").upper().strip()
    repaired["sourceType"] = st if st in VALID_SOURCE_TYPES else "TEXT"
    repaired["sourceUrl"] = str(repaired.get("sourceUrl") or meta.get("sourceUrl") or "")

    # Repair level
    repaired["level"] = str(repaired.get("level") or meta.get("level") or "B1").strip()

    # Repair passage & simplifiedPassage
    passage = str(repaired.get("passage") or repaired.get("passage_text") or meta.get("passage") or "").strip()
    repaired["passage"] = passage
    repaired["simplifiedPassage"] = str(repaired.get("simplifiedPassage") or passage)

    # Repair audioUrl
    repaired["audioUrl"] = str(repaired.get("audioUrl") or meta.get("audioUrl") or "")

    # Repair vocabulary
    raw_vocab = repaired.get("vocabulary", [])
    norm_vocab = []
    if isinstance(raw_vocab, list):
        for item in raw_vocab:
            if isinstance(item, dict):
                norm_vocab.append({
                    "word": str(item.get("word", "")).strip(),
                    "phonetic": str(item.get("phonetic", "")).strip(),
                    "definition": str(item.get("definition", item.get("meaning", ""))).strip(),
                    "meaningZh": str(item.get("meaningZh", "")).strip(),
                    "example": str(item.get("example", "")).strip(),
                    "collocations": [
                        str(value).strip()
                        for value in item.get("collocations", [])
                        if str(value).strip()
                    ] if isinstance(item.get("collocations", []), list) else [],
                    "usageNotes": str(item.get("usageNotes", "")).strip(),
                })
            elif isinstance(item, str) and item.strip():
                norm_vocab.append({
                    "word": item.strip(),
                    "phonetic": "",
                    "definition": "",
                    "meaningZh": "",
                    "example": "",
                    "collocations": [],
                    "usageNotes": "",
                })
    repaired["vocabulary"] = norm_vocab

    # Repair questions & speakingPrompts
    raw_questions = repaired.get("questions", [])
    norm_questions = []
    speaking_prompts = []

    if isinstance(raw_questions, dict):
        # Convert legacy dict format {"multiple_choice": {...}, "speaking": {...}}
        converted = []
        for k, v in raw_questions.items():
            if isinstance(v, dict):
                converted.append(dict(v, type=k))
        raw_questions = converted

    if isinstance(raw_questions, list):
        for q in raw_questions:
            if not isinstance(q, dict):
                continue
            raw_type = str(q.get("type", "")).lower()
            if raw_type == "speaking":
                sp_text = str(q.get("question") or q.get("prompt") or "").strip()
                if sp_text:
                    speaking_prompts.append(sp_text)
                continue

            # Normalize multiple choice / inference question
            q_prompt = str(q.get("prompt") or q.get("question") or "").strip()
            if not q_prompt:
                continue

            q_options = q.get("options") or q.get("choices") or []
            if not isinstance(q_options, list):
                q_options = []
            q_options = [str(opt).strip() for opt in q_options]

            q_type = str(q.get("type", "INFERENCE")).upper()
            if q_type not in VALID_QUESTION_TYPES:
                q_type = "INFERENCE"

            norm_questions.append({
                "type": q_type,
                "prompt": q_prompt,
                "options": q_options,
                "answer": str(q.get("answer", "")).strip(),
                "explanation": str(q.get("explanation", "")).strip(),
            })

    repaired["questions"] = norm_questions

    # Repair speakingPrompts
    raw_sp = repaired.get("speakingPrompts", [])
    if isinstance(raw_sp, list):
        for s in raw_sp:
            if isinstance(s, str) and s.strip():
                speaking_prompts.append(s.strip())

    if not speaking_prompts:
        speaking_prompts.append("Summarize the main idea of the article in your own words.")
    repaired["speakingPrompts"] = list(dict.fromkeys(speaking_prompts))  # deduplicate preserving order

    raw_writing = repaired.get("writingPrompts", [])
    writing_prompts = [
        str(value).strip()
        for value in raw_writing
        if isinstance(value, str) and value.strip()
    ] if isinstance(raw_writing, list) else []
    if not writing_prompts:
        writing_prompts.append(
            "Write 80-120 words explaining the main idea and one practical example."
        )
    repaired["writingPrompts"] = writing_prompts

    return repaired


def validate_and_repair_lesson_content(data: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Validate LessonContent schema.
    If invalid, attempts auto-repair ONCE. If still invalid after 1 repair attempt, raises SchemaValidationError.
    """
    is_valid, errors = validate_lesson_content(data)
    if is_valid:
        return data

    repaired = repair_lesson_content_once(data, metadata=metadata)
    is_valid_after_repair, repair_errors = validate_lesson_content(repaired)

    if not is_valid_after_repair:
        raise SchemaValidationError(
            f"LessonContent schema validation failed after 1 repair attempt. Errors: {repair_errors}"
        )

    return repaired
