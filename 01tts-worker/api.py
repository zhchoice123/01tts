import json
import logging
import re
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

import redis
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from src.backend_config import BackendConfig, load_backend_config
from src.backend_models import create_session_factory
from src.backend_service import BackendService

LOGGER = logging.getLogger("tts-python-api")
UUID_FILE_PATTERN = re.compile(r"^[0-9a-fA-F-]{36}\.(?:mp3|m4a)$")
APK_FILE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.apk$")


class CreateTaskRequest(BaseModel):
    prompt: str = Field(min_length=1)
    voice: str = "en-US-AvaNeural"
    difficulty: str = "medium"


class ImportContentRequest(BaseModel):
    sourceType: str = "TEXT"
    sourceUrl: str = ""
    text: str = ""
    title: str = ""
    level: str = "B1"


class CreateLongLessonRequest(BaseModel):
    topic: str = Field(default="", max_length=500)
    category: str = Field(default="BACKEND", min_length=1, max_length=80)
    voice: str = Field(default="en-US-AvaNeural", min_length=1, max_length=80)
    level: str = Field(default="B1", max_length=10)
    sourceMode: str = Field(default="AUTO", max_length=16)


class CreateDialogueLessonRequest(BaseModel):
    topic: str = Field(default="", max_length=500)
    category: str = Field(default="BACKEND", min_length=1, max_length=80)
    hostVoice: str = Field(
        default="en-US-AvaNeural",
        min_length=1,
        max_length=80,
    )
    expertVoice: str = Field(
        default="en-US-AndrewNeural",
        min_length=1,
        max_length=80,
    )
    level: str = Field(default="B1", max_length=10)
    sourceMode: str = Field(default="AUTO", max_length=16)


class CreateAttemptRequest(BaseModel):
    answersJson: str = Field(min_length=1)
    correctCount: int | None = None


class CompleteAnswerRequest(BaseModel):
    transcript: str
    score: int = Field(ge=0, le=100)
    feedback: str


class LearningProgressRequest(BaseModel):
    clientId: UUID
    contentUuid: UUID
    positionMs: int = Field(ge=0, le=86_400_000)
    durationMs: int = Field(ge=0, le=86_400_000)
    vocabularyDone: bool = False
    listeningDone: bool = False
    readingDone: bool = False
    quizCorrect: int = Field(default=0, ge=0, le=1000)
    quizTotal: int = Field(default=0, ge=0, le=1000)
    speakingScore: int | None = Field(default=None, ge=0, le=100)
    completed: bool = False

    @model_validator(mode="after")
    def validate_progress(self):
        if self.positionMs > self.durationMs:
            raise ValueError("positionMs must not exceed durationMs")
        if self.quizCorrect > self.quizTotal:
            raise ValueError("quizCorrect must not exceed quizTotal")
        return self


class VocabularyProgressRequest(BaseModel):
    clientId: UUID
    contentUuid: UUID
    word: str = Field(min_length=1, max_length=120)
    status: Literal["NEW", "LEARNING", "KNOWN"]

    @field_validator("word")
    @classmethod
    def validate_word(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("word must not be blank")
        return normalized


class AnkiReviewWordRequest(BaseModel):
    clientWordKey: str = Field(min_length=1, max_length=64)
    word: str = Field(min_length=1, max_length=120)
    meaning: str = Field(default="", max_length=500)
    example: str = Field(default="", max_length=500)
    usageNotes: str = Field(default="", max_length=500)


class CreateAnkiReviewLessonRequest(BaseModel):
    clientDate: date
    timezone: str = "Asia/Shanghai"
    deckAlias: str = Field(min_length=1, max_length=255)
    level: str = Field(default="B1", max_length=32)
    voice: str = Field(default="en-US-AvaNeural", max_length=80)
    topicMode: str = Field(default="DAILY_RECOMMENDED", max_length=32)
    topicId: str | None = Field(default=None, max_length=36)
    words: list[AnkiReviewWordRequest] = Field(min_length=1, max_length=30)


class AppReleaseManifest(BaseModel):
    versionCode: int = Field(ge=1)
    versionName: str = Field(min_length=1, max_length=40)
    minimumVersionCode: int = Field(default=1, ge=1)
    mandatory: bool = False
    title: str = Field(default="Listening Lab update", min_length=1, max_length=100)
    changelog: list[str] = Field(default_factory=list, max_length=20)
    apkUrl: str = Field(min_length=1, max_length=500)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    sizeBytes: int = Field(gt=0)
    publishedAt: str = Field(min_length=1, max_length=80)


def build_service(config: BackendConfig) -> BackendService:
    engine, session_factory = create_session_factory(config.database_url)
    redis_options = {"password": config.redis_password} if config.redis_password else {}
    queue = redis.Redis.from_url(
        config.redis_url,
        protocol=2,
        socket_connect_timeout=3,
        socket_timeout=15,
        health_check_interval=30,
        **redis_options,
    )
    return BackendService(config, engine, session_factory, queue)


def create_app(
    config: BackendConfig | None = None,
    service: BackendService | None = None,
    start_background: bool = True,
) -> FastAPI:
    resolved_config = config or load_backend_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        backend = service or build_service(resolved_config)
        backend.initialize()
        backend.redis.ping()
        app.state.backend = backend
        scheduler: BackgroundScheduler | None = None
        if start_background:
            backend.start_consumers()
            scheduler = BackgroundScheduler(timezone=resolved_config.timezone)
            scheduler.add_job(
                backend.run_daily_generation,
                "cron",
                hour=resolved_config.daily_hour,
                minute=resolved_config.daily_minute,
                id="daily-plan",
                replace_existing=True,
            )
            scheduler.add_job(
                backend.ensure_daily_generation,
                "date",
                id="daily-plan-startup-compensation",
                replace_existing=True,
            )
            scheduler.start()
            LOGGER.info(
                "Daily plan scheduled at %02d:%02d %s",
                resolved_config.daily_hour,
                resolved_config.daily_minute,
                resolved_config.timezone,
            )
        try:
            yield
        finally:
            if scheduler:
                scheduler.shutdown(wait=False)
            backend.stop_consumers()
            backend.engine.dispose()

    app = FastAPI(
        title="Listening Lab Python API",
        version="1.0.0",
        lifespan=lifespan,
    )

    def backend(request: Request) -> BackendService:
        return request.app.state.backend

    @app.get("/health")
    def health(request: Request) -> dict[str, str]:
        current = backend(request)
        current.redis.ping()
        with current.session_factory() as session:
            session.connection()
        return {"status": "UP", "service": "01tts-python-api"}

    @app.post("/api/v1/tasks", status_code=200)
    def create_task(payload: CreateTaskRequest, request: Request) -> dict[str, Any]:
        return backend(request).create_task(
            payload.prompt, payload.voice, payload.difficulty
        )

    @app.get("/api/v1/tasks/{task_uuid}")
    def get_task(task_uuid: str, request: Request) -> dict[str, Any]:
        task = backend(request).get_task(task_uuid)
        if not task:
            raise HTTPException(404, f"task {task_uuid} not found")
        return task

    @app.post("/api/v1/content/import")
    def import_content(
        payload: ImportContentRequest, request: Request
    ) -> dict[str, Any]:
        try:
            return backend(request).create_content(
                payload.sourceType,
                payload.sourceUrl,
                payload.text,
                payload.title,
                payload.level,
            )
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.get("/api/v1/content/{content_uuid}")
    def get_content(content_uuid: str, request: Request) -> dict[str, Any]:
        content = backend(request).get_content(content_uuid)
        if not content:
            raise HTTPException(404, f"content {content_uuid} not found")
        return content

    @app.post("/api/v1/content/{content_uuid}/complete")
    async def legacy_complete_content(
        content_uuid: str,
        request: Request,
        audio: Annotated[UploadFile, File()],
        lessonContent: Annotated[str, Form()],
    ) -> dict[str, Any]:
        current = backend(request)
        content = current.get_content(content_uuid)
        if not content:
            raise HTTPException(404, f"content {content_uuid} not found")
        destination = current.content_audio_dir / f"{content_uuid}.mp3"
        with destination.open("wb") as output:
            shutil.copyfileobj(audio.file, output)
        await audio.close()
        with current.session_factory() as session:
            from src.backend_models import ContentRecord

            record = session.get(ContentRecord, content_uuid)
            record.status = "READY"
            record.audio_url = f"/api/v1/audio/content/{content_uuid}.mp3"
            record.lesson_content = lessonContent
            record.failure_reason = None
            session.commit()
            return current.content_dict(record)

    @app.post("/api/v1/content/{content_uuid}/fail")
    def legacy_fail_content(
        content_uuid: str,
        request: Request,
        reason: Annotated[str, Form()] = "Content generation failed",
    ) -> dict[str, Any]:
        current = backend(request)
        with current.session_factory() as session:
            from src.backend_models import ContentRecord

            record = session.get(ContentRecord, content_uuid)
            if not record:
                raise HTTPException(404, f"content {content_uuid} not found")
            record.status = "FAILED"
            record.failure_reason = reason
            session.commit()
            return current.content_dict(record)

    @app.get("/api/v1/library")
    def library(request: Request) -> list[dict[str, Any]]:
        return backend(request).library()

    @app.put("/api/v1/learning/progress")
    def put_learning_progress(
        payload: LearningProgressRequest,
        request: Request,
    ) -> dict[str, Any]:
        return backend(request).upsert_learning_progress(
            client_id=str(payload.clientId),
            content_uuid=str(payload.contentUuid),
            position_ms=payload.positionMs,
            duration_ms=payload.durationMs,
            vocabulary_done=payload.vocabularyDone,
            listening_done=payload.listeningDone,
            reading_done=payload.readingDone,
            quiz_correct=payload.quizCorrect,
            quiz_total=payload.quizTotal,
            speaking_score=payload.speakingScore,
            completed=payload.completed,
        )

    @app.get("/api/v1/learning/progress/{client_id}/{content_uuid}")
    def get_learning_progress(
        client_id: UUID,
        content_uuid: UUID,
        request: Request,
    ) -> dict[str, Any]:
        progress = backend(request).get_learning_progress(
            str(client_id),
            str(content_uuid),
        )
        if not progress:
            raise HTTPException(404, "learning progress not found")
        return progress

    @app.get("/api/v1/learning/dashboard/{client_id}")
    def get_learning_dashboard(
        client_id: UUID,
        request: Request,
        days: Annotated[int, Query(ge=1, le=90)] = 7,
    ) -> dict[str, Any]:
        return backend(request).learning_dashboard(str(client_id), days)

    @app.get("/api/v1/learning/reports/{client_id}/{content_uuid}")
    def get_lesson_review_report(
        client_id: UUID,
        content_uuid: UUID,
        request: Request,
    ) -> dict[str, Any]:
        report = backend(request).lesson_review_report(
            str(client_id),
            str(content_uuid),
        )
        if not report:
            raise HTTPException(404, "learning progress not found")
        return report

    @app.get("/api/v1/learning/review-queue/{client_id}")
    def get_learning_review_queue(
        client_id: UUID,
        request: Request,
        review_date: Annotated[date, Query(alias="date")],
        limit: Annotated[int, Query(ge=1, le=50)] = 10,
    ) -> dict[str, Any]:
        return backend(request).learning_review_queue(
            str(client_id),
            review_date,
            limit,
        )

    @app.put("/api/v1/learning/vocabulary")
    def put_vocabulary_progress(
        payload: VocabularyProgressRequest,
        request: Request,
    ) -> dict[str, Any]:
        return backend(request).upsert_vocabulary_progress(
            client_id=str(payload.clientId),
            content_uuid=str(payload.contentUuid),
            word=payload.word,
            status=payload.status,
        )

    @app.get("/api/v1/learning/vocabulary/{client_id}")
    def get_vocabulary_progress(
        client_id: UUID,
        request: Request,
        status: Literal["NEW", "LEARNING", "KNOWN"] | None = None,
    ) -> list[dict[str, Any]]:
        return backend(request).list_vocabulary_progress(
            str(client_id),
            status,
        )

    @app.post("/api/v1/long-lessons", status_code=202)
    def create_long_lesson(
        payload: CreateLongLessonRequest,
        request: Request,
    ) -> dict[str, Any]:
        try:
            return backend(request).create_long_lesson(
                topic=payload.topic,
                category=payload.category,
                voice=payload.voice,
                level=payload.level,
                source_mode=payload.sourceMode,
            )
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.post("/api/v1/dialogue-lessons", status_code=202)
    def create_dialogue_lesson(
        payload: CreateDialogueLessonRequest,
        request: Request,
    ) -> dict[str, Any]:
        try:
            return backend(request).create_dialogue_lesson(
                topic=payload.topic,
                category=payload.category,
                host_voice=payload.hostVoice,
                expert_voice=payload.expertVoice,
                level=payload.level,
                source_mode=payload.sourceMode,
            )
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.post("/api/v1/anki/review-lessons", status_code=202)
    def create_anki_review_lesson(
        payload: CreateAnkiReviewLessonRequest,
        request: Request,
    ) -> dict[str, Any]:
        try:
            return backend(request).create_anki_review_lesson(
                client_date=payload.clientDate,
                deck_alias=payload.deckAlias,
                level=payload.level,
                voice=payload.voice,
                topic_mode=payload.topicMode,
                topic_uuid=payload.topicId,
                words=[word.model_dump() for word in payload.words],
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @app.get("/api/v1/anki/review-lessons")
    def list_anki_review_lessons(
        clientDate: date,
        request: Request,
    ) -> list[dict[str, Any]]:
        return backend(request).list_anki_review_lessons(clientDate)

    @app.get("/api/v1/anki/review-lessons/{lesson_uuid}")
    def get_anki_review_lesson(
        lesson_uuid: str,
        request: Request,
    ) -> dict[str, Any]:
        lesson = backend(request).get_anki_review_lesson(lesson_uuid)
        if not lesson:
            raise HTTPException(404, f"Anki review lesson {lesson_uuid} not found")
        return lesson

    @app.post("/api/v1/content/{content_uuid}/attempts")
    def create_attempt(
        content_uuid: str,
        payload: CreateAttemptRequest,
        request: Request,
    ) -> dict[str, Any]:
        attempt = backend(request).create_attempt(
            content_uuid, payload.answersJson, payload.correctCount
        )
        if not attempt:
            raise HTTPException(404, f"content {content_uuid} not found")
        return attempt

    @app.get("/api/v1/daily-plans/today")
    def today(request: Request) -> dict[str, Any]:
        return backend(request).today()

    @app.get("/api/v1/daily-plans/{plan_date}")
    def get_daily_plan(plan_date: date, request: Request) -> dict[str, Any]:
        plan = backend(request).get_daily_plan(plan_date)
        if not plan:
            raise HTTPException(404, f"daily plan {plan_date} not found")
        return plan

    @app.post("/api/v1/daily-plans/{plan_date}/generate")
    def generate_daily_plan(plan_date: date, request: Request) -> dict[str, Any]:
        return backend(request).generate_daily_plan(plan_date)

    @app.get("/api/v1/topics/recommendations")
    def topic_recommendations(
        request: Request,
        planDate: date | None = None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 10:
            raise HTTPException(422, "limit must be between 1 and 10")
        resolved = planDate or backend(request).local_today()
        return backend(request).topic_candidates(resolved)[:limit]

    @app.post("/api/v1/daily-generation/{plan_date}")
    def run_daily_generation(plan_date: date, request: Request) -> dict[str, Any]:
        return backend(request).run_daily_generation(plan_date)

    @app.post("/api/v1/topics/{topic_uuid}/lessons")
    def topic_lesson(topic_uuid: str, request: Request) -> dict[str, Any]:
        lesson = backend(request).topic_lesson(topic_uuid)
        if not lesson:
            raise HTTPException(404, f"topic {topic_uuid} not found")
        return lesson

    @app.post("/api/v1/tasks/{task_uuid}/answers")
    async def upload_answer(
        task_uuid: str,
        request: Request,
        audio: Annotated[UploadFile, File()],
    ) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as temporary:
            temporary_path = Path(temporary.name)
            shutil.copyfileobj(audio.file, temporary)
        try:
            answer = backend(request).create_answer(task_uuid, temporary_path)
        finally:
            temporary_path.unlink(missing_ok=True)
            await audio.close()
        if not answer:
            raise HTTPException(404, f"task {task_uuid} not found")
        return answer

    @app.get("/api/v1/answers/{answer_uuid}")
    def get_answer(answer_uuid: str, request: Request) -> dict[str, Any]:
        answer = backend(request).get_answer(answer_uuid)
        if not answer:
            raise HTTPException(404, f"answer {answer_uuid} not found")
        return answer

    @app.post("/api/v1/answers/{answer_uuid}/complete")
    def legacy_complete_answer(
        answer_uuid: str,
        payload: CompleteAnswerRequest,
        request: Request,
    ) -> dict[str, Any]:
        current = backend(request)
        with current.session_factory() as session:
            from src.backend_models import SpeakingAnswerRecord

            record = session.get(SpeakingAnswerRecord, answer_uuid)
            if not record:
                raise HTTPException(404, f"answer {answer_uuid} not found")
            record.status = "COMPLETED"
            record.transcript = payload.transcript
            record.score = payload.score
            record.feedback = payload.feedback
            record.failure_reason = None
            session.commit()
            return current.answer_dict(record)

    @app.post("/api/v1/tasks/{task_uuid}/complete")
    async def legacy_complete_task(
        task_uuid: str,
        request: Request,
        audio: Annotated[UploadFile, File()],
        questions: Annotated[str, Form()],
    ) -> dict[str, Any]:
        current = backend(request)
        task = current.get_task(task_uuid)
        if not task:
            raise HTTPException(404, f"task {task_uuid} not found")
        destination = current.task_audio_dir / f"{task_uuid}.mp3"
        with destination.open("wb") as output:
            shutil.copyfileobj(audio.file, output)
        await audio.close()
        with current.session_factory() as session:
            from src.backend_models import TaskRecord

            record = session.get(TaskRecord, task_uuid)
            record.status = "COMPLETED"
            record.audio_url = f"/audio/{task_uuid}.mp3"
            record.questions = questions
            session.commit()
            return current.task_dict(record)

    @app.post("/api/v1/tasks/{task_uuid}/fail")
    def legacy_fail_task(
        task_uuid: str,
        request: Request,
        reason: Annotated[str, Form()] = "Task execution failed",
    ) -> dict[str, Any]:
        current = backend(request)
        with current.session_factory() as session:
            from src.backend_models import TaskRecord

            record = session.get(TaskRecord, task_uuid)
            if not record:
                raise HTTPException(404, f"task {task_uuid} not found")
            record.status = "FAILED"
            record.failure_reason = reason
            session.commit()
            return current.task_dict(record)

    @app.get("/audio/{file_name}")
    def task_audio(file_name: str, request: Request):
        return audio_response(backend(request).task_audio_dir, file_name, "audio/mpeg")

    @app.get("/audio/answers/{file_name}")
    def answer_audio(file_name: str, request: Request):
        return audio_response(backend(request).answer_audio_dir, file_name, "audio/mp4")

    @app.get("/api/v1/audio/content/{file_name}")
    def content_audio(file_name: str, request: Request):
        return audio_response(backend(request).content_audio_dir, file_name, "audio/mpeg")

    @app.get("/api/v1/app/releases/latest")
    def latest_app_release(request: Request) -> dict[str, Any]:
        manifest_path = backend(request).app_release_dir / "latest.json"
        if not manifest_path.is_file():
            raise HTTPException(404, "no app release has been published")
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = AppReleaseManifest.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            LOGGER.error("Invalid app release manifest: %s", error)
            raise HTTPException(503, "app release manifest is invalid") from error
        expected_name = manifest.apkUrl.rsplit("/", 1)[-1]
        if not APK_FILE_PATTERN.fullmatch(expected_name):
            raise HTTPException(503, "app release download path is invalid")
        if not (backend(request).app_release_dir / expected_name).is_file():
            raise HTTPException(503, "app release APK is missing")
        return manifest.model_dump()

    @app.get("/api/v1/app/releases/{file_name}")
    def download_app_release(file_name: str, request: Request) -> FileResponse:
        if not APK_FILE_PATTERN.fullmatch(file_name):
            raise HTTPException(400, "invalid APK file name")
        directory = backend(request).app_release_dir.resolve()
        path = (directory / file_name).resolve()
        if path.parent != directory or not path.is_file():
            raise HTTPException(404, f"APK {file_name} not found")
        return FileResponse(
            path,
            media_type="application/vnd.android.package-archive",
            filename=file_name,
            headers={"Cache-Control": "no-cache"},
        )

    return app


def audio_response(directory: Path, file_name: str, media_type: str) -> FileResponse:
    if not UUID_FILE_PATTERN.fullmatch(file_name):
        raise HTTPException(400, "invalid audio file name")
    path = (directory / file_name).resolve()
    if path.parent != directory.resolve() or not path.is_file():
        raise HTTPException(404, f"audio {file_name} not found")
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-cache"})


app = create_app()


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    uvicorn.run("api:app", host="0.0.0.0", port=8080, workers=1)
