import json
import hashlib
import tempfile
import unittest
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from api import create_app
from src.backend_config import BackendConfig
from src.backend_models import (
    LearningProgressRecord,
    SpeakingAnswerRecord,
    VocabularyProgressRecord,
    create_session_factory,
)
from src.backend_service import BackendService
from src.config import WorkerConfig
from src.content_ingestion import ContentMetadata
from src.tts_service import _tts_provider_voice


class FakeRedis:
    def __init__(self):
        self.queues: dict[str, list[str]] = {}

    def ping(self):
        return True

    def lpush(self, name, *values):
        self.queues.setdefault(name, []).extend(values)
        return len(self.queues[name])

    def brpop(self, keys, timeout=0):
        if isinstance(keys, str):
            keys = [keys]
        for key in keys:
            items = self.queues.get(key, [])
            if items:
                return key, items.pop(0)
        return None

    def close(self):
        pass


class FakeGenerator:
    def generate_json(self, prompt, max_tokens=None, max_retries=None):
        return self.generate_lesson(prompt)

    def generate_lesson(self, prompt, metadata=None):
        target_words = (metadata or {}).get("targetWords", [])
        passage = (
            "A review article uses every target naturally: "
            + ". ".join(target_words)
            + "."
            if target_words
            else "Virtual threads help Java applications handle many waiting tasks."
        )
        return {
            "title": "Virtual Threads",
            "level": "B1",
            "passage": passage,
            "simplifiedPassage": "Virtual threads are lightweight Java threads.",
            "vocabulary": [
                {
                    "word": "lightweight",
                    "phonetic": "/ˈlaɪt.weɪt/",
                    "definition": "using few resources",
                    "meaningZh": "轻量的",
                    "example": "A virtual thread is lightweight.",
                }
            ],
            "questions": [
                {
                    "type": "INFERENCE",
                    "prompt": "What is the main benefit?",
                    "options": ["A. Lower waiting cost", "B. Larger files"],
                    "answer": "A. Lower waiting cost",
                    "explanation": "They use fewer resources.",
                }
            ],
            "speakingPrompts": ["Summarize virtual threads."],
            "writingPrompts": ["Write one example."],
        }

    def generate_long_lesson(self, prompt, metadata=None):
        lesson = self.generate_lesson(prompt, metadata)
        lesson["title"] = "Ten Minutes of Reliable Spring Services"
        lesson["passage"] = " ".join(["backend"] * 1250)
        lesson["questions"] = lesson["questions"] * 5
        return lesson

    def generate_dialogue_lesson(self, prompt, metadata=None):
        lesson = self.generate_lesson(prompt, metadata)
        lesson["title"] = "A Backend Engineering Conversation"
        lesson["dialogue"] = [
            {
                "speaker": "HOST" if index % 2 == 0 else "EXPERT",
                "text": " ".join(["backend"] * 50),
            }
            for index in range(16)
        ]
        lesson["passage"] = "\n\n".join(
            f"{turn['speaker'].title()}: {turn['text']}"
            for turn in lesson["dialogue"]
        )
        lesson["format"] = "DIALOGUE"
        return lesson


class FakeAssessor:
    def assess(self, audio_path, question):
        return {
            "transcript": "Virtual threads are lightweight.",
            "score": 91,
            "feedback": "Clear summary.",
            "evaluation": {
                "overallScore": 91,
                "pronunciationScore": 92,
                "fluencyScore": 90,
                "intonationScore": 88,
                "pacingScore": 91,
                "relevanceScore": 94,
                "grammarScore": 92,
                "vocabularyScore": 90,
                "summary": "Clear summary.",
                "strengths": ["Clear pronunciation"],
                "improvements": ["Use more varied intonation"],
                "practicePlan": ["Shadow one paragraph"],
                "mode": "AUDIO_AND_TRANSCRIPT",
                "model": "gpt-audio-test",
            },
        }


async def fake_audio_generator(
    text,
    output_path,
    voice,
    word_timings=None,
    api_key=None,
):
    _tts_provider_voice(voice)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"ID3-fake-mp3")
    if word_timings is not None:
        first_word = text.split()[0] if text.split() else ""
        word_timings.append(
            {
                "text": first_word,
                "startMs": 0,
                "endMs": 300,
                "charStart": 0,
                "charEnd": len(first_word),
            }
        )
    return output_path


async def fake_dialogue_audio_generator(
    turns,
    output_path,
    host_voice,
    expert_voice,
    api_key=None,
):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"ID3-fake-dialogue-mp3")
    position = 0
    for turn in turns:
        turn["startMs"] = position
        position += 3000
        turn["endMs"] = position
        turn["words"] = []
    return output_path


def fake_content_fetcher(source_type, source_input, news_sources=None):
    if source_type == "NEWS":
        return ContentMetadata(
            source_type="NEWS",
            source_url="https://news.example.com/java-update",
            published_at="2026-07-26T04:30:00+08:00",
            fetched_at="2026-07-26T04:31:00+08:00",
            title="Java improves developer productivity",
            passage="A public Java update explains safer and clearer application development.",
        )
    return ContentMetadata(
        source_type=source_type,
        source_url="",
        published_at="",
        fetched_at="2026-07-26T04:31:00+08:00",
        title=source_input[:60] or "Lesson",
        passage=source_input,
    )


class BackendApiTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        worker = WorkerConfig(
            redis_url="redis://localhost:6379/0",
            redis_password="",
            server_url="http://localhost:8080",
            audio_output_dir=str(root / "storage"),
            news_sources=["https://news.example.com/rss"],
            deepseek_model="deepseek-test",
            openai_model="openai-test",
            deepseek_api_key="test",
            openai_api_key="test",
        )
        self.config = BackendConfig(
            database_url=f"sqlite:///{root / 'test.db'}",
            redis_url=worker.redis_url,
            redis_password="",
            storage_dir=root / "storage",
            task_queue="test:tasks",
            content_queue="test:content",
            speaking_queue="test:speaking",
            anki_review_queue="test:anki-review",
            daily_hour=5,
            daily_minute=0,
            timezone="Asia/Shanghai",
            worker=worker,
        )
        engine, sessions = create_session_factory(self.config.database_url)
        self.redis = FakeRedis()
        self.service = BackendService(
            self.config,
            engine,
            sessions,
            self.redis,
            generator=FakeGenerator(),
            assessor=FakeAssessor(),
            audio_generator=fake_audio_generator,
            dialogue_audio_generator=fake_dialogue_audio_generator,
            content_fetcher=fake_content_fetcher,
        )
        self.client_context = TestClient(
            create_app(
                config=self.config,
                service=self.service,
                start_background=False,
            )
        )
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.temporary.cleanup()

    def test_task_contract_processing_and_audio(self):
        created = self.client.post(
            "/api/v1/tasks",
            json={
                "prompt": "Explain Java virtual threads.",
                "voice": "en-US-AvaNeural",
                "difficulty": "B1",
            },
        )
        self.assertEqual(200, created.status_code)
        task = created.json()
        self.assertEqual("PENDING", task["status"])
        self.assertIn(task["taskUuid"], self.redis.queues["test:tasks"])

        self.service.process_lesson(task["taskUuid"])
        completed = self.client.get(f"/api/v1/tasks/{task['taskUuid']}").json()

        self.assertEqual("COMPLETED", completed["status"])
        self.assertTrue(completed["audioUrl"].endswith(".mp3"))
        audio = self.client.get(completed["audioUrl"])
        self.assertEqual(200, audio.status_code)
        self.assertEqual(b"ID3-fake-mp3", audio.content)

    def test_app_release_manifest_and_apk_download(self):
        release_dir = self.service.app_release_dir
        apk_name = "Listening-Lab-2.6.0.apk"
        apk_bytes = b"fake-signed-apk"
        (release_dir / apk_name).write_bytes(apk_bytes)
        manifest = {
            "versionCode": 7,
            "versionName": "2.6.0",
            "minimumVersionCode": 6,
            "mandatory": False,
            "title": "App online update",
            "changelog": ["Download updates inside the app"],
            "apkUrl": f"/api/v1/app/releases/{apk_name}",
            "sha256": hashlib.sha256(apk_bytes).hexdigest(),
            "sizeBytes": len(apk_bytes),
            "publishedAt": "2026-08-01T10:00:00+08:00",
        }
        (release_dir / "latest.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )

        latest = self.client.get("/api/v1/app/releases/latest")
        self.assertEqual(200, latest.status_code)
        self.assertEqual(manifest, latest.json())
        download = self.client.get(latest.json()["apkUrl"])
        self.assertEqual(200, download.status_code)
        self.assertEqual(apk_bytes, download.content)
        self.assertEqual(
            "application/vnd.android.package-archive",
            download.headers["content-type"],
        )

    def test_app_release_rejects_invalid_or_missing_manifest(self):
        release_dir = self.service.app_release_dir
        missing = self.client.get("/api/v1/app/releases/latest")
        self.assertEqual(404, missing.status_code)
        (release_dir / "latest.json").write_text("{}", encoding="utf-8")
        invalid = self.client.get("/api/v1/app/releases/latest")
        self.assertEqual(503, invalid.status_code)
        traversal = self.client.get("/api/v1/app/releases/not-an-apk.txt")
        self.assertEqual(400, traversal.status_code)

    def test_daily_plan_library_and_attempt(self):
        generated = self.client.post("/api/v1/daily-plans/2026-07-26/generate")
        self.assertEqual(200, generated.status_code)
        plan = generated.json()
        self.assertEqual("2026-07-26", plan["planDate"])
        self.assertEqual("GENERATING", plan["content"]["status"])
        self.assertEqual(
            "BACKEND_DAILY_DIALOGUE_5_8MIN",
            plan["content"]["profile"],
        )
        self.assertEqual("DIALOGUE", plan["content"]["format"])
        self.assertEqual(7, plan["estimatedMinutes"])

        library = self.client.get("/api/v1/library").json()
        self.assertEqual(1, len(library))
        content_uuid = library[0]["uuid"]
        attempt = self.client.post(
            f"/api/v1/content/{content_uuid}/attempts",
            json={"answersJson": '{"q1":"A"}', "correctCount": 1},
        )
        self.assertEqual(200, attempt.status_code)
        self.assertEqual(1, attempt.json()["correctCount"])

    def test_failed_content_is_hidden_and_failed_daily_plan_is_replaced(self):
        first = self.client.post("/api/v1/daily-plans/2026-07-27/generate").json()
        failed_uuid = first["contentUuid"]
        failed = self.client.post(
            f"/api/v1/content/{failed_uuid}/fail",
            data={"reason": "SCRIPT_GENERATION: malformed JSON"},
        )
        self.assertEqual(200, failed.status_code)

        self.assertEqual([], self.client.get("/api/v1/library").json())
        self.assertEqual(
            404,
            self.client.get("/api/v1/daily-plans/2026-07-27").status_code,
        )

        replacement = self.client.post(
            "/api/v1/daily-plans/2026-07-27/generate"
        ).json()
        self.assertNotEqual(failed_uuid, replacement["contentUuid"])
        self.assertEqual("GENERATING", replacement["content"]["status"])
        visible = self.client.get("/api/v1/library").json()
        self.assertEqual([replacement["contentUuid"]], [item["uuid"] for item in visible])

    def test_long_lesson_is_accepted_asynchronously_and_becomes_ready(self):
        response = self.client.post(
            "/api/v1/long-lessons",
            json={
                "topic": "Spring transaction boundaries",
                "category": "SPRING",
                "voice": "en-US-AndrewNeural",
                "level": "B2",
                "sourceMode": "AI",
            },
        )
        self.assertEqual(202, response.status_code)
        created = response.json()
        self.assertEqual("GENERATING", created["status"])
        self.assertEqual("BACKEND_DAILY_10MIN", created["profile"])
        self.assertEqual(10, created["estimatedMinutes"])
        self.assertIn(created["uuid"], self.redis.queues["test:content"])

        visible = self.client.get("/api/v1/library").json()
        self.assertEqual(created["uuid"], visible[0]["uuid"])
        self.assertEqual("GENERATING", visible[0]["status"])

        self.service.process_lesson(created["uuid"])
        completed = self.client.get(f"/api/v1/content/{created['uuid']}").json()
        self.assertEqual("READY", completed["status"])
        self.assertEqual("en-US-AndrewNeural", completed["voice"])
        lesson = json.loads(completed["lessonContent"])
        self.assertEqual(1250, lesson["wordCount"])
        self.assertEqual(1, lesson["timingVersion"])
        self.assertEqual(1, len(lesson["wordTimings"]))
        self.assertEqual(0, lesson["wordTimings"][0]["charStart"])
        self.assertTrue(completed["audioUrl"].endswith(".mp3"))

    def test_long_lesson_validates_request_options(self):
        invalid = self.client.post(
            "/api/v1/long-lessons",
            json={"level": "C2", "sourceMode": "UNKNOWN"},
        )
        self.assertEqual(400, invalid.status_code)

    def test_dialogue_lesson_is_accepted_and_uses_two_voice_audio(self):
        response = self.client.post(
            "/api/v1/dialogue-lessons",
            json={
                "topic": "Diagnosing database latency",
                "category": "DATABASE",
                "hostVoice": "en-US-AvaNeural",
                "expertVoice": "en-US-AndrewNeural",
                "level": "B1",
                "sourceMode": "AI",
            },
        )
        self.assertEqual(202, response.status_code)
        created = response.json()
        self.assertEqual("GENERATING", created["status"])
        self.assertEqual("DIALOGUE", created["format"])
        self.assertEqual(
            "BACKEND_DAILY_DIALOGUE_5_8MIN",
            created["profile"],
        )

        self.service.process_lesson(created["uuid"])
        completed = self.client.get(
            f"/api/v1/content/{created['uuid']}"
        ).json()
        self.assertEqual("READY", completed["status"])
        lesson = json.loads(completed["lessonContent"])
        self.assertEqual("DIALOGUE", lesson["format"])
        self.assertEqual(16, len(lesson["dialogue"]))
        self.assertEqual(1, lesson["timingVersion"])
        self.assertEqual(0, lesson["dialogue"][0]["startMs"])
        self.assertEqual(48_000, lesson["dialogue"][-1]["endMs"])
        self.assertIn("words", lesson["dialogue"][0])
        self.assertEqual(
            b"ID3-fake-dialogue-mp3",
            self.client.get(completed["audioUrl"]).content,
        )

    def test_learning_progress_upsert_and_read(self):
        client_id = str(uuid.uuid4())
        content_uuid = str(uuid.uuid4())
        payload = {
            "clientId": client_id,
            "contentUuid": content_uuid,
            "positionMs": 120_000,
            "durationMs": 600_000,
            "vocabularyDone": True,
            "listeningDone": False,
            "readingDone": False,
            "quizCorrect": 2,
            "quizTotal": 5,
            "speakingScore": None,
            "completed": False,
        }
        created = self.client.put("/api/v1/learning/progress", json=payload)
        self.assertEqual(200, created.status_code)
        payload.update(
            {
                "positionMs": 245_000,
                "listeningDone": True,
                "quizCorrect": 4,
                "speakingScore": 86,
            }
        )
        updated = self.client.put("/api/v1/learning/progress", json=payload)
        self.assertEqual(200, updated.status_code)
        self.assertEqual(245_000, updated.json()["positionMs"])
        self.assertEqual(86, updated.json()["speakingScore"])
        loaded = self.client.get(
            f"/api/v1/learning/progress/{client_id}/{content_uuid}"
        )
        self.assertEqual(updated.json(), loaded.json())
        with self.service.session_factory() as session:
            count = session.scalar(
                select(func.count()).select_from(LearningProgressRecord)
            )
        self.assertEqual(1, count)

    def test_learning_progress_validation(self):
        valid_ids = {
            "clientId": str(uuid.uuid4()),
            "contentUuid": str(uuid.uuid4()),
        }
        defaults = {
            **valid_ids,
            "positionMs": 100,
            "durationMs": 200,
        }
        for changes in (
            {"clientId": "not-a-uuid"},
            {"contentUuid": "x" * 36},
            {"positionMs": -1},
            {"positionMs": 201, "durationMs": 200},
            {"durationMs": 86_400_001},
            {"quizCorrect": 2, "quizTotal": 1},
            {"speakingScore": 101},
        ):
            with self.subTest(changes=changes):
                response = self.client.put(
                    "/api/v1/learning/progress",
                    json={**defaults, **changes},
                )
                self.assertEqual(422, response.status_code)
        self.assertEqual(
            422,
            self.client.get(
                f"/api/v1/learning/progress/not-a-uuid/{uuid.uuid4()}"
            ).status_code,
        )

    def test_lesson_review_report_uses_only_client_scoped_learning_data(self):
        client_id = str(uuid.uuid4())
        other_client_id = str(uuid.uuid4())
        content_uuid = str(uuid.uuid4())
        self.service.upsert_learning_progress(
            client_id=client_id,
            content_uuid=content_uuid,
            position_ms=600_000,
            duration_ms=600_000,
            vocabulary_done=True,
            listening_done=True,
            reading_done=True,
            quiz_correct=4,
            quiz_total=5,
            speaking_score=90,
            completed=True,
        )
        for word, status in (("backpressure", "KNOWN"), ("latency", "NEW")):
            self.service.upsert_vocabulary_progress(
                client_id=client_id,
                content_uuid=content_uuid,
                word=word,
                status=status,
            )
        self.service.upsert_vocabulary_progress(
            client_id=other_client_id,
            content_uuid=content_uuid,
            word="private-foreign-word",
            status="NEW",
        )
        with self.service.session_factory() as session:
            session.add(
                SpeakingAnswerRecord(
                    answer_uuid=str(uuid.uuid4()),
                    task_uuid=content_uuid,
                    status="COMPLETED",
                    audio_url="/audio/answers/report-test.m4a",
                    score=42,
                    evaluation_json=json.dumps(
                        {
                            "overallScore": 42,
                            "improvements": ["Slow down before important terms."],
                        }
                    ),
                )
            )
            session.commit()

        response = self.client.get(
            f"/api/v1/learning/reports/{client_id}/{content_uuid}"
        )

        self.assertEqual(200, response.status_code)
        report = response.json()
        self.assertEqual(client_id, report["clientId"])
        self.assertEqual(content_uuid, report["contentUuid"])
        dimensions = {item["key"]: item for item in report["dimensions"]}
        self.assertEqual(100, dimensions["listening"]["score"])
        self.assertEqual(80, dimensions["comprehension"]["score"])
        self.assertEqual(50, dimensions["vocabulary"]["score"])
        self.assertEqual(90, dimensions["speaking"]["score"])
        self.assertEqual(80, report["overallScore"])
        self.assertNotIn("private-foreign-word", json.dumps(report))
        self.assertNotIn("Slow down before important terms.", json.dumps(report))
        self.assertEqual(
            404,
            self.client.get(
                f"/api/v1/learning/reports/{other_client_id}/{content_uuid}"
            ).status_code,
        )

    def test_lesson_review_report_handles_missing_progress_and_speaking(self):
        client_id = str(uuid.uuid4())
        content_uuid = str(uuid.uuid4())
        missing = self.client.get(
            f"/api/v1/learning/reports/{client_id}/{content_uuid}"
        )
        self.assertEqual(404, missing.status_code)
        self.assertEqual("learning progress not found", missing.json()["detail"])

        self.service.upsert_learning_progress(
            client_id=client_id,
            content_uuid=content_uuid,
            position_ms=0,
            duration_ms=0,
            vocabulary_done=False,
            listening_done=False,
            reading_done=False,
            quiz_correct=0,
            quiz_total=0,
            speaking_score=None,
            completed=False,
        )
        report = self.client.get(
            f"/api/v1/learning/reports/{client_id}/{content_uuid}"
        ).json()
        speaking = next(
            item for item in report["dimensions"] if item["key"] == "speaking"
        )
        self.assertIsNone(speaking["score"])
        self.assertEqual("NO_DATA", speaking["status"])
        invalid = self.client.get(
            f"/api/v1/learning/reports/not-a-uuid/{content_uuid}"
        )
        self.assertEqual(422, invalid.status_code)

    def test_learning_review_queue_empty_due_rules_and_client_isolation(self):
        client_id = str(uuid.uuid4())
        other_client_id = str(uuid.uuid4())
        review_date = date(2026, 8, 1)
        empty = self.client.get(
            f"/api/v1/learning/review-queue/{client_id}?date={review_date}"
        )
        self.assertEqual(200, empty.status_code)
        self.assertEqual([], empty.json()["items"])

        rows = (
            (
                "new-word",
                "NEW",
                datetime(2026, 8, 1, 23, 59, 59, tzinfo=timezone.utc),
            ),
            (
                "learning-word",
                "LEARNING",
                datetime(2026, 7, 31, 23, 59, 59, tzinfo=timezone.utc),
            ),
            (
                "known-word",
                "KNOWN",
                datetime(2026, 7, 25, 23, 59, 59, tzinfo=timezone.utc),
            ),
            (
                "not-due",
                "LEARNING",
                datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc),
            ),
        )
        row_ids: dict[str, int] = {}
        for word, status, _ in rows:
            result = self.service.upsert_vocabulary_progress(
                client_id=client_id,
                content_uuid=str(uuid.uuid4()),
                word=word,
                status=status,
            )
            self.assertEqual(word, result["word"])
        with self.service.session_factory() as session:
            for record in session.scalars(
                select(VocabularyProgressRecord).where(
                    VocabularyProgressRecord.client_id == client_id
                )
            ):
                row_ids[record.word] = record.id
            for word, _, updated_at in rows:
                session.get(VocabularyProgressRecord, row_ids[word]).updated_at = updated_at
            session.commit()
        self.service.upsert_vocabulary_progress(
            client_id=other_client_id,
            content_uuid=str(uuid.uuid4()),
            word="foreign-word",
            status="NEW",
        )

        response = self.client.get(
            f"/api/v1/learning/review-queue/{client_id}?date={review_date}"
        )

        self.assertEqual(200, response.status_code)
        queue = response.json()
        self.assertEqual(client_id, queue["clientId"])
        self.assertEqual("2026-08-01", queue["date"])
        self.assertEqual(3, queue["totalCount"])
        self.assertEqual(3, queue["estimatedMinutes"])
        self.assertEqual(
            {"new-word", "learning-word", "known-word"},
            {item["word"] for item in queue["items"]},
        )
        self.assertNotIn("foreign-word", json.dumps(queue))
        priorities = {item["word"]: item["priority"] for item in queue["items"]}
        self.assertEqual(
            {"new-word": 1, "learning-word": 2, "known-word": 3},
            priorities,
        )

    def test_learning_review_queue_limit_and_query_validation(self):
        client_id = str(uuid.uuid4())
        review_date = date.today()
        for index in range(6):
            self.service.upsert_vocabulary_progress(
                client_id=client_id,
                content_uuid=str(uuid.uuid4()),
                word=f"word-{index}",
                status="NEW",
            )
        response = self.client.get(
            f"/api/v1/learning/review-queue/{client_id}"
            f"?date={review_date}&limit=3"
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(3, response.json()["totalCount"])
        self.assertEqual(3, len(response.json()["items"]))

        for query in (
            "date=not-a-date",
            "date=2026-08-01&limit=0",
            "date=2026-08-01&limit=51",
            "date=2026-08-01&limit=abc",
            "",
        ):
            with self.subTest(query=query):
                suffix = f"?{query}" if query else ""
                invalid = self.client.get(
                    f"/api/v1/learning/review-queue/{client_id}{suffix}"
                )
                self.assertEqual(422, invalid.status_code)
        self.assertEqual(
            422,
            self.client.get(
                "/api/v1/learning/review-queue/not-a-uuid?date=2026-08-01"
            ).status_code,
        )

    def test_learning_dashboard_aggregation_and_streak(self):
        client_id = str(uuid.uuid4())
        first_content = str(uuid.uuid4())
        second_content = str(uuid.uuid4())
        old_content = str(uuid.uuid4())
        for content_uuid, position, completed, correct, total, score in (
            (first_content, 120_000, True, 4, 5, 80),
            (second_content, 180_000, False, 3, 5, 90),
            (old_content, 900_000, True, 5, 5, 100),
        ):
            self.service.upsert_learning_progress(
                client_id=client_id,
                content_uuid=content_uuid,
                position_ms=position,
                duration_ms=900_000,
                vocabulary_done=True,
                listening_done=completed,
                reading_done=completed,
                quiz_correct=correct,
                quiz_total=total,
                speaking_score=score,
                completed=completed,
            )
        self.service.upsert_vocabulary_progress(
            client_id=client_id,
            content_uuid=first_content,
            word="backpressure",
            status="LEARNING",
        )
        self.service.upsert_vocabulary_progress(
            client_id=client_id,
            content_uuid=second_content,
            word="throughput",
            status="KNOWN",
        )

        zone = ZoneInfo("Asia/Shanghai")
        today = datetime.now(zone).date()

        def local_noon(day):
            return datetime.combine(day, time(12), zone).astimezone(timezone.utc)

        with self.service.session_factory() as session:
            progress = {
                item.content_uuid: item
                for item in session.scalars(
                    select(LearningProgressRecord).where(
                        LearningProgressRecord.client_id == client_id
                    )
                )
            }
            progress[first_content].updated_at = local_noon(today - timedelta(days=1))
            progress[second_content].updated_at = local_noon(today)
            progress[old_content].updated_at = local_noon(today - timedelta(days=10))
            words = session.scalars(
                select(VocabularyProgressRecord).where(
                    VocabularyProgressRecord.client_id == client_id
                )
            ).all()
            for word in words:
                word.updated_at = local_noon(today)
            session.commit()

        dashboard = self.client.get(
            f"/api/v1/learning/dashboard/{client_id}?days=7"
        )
        self.assertEqual(200, dashboard.status_code)
        self.assertEqual(
            {
                "days": 7,
                "listeningMinutes": 5,
                "completedLessons": 1,
                "quizCorrect": 7,
                "quizTotal": 10,
                "speakingAverage": 85,
                "currentStreak": 2,
                "wordsReviewed": 2,
                "latestContentUuid": second_content,
                "latestPositionMs": 180_000,
            },
            dashboard.json(),
        )
        self.assertEqual(
            422,
            self.client.get(
                f"/api/v1/learning/dashboard/{client_id}?days=0"
            ).status_code,
        )

    def test_vocabulary_upsert_is_case_insensitive_and_filterable(self):
        client_id = str(uuid.uuid4())
        first_content = str(uuid.uuid4())
        second_content = str(uuid.uuid4())
        first = self.client.put(
            "/api/v1/learning/vocabulary",
            json={
                "clientId": client_id,
                "contentUuid": first_content,
                "word": " Backpressure ",
                "status": "NEW",
            },
        )
        self.assertEqual(200, first.status_code)
        second = self.client.put(
            "/api/v1/learning/vocabulary",
            json={
                "clientId": client_id,
                "contentUuid": second_content,
                "word": "backpressure",
                "status": "LEARNING",
            },
        )
        self.assertEqual(200, second.status_code)
        self.assertEqual(second_content, second.json()["contentUuid"])
        listed = self.client.get(
            f"/api/v1/learning/vocabulary/{client_id}?status=LEARNING"
        )
        self.assertEqual(200, listed.status_code)
        self.assertEqual(1, len(listed.json()))
        self.assertEqual("backpressure", listed.json()[0]["word"])
        with self.service.session_factory() as session:
            count = session.scalar(
                select(func.count()).select_from(VocabularyProgressRecord)
            )
        self.assertEqual(1, count)
        invalid_status = self.client.put(
            "/api/v1/learning/vocabulary",
            json={
                "clientId": client_id,
                "contentUuid": second_content,
                "word": "latency",
                "status": "MASTERED",
            },
        )
        self.assertEqual(422, invalid_status.status_code)

    def test_speaking_answer_processing(self):
        task = self.client.post(
            "/api/v1/tasks",
            json={"prompt": "Speak clearly.", "voice": "en-US-AvaNeural"},
        ).json()
        uploaded = self.client.post(
            f"/api/v1/tasks/{task['taskUuid']}/answers",
            files={"audio": ("answer.m4a", b"audio", "audio/mp4")},
        )
        self.assertEqual(200, uploaded.status_code)
        answer_uuid = uploaded.json()["answerUuid"]

        self.service.process_answer(answer_uuid)
        answer = self.client.get(f"/api/v1/answers/{answer_uuid}").json()
        self.assertEqual("COMPLETED", answer["status"])
        self.assertEqual(91, answer["score"])
        self.assertEqual(
            92,
            answer["evaluation"]["pronunciationScore"],
        )

    def test_speaking_answer_accepts_library_content_uuid(self):
        content = self.client.post(
            "/api/v1/content/import",
            json={
                "sourceType": "TEXT",
                "text": "Explain why asynchronous processing improves responsiveness.",
                "title": "Async Processing",
                "level": "B1",
            },
        ).json()
        completed = self.client.post(
            f"/api/v1/content/{content['uuid']}/complete",
            files={"audio": ("lesson.mp3", b"ID3-lesson", "audio/mpeg")},
            data={
                "lessonContent": json.dumps(
                    {
                        "passage": "Async processing keeps slow work off the UI thread.",
                        "speakingPrompts": [
                            "Explain one benefit of asynchronous processing."
                        ],
                    }
                )
            },
        )
        self.assertEqual(200, completed.status_code)

        uploaded = self.client.post(
            f"/api/v1/tasks/{content['uuid']}/answers",
            files={"audio": ("answer.m4a", b"audio", "audio/mp4")},
        )
        self.assertEqual(200, uploaded.status_code)
        answer_uuid = uploaded.json()["answerUuid"]

        self.service.process_answer(answer_uuid)
        answer = self.client.get(f"/api/v1/answers/{answer_uuid}").json()
        self.assertEqual("COMPLETED", answer["status"])
        self.assertEqual(91, answer["score"])

    def test_speaking_question_reads_content_prompt(self):
        lesson = json.dumps(
            {
                "questions": [],
                "speakingPrompts": ["Describe the system in your own words."],
            }
        )
        self.assertEqual(
            "Describe the system in your own words.",
            self.service.speaking_question(lesson),
        )

    def test_health_and_not_found(self):
        self.assertEqual("UP", self.client.get("/health").json()["status"])
        self.assertEqual(404, self.client.get("/api/v1/tasks/missing").status_code)

    def test_anki_review_lesson_is_idempotent_and_generates_audio(self):
        payload = {
            "clientDate": "2026-07-26",
            "deckAlias": "English Vocabulary",
            "level": "B1",
            "voice": "en-US-AvaNeural",
            "topicMode": "DAILY_RECOMMENDED",
            "words": [
                {
                    "clientWordKey": "a" * 64,
                    "word": "virtual",
                    "meaning": "虚拟的",
                    "example": "A virtual thread is lightweight.",
                },
                {
                    "clientWordKey": "b" * 64,
                    "word": "lightweight",
                    "meaning": "轻量的",
                },
            ],
        }
        created = self.client.post("/api/v1/anki/review-lessons", json=payload)
        self.assertEqual(202, created.status_code)
        lesson = created.json()
        self.assertEqual(2, lesson["targetWordCount"])
        self.assertIn(lesson["uuid"], self.redis.queues["test:anki-review"])

        repeated = self.client.post("/api/v1/anki/review-lessons", json=payload)
        self.assertEqual(lesson["uuid"], repeated.json()["uuid"])
        self.assertEqual(1, len(self.redis.queues["test:anki-review"]))

        self.service.process_anki_review(lesson["uuid"])
        completed = self.client.get(
            f"/api/v1/anki/review-lessons/{lesson['uuid']}"
        ).json()
        self.assertEqual("READY", completed["status"])
        self.assertEqual(2, completed["coveredWordCount"])
        self.assertEqual(200, self.client.get(completed["audioUrl"]).status_code)

        by_date = self.client.get(
            "/api/v1/anki/review-lessons?clientDate=2026-07-26"
        ).json()
        self.assertEqual(1, len(by_date))

    def test_anki_review_request_validates_word_limit(self):
        response = self.client.post(
            "/api/v1/anki/review-lessons",
            json={
                "clientDate": "2026-07-26",
                "deckAlias": "Deck",
                "words": [],
            },
        )
        self.assertEqual(422, response.status_code)

    def test_anki_review_covers_ten_target_words(self):
        target_words = [
            "concurrency",
            "immutable",
            "throughput",
            "latency",
            "consistency",
            "resilience",
            "scalability",
            "encapsulation",
            "abstraction",
            "coordination",
        ]
        created = self.client.post(
            "/api/v1/anki/review-lessons",
            json={
                "clientDate": "2026-07-26",
                "deckAlias": "Ten Word Deck",
                "words": [
                    {
                        "clientWordKey": f"{index:064x}",
                        "word": word,
                    }
                    for index, word in enumerate(target_words, start=1)
                ],
            },
        ).json()

        self.service.process_anki_review(created["uuid"])
        completed = self.client.get(
            f"/api/v1/anki/review-lessons/{created['uuid']}"
        ).json()
        lesson = json.loads(completed["lessonContent"])

        self.assertEqual("READY", completed["status"])
        self.assertEqual(10, completed["targetWordCount"])
        self.assertEqual(10, completed["coveredWordCount"])
        self.assertEqual([], lesson["missingTargetWords"])

    def test_startup_requeues_incomplete_jobs_and_skips_completed_records(self):
        task = self.client.post(
            "/api/v1/tasks",
            json={"prompt": "Recover this task.", "voice": "en-US-AvaNeural"},
        ).json()
        content = self.client.post(
            "/api/v1/content/import",
            json={
                "sourceType": "TEXT",
                "text": "Recover this content.",
                "title": "Recovery",
                "level": "B1",
            },
        ).json()
        anki = self.client.post(
            "/api/v1/anki/review-lessons",
            json={
                "clientDate": "2026-07-26",
                "deckAlias": "Recovery Deck",
                "words": [
                    {
                        "clientWordKey": "c" * 64,
                        "word": "lightweight",
                    }
                ],
            },
        ).json()

        self.redis.queues.clear()
        recovered = self.service.recover_incomplete_jobs()

        self.assertEqual(1, recovered["tasks"])
        self.assertEqual(1, recovered["content"])
        self.assertEqual(1, recovered["anki"])
        self.assertIn(task["taskUuid"], self.redis.queues["test:tasks"])
        self.assertIn(content["uuid"], self.redis.queues["test:content"])
        self.assertIn(anki["uuid"], self.redis.queues["test:anki-review"])

        self.service.process_lesson(task["taskUuid"])
        self.service.process_lesson(content["uuid"])
        self.service.process_anki_review(anki["uuid"])
        self.redis.queues.clear()

        recovered_after_completion = self.service.recover_incomplete_jobs()
        self.assertEqual(0, recovered_after_completion["tasks"])
        self.assertEqual(0, recovered_after_completion["content"])
        self.assertEqual(0, recovered_after_completion["anki"])

    def test_daily_generation_is_idempotent_and_keeps_source_attribution(self):
        first = self.client.post("/api/v1/daily-generation/2026-07-26")
        self.assertEqual(200, first.status_code)
        generated = first.json()
        self.assertEqual(3, len(generated["topics"]))
        self.assertEqual(1, generated["sourceCount"])
        source = next(item for item in generated["topics"] if item["kind"] == "SOURCE_ARTICLE")
        self.assertEqual(
            "https://news.example.com/java-update",
            source["sourceUrl"],
        )

        repeated = self.client.post("/api/v1/daily-generation/2026-07-26").json()
        self.assertEqual(
            [item["uuid"] for item in generated["topics"]],
            [item["uuid"] for item in repeated["topics"]],
        )

        topics = self.client.get(
            "/api/v1/topics/recommendations?planDate=2026-07-26"
        ).json()
        self.assertEqual(3, len(topics))
        self.assertTrue(any(item["kind"] == "AI_ORIGINAL" for item in topics))

        for item in topics:
            self.service.process_lesson(item["contentUuid"])
        ready_run = self.client.post("/api/v1/daily-generation/2026-07-26").json()
        self.assertEqual("READY", ready_run["status"])
        self.assertEqual(3, ready_run["readyCount"])
        ready_ai = next(
            item for item in ready_run["topics"] if item["kind"] == "AI_ORIGINAL"
        )
        self.assertEqual("Virtual Threads", ready_ai["title"])
        self.assertIsNone(ready_ai["sourceUrl"])

        self.service.local_today = lambda: date(2026, 7, 26)
        default_topics = self.client.get("/api/v1/topics/recommendations").json()
        self.assertEqual(
            [item["uuid"] for item in ready_run["topics"]],
            [item["uuid"] for item in default_topics],
        )

        lesson = self.client.post(f"/api/v1/topics/{source['uuid']}/lessons")
        self.assertEqual(200, lesson.status_code)
        self.assertEqual(source["contentUuid"], lesson.json()["content"]["uuid"])

    def test_daily_generation_repairs_a_day_created_without_a_source(self):
        original_fetcher = self.service.content_fetcher

        def unavailable_source(**_kwargs):
            raise RuntimeError("source temporarily unavailable")

        self.service.content_fetcher = unavailable_source
        without_source = self.client.post(
            "/api/v1/daily-generation/2026-07-28"
        ).json()
        self.assertEqual(0, without_source["sourceCount"])
        self.assertEqual(
            {"AI_ORIGINAL"},
            {topic["kind"] for topic in without_source["topics"]},
        )

        self.service.content_fetcher = original_fetcher
        repaired = self.client.post(
            "/api/v1/daily-generation/2026-07-28"
        ).json()
        self.assertEqual(1, repaired["sourceCount"])
        self.assertTrue(
            any(topic["kind"] == "SOURCE_ARTICLE" for topic in repaired["topics"])
        )
        visible_topics = self.client.get(
            "/api/v1/topics/recommendations?planDate=2026-07-28&limit=3"
        ).json()
        self.assertEqual(3, len(visible_topics))
        self.assertTrue(
            any(topic["kind"] == "SOURCE_ARTICLE" for topic in visible_topics)
        )

    def test_legacy_completion_routes_remain_compatible(self):
        content = self.client.post(
            "/api/v1/content/import",
            json={
                "sourceType": "TEXT",
                "text": "A short source.",
                "title": "Compatibility",
                "level": "B1",
            },
        ).json()
        completed_content = self.client.post(
            f"/api/v1/content/{content['uuid']}/complete",
            files={"audio": ("lesson.mp3", b"ID3-legacy", "audio/mpeg")},
            data={"lessonContent": '{"passage":"A short source."}'},
        )
        self.assertEqual(200, completed_content.status_code)
        self.assertEqual("READY", completed_content.json()["status"])

        task = self.client.post(
            "/api/v1/tasks",
            json={"prompt": "Speak.", "voice": "en-US-AvaNeural"},
        ).json()
        answer = self.client.post(
            f"/api/v1/tasks/{task['taskUuid']}/answers",
            files={"audio": ("answer.m4a", b"audio", "audio/mp4")},
        ).json()
        completed_answer = self.client.post(
            f"/api/v1/answers/{answer['answerUuid']}/complete",
            json={"transcript": "Hello.", "score": 88, "feedback": "Clear."},
        )
        self.assertEqual(200, completed_answer.status_code)
        self.assertEqual("COMPLETED", completed_answer.json()["status"])

    def test_vocabulary_lookup_and_user_words_lifecycle(self):
        client_id = str(uuid.uuid4())
        content_uuid = str(uuid.uuid4())

        # 1. Lookup vocabulary
        lookup_resp = self.client.post(
            "/api/v1/vocabulary/lookup",
            json={
                "word": "throughput",
                "contextSentence": "Connection pools improve throughput under load.",
            },
        )
        self.assertEqual(200, lookup_resp.status_code)
        data = lookup_resp.json()
        self.assertEqual("throughput", data["word"])
        self.assertTrue("definitionCn" in data)

        # 2. Save user vocabulary card
        save_resp = self.client.post(
            "/api/v1/vocabulary/user-words",
            json={
                "clientId": client_id,
                "word": "throughput",
                "definitionCn": "吞吐量；处理能力",
                "definitionEn": "Amount of work completed per unit time.",
                "phoneticUs": "/ˈθruːˌpʊt/",
                "contextSentence": "Connection pools improve throughput under load.",
                "contentUuid": content_uuid,
                "sentenceStartMs": 14000,
                "sentenceEndMs": 18500,
            },
        )
        self.assertEqual(201, save_resp.status_code)
        card = save_resp.json()
        self.assertEqual("throughput", card["word"])
        self.assertEqual("NEW", card["fsrsState"])

        # 3. Query user vocabulary list
        list_resp = self.client.get(f"/api/v1/vocabulary/user-words?clientId={client_id}&limit=10")
        self.assertEqual(200, list_resp.status_code)
        words_list = list_resp.json()
        self.assertEqual(1, len(words_list))
        self.assertEqual("throughput", words_list[0]["word"])

    def test_speaking_session_lifecycle_with_audio_and_assessment(self):
        client_id = str(uuid.uuid4())
        content_uuid = str(uuid.uuid4())

        # 1. Create session (verifies async audio synthesis & Path argument)
        create_resp = self.client.post(
            "/api/v1/speaking/sessions",
            json={
                "clientId": client_id,
                "contentUuid": content_uuid,
                "scenario": "SYSTEM_DESIGN_INTERVIEW",
                "role": "TECH_LEAD",
            },
        )
        self.assertEqual(201, create_resp.status_code)
        session_data = create_resp.json()
        session_id = session_data["sessionId"]
        self.assertEqual(1, session_data["turnIndex"])
        self.assertTrue(bool(session_data["aiAudioUrl"]))

        # Verify AI audio URL is downloadable
        audio_get = self.client.get(session_data["aiAudioUrl"])
        self.assertEqual(200, audio_get.status_code)
        self.assertEqual("audio/mpeg", audio_get.headers.get("content-type"))

        # 2. Submit user turn with assessor configured
        mock_assessor = Mock()
        mock_assessor.transcribe.return_value = "I use message queues for decoupling."
        mock_assessor.score.return_value = {"score": 92, "grammar_score": 94, "feedback": "Excellent response."}
        self.service.assessor = mock_assessor

        turn_resp = self.client.post(
            f"/api/v1/speaking/sessions/{session_id}/turns",
            data={"turnIndex": 1},
            files={"audio": ("turn1.m4a", b"user_speech_bytes", "audio/mp4")},
        )
        self.assertEqual(200, turn_resp.status_code)
        turn_data = turn_resp.json()
        self.assertEqual("COMPLETED", turn_data["evaluationStatus"])
        self.assertEqual("I use message queues for decoupling.", turn_data["userTranscript"])
        self.assertEqual(92, turn_data["pronunciationScore"])
        self.assertEqual(94, turn_data["grammarScore"])
        self.assertEqual("Excellent response.", turn_data["quickFeedback"])
        self.assertFalse(turn_data["isFinished"])
        self.assertIsNotNone(turn_data["nextTurn"])
        self.assertEqual(2, turn_data["nextTurn"]["turnIndex"])

        # 3. Test assessor failure does NOT return fabricated scores
        mock_assessor.score.side_effect = RuntimeError("scoring service down")
        turn2_resp = self.client.post(
            f"/api/v1/speaking/sessions/{session_id}/turns",
            data={"turnIndex": 2},
            files={"audio": ("turn2.m4a", b"user_speech_bytes_2", "audio/mp4")},
        )
        self.assertEqual(200, turn2_resp.status_code)
        turn2_data = turn2_resp.json()
        self.assertEqual("FAILED", turn2_data["evaluationStatus"])
        self.assertIsNone(turn2_data["pronunciationScore"])
        self.assertIsNone(turn2_data["grammarScore"])
        self.assertIsNone(turn2_data["userTranscript"])
        self.assertIsNone(turn2_data["quickFeedback"])

        # 4. Out-of-order turn rejected
        invalid_turn_resp = self.client.post(
            f"/api/v1/speaking/sessions/{session_id}/turns",
            data={"turnIndex": 5},
            files={"audio": ("turn5.m4a", b"out_of_order", "audio/mp4")},
        )
        self.assertEqual(400, invalid_turn_resp.status_code)

        # 5. Complete round 3
        mock_assessor.score.side_effect = None
        mock_assessor.score.return_value = {"score": 88, "grammar_score": 90, "feedback": "Good summary."}
        turn3_resp = self.client.post(
            f"/api/v1/speaking/sessions/{session_id}/turns",
            data={"turnIndex": 3},
            files={"audio": ("turn3.m4a", b"user_speech_bytes_3", "audio/mp4")},
        )
        self.assertEqual(200, turn3_resp.status_code)
        turn3_data = turn3_resp.json()
        self.assertTrue(turn3_data["isFinished"])

        # 6. Submission on completed session rejected
        after_comp_resp = self.client.post(
            f"/api/v1/speaking/sessions/{session_id}/turns",
            data={"turnIndex": 3},
            files={"audio": ("turn3_again.m4a", b"extra", "audio/mp4")},
        )
        self.assertEqual(400, after_comp_resp.status_code)

    def test_speaking_session_audio_endpoint_validation(self):
        # Invalid file name
        resp_bad = self.client.get("/api/v1/audio/speaking-sessions/not_a_valid_speaking_file.mp3")
        self.assertEqual(400, resp_bad.status_code)

        # Directory traversal
        resp_traversal = self.client.get("/api/v1/audio/speaking-sessions/..%2Ftasks%2Fuuid.mp3")
        self.assertIn(resp_traversal.status_code, (400, 404))

        # Non-existent valid filename format
        resp_404 = self.client.get("/api/v1/audio/speaking-sessions/spk_0123456789ab_turn1_ai.mp3")
        self.assertEqual(404, resp_404.status_code)

    def test_preview_tts_voice_validation(self):
        # Valid voices
        resp_openai = self.client.post(
            "/api/v1/tts/demo",
            json={"voice": "openai:nova", "text": "Testing voice validation."},
        )
        self.assertEqual(200, resp_openai.status_code)

        resp_aliyun = self.client.post(
            "/api/v1/tts/demo",
            json={"voice": "aliyun:loongdavid_v2", "text": "Testing voice validation."},
        )
        self.assertEqual(200, resp_aliyun.status_code)

        # Invalid provider
        resp_inv_prov = self.client.post(
            "/api/v1/tts/demo",
            json={"voice": "invalid_prov:voice", "text": "Testing."},
        )
        self.assertEqual(400, resp_inv_prov.status_code)

        # Invalid voice for provider
        resp_inv_voice = self.client.post(
            "/api/v1/tts/demo",
            json={"voice": "openai:invalid_voice_name", "text": "Testing."},
        )
        self.assertEqual(400, resp_inv_voice.status_code)

        resp_malformed_voice = self.client.post(
            "/api/v1/tts/demo",
            json={"voice": "openai:openai:nova", "text": "Testing."},
        )
        self.assertEqual(400, resp_malformed_voice.status_code)

    def test_create_task_voice_validation(self):
        resp_valid = self.client.post(
            "/api/v1/tasks",
            json={"prompt": "Test prompt", "voice": "en-US-AvaNeural"},
        )
        self.assertEqual(200, resp_valid.status_code)

        resp_invalid = self.client.post(
            "/api/v1/tasks",
            json={"prompt": "Test prompt", "voice": "unknown_provider:voice"},
        )
        self.assertEqual(400, resp_invalid.status_code)

    @patch("api.TASK_EVENTS_MAX_ITERATIONS", 1)
    @patch("api.TASK_EVENTS_POLL_INTERVAL_SECONDS", 0)
    def test_task_events_stream_endpoint(self):
        task = self.client.post(
            "/api/v1/tasks",
            json={"prompt": "Explain Redis caching.", "voice": "en-US-AvaNeural"},
        ).json()
        with self.client.stream("GET", f"/api/v1/tasks/{task['taskUuid']}/events") as response:
            self.assertEqual(200, response.status_code)
            self.assertTrue("text/event-stream" in response.headers.get("content-type", ""))
            first_chunk = next(response.iter_text())
            self.assertTrue("event:" in first_chunk)
            self.assertIn("event: timeout", first_chunk)


if __name__ == "__main__":
    unittest.main()
