"""Apply a reviewed duplicate manifest with an exclusive, reversible backup."""
import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import select

from src.backend_models import ContentArchiveRecord, ContentRecord


def lesson_digest(payload: str | None) -> str:
    return hashlib.sha256((payload or "").encode("utf-8")).hexdigest()


def archive_reviewed(session_factory, entries: list[dict], backup_path: Path,
                     protected_uuids: set[str] | None = None, apply: bool = False) -> int:
    protected = protected_uuids or set()
    ids = [entry["uuid"] for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("Manifest contains repeated UUIDs")
    targets = set(ids)
    planned = []
    with session_factory() as session:
        for entry in entries:
            content = session.get(ContentRecord, entry["uuid"])
            keeper = session.get(ContentRecord, entry["duplicateOf"])
            if not content or not keeper or content.uuid == keeper.uuid:
                raise ValueError("Missing lesson or invalid representative")
            if content.uuid in protected or keeper.uuid in targets:
                raise ValueError("Protected lesson or representative is itself a duplicate")
            if content.status != "READY" or keeper.status != "READY":
                raise ValueError("Only completed lessons can be archived")
            if lesson_digest(content.lesson_content) != entry["lessonSha256"]:
                raise ValueError(f"Lesson changed after review: {content.uuid}")
            if lesson_digest(keeper.lesson_content) != entry["keeperSha256"]:
                raise ValueError(f"Representative changed after review: {keeper.uuid}")
            if session.get(ContentArchiveRecord, keeper.uuid):
                raise ValueError("Representative is already archived")
            existing = session.get(ContentArchiveRecord, content.uuid)
            if existing:
                if existing.duplicate_of != keeper.uuid or existing.reason != entry["reason"]:
                    raise ValueError("Conflicting archive entry")
                continue
            planned.append({
                "entry": entry,
                "content": {column.name: getattr(content, column.name)
                            for column in ContentRecord.__table__.columns},
            })
        if not apply:
            return len(planned)
        # All rows are verified before writing an exclusive backup or mutating the DB.
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(backup_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"version": 1, "insertions": planned}, output,
                      ensure_ascii=False, indent=2, default=str)
            output.flush()
            os.fsync(output.fileno())
        for row in planned:
            entry = row["entry"]
            session.add(ContentArchiveRecord(content_uuid=entry["uuid"],
                                            duplicate_of=entry["duplicateOf"],
                                            reason=entry["reason"]))
        session.commit()
    return len(planned)


def restore_archive(session_factory, backup_path: Path) -> int:
    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    if backup.get("version") != 1:
        raise ValueError("Unsupported archive backup")
    with session_factory() as session:
        restored = []
        for row in backup["insertions"]:
            entry = row["entry"]
            archive = session.get(ContentArchiveRecord, entry["uuid"])
            if archive:
                if archive.duplicate_of != entry["duplicateOf"] or archive.reason != entry["reason"]:
                    raise ValueError("Archive changed since backup; refusing to overwrite it")
                restored.append(archive)
        for archive in restored:
            session.delete(archive)
        session.commit()
    return len(restored)
