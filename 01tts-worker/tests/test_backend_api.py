import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from api import create_app
from src.backend_config import BackendConfig
from src.backend_models import create_session_factory
from src.backend_service import BackendService
from src.config import WorkerConfig
from src.content_ingestion import ContentMetadata


class FakeRedis:
    def __init__(self):
        self.queues: dict[str, list[str]] = {}

    def ping(self):
        return True

    def lpush(self, queue: str, value: str):
        self.queues.setdefault(queue, []).insert(0, value)
        return len(self.queues[queue])

    def brpop(self, queues, timeout=0):
        return None


class FakeGenerator:
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
                "text": " ".join(["backend"] * 63),
            }
            for index in range(20)
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
        }


async def fake_audio_generator(text, output_path, voice):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"ID3-fake-mp3")
    return output_path


async def fake_dialogue_audio_generator(
    turns,
    output_path,
    host_voice,
    expert_voice,
):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"ID3-fake-dialogue-mp3")
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
            moonshot_model="kimi-test",
            deepseek_api_key="test",
            openai_api_key="test",
            moonshot_api_key="test",
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

    def test_daily_plan_library_and_attempt(self):
        generated = self.client.post("/api/v1/daily-plans/2026-07-26/generate")
        self.assertEqual(200, generated.status_code)
        plan = generated.json()
        self.assertEqual("2026-07-26", plan["planDate"])
        self.assertEqual("GENERATING", plan["content"]["status"])
        self.assertEqual(
            "BACKEND_DAILY_DIALOGUE_10MIN",
            plan["content"]["profile"],
        )
        self.assertEqual("DIALOGUE", plan["content"]["format"])
        self.assertEqual(10, plan["estimatedMinutes"])

        library = self.client.get("/api/v1/library").json()
        self.assertEqual(1, len(library))
        content_uuid = library[0]["uuid"]
        attempt = self.client.post(
            f"/api/v1/content/{content_uuid}/attempts",
            json={"answersJson": '{"q1":"A"}', "correctCount": 1},
        )
        self.assertEqual(200, attempt.status_code)
        self.assertEqual(1, attempt.json()["correctCount"])

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
            "BACKEND_DAILY_DIALOGUE_10MIN",
            created["profile"],
        )

        self.service.process_lesson(created["uuid"])
        completed = self.client.get(
            f"/api/v1/content/{created['uuid']}"
        ).json()
        self.assertEqual("READY", completed["status"])
        lesson = json.loads(completed["lessonContent"])
        self.assertEqual("DIALOGUE", lesson["format"])
        self.assertEqual(20, len(lesson["dialogue"]))
        self.assertEqual(
            b"ID3-fake-dialogue-mp3",
            self.client.get(completed["audioUrl"]).content,
        )

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


if __name__ == "__main__":
    unittest.main()
