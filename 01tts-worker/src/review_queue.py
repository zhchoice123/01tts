"""Deterministic daily review queue selection.

This module deliberately contains no database or web-framework dependencies so the
selection policy can be tested and reused by API/service adapters independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Any, Iterable, Mapping
import unicodedata


VALID_VOCABULARY_STATUSES = frozenset({"NEW", "LEARNING", "KNOWN"})
_STATUS_DELAY = {
    "NEW": timedelta(0),
    "LEARNING": timedelta(days=1),
    "KNOWN": timedelta(days=7),
}
_STATUS_PRIORITY = {"NEW": 1, "LEARNING": 2, "KNOWN": 3}
_MAX_LIMIT = 50
_ESTIMATED_MINUTES_CAP = 15


@dataclass(frozen=True)
class VocabularyProgress:
    """Lightweight input type; mappings and arbitrary attribute objects also work."""

    contentUuid: str
    word: str
    status: str
    updatedAt: datetime | str


def build_review_queue(
    client_id: str,
    as_of: datetime | str,
    vocabulary_progress: Iterable[Mapping[str, Any] | Any],
    course_weaknesses: Iterable[Mapping[str, Any] | Any] | None = None,
    *,
    limit: int = 10,
) -> dict[str, Any]:
    """Build a due-only V1 review queue.

    Invalid/incomplete rows are ignored, keeping one bad persisted row from making
    the whole daily queue unavailable. Naive datetimes are interpreted as UTC.
    Vocabulary is de-duplicated with Unicode NFKC, whitespace folding and
    case-folding. All emitted timestamps are canonical UTC ISO-8601 strings.
    """

    queue_time = _parse_datetime(as_of)
    client_date = _local_date(as_of, queue_time)
    bounded_limit = _bounded_limit(limit)

    vocabulary_candidates: dict[str, _Candidate] = {}
    for raw in vocabulary_progress or ():
        candidate = _vocabulary_candidate(raw, queue_time)
        if candidate is None:
            continue
        word_key = _normalize_word(candidate.item["word"])
        previous = vocabulary_candidates.get(word_key)
        if previous is None or candidate.sort_key < previous.sort_key:
            vocabulary_candidates[word_key] = candidate

    candidates = list(vocabulary_candidates.values())
    for raw in course_weaknesses or ():
        candidate = _lesson_candidate(raw, queue_time)
        if candidate is not None:
            candidates.append(candidate)

    candidates.sort(key=lambda value: value.sort_key)
    items = [candidate.item for candidate in candidates[:bounded_limit]]
    return {
        "clientId": str(client_id),
        "date": client_date,
        "totalCount": len(items),
        "estimatedMinutes": min(len(items), _ESTIMATED_MINUTES_CAP),
        "items": items,
    }


@dataclass(frozen=True)
class _Candidate:
    sort_key: tuple[int, int, datetime, str]
    item: dict[str, Any]


def _vocabulary_candidate(raw: Mapping[str, Any] | Any, as_of: datetime) -> _Candidate | None:
    content_uuid = str(_value(raw, "contentUuid", "content_uuid") or "").strip()
    word = str(_value(raw, "word") or "").strip()
    status = str(_value(raw, "status") or "").strip().upper()
    updated_value = _value(raw, "updatedAt", "updated_at")
    if not content_uuid or not _normalize_word(word) or status not in VALID_VOCABULARY_STATUSES:
        return None
    try:
        updated_at = _parse_datetime(updated_value)
    except (TypeError, ValueError):
        return None

    due_at = updated_at + _STATUS_DELAY[status]
    if due_at > as_of:
        return None
    priority = _STATUS_PRIORITY[status]
    stable_id = _stable_id("vocabulary", content_uuid, _normalize_word(word))
    reason = {
        "NEW": "New vocabulary is ready for its first review.",
        "LEARNING": "Vocabulary is due for a one-day follow-up.",
        "KNOWN": "Known vocabulary is due for a seven-day refresh.",
    }[status]
    item = {
        "id": stable_id,
        "type": "VOCABULARY",
        "contentUuid": content_uuid,
        "title": word,
        "reason": reason,
        "priority": priority,
        "dueAt": _iso_utc(due_at),
        "word": word,
        "status": status,
        "action": "REVIEW_WORD",
    }
    return _Candidate(_sort_key(due_at, as_of, priority, stable_id), item)


def _lesson_candidate(raw: Mapping[str, Any] | Any, as_of: datetime) -> _Candidate | None:
    content_uuid = str(_value(raw, "contentUuid", "content_uuid") or "").strip()
    if not content_uuid:
        return None
    title = str(_value(raw, "title") or "Review weak lesson").strip() or "Review weak lesson"
    reason = str(_value(raw, "reason") or "This lesson contains a recent weak point.").strip()
    priority = _coerce_priority(_value(raw, "priority"))
    due_value = _value(raw, "dueAt", "due_at")
    try:
        due_at = as_of if due_value in (None, "") else _parse_datetime(due_value)
    except (TypeError, ValueError):
        return None
    if due_at > as_of:
        return None

    stable_id = str(_value(raw, "id") or "").strip()
    if not stable_id:
        stable_id = _stable_id("lesson", content_uuid, title.casefold())
    item = {
        "id": stable_id,
        "type": "LESSON",
        "contentUuid": content_uuid,
        "title": title,
        "reason": reason,
        "priority": priority,
        "dueAt": _iso_utc(due_at),
        "word": None,
        "status": "NEEDS_REVIEW",
        "action": "REVIEW_LESSON",
    }
    return _Candidate(_sort_key(due_at, as_of, priority, stable_id), item)


def _sort_key(
    due_at: datetime,
    as_of: datetime,
    priority: int,
    stable_id: str,
) -> tuple[int, int, datetime, str]:
    # Due-before-now is intentionally separated from due-exactly-now. This makes
    # existing backlog precede items that become due during the current request.
    return (0 if due_at < as_of else 1, priority, due_at, stable_id)


def _value(raw: Mapping[str, Any] | Any, *names: str) -> Any:
    if isinstance(raw, Mapping):
        for name in names:
            if name in raw:
                return raw[name]
        return None
    for name in names:
        if hasattr(raw, name):
            return getattr(raw, name)
    return None


def _parse_datetime(value: datetime | str | Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("datetime is empty")
        if text.endswith(("Z", "z")):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
    else:
        raise TypeError("datetime must be a datetime or ISO-8601 string")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _local_date(original: datetime | str, parsed_utc: datetime) -> str:
    if isinstance(original, datetime) and original.tzinfo is not None:
        return original.date().isoformat()
    if isinstance(original, str):
        text = original.strip()
        if text.endswith(("Z", "z")):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is not None:
                return parsed.date().isoformat()
        except ValueError:
            pass
    return parsed_utc.date().isoformat()


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_word(word: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(word))
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def _stable_id(kind: str, *parts: str) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{kind}-{hashlib.sha256(payload).hexdigest()[:20]}"


def _coerce_priority(value: Any) -> int:
    try:
        priority = int(value)
    except (TypeError, ValueError):
        return 2
    return min(3, max(1, priority))


def _bounded_limit(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 10
    return min(_MAX_LIMIT, max(0, parsed))
