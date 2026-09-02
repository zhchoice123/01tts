import argparse
import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import redis
import requests

from src.config import WorkerConfig, load_config
from src.content_ingestion import ContentMetadata, fetch_content
from src.deepseek_service import DeepSeekService
from src.provider_router import ProviderRouter
from src.schema_validator import validate_and_repair_lesson_content
from src.speaking_service import SpeakingAssessmentService
from src.tts_service import generate_audio

LOGGER = logging.getLogger("tts-worker")


class TaskWorker:
    def __init__(self, queue: Any, generator: DeepSeekService, server_url: str, config: WorkerConfig | None = None):
        self.queue = queue
        self.generator = generator
        self.server_url = server_url.rstrip("/")
        self.config = config

    def run_once(self, timeout: int = 5) -> bool:
        item = self.queue.brpop(["queue:tts_tasks", "queue:content_tasks"], timeout=timeout)
        if not item:
            return False

        task_uuid = item[1].decode() if isinstance(item[1], bytes) else item[1]
        LOGGER.info("Received task %s from queue %s", task_uuid, item[0])

        try:
            task = requests.get(f"{self.server_url}/api/v1/tasks/{task_uuid}", timeout=20)
            if task.status_code == 404:
                task = requests.get(f"{self.server_url}/api/v1/content/{task_uuid}", timeout=20)
            task.raise_for_status()
            task_data = task.json()

            st = task_data.get("sourceType") or ("TEXT" if "prompt" in task_data else "URL")
            src_input = task_data.get("sourceUrl") or task_data.get("prompt") or task_data.get("url") or ""
            difficulty = task_data.get("difficulty") or task_data.get("level") or "medium"
            voice = task_data.get("voice") or "en-US-AvaNeural"

            LOGGER.info(
                "Fetched task %s: sourceType=%s difficulty=%s voice=%s",
                task_uuid,
                st,
                difficulty,
                voice,
            )

            news_src = self.config.news_sources if self.config else []
            ingested = fetch_content(source_type=st, source_input=src_input, news_sources=news_src)
            LOGGER.info(
                "Ingested content for task %s: title=%r passage_len=%d",
                task_uuid,
                ingested.title,
                len(ingested.passage),
            )

            prompt = (
                f"Difficulty: {difficulty}. Title: {ingested.title}. "
                f"SourceType: {ingested.source_type}. Text: {ingested.passage[:1500]}"
            )

            metadata = {
                "uuid": task_uuid,
                "title": ingested.title,
                "sourceType": ingested.source_type,
                "sourceUrl": ingested.source_url,
                "level": difficulty,
                "passage": ingested.passage,
            }

            lesson = self.generator.generate_lesson(prompt=prompt, metadata=metadata)
            lesson = validate_and_repair_lesson_content(lesson, metadata=metadata)

            passage_for_tts = lesson.get("passage") or lesson.get("simplifiedPassage") or ingested.passage
            questions_payload = json.dumps(lesson.get("questions", []))

            with tempfile.TemporaryDirectory() as directory:
                audio_path = Path(directory) / f"{task_uuid}.mp3"
                LOGGER.info("Starting TTS generation for task %s", task_uuid)
                asyncio.run(
                    generate_audio(
                        text=passage_for_tts,
                        output_path=audio_path,
                        voice=voice,
                    )
                )
                file_bytes = audio_path.stat().st_size if audio_path.exists() else 0
                LOGGER.info("Generated TTS audio for task %s: bytes=%d", task_uuid, file_bytes)

                LOGGER.info("Uploading result for task %s", task_uuid)
                with audio_path.open("rb") as audio:
                    result = requests.post(
                        f"{self.server_url}/api/v1/tasks/{task_uuid}/complete",
                        files={"audio": (audio_path.name, audio, "audio/mpeg")},
                        data={
                            "questions": questions_payload,
                            "lessonContent": json.dumps(lesson),
                        },
                        timeout=60,
                    )
                    if result.status_code == 404:
                        audio.seek(0)
                        result = requests.post(
                            f"{self.server_url}/api/v1/content/{task_uuid}/complete",
                            files={"audio": (audio_path.name, audio, "audio/mpeg")},
                            data={"lessonContent": json.dumps(lesson)},
                            timeout=60,
                        )
                    result.raise_for_status()
                    LOGGER.info("Server accepted result for task %s: HTTP %d", task_uuid, result.status_code)

            LOGGER.info("Successfully completed task %s", task_uuid)
            return True

        except Exception as exc:
            LOGGER.error("Failed executing task %s: %s. Notifying server failure endpoint...", task_uuid, exc)
            for endpoint in [f"/api/v1/tasks/{task_uuid}/fail", f"/api/v1/content/{task_uuid}/fail"]:
                try:
                    requests.post(f"{self.server_url}{endpoint}", data={"reason": str(exc)}, timeout=10)
                    break
                except Exception:
                    pass
            raise exc


class SpeakingAnswerWorker:
    def __init__(self, queue: Any, assessor: SpeakingAssessmentService, server_url: str):
        self.queue = queue
        self.assessor = assessor
        self.server_url = server_url.rstrip("/")

    def run_once(self, timeout: int = 5) -> bool:
        item = self.queue.brpop("queue:speaking_answers", timeout=timeout)
        if not item:
            return False
        answer_uuid = item[1].decode() if isinstance(item[1], bytes) else item[1]
        LOGGER.info("Received speaking answer %s", answer_uuid)
        answer_response = requests.get(f"{self.server_url}/api/v1/answers/{answer_uuid}", timeout=20)
        answer_response.raise_for_status()
        answer = answer_response.json()

        task_response = requests.get(f"{self.server_url}/api/v1/tasks/{answer['taskUuid']}", timeout=20)
        task_response.raise_for_status()
        task = task_response.json()
        question = self._speaking_question(task.get("questions"))

        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / f"{answer_uuid}.m4a"
            LOGGER.info("Downloading recording for speaking answer %s", answer_uuid)
            audio_response = requests.get(f"{self.server_url}{answer['audioUrl']}", timeout=60)
            audio_response.raise_for_status()
            audio_path.write_bytes(audio_response.content)

            LOGGER.info("Starting transcription and scoring for answer %s", answer_uuid)
            assessment = self.assessor.assess(audio_path, question)
            LOGGER.info("Completed assessment for answer %s: score=%s", answer_uuid, assessment["score"])

        LOGGER.info("Uploading assessment for speaking answer %s", answer_uuid)
        complete = requests.post(
            f"{self.server_url}/api/v1/answers/{answer_uuid}/complete",
            json=assessment,
            timeout=30,
        )
        complete.raise_for_status()
        LOGGER.info("Server accepted assessment for answer %s: HTTP %d", answer_uuid, complete.status_code)
        return True

    @staticmethod
    def _speaking_question(raw_questions: Any) -> str:
        questions = json.loads(raw_questions) if isinstance(raw_questions, str) else raw_questions
        for question in questions or []:
            if isinstance(question, dict) and question.get("type") in ("speaking", "SPEAKING"):
                return question.get("question") or question.get("prompt") or "Answer clearly."
        return "Summarize the lesson in your own words."


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    parser = argparse.ArgumentParser(description="Consume one or more TTS/Content tasks.")
    parser.add_argument("--once", action="store_true", help="Exit after one queue poll")
    parser.add_argument("--speaking", action="store_true", help="Consume speaking-answer tasks")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="YAML configuration file (default: config.yaml)",
    )
    args = parser.parse_args()
    config = load_config(args.config)

    LOGGER.info("Loaded configuration: %r", config)

    if not config.deepseek_api_key and not args.speaking:
        LOGGER.warning("DEEPSEEK_API_KEY is not set. Worker will rely on default AI mock or fallback if available.")
    if args.speaking and not config.openai_api_key:
        parser.error("openai.api_key or OPENAI_API_KEY is required for --speaking")

    redis_options = {"password": config.redis_password} if config.redis_password else {}

    try:
        queue = redis.Redis.from_url(
            config.redis_url,
            protocol=2,
            socket_connect_timeout=3,
            socket_timeout=15,
            health_check_interval=30,
            **redis_options,
        )
        queue.ping()
    except Exception as err:
        LOGGER.warning("Unable to connect to Redis server at %s: %s", config.redis_url, err)
        if args.once:
            LOGGER.info("Redis unavailable; --once mode exiting cleanly.")
            return
        raise err

    worker_type = "speaking" if args.speaking else "lesson"
    LOGGER.info("Connected to Redis; starting %s worker for server %s", worker_type, config.server_url)

    if args.speaking:
        worker: Any = SpeakingAnswerWorker(
            queue,
            SpeakingAssessmentService(config.openai_api_key, config.deepseek_api_key),
            config.server_url,
        )
    else:
        worker = TaskWorker(
            queue,
            ProviderRouter([
                (
                    "deepseek",
                    DeepSeekService(
                        config.deepseek_api_key,
                        base_url="https://api.deepseek.com",
                        model=config.deepseek_model,
                    ),
                ),
            ]),
            config.server_url,
            config=config,
        )

    queue_name = "queue:speaking_answers" if args.speaking else "queue:tts_tasks"
    LOGGER.info("Waiting for tasks on Redis queue %s", queue_name)

    if args.once:
        try:
            processed = worker.run_once(timeout=2)
            if not processed:
                LOGGER.info("No queued task was available on %s", queue_name)
        except Exception as exc:
            LOGGER.info("Queue poll completed with status: %s", exc)
    else:
        while True:
            try:
                worker.run_once(timeout=5)
            except redis.exceptions.TimeoutError:
                # A blocking queue poll may time out on a remote Redis proxy.
                # This is an idle poll, not a task-processing failure.
                LOGGER.debug("Redis queue poll timed out; continuing")
            except redis.exceptions.ConnectionError as exc:
                if "Timeout reading from socket" in str(exc):
                    LOGGER.debug("Remote Redis idle poll ended; continuing")
                else:
                    LOGGER.error("Redis connection error: %s. Worker continuing...", exc)
            except Exception as exc:
                LOGGER.error("Task processing exception: %s. Worker continuing...", exc)


if __name__ == "__main__":
    main()
