"""Pure lesson-review calculations.

This module deliberately has no database, network, or framework dependencies.  It
accepts the camelCase dictionaries already exposed by the backend persistence
layer and returns a JSON-serialisable V1 lesson-review report.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any


DIMENSION_ORDER = ("listening", "comprehension", "vocabulary", "speaking")
DIMENSION_LABELS = {
    "listening": "Listening",
    "comprehension": "Comprehension",
    "vocabulary": "Vocabulary",
    "speaking": "Speaking",
}
VOCABULARY_WEAK_POINT_LIMIT = 5


def _number(value: Any) -> float | None:
    """Return a finite numeric value without treating booleans as scores."""

    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamped_score(value: Any) -> int | None:
    number = _number(value)
    if number is None:
        return None
    return max(0, min(100, int(math.floor(number + 0.5))))


def _rounded_percentage(numerator: float, denominator: float) -> int:
    if denominator <= 0:
        raise ValueError("percentage denominator must be positive")
    return _clamped_score(numerator * 100 / denominator) or 0


def _status(score: int | None) -> str:
    if score is None:
        return "NO_DATA"
    if score < 70:
        return "NEEDS_WORK"
    if score < 85:
        return "DEVELOPING"
    return "STRONG"


def _dimension(key: str, score: int | None) -> dict[str, Any]:
    return {
        "key": key,
        "label": DIMENSION_LABELS[key],
        "score": score,
        "status": _status(score),
    }


def _listening_score(progress: Mapping[str, Any]) -> int | None:
    if progress.get("listeningDone") is True:
        return 100
    if "positionMs" not in progress or "durationMs" not in progress:
        return None
    position = _number(progress.get("positionMs"))
    duration = _number(progress.get("durationMs"))
    if position is None or duration is None or duration <= 0:
        return None
    return _rounded_percentage(max(0.0, position), duration)


def _comprehension_score(progress: Mapping[str, Any]) -> int | None:
    total = _number(progress.get("quizTotal"))
    correct = _number(progress.get("quizCorrect"))
    if total is None or correct is None or total <= 0:
        return None
    return _rounded_percentage(max(0.0, correct), total)


def _course_vocabulary(
    vocabulary_progress: Iterable[Mapping[str, Any]],
    content_uuid: str,
) -> list[dict[str, str]]:
    """Normalise and de-duplicate course vocabulary independent of input order."""

    status_rank = {"NEW": 0, "LEARNING": 1, "KNOWN": 2}
    words: dict[str, dict[str, str]] = {}
    for item in vocabulary_progress:
        item_content_uuid = str(item.get("contentUuid") or "").strip()
        if item_content_uuid and item_content_uuid != content_uuid:
            continue
        word = str(item.get("word") or "").strip()
        status = str(item.get("status") or "").strip().upper()
        if not word or status not in status_rank:
            continue
        normalized = word.casefold()
        existing = words.get(normalized)
        candidate = {"word": word, "status": status}
        if existing is None:
            words[normalized] = candidate
        elif status_rank[status] > status_rank[existing["status"]]:
            words[normalized] = candidate
        elif status == existing["status"] and word < existing["word"]:
            words[normalized] = candidate
    return sorted(words.values(), key=lambda item: item["word"].casefold())


def _vocabulary_score(vocabulary: list[dict[str, str]]) -> int | None:
    if not vocabulary:
        return None
    known = sum(item["status"] == "KNOWN" for item in vocabulary)
    return _rounded_percentage(known, len(vocabulary))


def _speaking_score(
    progress: Mapping[str, Any],
    speaking_evaluation: Mapping[str, Any] | int | float | None,
) -> int | None:
    if isinstance(speaking_evaluation, Mapping):
        for key in ("overallScore", "score", "speakingScore"):
            score = _clamped_score(speaking_evaluation.get(key))
            if score is not None:
                return score
    elif speaking_evaluation is not None:
        score = _clamped_score(speaking_evaluation)
        if score is not None:
            return score
    return _clamped_score(progress.get("speakingScore"))


def _generated_at(value: datetime | str | None) -> str:
    if value is None:
        moment = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("generated_at must be an ISO-8601 timestamp") from error
    else:
        raise TypeError("generated_at must be a datetime, ISO-8601 string, or None")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _weak_points(
    dimensions: list[dict[str, Any]],
    vocabulary: list[dict[str, str]],
    speaking_evaluation: Mapping[str, Any] | int | float | None,
) -> list[dict[str, Any]]:
    by_key = {item["key"]: item for item in dimensions}
    points: list[dict[str, Any]] = []

    score = by_key["listening"]["score"]
    if score is not None and score < 70:
        points.append(
            {
                "kind": "LISTENING",
                "title": "Finish listening to the lesson",
                "detail": f"Listening completion is {score}%.",
                "priority": 1 if score < 50 else 2,
            }
        )

    score = by_key["comprehension"]["score"]
    if score is not None and score < 70:
        # Only aggregate quiz results are available here.  Do not infer which
        # question, concept, or answer the learner got wrong.
        points.append(
            {
                "kind": "COMPREHENSION",
                "title": "Review lesson comprehension",
                "detail": (
                    f"Quiz accuracy is {score}%; review the lesson before retrying."
                ),
                "priority": 1 if score < 50 else 2,
            }
        )

    score = by_key["vocabulary"]["score"]
    if score is not None and score < 70:
        known = sum(item["status"] == "KNOWN" for item in vocabulary)
        points.append(
            {
                "kind": "VOCABULARY",
                "title": "Strengthen course vocabulary",
                "detail": (
                    f"{known} of {len(vocabulary)} course words are marked KNOWN."
                ),
                "priority": 1 if score < 50 else 2,
            }
        )
        weak_words = sorted(
            (item for item in vocabulary if item["status"] != "KNOWN"),
            key=lambda item: (
                0 if item["status"] == "LEARNING" else 1,
                item["word"].casefold(),
            ),
        )[:VOCABULARY_WEAK_POINT_LIMIT]
        for item in weak_words:
            points.append(
                {
                    "kind": "VOCABULARY_WORD",
                    "title": item["word"],
                    "detail": f"This course word is currently {item['status']}.",
                    "priority": 2 if item["status"] == "LEARNING" else 3,
                }
            )

    score = by_key["speaking"]["score"]
    if score is not None and score < 70:
        detail = f"Speaking score is {score}%; record another response for practice."
        if isinstance(speaking_evaluation, Mapping):
            improvements = speaking_evaluation.get("improvements")
            if isinstance(improvements, list):
                first = next(
                    (str(item).strip() for item in improvements if str(item).strip()),
                    None,
                )
                if first:
                    detail = first
        points.append(
            {
                "kind": "SPEAKING",
                "title": "Practice the speaking task again",
                "detail": detail,
                "priority": 1 if score < 50 else 2,
            }
        )

    kind_order = {
        "LISTENING": 0,
        "COMPREHENSION": 1,
        "VOCABULARY": 2,
        "VOCABULARY_WORD": 3,
        "SPEAKING": 4,
    }
    return sorted(
        points,
        key=lambda item: (
            item["priority"],
            kind_order[item["kind"]],
            item["title"].casefold(),
        ),
    )


def _next_actions(dimensions: list[dict[str, Any]]) -> list[str]:
    scored = [item for item in dimensions if item["score"] is not None]
    if not scored:
        return ["Complete at least one lesson activity to create a learning report."]

    action_by_key = {
        "listening": "Finish the lesson audio, then replay the hardest section.",
        "comprehension": "Review the lesson and retry the comprehension quiz.",
        "vocabulary": "Review the course words still marked NEW or LEARNING.",
        "speaking": "Record the speaking task again and compare the feedback.",
    }
    actions = [
        action_by_key[item["key"]]
        for item in dimensions
        if item["score"] is not None and item["score"] < 70
    ]
    return actions or ["Continue with the next lesson while this material is fresh."]


def generate_lesson_review_report(
    *,
    learning_progress: Mapping[str, Any],
    vocabulary_progress: Iterable[Mapping[str, Any]] = (),
    speaking_evaluation: Mapping[str, Any] | int | float | None = None,
    generated_at: datetime | str | None = None,
) -> dict[str, Any]:
    """Build a deterministic V1 lesson review from aggregate learning data.

    ``generated_at`` should be supplied by callers that need byte-for-byte stable
    output (for example tests or idempotent persistence). Missing dimensions have
    a null score, are labelled ``NO_DATA``, and do not contribute to the overall
    score. If every dimension is missing, ``overallScore`` is zero.
    """

    client_id = str(learning_progress.get("clientId") or "").strip()
    content_uuid = str(learning_progress.get("contentUuid") or "").strip()
    if not client_id or not content_uuid:
        raise ValueError("learning_progress must contain clientId and contentUuid")

    vocabulary = _course_vocabulary(vocabulary_progress, content_uuid)
    scores = {
        "listening": _listening_score(learning_progress),
        "comprehension": _comprehension_score(learning_progress),
        "vocabulary": _vocabulary_score(vocabulary),
        "speaking": _speaking_score(learning_progress, speaking_evaluation),
    }
    dimensions = [_dimension(key, scores[key]) for key in DIMENSION_ORDER]
    available_scores = [score for score in scores.values() if score is not None]
    overall_score = (
        _clamped_score(sum(available_scores) / len(available_scores))
        if available_scores
        else 0
    )

    return {
        "clientId": client_id,
        "contentUuid": content_uuid,
        "overallScore": overall_score,
        "dimensions": dimensions,
        "weakPoints": _weak_points(dimensions, vocabulary, speaking_evaluation),
        "nextActions": _next_actions(dimensions),
        "generatedAt": _generated_at(generated_at),
    }
