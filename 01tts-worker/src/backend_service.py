import asyncio
import hashlib
import json
import logging
import re
import shutil
import tempfile
import threading
import uuid as uuid_module
from datetime import date, datetime, time, timedelta, timezone
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
    LearningProgressRecord,
    SpeakingAnswerRecord,
    SpeakingSessionRecord,
    SpeakingSessionTurnRecord,
    TaskRecord,
    TopicCandidateRecord,
    UserVocabularyCardRecord,
    VocabularyProgressRecord,
    utc_now,
)
from src.content_ingestion import fetch_content, fetch_feed_candidates
from src.deepseek_service import DeepSeekService, count_english_words
from src.lesson_review import generate_lesson_review_report
from src.provider_router import ProviderRouter
from src.review_queue import build_review_queue
from src.schema_validator import validate_and_repair_lesson_content
from src.speaking_service import SpeakingAssessmentService
from src.tts_service import _tts_provider_voice, generate_audio, generate_dialogue_audio

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
            self.app_release_dir,
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

    @property
    def speaking_session_audio_dir(self) -> Path:
        directory = self.config.storage_dir / "speaking-sessions"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @property
    def app_release_dir(self) -> Path:
        return self.config.storage_dir / "app-releases"

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
        _tts_provider_voice(voice)
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

    def upsert_learning_progress(
        self,
        *,
        client_id: str,
        content_uuid: str,
        position_ms: int,
        duration_ms: int,
        vocabulary_done: bool,
        listening_done: bool,
        reading_done: bool,
        quiz_correct: int,
        quiz_total: int,
        speaking_score: int | None,
        completed: bool,
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            progress = session.scalar(
                select(LearningProgressRecord).where(
                    LearningProgressRecord.client_id == client_id,
                    LearningProgressRecord.content_uuid == content_uuid,
                )
            )
            if progress is None:
                progress = LearningProgressRecord(
                    client_id=client_id,
                    content_uuid=content_uuid,
                )
                session.add(progress)
            progress.position_ms = position_ms
            progress.duration_ms = duration_ms
            progress.vocabulary_done = vocabulary_done
            progress.listening_done = listening_done
            progress.reading_done = reading_done
            progress.quiz_correct = quiz_correct
            progress.quiz_total = quiz_total
            progress.speaking_score = speaking_score
            progress.completed = completed
            progress.updated_at = utc_now()
            session.commit()
            return self.learning_progress_dict(progress)

    def get_learning_progress(
        self,
        client_id: str,
        content_uuid: str,
    ) -> dict[str, Any] | None:
        with self.session_factory() as session:
            progress = session.scalar(
                select(LearningProgressRecord).where(
                    LearningProgressRecord.client_id == client_id,
                    LearningProgressRecord.content_uuid == content_uuid,
                )
            )
            return self.learning_progress_dict(progress) if progress else None

    def lesson_review_report(
        self,
        client_id: str,
        content_uuid: str,
    ) -> dict[str, Any] | None:
        with self.session_factory() as session:
            progress = session.scalar(
                select(LearningProgressRecord).where(
                    LearningProgressRecord.client_id == client_id,
                    LearningProgressRecord.content_uuid == content_uuid,
                )
            )
            if progress is None:
                return None
            vocabulary = session.scalars(
                select(VocabularyProgressRecord)
                .where(
                    VocabularyProgressRecord.client_id == client_id,
                    VocabularyProgressRecord.content_uuid == content_uuid,
                )
                .order_by(
                    VocabularyProgressRecord.updated_at.desc(),
                    VocabularyProgressRecord.id.desc(),
                )
            ).all()

            progress_payload = self.learning_progress_dict(progress)
            vocabulary_payload = [
                self.vocabulary_progress_dict(item) for item in vocabulary
            ]
        # SpeakingAnswerRecord has no client_id, so joining it by content UUID
        # could expose another learner's evaluation. Use the scoped progress score.
        return generate_lesson_review_report(
            learning_progress=progress_payload,
            vocabulary_progress=vocabulary_payload,
        )

    def upsert_vocabulary_progress(
        self,
        *,
        client_id: str,
        content_uuid: str,
        word: str,
        status: str,
    ) -> dict[str, Any]:
        normalized_word = word.strip().casefold()
        with self.session_factory() as session:
            vocabulary = session.scalar(
                select(VocabularyProgressRecord).where(
                    VocabularyProgressRecord.client_id == client_id,
                    VocabularyProgressRecord.normalized_word == normalized_word,
                )
            )
            if vocabulary is None:
                vocabulary = VocabularyProgressRecord(
                    client_id=client_id,
                    content_uuid=content_uuid,
                    word=word.strip(),
                    normalized_word=normalized_word,
                )
                session.add(vocabulary)
            vocabulary.content_uuid = content_uuid
            vocabulary.word = word.strip()
            vocabulary.status = status
            vocabulary.updated_at = utc_now()
            session.commit()
            return self.vocabulary_progress_dict(vocabulary)

    def list_vocabulary_progress(
        self,
        client_id: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            query = select(VocabularyProgressRecord).where(
                VocabularyProgressRecord.client_id == client_id
            )
            if status:
                query = query.where(VocabularyProgressRecord.status == status)
            vocabulary = session.scalars(
                query.order_by(VocabularyProgressRecord.updated_at.desc())
            ).all()
            return [self.vocabulary_progress_dict(item) for item in vocabulary]

    def learning_review_queue(
        self,
        client_id: str,
        review_date: date,
        limit: int,
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            vocabulary = session.scalars(
                select(VocabularyProgressRecord)
                .where(VocabularyProgressRecord.client_id == client_id)
                .order_by(
                    VocabularyProgressRecord.updated_at.desc(),
                    VocabularyProgressRecord.id.desc(),
                )
            ).all()
            vocabulary_payload = [
                self.vocabulary_progress_dict(item) for item in vocabulary
            ]
        as_of = datetime.combine(
            review_date,
            time(23, 59, 59),
            tzinfo=timezone.utc,
        )
        return build_review_queue(
            client_id=client_id,
            as_of=as_of,
            vocabulary_progress=vocabulary_payload,
            limit=limit,
        )

    def learning_dashboard(
        self,
        client_id: str,
        days: int,
    ) -> dict[str, Any]:
        now = datetime.now(ZoneInfo(self.config.timezone))
        first_day = now.date() - timedelta(days=days - 1)
        with self.session_factory() as session:
            all_progress = session.scalars(
                select(LearningProgressRecord).where(
                    LearningProgressRecord.client_id == client_id
                )
            ).all()
            all_vocabulary = session.scalars(
                select(VocabularyProgressRecord).where(
                    VocabularyProgressRecord.client_id == client_id
                )
            ).all()

        progress = [
            item
            for item in all_progress
            if self._local_date(item.updated_at) >= first_day
        ]
        vocabulary = [
            item
            for item in all_vocabulary
            if self._local_date(item.updated_at) >= first_day
        ]
        speaking_scores = [
            item.speaking_score
            for item in progress
            if item.speaking_score is not None
        ]
        latest = max(all_progress, key=lambda item: self._as_utc(item.updated_at), default=None)
        activity_days = {
            self._local_date(item.updated_at)
            for item in [*all_progress, *all_vocabulary]
        }
        return {
            "days": days,
            "listeningMinutes": sum(item.position_ms for item in progress) // 60_000,
            "completedLessons": sum(1 for item in progress if item.completed),
            "quizCorrect": sum(item.quiz_correct for item in progress),
            "quizTotal": sum(item.quiz_total for item in progress),
            "speakingAverage": (
                round(sum(speaking_scores) / len(speaking_scores))
                if speaking_scores
                else 0
            ),
            "currentStreak": self._current_streak(activity_days, now.date()),
            "wordsReviewed": sum(
                1 for item in vocabulary if item.status in {"LEARNING", "KNOWN"}
            ),
            "latestContentUuid": latest.content_uuid if latest else None,
            "latestPositionMs": latest.position_ms if latest else 0,
        }

    def _local_date(self, value: datetime) -> date:
        return self._as_utc(value).astimezone(
            ZoneInfo(self.config.timezone)
        ).date()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _current_streak(activity_days: set[date], today: date) -> int:
        streak = 0
        cursor = today
        while cursor in activity_days:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

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
            "profile": "BACKEND_DAILY_DIALOGUE_5_8MIN",
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
                select(ContentRecord)
                .where(ContentRecord.status != "FAILED")
                .order_by(ContentRecord.created_at.desc())
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
                if content and content.status != "FAILED":
                    return self.daily_dict(plan, content)
                # Keep the failed content row for diagnostics, but replace its visible
                # daily-plan reference so the app never gets stuck on a failed lesson.
                session.delete(plan)
                session.commit()

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
            content = session.get(ContentRecord, plan.content_uuid)
            if not content or content.status == "FAILED":
                return None
            return self.daily_dict(plan, content)

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
                provider="deepseek",
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
                .where(
                    TopicCandidateRecord.plan_date == plan_date,
                    TopicCandidateRecord.status != "FAILED",
                )
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
            if not topic or topic.status == "FAILED":
                return None
            content = session.get(ContentRecord, topic.content_uuid)
            if not content or content.status == "FAILED":
                return None
            return {
                "topic": self.topic_dict(topic, content),
                "content": self.content_dict(content),
            }

    def create_answer(self, task_uuid: str, source_file: Path) -> dict[str, Any] | None:
        with self.session_factory() as session:
            task = session.get(TaskRecord, task_uuid)
            content = session.get(ContentRecord, task_uuid)
            if not task and not content:
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

        failure_stage = "SOURCE_INGESTION"
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
                    f"Create today's {'5-8 minute' if long_metadata.get('format') == 'DIALOGUE' else 'ten-minute'} {lesson_kind}. "
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
            failure_stage = "SCRIPT_GENERATION"
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
                minimum_words = 700 if is_dialogue else 1200
                maximum_words = 1050 if is_dialogue else 1500
                if not minimum_words <= word_count <= maximum_words:
                    raise ValueError(
                        "Long lesson passage must contain "
                        f"{minimum_words}-{maximum_words} English words; got {word_count}"
                    )
                lesson["wordCount"] = word_count
                lesson["estimatedDurationSeconds"] = round(
                    word_count / 130 * 60
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
            failure_stage = "AUDIO_SYNTHESIS"
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
                        api_key=self.config.worker.openai_api_key,
                    )
                )
                lesson["timingVersion"] = 1
            else:
                word_timings: list[dict[str, Any]] = []
                asyncio.run(
                    self.audio_generator(
                        text=passage,
                        output_path=destination,
                        voice=voice,
                        word_timings=word_timings,
                        api_key=self.config.worker.openai_api_key,
                    )
                )
                lesson["timingVersion"] = 1
                lesson["wordTimings"] = word_timings
            failure_stage = "PERSISTENCE"
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
            failure_reason = f"{failure_stage}: {error}"[:4000]
            with self.session_factory() as session:
                record = session.get(TaskRecord if task else ContentRecord, record_uuid)
                if record:
                    record.status = "FAILED"
                    record.failure_reason = failure_reason
                    session.commit()
            if content:
                self._sync_topic_status(record_uuid, "FAILED", failure_reason)

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
            word_timings: list[dict[str, Any]] = []
            asyncio.run(
                self.audio_generator(
                    text=lesson_content["passage"],
                    output_path=destination,
                    voice=voice,
                    word_timings=word_timings,
                    api_key=self.config.worker.openai_api_key,
                )
            )
            lesson_content["timingVersion"] = 1
            lesson_content["wordTimings"] = word_timings
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
            content = (
                None
                if task
                else session.get(ContentRecord, answer.task_uuid)
            )
            question = self.speaking_question(
                task.questions if task else content.lesson_content if content else None
            )
            audio_path = self.answer_audio_dir / f"{answer_uuid}.m4a"
        try:
            assessment = self.assessor.assess(audio_path, question)
            with self.session_factory() as session:
                answer = session.get(SpeakingAnswerRecord, answer_uuid)
                answer.status = "COMPLETED"
                answer.transcript = assessment["transcript"]
                answer.score = int(assessment["score"])
                answer.feedback = str(assessment["feedback"])
                answer.evaluation_json = json.dumps(
                    assessment.get("evaluation") or {},
                    ensure_ascii=False,
                )
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
        if isinstance(questions, dict):
            prompts = questions.get("speakingPrompts") or []
            if prompts and isinstance(prompts[0], str) and prompts[0].strip():
                return prompts[0].strip()
            questions = questions.get("questions") or []
        for question in questions or []:
            if not isinstance(question, dict):
                continue
            if question.get("type", "").upper() == "SPEAKING":
                return question.get("question") or question.get("prompt") or "Answer clearly."
        return "Summarize the lesson in your own words."

    @staticmethod
    def iso(value: datetime | None) -> str | None:
        if not value:
            return None
        normalized = (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )
        return normalized.isoformat().replace("+00:00", "Z")

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
                    "estimatedMinutes": (
                        7 if long_metadata.get("format") == "DIALOGUE" else 10
                    ),
                    "format": long_metadata.get("format", "ARTICLE"),
                    "hostVoice": long_metadata.get("hostVoice"),
                    "expertVoice": long_metadata.get("expertVoice"),
                }
            )
        return result

    @classmethod
    def learning_progress_dict(
        cls,
        progress: LearningProgressRecord,
    ) -> dict[str, Any]:
        return {
            "clientId": progress.client_id,
            "contentUuid": progress.content_uuid,
            "positionMs": progress.position_ms,
            "durationMs": progress.duration_ms,
            "vocabularyDone": progress.vocabulary_done,
            "listeningDone": progress.listening_done,
            "readingDone": progress.reading_done,
            "quizCorrect": progress.quiz_correct,
            "quizTotal": progress.quiz_total,
            "speakingScore": progress.speaking_score,
            "completed": progress.completed,
            "updatedAt": cls.iso(progress.updated_at),
        }

    @classmethod
    def vocabulary_progress_dict(
        cls,
        vocabulary: VocabularyProgressRecord,
    ) -> dict[str, Any]:
        return {
            "clientId": vocabulary.client_id,
            "contentUuid": vocabulary.content_uuid,
            "word": vocabulary.word,
            "status": vocabulary.status,
            "updatedAt": cls.iso(vocabulary.updated_at),
        }

    @classmethod
    def answer_dict(cls, answer: SpeakingAnswerRecord) -> dict[str, Any]:
        evaluation = None
        if answer.evaluation_json:
            try:
                evaluation = json.loads(answer.evaluation_json)
            except (TypeError, json.JSONDecodeError):
                evaluation = None
        return {
            "answerUuid": answer.answer_uuid,
            "taskUuid": answer.task_uuid,
            "status": answer.status,
            "audioUrl": answer.audio_url,
            "transcript": answer.transcript,
            "score": answer.score,
            "feedback": answer.feedback,
            "evaluation": evaluation,
            "failureReason": answer.failure_reason,
        }

    @classmethod
    def daily_dict(
        cls, plan: DailyPlanRecord, content: ContentRecord
    ) -> dict[str, Any]:
        long_metadata = cls._long_lesson_metadata(content.source_text) or {}
        return {
            "planDate": plan.plan_date.isoformat(),
            "contentUuid": plan.content_uuid,
            "createdAt": cls.iso(plan.created_at),
            "estimatedMinutes": (
                7
                if long_metadata.get("format") == "DIALOGUE"
                else 10
            ),
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

    def lookup_vocabulary(
        self, word: str, context_sentence: str | None = None
    ) -> dict[str, Any]:
        clean_word = re.sub(r"[^\w'-]", "", word.strip())
        if not clean_word:
            raise ValueError("Word cannot be empty")

        prompt = (
            f"Define this English word for a software engineer:\nWord: {clean_word}\n"
            f"Context sentence: {context_sentence or 'None'}\n\n"
            "Return JSON only with fields:\n"
            "- word (string)\n"
            "- phoneticUs (string, e.g. /.../)\n"
            "- phoneticUk (string, e.g. /.../)\n"
            "- definitionCn (concise Chinese definition)\n"
            "- definitionEn (concise English definition)\n"
            "- collocations (array of 2-4 strings)\n"
            "- contextExplanation (string, how it applies to the sentence)"
        )
        try:
            if hasattr(self.generator, "generate_json"):
                data = self.generator.generate_json(prompt, max_tokens=300, max_retries=1)
            else:
                raw = self.generator.generate(prompt)
                data = json.loads(raw)
            return {
                "word": data.get("word", clean_word),
                "phoneticUs": data.get("phoneticUs", ""),
                "phoneticUk": data.get("phoneticUk", ""),
                "definitionCn": data.get("definitionCn", "暂无释义"),
                "definitionEn": data.get("definitionEn", ""),
                "collocations": data.get("collocations", []),
                "contextExplanation": data.get("contextExplanation", ""),
            }
        except Exception as err:
            LOGGER.warning("Vocabulary lookup failed for %s: %s", clean_word, err)
            return {
                "word": clean_word,
                "phoneticUs": "",
                "phoneticUk": "",
                "definitionCn": "释义获取中",
                "definitionEn": "",
                "collocations": [],
                "contextExplanation": "",
            }

    def save_user_vocabulary(
        self,
        client_id: str,
        word: str,
        definition_cn: str,
        definition_en: str | None = None,
        phonetic_us: str | None = None,
        phonetic_uk: str | None = None,
        context_sentence: str | None = None,
        content_uuid: str | None = None,
        sentence_start_ms: int | None = None,
        sentence_end_ms: int | None = None,
    ) -> dict[str, Any]:
        normalized = word.strip().casefold()
        with self.session_factory() as session:
            existing = session.scalar(
                select(UserVocabularyCardRecord).where(
                    UserVocabularyCardRecord.client_id == client_id,
                    UserVocabularyCardRecord.normalized_word == normalized,
                )
            )
            if existing:
                existing.definition_cn = definition_cn
                if definition_en:
                    existing.definition_en = definition_en
                if phonetic_us:
                    existing.phonetic_us = phonetic_us
                if phonetic_uk:
                    existing.phonetic_uk = phonetic_uk
                if context_sentence:
                    existing.context_sentence = context_sentence
                if content_uuid:
                    existing.content_uuid = content_uuid
                existing.updated_at = utc_now()
                session.commit()
                record = existing
            else:
                record = UserVocabularyCardRecord(
                    client_id=client_id,
                    word=word.strip(),
                    normalized_word=normalized,
                    phonetic_us=phonetic_us,
                    phonetic_uk=phonetic_uk,
                    definition_cn=definition_cn,
                    definition_en=definition_en,
                    context_sentence=context_sentence,
                    content_uuid=content_uuid,
                    sentence_start_ms=sentence_start_ms,
                    sentence_end_ms=sentence_end_ms,
                    fsrs_state="NEW",
                    stability=0.0,
                    difficulty=0.0,
                    reps=0,
                    lapses=0,
                    due_time=utc_now(),
                )
                session.add(record)
                session.commit()

            return {
                "id": record.id,
                "clientId": record.client_id,
                "word": record.word,
                "phoneticUs": record.phonetic_us,
                "phoneticUk": record.phonetic_uk,
                "definitionCn": record.definition_cn,
                "definitionEn": record.definition_en,
                "contextSentence": record.context_sentence,
                "contentUuid": record.content_uuid,
                "fsrsState": record.fsrs_state,
                "dueTime": record.due_time.isoformat(),
                "reps": record.reps,
            }

    def get_user_vocabulary(
        self, client_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            records = session.scalars(
                select(UserVocabularyCardRecord)
                .where(UserVocabularyCardRecord.client_id == client_id)
                .order_by(UserVocabularyCardRecord.updated_at.desc())
                .limit(limit)
            ).all()
            return [
                {
                    "id": r.id,
                    "clientId": r.client_id,
                    "word": r.word,
                    "phoneticUs": r.phonetic_us,
                    "phoneticUk": r.phonetic_uk,
                    "definitionCn": r.definition_cn,
                    "definitionEn": r.definition_en,
                    "contextSentence": r.context_sentence,
                    "contentUuid": r.content_uuid,
                    "sentenceStartMs": r.sentence_start_ms,
                    "sentenceEndMs": r.sentence_end_ms,
                    "fsrsState": r.fsrs_state,
                    "dueTime": r.due_time.isoformat(),
                    "reps": r.reps,
                }
                for r in records
            ]

    async def create_speaking_session(
        self,
        client_id: str,
        content_uuid: str,
        scenario: str = "SYSTEM_DESIGN_INTERVIEW",
        role: str = "TECH_LEAD",
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            content = session.get(ContentRecord, content_uuid)
            topic_title = content.title if content else "Technical Discussion"

            session_id = f"spk_{uuid_module.uuid4().hex[:12]}"
            ai_text = (
                f"Hi there! Let's discuss {topic_title}. "
                "Could you briefly introduce your approach to handling this in production?"
            )

            audio_filename = f"{session_id}_turn1_ai.mp3"
            output_path = self.speaking_session_audio_dir / audio_filename
            try:
                await self.audio_generator(ai_text, output_path, voice="en-US-AndrewNeural")
                ai_audio_url = f"/api/v1/audio/speaking-sessions/{audio_filename}"
            except Exception as err:
                LOGGER.error("Could not synthesize AI audio for speaking session: %s", err)
                raise RuntimeError(
                    f"Could not synthesize AI audio for speaking session: {err}"
                ) from err

            session_record = SpeakingSessionRecord(
                session_id=session_id,
                client_id=client_id,
                content_uuid=content_uuid,
                scenario=scenario,
                role=role,
                status="IN_PROGRESS",
                current_turn=1,
                total_turns=3,
                topic=topic_title,
            )
            session.add(session_record)

            turn_record = SpeakingSessionTurnRecord(
                session_id=session_id,
                turn_index=1,
                ai_prompt_text=ai_text,
                ai_audio_url=ai_audio_url,
                evaluation_status="PENDING",
            )
            session.add(turn_record)
            session.commit()

            return {
                "sessionId": session_id,
                "turnIndex": 1,
                "totalTurns": 3,
                "scenario": scenario,
                "role": role,
                "aiPromptText": ai_text,
                "aiAudioUrl": ai_audio_url,
            }

    async def submit_speaking_session_turn(
        self,
        session_id: str,
        turn_index: int,
        audio_bytes: bytes,
        audio_filename: str,
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            sess_rec = session.get(SpeakingSessionRecord, session_id)
            if not sess_rec:
                raise ValueError(f"Speaking session {session_id} not found")

            if sess_rec.status in ("COMPLETED", "FAILED"):
                raise ValueError(
                    f"Speaking session {session_id} is already {sess_rec.status}"
                )

            turn_rec = session.scalar(
                select(SpeakingSessionTurnRecord).where(
                    SpeakingSessionTurnRecord.session_id == session_id,
                    SpeakingSessionTurnRecord.turn_index == turn_index,
                )
            )
            if not turn_rec:
                raise ValueError(f"Turn {turn_index} of session {session_id} not found")

            if turn_index > sess_rec.current_turn:
                raise ValueError(
                    f"Out of order turn: expected turn {sess_rec.current_turn}, got {turn_index}"
                )

            if turn_index < sess_rec.current_turn:
                if turn_rec.user_audio_url:
                    is_fin = turn_index >= sess_rec.total_turns
                    next_turn_rec = session.scalar(
                        select(SpeakingSessionTurnRecord).where(
                            SpeakingSessionTurnRecord.session_id == session_id,
                            SpeakingSessionTurnRecord.turn_index == turn_index + 1,
                        )
                    )
                    next_turn_dict = (
                        {
                            "turnIndex": next_turn_rec.turn_index,
                            "aiPromptText": next_turn_rec.ai_prompt_text,
                            "aiAudioUrl": next_turn_rec.ai_audio_url,
                        }
                        if next_turn_rec
                        else None
                    )
                    return {
                        "sessionId": session_id,
                        "turnIndex": turn_index,
                        "evaluationStatus": turn_rec.evaluation_status,
                        "userTranscript": turn_rec.user_transcript,
                        "pronunciationScore": turn_rec.pronunciation_score,
                        "grammarScore": turn_rec.grammar_score,
                        "quickFeedback": turn_rec.quick_feedback,
                        "isFinished": is_fin,
                        "nextTurn": next_turn_dict,
                    }

            # Save user audio
            save_name = f"{session_id}_turn{turn_index}_user.m4a"
            dest_path = self.speaking_session_audio_dir / save_name
            dest_path.write_bytes(audio_bytes)
            user_audio_url = f"/api/v1/audio/speaking-sessions/{save_name}"

            user_transcript = None
            score_p = None
            score_g = None
            feedback = None
            eval_status = "PENDING"
            eval_error = None

            if self.assessor:
                try:
                    user_transcript = self.assessor.transcribe(dest_path)
                    scoring = self.assessor.score(user_transcript, turn_rec.ai_prompt_text)
                    score_p = scoring.get("score")
                    score_g = scoring.get("grammar_score", scoring.get("score"))
                    feedback = scoring.get("feedback")
                    eval_status = "COMPLETED"
                except Exception as err:
                    LOGGER.warning("Assessor evaluation error: %s", err)
                    eval_status = "FAILED"
                    eval_error = "ASSESSMENT_FAILED"
                    user_transcript = None
                    score_p = None
                    score_g = None
                    feedback = None
            else:
                eval_status = "NO_DATA"

            turn_rec.user_audio_url = user_audio_url
            turn_rec.user_transcript = user_transcript
            turn_rec.pronunciation_score = score_p
            turn_rec.grammar_score = score_g
            turn_rec.quick_feedback = feedback
            turn_rec.evaluation_status = eval_status
            turn_rec.evaluation_error = eval_error

            is_finished = turn_index >= sess_rec.total_turns
            next_turn_data = None

            if not is_finished:
                next_index = turn_index + 1
                sess_rec.current_turn = next_index

                ai_next_text = (
                    "That makes sense. "
                    "How would you monitor database query latencies in high-concurrency traffic?"
                )
                audio_name = f"{session_id}_turn{next_index}_ai.mp3"
                next_out = self.speaking_session_audio_dir / audio_name
                try:
                    await self.audio_generator(
                        ai_next_text, next_out, voice="en-US-AndrewNeural"
                    )
                    ai_audio_url = f"/api/v1/audio/speaking-sessions/{audio_name}"
                except Exception as err:
                    LOGGER.error("Could not synthesize next turn audio: %s", err)
                    sess_rec.status = "FAILED"
                    session.commit()
                    raise RuntimeError(
                        f"Could not synthesize next turn audio: {err}"
                    ) from err

                next_turn_rec = SpeakingSessionTurnRecord(
                    session_id=session_id,
                    turn_index=next_index,
                    ai_prompt_text=ai_next_text,
                    ai_audio_url=ai_audio_url,
                    evaluation_status="PENDING",
                )
                session.add(next_turn_rec)
                next_turn_data = {
                    "turnIndex": next_index,
                    "aiPromptText": ai_next_text,
                    "aiAudioUrl": ai_audio_url,
                }
            else:
                sess_rec.status = "COMPLETED"
                all_turns = session.scalars(
                    select(SpeakingSessionTurnRecord).where(
                        SpeakingSessionTurnRecord.session_id == session_id
                    )
                ).all()
                scored_turns = [
                    t
                    for t in all_turns
                    if t.pronunciation_score is not None and t.grammar_score is not None
                ]
                if scored_turns:
                    avg_p = sum(t.pronunciation_score for t in scored_turns) // len(
                        scored_turns
                    )
                    avg_g = sum(t.grammar_score for t in scored_turns) // len(
                        scored_turns
                    )
                    overall = (avg_p + avg_g) // 2
                else:
                    avg_p, avg_g, overall = None, None, None
                sess_rec.final_report_json = json.dumps(
                    {
                        "overallScore": overall,
                        "fluency": avg_p,
                        "accuracy": avg_g,
                        "summary": "Completed all rounds of interactive dialogue.",
                        "evaluatedTurns": len(scored_turns),
                    }
                )

            session.commit()

            return {
                "sessionId": session_id,
                "turnIndex": turn_index,
                "evaluationStatus": eval_status,
                "userTranscript": user_transcript,
                "pronunciationScore": score_p,
                "grammarScore": score_g,
                "quickFeedback": feedback,
                "isFinished": is_finished,
                "nextTurn": next_turn_data,
            }

    def get_speaking_session(self, session_id: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            sess = session.get(SpeakingSessionRecord, session_id)
            if not sess:
                return None
            turns = session.scalars(
                select(SpeakingSessionTurnRecord)
                .where(SpeakingSessionTurnRecord.session_id == session_id)
                .order_by(SpeakingSessionTurnRecord.turn_index.asc())
            ).all()
            return {
                "sessionId": sess.session_id,
                "clientId": sess.client_id,
                "contentUuid": sess.content_uuid,
                "scenario": sess.scenario,
                "role": sess.role,
                "status": sess.status,
                "currentTurn": sess.current_turn,
                "totalTurns": sess.total_turns,
                "topic": sess.topic,
                "finalReport": json.loads(sess.final_report_json)
                if sess.final_report_json
                else None,
                "turns": [
                    {
                        "turnIndex": t.turn_index,
                        "aiPromptText": t.ai_prompt_text,
                        "aiAudioUrl": t.ai_audio_url,
                        "userAudioUrl": t.user_audio_url,
                        "userTranscript": t.user_transcript,
                        "pronunciationScore": t.pronunciation_score,
                        "grammarScore": t.grammar_score,
                        "quickFeedback": t.quick_feedback,
                        "evaluationStatus": t.evaluation_status,
                        "evaluationError": t.evaluation_error,
                    }
                    for t in turns
                ],
            }


class TargetWordCoverageError(ValueError):
    def __init__(self, missing: list[str]):
        super().__init__(f"Missing target words after repair: {', '.join(missing)}")
        self.missing = missing
