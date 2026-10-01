import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import select
from src.backend_models import ContentArchiveRecord, ContentRecord, TopicCandidateRecord, DailyPlanRecord
from src.content_archive import archive_reviewed, lesson_digest, restore_archive
from src.content_diversity import TOPIC_CATALOG, coverage_digest, duplicate_passage
from tests import test_backend_api


class ContentDiversityTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_backend_api.BackendApiTest()
        self.fixture.setUp()
        self.service = self.fixture.service
        self.sessions = self.service.session_factory
        self.root = Path(self.fixture.temporary.name)

    def tearDown(self):
        self.fixture.tearDown()

    def record(self, uuid, passage):
        with self.sessions() as session:
            session.add(ContentRecord(uuid=uuid, title="A backend case", source_type="TEXT",
                                      source_text="A backend case", level="B1", status="READY",
                                      lesson_content=json.dumps({"passage": passage})))
            session.commit()

    def entry(self):
        return {"uuid": "duplicate", "duplicateOf": "keep", "reason": "Reviewed duplicate",
                "lessonSha256": lesson_digest(json.dumps({"passage": "Duplicate draft"})),
                "keeperSha256": lesson_digest(json.dumps({"passage": "Representative"}))}

    def test_archive_hides_lists_preserves_links_and_can_restore(self):
        self.record("keep", "Representative")
        self.record("duplicate", "Duplicate draft")
        with self.sessions() as session:
            session.add(DailyPlanRecord(plan_date=date(2026, 9, 1), content_uuid="duplicate"))
            session.add(TopicCandidateRecord(uuid="topic", plan_date=date(2026, 9, 1),
                                            kind="AI_ORIGINAL", category="JAVA", title="Duplicate",
                                            summary="", source_hash="hash", provider="test",
                                            score=1, status="READY", content_uuid="duplicate"))
            session.commit()
        backup = self.root / "backup.json"
        self.assertEqual(1, archive_reviewed(self.sessions, [self.entry()], backup))
        self.assertFalse(backup.exists())
        self.assertEqual(1, archive_reviewed(self.sessions, [self.entry()], backup, apply=True))
        self.assertEqual(["keep"], [row["uuid"] for row in self.service.library()])
        self.assertEqual(1, self.service.library_page(page=1, page_size=10)["total"])
        self.assertEqual([], self.service.topic_candidates(date(2026, 9, 1)))
        self.assertEqual("READY", self.service.get_content("duplicate")["status"])
        self.assertEqual("duplicate", self.service.get_daily_plan(date(2026, 9, 1))["contentUuid"])
        self.assertIsNotNone(self.service.topic_lesson("topic"))
        self.assertEqual(1, restore_archive(self.sessions, backup))
        self.assertEqual(2, len(self.service.library()))

    def test_archive_refuses_stale_and_protected_rows(self):
        self.record("keep", "Representative")
        self.record("duplicate", "Duplicate draft")
        backup = self.root / "backup.json"
        for protected in [set(), {"duplicate"}]:
            entry = self.entry()
            if not protected:
                entry["lessonSha256"] = "stale"
            with self.assertRaises(ValueError):
                archive_reviewed(self.sessions, [entry], backup, protected, apply=True)
        self.assertFalse(backup.exists())
        with self.sessions() as session:
            self.assertEqual([], session.scalars(select(ContentArchiveRecord)).all())

    def test_catalog_is_specific_and_unique(self):
        self.assertEqual(240, len(TOPIC_CATALOG))
        self.assertEqual(240, len({item.title for item in TOPIC_CATALOG}))
        self.assertEqual(60, len({item.problem for item in TOPIC_CATALOG}))

    def test_selection_uses_stable_hash_and_respects_plan_reservations(self):
        day = date(2026, 10, 1)
        chosen = self.service.select_daily_topics(day, 1)[0]
        with self.sessions() as session:
            session.add(TopicCandidateRecord(uuid="reserved", plan_date=day-timedelta(days=2),
                                            kind="AI_ORIGINAL", category=chosen.category,
                                            title="Changed display title", summary="",
                                            source_hash=self.service.topic_source_hash("AI_ORIGINAL", chosen.category, chosen.title),
                                            provider="test", score=1, status="FAILED", content_uuid="reserved-content"))
            session.commit()
        self.assertNotIn(chosen.problem, [item.problem for item in self.service.select_daily_topics(day, 3)])
        daily = self.service.generate_daily_plan(day)
        with self.sessions() as session:
            metadata = self.service._long_lesson_metadata(session.get(ContentRecord, daily["contentUuid"]).source_text)
        self.assertEqual("AI", metadata["sourceMode"])
        self.assertTrue(all(not metadata["topic"].startswith(item.title) for item in self.service.select_daily_topics(day, 3)))

    def test_overlap_rejects_repeat_preserves_audio_placeholders(self):
        text = " ".join(f"database connection operation{i} timeout evidence" for i in range(20))
        self.assertEqual("keep", duplicate_passage(text, [("keep", text)]))
        self.assertIsNone(duplicate_passage("Audio-only lesson from a course", [("keep", text)]))
        self.assertIsNone(duplicate_passage(text, [("other", "credential rotation canary release recovery " * 40)]))

    def test_repeat_is_rejected_before_audio(self):
        text = " ".join(f"database connection operation{i} timeout evidence" for i in range(20))
        self.record("keep", text)
        generated = self.fixture.client.post("/api/v1/daily-generation/2026-10-01").json()
        topic = next(item for item in generated["topics"] if item["kind"] == "AI_ORIGINAL")
        lesson = self.service.generator.generate_lesson("stub")
        lesson["passage"] = text
        with patch.object(self.service.generator, "generate_lesson", return_value=lesson), patch.object(self.service, "audio_generator") as audio:
            self.service.process_lesson(topic["contentUuid"])
            audio.assert_not_called()
        content = self.service.get_content(topic["contentUuid"])
        self.assertEqual("FAILED", content["status"])
        self.assertIn("CONTENT_NOVELTY", content["failureReason"])

    def test_coverage_digest_summarizes_title_recap_and_terms(self):
        digest = coverage_digest({
            "title": "Pool exhaustion",
            "simplifiedPassage": "A slow query held every connection. " * 20,
            "vocabulary": [{"word": "pool"}, {"word": "timeout"}],
        })
        self.assertTrue(digest.startswith("Pool exhaustion: A slow query held every connection."))
        self.assertLess(len(digest), 320)
        self.assertTrue(digest.endswith("Key terms: pool, timeout."))
        dialogue = coverage_digest({"title": "Talk", "passage": "Host: Why retry?\n\nExpert: Because."})
        self.assertEqual("Talk: Why retry? Because.", dialogue)

    def test_prompt_lists_covered_lessons_instead_of_passage_openings(self):
        # Regression: the prompt used the first 220 characters of each passage,
        # which were mostly greetings and did not describe what was covered.
        with self.sessions() as session:
            session.add(ContentRecord(
                uuid="covered", title="Pool exhaustion", source_type="TEXT",
                source_text="Pool exhaustion", level="B1", status="READY",
                lesson_content=json.dumps({
                    "title": "Pool exhaustion under a slow report query",
                    "passage": "Host: Welcome back to the show, everyone.",
                    "simplifiedPassage": "A reporting query held all twenty connections.",
                    "vocabulary": [{"word": "saturation"}],
                }),
            ))
            session.commit()
        item = next(item for item in TOPIC_CATALOG if item.angle == "Diagnosis")
        response = self.fixture.client.post("/api/v1/dialogue-lessons", json={
            "topic": item.title, "category": item.category, "sourceMode": "AI",
        }).json()
        original = self.service.generator.generate_dialogue_lesson
        with patch.object(self.service.generator, "generate_dialogue_lesson", wraps=original) as generate:
            self.service.process_lesson(response["uuid"])
            prompt = generate.call_args.kwargs["prompt"]
        self.assertIn(
            "- Pool exhaustion under a slow report query: A reporting query held all "
            "twenty connections. Key terms: saturation.",
            prompt,
        )
        self.assertNotIn("Welcome back to the show", prompt)

    def test_catalog_supports_four_daily_reservations_for_seventy_days(self):
        start = date(2026, 7, 1)
        for offset in range(70):
            day = start + timedelta(days=offset)
            chosen = self.service.select_daily_topics(day, 4)
            self.assertEqual(4, len({item.problem for item in chosen}))
            with self.sessions() as session:
                for index, item in enumerate(chosen):
                    session.add(TopicCandidateRecord(
                        uuid=f"reserved-{offset}-{index}", plan_date=day,
                        kind="AI_ORIGINAL", category=item.category,
                        title=item.title, summary="", provider="test", score=1,
                        source_hash=self.service.topic_source_hash("AI_ORIGINAL", item.category, item.title),
                        status="READY", content_uuid=f"content-{offset}-{index}",
                    ))
                session.commit()

    def test_catalog_title_alone_injects_verification_objective(self):
        item = next(item for item in TOPIC_CATALOG if item.angle == "Verification")
        response = self.fixture.client.post("/api/v1/dialogue-lessons", json={
            "topic": item.title, "category": item.category, "sourceMode": "AI",
        }).json()
        original = self.service.generator.generate_dialogue_lesson
        with patch.object(self.service.generator, "generate_dialogue_lesson", wraps=original) as generate:
            self.service.process_lesson(response["uuid"])
            prompt = generate.call_args.kwargs["prompt"]
        self.assertIn("Build a reproducible experiment", prompt)
        self.assertIn("explicitly hypothetical production case", prompt)

    def test_direct_catalog_lesson_reserves_its_problem_for_daily_selection(self):
        day = self.service.local_today()
        chosen = self.service.select_daily_topics(day, 1)[0]
        self.service.create_dialogue_lesson(topic=chosen.title, category=chosen.category, source_mode="AI")
        self.assertNotIn(chosen.problem, [item.problem for item in self.service.select_daily_topics(day, 3)])
