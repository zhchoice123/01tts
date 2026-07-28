import asyncio
import hashlib
import json
import logging
import re
import shutil
import tempfile
import threading
import uuid as uuid_module
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from sqlalchemy import select

from src.backend_config import BackendConfig
from src.backend_models import (
    AnkiReviewLessonRecord,
    AnkiReviewTargetRecord,
    Base,
    ContentRecord,
    DailyGenerationRunRecord,
    DailyPlanRecord,
    LearningAttemptRecord,
    SpeakingAnswerRecord,
    TaskRecord,
    TopicCandidateRecord,
)
from src.content_ingestion import fetch_content, fetch_feed_candidates
from src.deepseek_service import DeepSeekService, count_english_words
from src.provider_router import ProviderRouter
from src.schema_validator import validate_and_repair_lesson_content
from src.speaking_service import SpeakingAssessmentService
from src.tts_service import generate_audio, generate_dialogue_audio

LOGGER = logging.getLogger("tts-python-api.service")

DAILY_TOPICS = [
    (
        "JAVA",
        "Modern Java in Production",
        "Explain one modern Java feature and how a backend team can adopt it safely.",
    ),
    (
        "SPRING",
        "Reliable Spring Services",
        "Explain one Spring Boot design pattern with a realistic production example.",
    ),
    (
        "DATA",
        "MySQL and Redis Trade-offs",
        "Compare a practical MySQL or Redis design decision, including consistency and failure modes.",
    ),
    (
        "DISTRIBUTED_SYSTEMS",
        "Building Resilient Distributed Systems",
        "Teach one distributed-systems concept through an incident and its engineering response.",
    ),
    (
        "CLOUD_NATIVE",
        "Operating Cloud-Native Backends",
        "Explain a Docker, Kubernetes, observability, or performance topic for backend developers.",
    ),
]

LONG_LESSON_PREFIX = "__LISTENING_LAB_LONG_V1__:"

class BackendService:
    def __init__(
        self,
        config: BackendConfig,
        engine: Any,
        session_factory: Any,
        redis_client: Any,
        generator: Any | None = None,
        assessor: Any | None = None,
        audio_generator: Callable[..., Any] = generate_audio,
        dialogue_audio_generator: Callable[..., Any] = generate_dialogue_audio,
        content_fetcher: Callable[..., Any] = fetch_content,
        feed_fetcher: Callable[..., Any] | None = None,
    ):
        self.config = config
        self.engine = engine
        self.session_factory = session_factory
        self.redis = redis_client
        self.generator = generator or ProviderRouter(
            [
                (
                    "deepseek",
                    DeepSeekService(
                        config.worker.deepseek_api_key,
                        base_url="https://api.deepseek.com",
                        model=config.worker.deepseek_model,
                    ),
                ),
                (
                    "kimi",
                    DeepSeekService(
                        config.worker.moonshot_api_key,
                        base_url="https://api.moonshot.cn/v1",
                        model=config.worker.moonshot_model,
                        timeout_seconds=20,
                    ),
                ),
            ]
        )
        self.assessor = assessor or SpeakingAssessmentService(
            config.worker.openai_api_key,
            config.worker.deepseek_api_key,
        )
        self.audio_generator = audio_generator
        self.dialogue_audio_generator = dialogue_audio_generator
        self.content_fetcher = content_fetcher
        self.feed_fetcher = (
            feed_fetcher
            if feed_fetcher is not None
            else (fetch_feed_candidates if content_fetcher is fetch_content else None)
        )
        self.stop_event = threading.Event()
        self.threads: list[threading.Thread] = []

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)
        for directory in (
            self.task_audio_dir,
            self.content_audio_dir,
            self.answer_audio_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self.recover_incomplete_jobs()

    def recover_incomplete_jobs(self) -> dict[str, int]:
        with self.session_factory() as session:
            pending = {
                "tasks": (
                    self.config.task_queue,
                    session.scalars(
                        select(TaskRecord.task_uuid).where(
                            TaskRecord.status == "PENDING"
                        )
                    ).all(),
                ),
                "content": (
                    self.config.content_queue,
                    session.scalars(
                        select(ContentRecord.uuid).where(
                            ContentRecord.status == "GENERATING"
                        )
                    ).all(),
                ),
                "anki": (
                    self.config.anki_review_queue,
                    session.scalars(
                        select(AnkiReviewLessonRecord.uuid).where(
                            AnkiReviewLessonRecord.status == "GENERATING"
                        )
                    ).all(),
                ),
                "speaking": (
                    self.config.speaking_queue,
                    session.scalars(
                        select(SpeakingAnswerRecord.answer_uuid).where(
                            SpeakingAnswerRecord.status == "PENDING"
                        )
                    ).all(),
                ),
            }
        recovered: dict[str, int] = {}
        for job_type, (queue_name, record_ids) in pending.items():
            for record_id in record_ids:
                self.redis.lpush(queue_name, record_id)
            recovered[job_type] = len(record_ids)
        if any(recovered.values()):
            LOGGER.warning("Requeued incomplete jobs after startup: %s", recovered)
        return recovered

    @property
    def task_audio_dir(self) -> Path:
        return self.config.storage_dir / "tasks"

    @property
    def content_audio_dir(self) -> Path:
        return self.config.storage_dir / "content"

    @property
    def answer_audio_dir(self) -> Path:
        return self.config.storage_dir / "answers"

    def start_consumers(self) -> None:
        if self.threads:
            return
        for name, target in (
            ("lesson-consumer", self._lesson_loop),
            ("speaking-consumer", self._speaking_loop),
        ):
            thread = threading.Thread(name=name, target=target, daemon=True)
            thread.start()
            self.threads.append(thread)
        LOGGER.info("Started Redis consumers")

    def stop_consumers(self) -> None:
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=4)
        self.threads.clear()

    def create_task(self, prompt: str, voice: str, difficulty: str) -> dict[str, Any]:
        task = TaskRecord(
            task_uuid=str(uuid_module.uuid4()),
            prompt=prompt.strip(),
            voice=voice,
            difficulty=difficulty,
            status="PENDING",
        )
        with self.session_factory() as session:
            session.add(task)
            session.commit()
        self.redis.lpush(self.config.task_queue, task.task_uuid)
        LOGGER.info("Created and queued task %s", task.task_uuid)
        return self.task_dict(task)

    def create_anki_review_lesson(
        self,
        *,
        client_date: date,
        deck_alias: str,
        level: str,
        voice: str,
        topic_mode: str,
        topic_uuid: str | None,
        words: list[dict[str, str]],
    ) -> dict[str, Any]:
        normalized_words: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in words:
            word = str(item.get("word", "")).strip()
            key = word.casefold()
            if not word or key in seen:
                continue
            seen.add(key)
            normalized_words.append(
                {
                    "clientWordKey": str(item.get("clientWordKey", "")).strip(),
                    "word": word[:120],
                    "meaning": str(item.get("meaning", "")).strip()[:500],
                    "example": str(item.get("example", "")).strip()[:500],
                    "usageNotes": str(item.get("usageNotes", "")).strip()[:500],
                }
            )
        if not normalized_words:
            raise ValueError("at least one unique word is required")
        if len(normalized_words) > 30:
            raise ValueError("no more than 30 words are allowed")

        fingerprint_source = {
            "clientDate": client_date.isoformat(),
            "deckAlias": deck_alias.strip(),
            "level": level.strip().upper(),
            "voice": voice.strip(),
            "topicMode": topic_mode.strip().upper(),
            "topicUuid": topic_uuid or "",
            "words": sorted(
                (
                    item["clientWordKey"],
                    item["word"].casefold(),
                    item["meaning"],
                    item["example"],
                )
                for item in normalized_words
            ),
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                fingerprint_source,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        with self.session_factory() as session:
            existing = session.scalar(
                select(AnkiReviewLessonRecord).where(
                    AnkiReviewLessonRecord.request_fingerprint == fingerprint
                )
            )
            if existing:
                targets = session.scalars(
                    select(AnkiReviewTargetRecord).where(
                        AnkiReviewTargetRecord.lesson_uuid == existing.uuid
                    )
                ).all()
                return self.anki_review_dict(existing, targets)

            lesson_uuid = str(uuid_module.uuid4())
            lesson = AnkiReviewLessonRecord(
                uuid=lesson_uuid,
                client_date=client_date,
                deck_alias=deck_alias.strip()[:255] or "Anki",
                level=level.strip().upper() or "B1",
                voice=voice.strip() or "en-US-AvaNeural",
                topic_mode=topic_mode.strip().upper() or "DAILY_RECOMMENDED",
                topic_uuid=topic_uuid,
                request_fingerprint=fingerprint,
                status="GENERATING",
                target_word_count=len(normalized_words),
                covered_word_count=0,
            )
            targets = [
                AnkiReviewTargetRecord(
                    lesson_uuid=lesson_uuid,
                    client_word_key=item["clientWordKey"],
                    word=item["word"],
                    meaning=item["meaning"],
                    example=item["example"],
                    usage_notes=item["usageNotes"],
                )
                for item in normalized_words
            ]
            session.add(lesson)
            session.add_all(targets)
            session.commit()
            response = self.anki_review_dict(lesson, targets)
        self.redis.lpush(self.config.anki_review_queue, lesson_uuid)
        LOGGER.info(
            "Created Anki review lesson %s with %d target words",
            lesson_uuid,
            len(normalized_words),
        )
        return response

    def get_anki_review_lesson(self, lesson_uuid: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            lesson = session.get(AnkiReviewLessonRecord, lesson_uuid)
            if not lesson:
                return None
            targets = session.scalars(
                select(AnkiReviewTargetRecord).where(
                    AnkiReviewTargetRecord.lesson_uuid == lesson_uuid
                )
            ).all()
            return self.anki_review_dict(lesson, targets)

    def list_anki_review_lessons(self, client_date: date) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            lessons = session.scalars(
                select(AnkiReviewLessonRecord)
                .where(AnkiReviewLessonRecord.client_date == client_date)
                .order_by(AnkiReviewLessonRecord.created_at.desc())
            ).all()
            results = []
            for lesson in lessons:
                targets = session.scalars(
                    select(AnkiReviewTargetRecord).where(
                        AnkiReviewTargetRecord.lesson_uuid == lesson.uuid
                    )
                ).all()
                results.append(self.anki_review_dict(lesson, targets))
            return results

    def get_task(self, task_uuid: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            task = session.get(TaskRecord, task_uuid)
            return self.task_dict(task) if task else None

    def create_content(
        self,
        source_type: str,
        source_url: str,
        text: str,
        title: str,
        level: str,
    ) -> dict[str, Any]:
        normalized_type = source_type.strip().upper()
        if normalized_type not in {"TEXT", "URL", "NEWS", "TECH_DOC"}:
            raise ValueError("unsupported sourceType")
        source_text = text.strip()
        source_url = source_url.strip()
        if normalized_type == "TEXT" and not source_text:
            raise ValueError("text is required for TEXT content")
        if normalized_type != "TEXT" and not source_url and not source_text:
            raise ValueError("sourceUrl or text is required")
        resolved_text = source_text or source_url
        content = ContentRecord(
            uuid=str(uuid_module.uuid4()),
            title=title.strip() or resolved_text[:60] or "English learning content",
            source_type=normalized_type,
            source_url=source_url or None,
            source_text=resolved_text,
            level=level or "B1",
            status="GENERATING",
        )
        with self.session_factory() as session:
            session.add(content)
            session.commit()
        self.redis.lpush(self.config.content_queue, content.uuid)
        LOGGER.info("Created and queued content %s", content.uuid)
        return self.content_dict(content)

    def create_long_lesson(
        self,
        topic: str = "",
        category: str = "BACKEND",
        voice: str = "en-US-AvaNeural",
        level: str = "B1",
        source_mode: str = "AUTO",
    ) -> dict[str, Any]:
        normalized_mode = (source_mode or "AUTO").strip().upper()
        if normalized_mode not in {"AUTO", "AI", "FEED"}:
            raise ValueError("sourceMode must be AUTO, AI, or FEED")
        normalized_level = (level or "B1").strip().upper()
        if normalized_level not in {"B1", "B2"}:
            raise ValueError("level must be B1 or B2")
        envelope = {
            "profile": "BACKEND_DAILY_10MIN",
            "topic": topic.strip(),
            "category": (category or "BACKEND").strip().upper(),
            "voice": (voice or "en-US-AvaNeural").strip(),
            "level": normalized_level,
            "sourceMode": normalized_mode,
        }
        resolved_title = topic.strip() or f"{envelope['category'].title()} Backend English"
        content = ContentRecord(
            uuid=str(uuid_module.uuid4()),
            title=resolved_title[:255],
            source_type="TECH_DOC",
            source_url=None,
            source_text=LONG_LESSON_PREFIX + json.dumps(envelope, ensure_ascii=False),
            level=normalized_level,
            status="GENERATING",
        )
        with self.session_factory() as session:
            session.add(content)
            session.commit()
        self.redis.lpush(self.config.content_queue, content.uuid)
        LOGGER.info(
            "Created asynchronous long lesson %s category=%s source_mode=%s",
            content.uuid,
            envelope["category"],
            normalized_mode,
        )
        return self.content_dict(content)

    def create_dialogue_lesson(
        self,
        topic: str = "",
        category: str = "BACKEND",
        host_voice: str = "en-US-AvaNeural",
        expert_voice: str = "en-US-AndrewNeural",
        level: str = "B1",
        source_mode: str = "AUTO",
    ) -> dict[str, Any]:
        normalized_mode = (source_mode or "AUTO").strip().upper()
        if normalized_mode not in {"AUTO", "AI", "FEED"}:
            raise ValueError("sourceMode must be AUTO, AI, or FEED")
        normalized_level = (level or "B1").strip().upper()
        if normalized_level not in {"B1", "B2"}:
            raise ValueError("level must be B1 or B2")
        envelope = {
            "profile": "BACKEND_DAILY_DIALOGUE_10MIN",
            "format": "DIALOGUE",
            "topic": topic.strip(),
            "category": (category or "BACKEND").strip().upper(),
            "voice": (host_voice or "en-US-AvaNeural").strip(),
            "hostVoice": (host_voice or "en-US-AvaNeural").strip(),
            "expertVoice": (expert_voice or "en-US-AndrewNeural").strip(),
            "level": normalized_level,
            "sourceMode": normalized_mode,
        }
        resolved_title = (
            topic.strip()
            or f"{envelope['category'].title()} Engineering Dialogue"
        )
        content = ContentRecord(
            uuid=str(uuid_module.uuid4()),
            title=resolved_title[:255],
            source_type="TECH_DOC",
            source_url=None,
            source_text=LONG_LESSON_PREFIX
            + json.dumps(envelope, ensure_ascii=False),
            level=normalized_level,
            status="GENERATING",
        )
        with self.session_factory() as session:
            session.add(content)
            session.commit()
        self.redis.lpush(self.config.content_queue, content.uuid)
        LOGGER.info(
            "Created asynchronous dialogue %s category=%s source_mode=%s",
            content.uuid,
            envelope["category"],
            normalized_mode,
        )
        return self.content_dict(content)

    @staticmethod
    def _long_lesson_metadata(source_text: str) -> dict[str, Any] | None:
        if not source_text.startswith(LONG_LESSON_PREFIX):
            return None
        try:
            parsed = json.loads(source_text[len(LONG_LESSON_PREFIX):])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    def get_content(self, content_uuid: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            content = session.get(ContentRecord, content_uuid)
            return self.content_dict(content) if content else None

    def library(self) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            records = session.scalars(
                select(ContentRecord).order_by(ContentRecord.created_at.desc())
            ).all()
            return [self.content_dict(record) for record in records]

    def create_attempt(
        self, content_uuid: str, answers_json: str, correct_count: int | None
    ) -> dict[str, Any] | None:
        with self.session_factory() as session:
            if not session.get(ContentRecord, content_uuid):
                return None
            attempt = LearningAttemptRecord(
                content_uuid=content_uuid,
                answers_json=answers_json,
                correct_count=correct_count,
            )
            session.add(attempt)
            session.commit()
            return {
                "id": attempt.id,
                "contentUuid": attempt.content_uuid,
                "answersJson": attempt.answers_json,
                "correctCount": attempt.correct_count,
                "submittedAt": self.iso(attempt.submitted_at),
            }

    def generate_daily_plan(self, plan_date: date) -> dict[str, Any]:
        with self.session_factory() as session:
            plan = session.get(DailyPlanRecord, plan_date)
            if plan:
                content = session.get(ContentRecord, plan.content_uuid)
                return self.daily_dict(plan, content)

        category, title, prompt = DAILY_TOPICS[plan_date.toordinal() % len(DAILY_TOPICS)]
        content = self.create_dialogue_lesson(
            topic=f"{title}. {prompt}",
            category=category,
            host_voice="en-US-AvaNeural",
            expert_voice="en-US-AndrewNeural",
            level="B1",
            source_mode="AUTO",
        )
        plan = DailyPlanRecord(plan_date=plan_date, content_uuid=content["uuid"])
        with self.session_factory() as session:
            session.add(plan)
            session.commit()
            content_record = session.get(ContentRecord, plan.content_uuid)
            return self.daily_dict(plan, content_record)

    def get_daily_plan(self, plan_date: date) -> dict[str, Any] | None:
        with self.session_factory() as session:
            plan = session.get(DailyPlanRecord, plan_date)
            if not plan:
                return None
            return self.daily_dict(plan, session.get(ContentRecord, plan.content_uuid))

    def today(self) -> dict[str, Any]:
        today = self.local_today()
        return self.get_daily_plan(today) or self.generate_daily_plan(today)

    def local_today(self) -> date:
        return datetime.now(ZoneInfo(self.config.timezone)).date()

    def run_daily_generation(self, plan_date: date | None = None) -> dict[str, Any]:
        resolved_date = plan_date or datetime.now(
            ZoneInfo(self.config.timezone)
        ).date()
        existing_topics: list[dict[str, Any]] = []
        recovering_missing_source = False
        with self.session_factory() as session:
            existing = session.get(DailyGenerationRunRecord, resolved_date)
            if existing:
                existing_topics = self.topic_candidates(resolved_date)
                has_source = any(
                    topic["kind"] == "SOURCE_ARTICLE" for topic in existing_topics
                )
                if has_source or not self.config.worker.news_sources:
                    if has_source and existing.source_count == 0:
                        existing.source_count = 1
                        session.commit()
                    return self.daily_generation_dict(existing, existing_topics)
                recovering_missing_source = True
            else:
                run = DailyGenerationRunRecord(
                    plan_date=resolved_date,
                    status="GENERATING",
                )
                session.add(run)
                session.commit()

        failures = []
        source_count = sum(
            topic["kind"] == "SOURCE_ARTICLE" for topic in existing_topics
        )
        candidate_count = len(existing_topics)
        initial_candidate_count = candidate_count
        source_urls = list(self.config.worker.news_sources)
        if source_urls:
            rotation = resolved_date.toordinal() % len(source_urls)
            source_urls = source_urls[rotation:] + source_urls[:rotation]
        for source_url in source_urls:
            if source_count >= 1 or (
                candidate_count >= 3 and not recovering_missing_source
            ):
                break
            try:
                if self.feed_fetcher:
                    candidates = self.feed_fetcher(source_url, limit=8)
                    ingested = next(
                        (
                            candidate
                            for candidate in candidates
                            if not self._source_seen_recently(
                                candidate.source_url, resolved_date
                            )
                        ),
                        None,
                    )
                    if ingested is None:
                        raise ValueError("feed has no new attributable candidates")
                else:
                    ingested = self.content_fetcher(
                        source_type="NEWS",
                        source_input=source_url,
                        news_sources=self.config.worker.news_sources,
                    )
                if not ingested.passage.strip() or not ingested.source_url.strip():
                    raise ValueError("news source returned no attributable article")
                source_hash = self.topic_source_hash(
                    "SOURCE_ARTICLE",
                    ingested.source_url,
                    ingested.title,
                )
                if self._topic_exists(resolved_date, source_hash):
                    continue
                content = self.create_content(
                    "NEWS",
                    ingested.source_url,
                    ingested.passage[:6000],
                    ingested.title,
                    "B1",
                )
                candidate = TopicCandidateRecord(
                    uuid=str(uuid_module.uuid4()),
                    plan_date=resolved_date,
                    kind="SOURCE_ARTICLE",
                    category="NEWS",
                    title=ingested.title[:255] or "Daily news",
                    summary=ingested.passage[:600],
                    source_name=urlparse(ingested.source_url).hostname or "News source",
                    source_url=ingested.source_url,
                    published_at=ingested.published_at or None,
                    source_hash=source_hash,
                    provider="source",
                    score=1.0,
                    status="GENERATING",
                    content_uuid=content["uuid"],
                )
                with self.session_factory() as session:
                    session.add(candidate)
                    session.commit()
                source_count += 1
                candidate_count += 1
            except Exception as error:
                failures.append(f"{source_url}: {error}")
                LOGGER.warning("Daily news source failed url=%s error=%s", source_url, error)

        topic_offset = resolved_date.toordinal() % len(DAILY_TOPICS)
        for index in range(len(DAILY_TOPICS)):
            if candidate_count >= 3:
                break
            category, title, prompt = DAILY_TOPICS[(topic_offset + index) % len(DAILY_TOPICS)]
            source_hash = self.topic_source_hash(
                "AI_ORIGINAL", category, f"{resolved_date}:{title}"
            )
            if self._topic_exists(resolved_date, source_hash):
                continue
            content = self.create_content(
                "TEXT",
                "",
                (
                    f"Recommend one timely and useful {category.lower()} topic for an "
                    f"English learner, then write the lesson about the specific angle you "
                    f"choose. Starting idea: {prompt} This is AI-original learning content, "
                    "not a live news report; do not invent current events or sources. "
                    "Choose a specific title and include useful vocabulary and "
                    "comprehension questions."
                ),
                title,
                "B1",
            )
            candidate = TopicCandidateRecord(
                uuid=str(uuid_module.uuid4()),
                plan_date=resolved_date,
                kind="AI_ORIGINAL",
                category=category,
                title=title,
                summary=prompt,
                source_name=None,
                source_url=None,
                published_at=None,
                source_hash=source_hash,
                provider="deepseek-kimi-router",
                score=0.7,
                status="GENERATING",
                content_uuid=content["uuid"],
            )
            with self.session_factory() as session:
                session.add(candidate)
                session.commit()
            candidate_count += 1

        self.generate_daily_plan(resolved_date)
        with self.session_factory() as session:
            run = session.get(DailyGenerationRunRecord, resolved_date)
            run.source_count = max(run.source_count, source_count)
            if candidate_count > initial_candidate_count or not existing_topics:
                run.status = "GENERATING" if candidate_count else "FAILED"
            run.failure_reason = "; ".join(failures)[:4000] or None
            session.commit()
            return self.daily_generation_dict(run, self.topic_candidates(resolved_date))

    def ensure_daily_generation(self) -> dict[str, Any] | None:
        now = datetime.now(ZoneInfo(self.config.timezone))
        scheduled = now.replace(
            hour=self.config.daily_hour,
            minute=self.config.daily_minute,
            second=0,
            microsecond=0,
        )
        if now < scheduled:
            return None
        return self.run_daily_generation(now.date())

    def topic_candidates(self, plan_date: date) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            candidates = session.scalars(
                select(TopicCandidateRecord)
                .where(TopicCandidateRecord.plan_date == plan_date)
                .order_by(
                    TopicCandidateRecord.score.desc(),
                    TopicCandidateRecord.created_at.asc(),
                )
            ).all()
            return [
                self.topic_dict(candidate, session.get(ContentRecord, candidate.content_uuid))
                for candidate in candidates
            ]

    def topic_lesson(self, topic_uuid: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            topic = session.get(TopicCandidateRecord, topic_uuid)
            if not topic:
                return None
            content = session.get(ContentRecord, topic.content_uuid)
            return {
                "topic": self.topic_dict(topic, content),
                "content": self.content_dict(content),
            }

    def create_answer(self, task_uuid: str, source_file: Path) -> dict[str, Any] | None:
        with self.session_factory() as session:
            if not session.get(TaskRecord, task_uuid):
                return None
        answer_uuid = str(uuid_module.uuid4())
        destination = self.answer_audio_dir / f"{answer_uuid}.m4a"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, destination)
        answer = SpeakingAnswerRecord(
            answer_uuid=answer_uuid,
            task_uuid=task_uuid,
            status="PENDING",
            audio_url=f"/audio/answers/{answer_uuid}.m4a",
        )
        with self.session_factory() as session:
            session.add(answer)
            session.commit()
        self.redis.lpush(self.config.speaking_queue, answer_uuid)
        return self.answer_dict(answer)

    def get_answer(self, answer_uuid: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            answer = session.get(SpeakingAnswerRecord, answer_uuid)
            return self.answer_dict(answer) if answer else None

    def process_lesson(self, record_uuid: str) -> None:
        with self.session_factory() as session:
            task = session.get(TaskRecord, record_uuid)
            content = None if task else session.get(ContentRecord, record_uuid)
            if not task and not content:
                LOGGER.warning("Ignoring queue item without database record: %s", record_uuid)
                return
            if task and task.status != "PENDING":
                LOGGER.info("Skipping terminal task %s status=%s", record_uuid, task.status)
                return
            if content and content.status != "GENERATING":
                LOGGER.info(
                    "Skipping terminal content %s status=%s",
                    record_uuid,
                    content.status,
                )
                return
            source_type = content.source_type if content else "TEXT"
            source_input = (
                (content.source_url or content.source_text) if content else task.prompt
            )
            difficulty = content.level if content else task.difficulty
            voice = "en-US-AvaNeural" if content else task.voice
            original_title = content.title if content else task.prompt[:60]
            long_metadata = (
                self._long_lesson_metadata(content.source_text) if content else None
            )
            if long_metadata:
                voice = str(long_metadata.get("voice") or voice)
            topic = (
                session.scalar(
                    select(TopicCandidateRecord).where(
                        TopicCandidateRecord.content_uuid == record_uuid
                    )
                )
                if content
                else None
            )
            is_ai_original_topic = topic is not None and topic.kind == "AI_ORIGINAL"

        try:
            if long_metadata:
                ingested = self._resolve_long_lesson_source(
                    long_metadata, record_uuid
                )
            else:
                ingested = self.content_fetcher(
                    source_type=source_type,
                    source_input=source_input,
                    news_sources=self.config.worker.news_sources,
                )
            title_instruction = (
                "Choose a specific, reader-friendly title for the topic you recommend."
                if is_ai_original_topic
                else f"Use this source title: {original_title or ingested.title}."
            )
            if long_metadata:
                lesson_kind = (
                    "two-speaker HOST and EXPERT technical podcast dialogue"
                    if long_metadata.get("format") == "DIALOGUE"
                    else "backend technical English lesson"
                )
                prompt = (
                    f"Create today's ten-minute {lesson_kind}. "
                    f"Level: {difficulty}. Category: {long_metadata.get('category', 'BACKEND')}. "
                    f"Requested topic: {long_metadata.get('topic') or 'choose a practical backend topic'}. "
                    f"{title_instruction} SourceType: {ingested.source_type}. "
                    f"Source title: {ingested.title}. Source URL: {ingested.source_url}. "
                    f"Source material: {ingested.passage[:8000]}"
                )
            else:
                prompt = (
                    f"Difficulty: {difficulty}. {title_instruction} "
                    f"SourceType: {ingested.source_type}. Text: {ingested.passage[:1500]}"
                )
            metadata = {
                "uuid": record_uuid,
                "title": original_title or ingested.title,
                "sourceType": ingested.source_type,
                "sourceUrl": ingested.source_url,
                "level": difficulty,
                "passage": ingested.passage,
            }
            if long_metadata:
                is_dialogue = long_metadata.get("format") == "DIALOGUE"
                generator_method = (
                    "generate_dialogue_lesson"
                    if is_dialogue
                    else "generate_long_lesson"
                )
                if not hasattr(self.generator, generator_method):
                    raise RuntimeError(
                        f"Configured generator does not support {generator_method}"
                    )
                lesson = getattr(self.generator, generator_method)(
                    prompt=prompt,
                    metadata=metadata,
                )
                word_count = count_english_words(str(lesson.get("passage", "")))
                minimum_words = 1250 if is_dialogue else 1200
                if not minimum_words <= word_count <= 1500:
                    raise ValueError(
                        "Long lesson passage must contain "
                        f"{minimum_words}-1500 English words; got {word_count}"
                    )
                lesson["wordCount"] = word_count
                lesson["estimatedDurationSeconds"] = round(
                    word_count / (125 if is_dialogue else 130) * 60
                )
                lesson["sourceAttribution"] = {
                    "title": ingested.title,
                    "url": ingested.source_url,
                    "publishedAt": ingested.published_at,
                    "sourceType": ingested.source_type,
                }
            else:
                lesson = validate_and_repair_lesson_content(
                    self.generator.generate_lesson(prompt=prompt, metadata=metadata),
                    metadata=metadata,
                )
            passage = (
                lesson.get("passage")
                or lesson.get("simplifiedPassage")
                or ingested.passage
            )
            destination = (
                self.task_audio_dir if task else self.content_audio_dir
            ) / f"{record_uuid}.mp3"
            if long_metadata and long_metadata.get("format") == "DIALOGUE":
                asyncio.run(
                    self.dialogue_audio_generator(
                        turns=lesson.get("dialogue") or [],
                        output_path=destination,
                        host_voice=str(
                            long_metadata.get("hostVoice")
                            or "en-US-AvaNeural"
                        ),
                        expert_voice=str(
                            long_metadata.get("expertVoice")
                            or "en-US-AndrewNeural"
                        ),
                    )
                )
            else:
                asyncio.run(
                    self.audio_generator(
                        text=passage,
                        output_path=destination,
                        voice=voice,
                    )
                )
            with self.session_factory() as session:
                if task:
                    record = session.get(TaskRecord, record_uuid)
                    record.status = "COMPLETED"
                    record.audio_url = f"/audio/{record_uuid}.mp3"
                    record.questions = json.dumps(lesson.get("questions", []))
                    record.failure_reason = None
                else:
                    record = session.get(ContentRecord, record_uuid)
                    record.status = "READY"
                    record.audio_url = f"/api/v1/audio/content/{record_uuid}.mp3"
                    record.lesson_content = json.dumps(lesson, ensure_ascii=False)
                    if long_metadata:
                        record.title = str(lesson.get("title") or record.title)[:255]
                        record.source_url = ingested.source_url or None
                    record.failure_reason = None
                session.commit()
            if content:
                self._sync_topic_status(
                    record_uuid,
                    "READY",
                    None,
                    generated_lesson=lesson,
                )
            LOGGER.info("Completed lesson %s", record_uuid)
        except Exception as error:
            LOGGER.exception("Lesson %s failed", record_uuid)
            with self.session_factory() as session:
                record = session.get(TaskRecord if task else ContentRecord, record_uuid)
                if record:
                    record.status = "FAILED"
                    record.failure_reason = str(error)[:4000]
                    session.commit()
            if content:
                self._sync_topic_status(record_uuid, "FAILED", str(error))

    def _resolve_long_lesson_source(
        self,
        long_metadata: dict[str, Any],
        record_uuid: str,
    ) -> Any:
        source_mode = str(long_metadata.get("sourceMode", "AUTO")).upper()
        if source_mode in {"AUTO", "FEED"} and self.feed_fetcher:
            feeds = list(self.config.worker.news_sources)
            if feeds:
                offset = int(
                    hashlib.sha256(record_uuid.encode("utf-8")).hexdigest()[:8], 16
                ) % len(feeds)
                ordered = feeds[offset:] + feeds[:offset]
                for feed_url in ordered:
                    try:
                        candidates = self.feed_fetcher(feed_url, limit=8)
                        candidate = next(
                            (
                                item for item in candidates
                                if not self._content_source_seen_recently(item.source_url)
                            ),
                            None,
                        )
                        if candidate:
                            return candidate
                    except Exception as error:
                        LOGGER.warning(
                            "Long lesson feed failed url=%s error=%s",
                            feed_url,
                            error,
                        )
        if source_mode == "FEED":
            raise RuntimeError("No usable official feed article was available")
        topic = str(long_metadata.get("topic") or "").strip()
        category = str(long_metadata.get("category") or "BACKEND").strip()
        topic_preference = topic or (
            "choose a useful Java, Spring, database, distributed systems, "
            "cloud-native, or observability topic"
        )
        return self.content_fetcher(
            source_type="TEXT",
            source_input=(
                f"Create an original backend engineering lesson. Category: {category}. "
                f"Topic preference: {topic_preference}. "
                "Do not invent a news source or claim this is current news."
            ),
            news_sources=self.config.worker.news_sources,
        )

    def _content_source_seen_recently(self, source_url: str) -> bool:
        if not source_url:
            return False
        cutoff = datetime.now().astimezone() - timedelta(days=30)
        with self.session_factory() as session:
            return session.scalar(
                select(ContentRecord.uuid).where(
                    ContentRecord.source_url == source_url,
                    ContentRecord.created_at >= cutoff,
                )
            ) is not None

    def process_anki_review(self, lesson_uuid: str) -> None:
        with self.session_factory() as session:
            lesson = session.get(AnkiReviewLessonRecord, lesson_uuid)
            if not lesson:
                LOGGER.warning("Ignoring unknown Anki review lesson %s", lesson_uuid)
                return
            if lesson.status != "GENERATING":
                LOGGER.info(
                    "Skipping terminal Anki review lesson %s status=%s",
                    lesson_uuid,
                    lesson.status,
                )
                return
            targets = session.scalars(
                select(AnkiReviewTargetRecord).where(
                    AnkiReviewTargetRecord.lesson_uuid == lesson_uuid
                )
            ).all()
            target_words = [target.word for target in targets]
            word_context = [
                {
                    "word": target.word,
                    "meaning": target.meaning,
                    "example": target.example,
                    "usageNotes": target.usage_notes,
                }
                for target in targets
            ]
            level = lesson.level
            voice = lesson.voice
            topic_mode = lesson.topic_mode

        metadata = {
            "uuid": lesson_uuid,
            "title": "Anki Review Story",
            "sourceType": "TEXT",
            "sourceUrl": "",
            "level": level,
            "targetWords": target_words,
        }
        prompt = (
            f"Create a {level} English learning article of 250-500 words. "
            f"Use every target word naturally and preserve its intended meaning. "
            f"Topic mode: {topic_mode}. Target word context: "
            f"{json.dumps(word_context, ensure_ascii=False)}. "
            "Return 3-5 multiple-choice comprehension questions and one speaking prompt."
        )
        try:
            lesson_content = validate_and_repair_lesson_content(
                self.generator.generate_lesson(prompt=prompt, metadata=metadata),
                metadata=metadata,
            )
            covered, missing = self.target_word_coverage(
                lesson_content.get("passage", ""), target_words
            )
            if missing:
                repair_prompt = (
                    f"{prompt} The previous passage omitted these exact target words: "
                    f"{', '.join(missing)}. Rewrite the complete passage and include every one."
                )
                lesson_content = validate_and_repair_lesson_content(
                    self.generator.generate_lesson(
                        prompt=repair_prompt,
                        metadata={**metadata, "missingTargetWords": missing},
                    ),
                    metadata=metadata,
                )
                covered, missing = self.target_word_coverage(
                    lesson_content.get("passage", ""), target_words
                )
            if missing:
                raise TargetWordCoverageError(missing)

            lesson_content["targetWords"] = target_words
            lesson_content["coveredTargetWords"] = covered
            lesson_content["missingTargetWords"] = []
            destination = self.content_audio_dir / f"{lesson_uuid}.mp3"
            asyncio.run(
                self.audio_generator(
                    text=lesson_content["passage"],
                    output_path=destination,
                    voice=voice,
                )
            )
            with self.session_factory() as session:
                record = session.get(AnkiReviewLessonRecord, lesson_uuid)
                record.status = "READY"
                record.lesson_content = json.dumps(lesson_content, ensure_ascii=False)
                record.audio_url = f"/api/v1/audio/content/{lesson_uuid}.mp3"
                record.covered_word_count = len(covered)
                record.failure_code = None
                record.failure_reason = None
                session.commit()
            LOGGER.info(
                "Completed Anki review lesson %s with %d/%d target words",
                lesson_uuid,
                len(covered),
                len(target_words),
            )
        except Exception as error:
            LOGGER.exception("Anki review lesson %s failed", lesson_uuid)
            with self.session_factory() as session:
                record = session.get(AnkiReviewLessonRecord, lesson_uuid)
                if record:
                    record.status = "FAILED"
                    record.failure_code = (
                        "TARGET_WORD_COVERAGE_FAILED"
                        if isinstance(error, TargetWordCoverageError)
                        else "GENERATION_FAILED"
                    )
                    record.failure_reason = str(error)[:4000]
                    session.commit()

    def process_answer(self, answer_uuid: str) -> None:
        with self.session_factory() as session:
            answer = session.get(SpeakingAnswerRecord, answer_uuid)
            if not answer:
                LOGGER.warning("Ignoring unknown answer %s", answer_uuid)
                return
            if answer.status != "PENDING":
                LOGGER.info(
                    "Skipping terminal speaking answer %s status=%s",
                    answer_uuid,
                    answer.status,
                )
                return
            task = session.get(TaskRecord, answer.task_uuid)
            question = self.speaking_question(task.questions if task else None)
            audio_path = self.answer_audio_dir / f"{answer_uuid}.m4a"
        try:
            assessment = self.assessor.assess(audio_path, question)
            with self.session_factory() as session:
                answer = session.get(SpeakingAnswerRecord, answer_uuid)
                answer.status = "COMPLETED"
                answer.transcript = assessment["transcript"]
                answer.score = int(assessment["score"])
                answer.feedback = str(assessment["feedback"])
                answer.failure_reason = None
                session.commit()
        except Exception as error:
            LOGGER.exception("Speaking assessment %s failed", answer_uuid)
            with self.session_factory() as session:
                answer = session.get(SpeakingAnswerRecord, answer_uuid)
                if answer:
                    answer.status = "FAILED"
                    answer.failure_reason = str(error)[:4000]
                    session.commit()

    def _lesson_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                item = self.redis.brpop(
                    [
                        self.config.task_queue,
                        self.config.content_queue,
                        self.config.anki_review_queue,
                    ],
                    timeout=2,
                )
                if item:
                    queue_name = item[0].decode() if isinstance(item[0], bytes) else item[0]
                    value = item[1].decode() if isinstance(item[1], bytes) else item[1]
                    if str(queue_name) == self.config.anki_review_queue:
                        self.process_anki_review(str(value))
                    else:
                        self.process_lesson(str(value))
            except Exception:
                LOGGER.exception("Lesson consumer error")
                self.stop_event.wait(2)

    def _speaking_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                item = self.redis.brpop(self.config.speaking_queue, timeout=2)
                if item:
                    value = item[1].decode() if isinstance(item[1], bytes) else item[1]
                    self.process_answer(str(value))
            except Exception:
                LOGGER.exception("Speaking consumer error")
                self.stop_event.wait(2)

    @staticmethod
    def speaking_question(raw_questions: Any) -> str:
        questions = json.loads(raw_questions) if isinstance(raw_questions, str) else raw_questions
        for question in questions or []:
            if not isinstance(question, dict):
                continue
            if question.get("type", "").upper() == "SPEAKING":
                return question.get("question") or question.get("prompt") or "Answer clearly."
        return "Summarize the lesson in your own words."

    @staticmethod
    def iso(value: datetime | None) -> str | None:
        return value.isoformat().replace("+00:00", "Z") if value else None

    @classmethod
    def task_dict(cls, task: TaskRecord) -> dict[str, Any]:
        return {
            "taskUuid": task.task_uuid,
            "prompt": task.prompt,
            "voice": task.voice,
            "difficulty": task.difficulty,
            "status": task.status,
            "audioUrl": task.audio_url,
            "questions": task.questions,
        }

    @classmethod
    def content_dict(cls, content: ContentRecord) -> dict[str, Any]:
        long_metadata = cls._long_lesson_metadata(content.source_text)
        result = {
            "uuid": content.uuid,
            "title": content.title,
            "sourceType": content.source_type,
            "sourceUrl": content.source_url,
            "sourceText": (
                str(long_metadata.get("topic", "")) if long_metadata else content.source_text
            ),
            "prompt": (
                str(long_metadata.get("topic", "")) if long_metadata else content.source_text
            ),
            "level": content.level,
            "status": content.status,
            "audioUrl": content.audio_url,
            "lessonContent": content.lesson_content,
            "failureReason": content.failure_reason,
            "createdAt": cls.iso(content.created_at),
        }
        if long_metadata:
            result.update(
                {
                    "profile": long_metadata.get("profile"),
                    "category": long_metadata.get("category"),
                    "voice": long_metadata.get("voice"),
                    "sourceMode": long_metadata.get("sourceMode"),
                    "estimatedMinutes": 10,
                    "format": long_metadata.get("format", "ARTICLE"),
                    "hostVoice": long_metadata.get("hostVoice"),
                    "expertVoice": long_metadata.get("expertVoice"),
                }
            )
        return result

    @classmethod
    def answer_dict(cls, answer: SpeakingAnswerRecord) -> dict[str, Any]:
        return {
            "answerUuid": answer.answer_uuid,
            "taskUuid": answer.task_uuid,
            "status": answer.status,
            "audioUrl": answer.audio_url,
            "transcript": answer.transcript,
            "score": answer.score,
            "feedback": answer.feedback,
        }

    @classmethod
    def daily_dict(
        cls, plan: DailyPlanRecord, content: ContentRecord
    ) -> dict[str, Any]:
        return {
            "planDate": plan.plan_date.isoformat(),
            "contentUuid": plan.content_uuid,
            "createdAt": cls.iso(plan.created_at),
            "estimatedMinutes": 10,
            "content": cls.content_dict(content),
        }

    @classmethod
    def anki_review_dict(
        cls,
        lesson: AnkiReviewLessonRecord,
        targets: list[AnkiReviewTargetRecord],
    ) -> dict[str, Any]:
        return {
            "uuid": lesson.uuid,
            "clientDate": lesson.client_date.isoformat(),
            "deckAlias": lesson.deck_alias,
            "level": lesson.level,
            "voice": lesson.voice,
            "topicMode": lesson.topic_mode,
            "topicId": lesson.topic_uuid,
            "status": lesson.status,
            "targetWordCount": lesson.target_word_count,
            "coveredWordCount": lesson.covered_word_count,
            "audioUrl": lesson.audio_url,
            "lessonContent": lesson.lesson_content,
            "failureCode": lesson.failure_code,
            "failureReason": lesson.failure_reason,
            "words": [
                {
                    "clientWordKey": target.client_word_key,
                    "word": target.word,
                    "meaning": target.meaning,
                    "example": target.example,
                    "usageNotes": target.usage_notes,
                }
                for target in targets
            ],
            "createdAt": cls.iso(lesson.created_at),
        }

    @classmethod
    def topic_dict(
        cls,
        topic: TopicCandidateRecord,
        content: ContentRecord | None,
    ) -> dict[str, Any]:
        status = content.status if content else topic.status
        return {
            "uuid": topic.uuid,
            "planDate": topic.plan_date.isoformat(),
            "kind": topic.kind,
            "category": topic.category,
            "title": topic.title,
            "summary": topic.summary,
            "sourceName": topic.source_name,
            "sourceUrl": topic.source_url,
            "publishedAt": topic.published_at,
            "provider": topic.provider,
            "score": topic.score,
            "status": status,
            "contentUuid": topic.content_uuid,
            "audioUrl": content.audio_url if content else None,
            "failureReason": (
                content.failure_reason if content and content.failure_reason else topic.failure_reason
            ),
        }

    @staticmethod
    def daily_generation_dict(
        run: DailyGenerationRunRecord,
        topics: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "planDate": run.plan_date.isoformat(),
            "status": run.status,
            "sourceCount": run.source_count,
            "readyCount": run.ready_count,
            "failureReason": run.failure_reason,
            "topics": topics,
        }

    @staticmethod
    def topic_source_hash(kind: str, source: str, title: str) -> str:
        normalized = "|".join(
            part.strip().casefold() for part in (kind, source.rstrip("/"), title)
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _topic_exists(self, plan_date: date, source_hash: str) -> bool:
        with self.session_factory() as session:
            return session.scalar(
                select(TopicCandidateRecord.uuid).where(
                    TopicCandidateRecord.plan_date == plan_date,
                    TopicCandidateRecord.source_hash == source_hash,
                )
            ) is not None

    def _source_seen_recently(self, source_url: str, plan_date: date) -> bool:
        if not source_url:
            return False
        with self.session_factory() as session:
            return session.scalar(
                select(TopicCandidateRecord.uuid).where(
                    TopicCandidateRecord.source_url == source_url,
                    TopicCandidateRecord.plan_date >= plan_date - timedelta(days=30),
                    TopicCandidateRecord.plan_date < plan_date,
                )
            ) is not None

    def _sync_topic_status(
        self,
        content_uuid: str,
        status: str,
        failure_reason: str | None,
        generated_lesson: dict[str, Any] | None = None,
    ) -> None:
        with self.session_factory() as session:
            topic = session.scalar(
                select(TopicCandidateRecord).where(
                    TopicCandidateRecord.content_uuid == content_uuid
                )
            )
            if not topic:
                return
            topic.status = status
            topic.failure_reason = failure_reason[:4000] if failure_reason else None
            if topic.kind == "AI_ORIGINAL" and generated_lesson:
                generated_title = str(generated_lesson.get("title", "")).strip()
                generated_passage = str(generated_lesson.get("passage", "")).strip()
                if generated_title:
                    topic.title = generated_title[:255]
                if generated_passage:
                    topic.summary = generated_passage[:600]
            topics = session.scalars(
                select(TopicCandidateRecord).where(
                    TopicCandidateRecord.plan_date == topic.plan_date
                )
            ).all()
            statuses = [
                status if item.uuid == topic.uuid else item.status for item in topics
            ]
            run = session.get(DailyGenerationRunRecord, topic.plan_date)
            if run:
                run.ready_count = sum(value == "READY" for value in statuses)
                if statuses and all(value in {"READY", "FAILED"} for value in statuses):
                    run.status = "READY" if any(value == "READY" for value in statuses) else "FAILED"
                    run.completed_at = datetime.now().astimezone()
            session.commit()

    @staticmethod
    def target_word_coverage(
        passage: str, target_words: list[str]
    ) -> tuple[list[str], list[str]]:
        covered = []
        missing = []
        for word in target_words:
            pattern = rf"(?<![\w-]){re.escape(word)}(?![\w-])"
            if re.search(pattern, passage, flags=re.IGNORECASE):
                covered.append(word)
            else:
                missing.append(word)
        return covered, missing


class TargetWordCoverageError(ValueError):
    def __init__(self, missing: list[str]):
        super().__init__(f"Missing target words after repair: {', '.join(missing)}")
        self.missing = missing
