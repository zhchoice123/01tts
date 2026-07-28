import logging
import re
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Any

import redis
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.backend_config import BackendConfig, load_backend_config
from src.backend_models import create_session_factory
from src.backend_service import BackendService

LOGGER = logging.getLogger("tts-python-api")
UUID_FILE_PATTERN = re.compile(r"^[0-9a-fA-F-]{36}\.(?:mp3|m4a)$")


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
