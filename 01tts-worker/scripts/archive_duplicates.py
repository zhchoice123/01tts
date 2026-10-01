"""Dry-run by default. Run using the API service environment and worker venv."""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from src.backend_config import load_backend_config
from src.backend_models import Base, DailyPlanRecord, create_session_factory
from src.content_archive import archive_reviewed, restore_archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args()
    config = load_backend_config()
    engine, sessions = create_session_factory(config.database_url)
    if args.restore:
        print(json.dumps({"restored": restore_archive(sessions, args.restore)}))
        return
    if not args.manifest or (args.apply and not args.backup):
        parser.error("--manifest is required; --apply also requires --backup")
    # API startup creates this additive table. A dry run does not create tables.
    if args.apply:
        Base.metadata.create_all(engine)
    with sessions() as session:
        protected = set(session.scalars(select(DailyPlanRecord.content_uuid).where(
            DailyPlanRecord.plan_date == datetime.now(ZoneInfo(config.timezone)).date()
        )).all())
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    count = archive_reviewed(sessions, manifest["entries"],
                            args.backup or Path("unused.json"), protected, args.apply)
    print(json.dumps({"applied": args.apply, "count": count}))


if __name__ == "__main__":
    main()
