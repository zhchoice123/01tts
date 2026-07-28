from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TaskRecord(Base):
    __tablename__ = "tts_tasks"

    task_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    voice: Mapped[str] = mapped_column(String(80), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    audio_url: Mapped[str | None] = mapped_column(String(255))
    questions: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ContentRecord(Base):
    __tablename__ = "learning_content"

    uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="GENERATING")
    audio_url: Mapped[str | None] = mapped_column(String(255))
    lesson_content: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DailyPlanRecord(Base):
    __tablename__ = "daily_plans"

    plan_date: Mapped[date] = mapped_column(Date, primary_key=True)
    content_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LearningAttemptRecord(Base):
    __tablename__ = "learning_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    answers_json: Mapped[str] = mapped_column(Text, nullable=False)
    correct_count: Mapped[int | None] = mapped_column(Integer)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LearningProgressRecord(Base):
    __tablename__ = "learning_progress"
    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "content_uuid",
            name="uq_learning_progress_client_content",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    content_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    position_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    vocabulary_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    listening_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reading_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quiz_correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quiz_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    speaking_score: Mapped[int | None] = mapped_column(Integer)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True
    )


class VocabularyProgressRecord(Base):
    __tablename__ = "vocabulary_progress"
    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "normalized_word",
            name="uq_vocabulary_progress_client_word",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    content_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    word: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_word: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NEW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True
    )


class SpeakingAnswerRecord(Base):
    __tablename__ = "speaking_answers"

    answer_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    audio_url: Mapped[str] = mapped_column(String(255), nullable=False)
    transcript: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int | None] = mapped_column(Integer)
    feedback: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AnkiReviewLessonRecord(Base):
    __tablename__ = "anki_review_lessons"

    uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    client_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    deck_alias: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    voice: Mapped[str] = mapped_column(String(80), nullable=False)
    topic_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    topic_uuid: Mapped[str | None] = mapped_column(String(36))
    request_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="GENERATING")
    lesson_content: Mapped[str | None] = mapped_column(Text)
    audio_url: Mapped[str | None] = mapped_column(String(255))
    target_word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    covered_word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AnkiReviewTargetRecord(Base):
    __tablename__ = "anki_review_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lesson_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    client_word_key: Mapped[str] = mapped_column(String(64), nullable=False)
    word: Mapped[str] = mapped_column(String(120), nullable=False)
    meaning: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    example: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    usage_notes: Mapped[str] = mapped_column(String(500), nullable=False, default="")


class TopicCandidateRecord(Base):
    __tablename__ = "topic_candidates"
    __table_args__ = (
        UniqueConstraint("plan_date", "source_hash", name="uq_topic_date_source"),
    )

    uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(160))
    source_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[str | None] = mapped_column(String(120))
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="GENERATING")
    content_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DailyGenerationRunRecord(Base):
    __tablename__ = "daily_generation_runs"

    plan_date: Mapped[date] = mapped_column(Date, primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="GENERATING")
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ready_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def create_session_factory(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
