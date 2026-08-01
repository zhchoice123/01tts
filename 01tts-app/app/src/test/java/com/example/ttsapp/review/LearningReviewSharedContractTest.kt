package com.example.ttsapp.review

import com.google.gson.Gson
import com.google.gson.JsonObject
import java.nio.file.Files
import java.nio.file.Path
import kotlin.io.path.exists
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LearningReviewSharedContractTest {
    private val gson = Gson()

    @Test
    fun lessonReviewExpectedPayloadUsesAndroidModelsWithoutLosingNullScores() {
        val expected = loadContract("lesson_review_case.json").getAsJsonObject("expected")
        val report = gson.fromJson(expected, LessonReviewReportResponse::class.java)

        assertEquals("11111111-1111-4111-8111-111111111111", report.clientId)
        assertEquals("22222222-2222-4222-8222-222222222222", report.contentUuid)
        assertEquals(53, report.overallScore)
        assertEquals(listOf("listening", "comprehension", "vocabulary", "speaking"), report.dimensions.map { it.key })
        val speaking = report.dimensions.single { it.key == "speaking" }
        assertNull(speaking.score)
        assertEquals("NO_DATA", speaking.status)
        assertTrue(report.asContentState() is ReviewContentState.Data)
    }

    @Test
    fun reviewQueueExpectedPayloadKeepsOptionalFieldsAndPriorityOneHighest() {
        val expected = loadContract("review_queue_case.json").getAsJsonObject("expected")
        val queue = gson.fromJson(expected, ReviewQueueResponse::class.java)

        assertEquals(4, queue.totalCount)
        val lesson = queue.items.single { it.type == "LESSON" }
        assertNull(lesson.word)
        assertEquals("2026-08-01T08:00:00Z", lesson.dueAt)
        assertEquals("NEEDS_REVIEW", lesson.status)
        assertEquals("REVIEW_LESSON", lesson.action)

        val latency = queue.items.single { it.word == "latency" }
        assertEquals(1, latency.priority)
        assertEquals("NEW", latency.status)
        assertEquals("REVIEW_WORD", latency.action)
        assertEquals(
            listOf(1, 1, 2, 3),
            prioritizedReviewItems(queue.items).map { it.priority },
        )
        assertTrue(queue.asContentState() is ReviewContentState.Data)
    }

    @Test
    fun emptyQueueStillMapsToAnExplicitEmptyState() {
        assertTrue(
            ReviewQueueResponse(
                clientId = "11111111-1111-4111-8111-111111111111",
                date = "2026-08-01",
            ).asContentState() is ReviewContentState.Empty,
        )
    }

    private fun loadContract(fileName: String): JsonObject {
        val start = Path.of(System.getProperty("user.dir")).toAbsolutePath().normalize()
        val contractPath = generateSequence(start) { it.parent }
            .map { it.resolve("contracts/learning_review/$fileName") }
            .firstOrNull { it.exists() }
            ?: error("Cannot find shared learning-review contract $fileName from $start")
        return Files.newBufferedReader(contractPath).use { reader ->
            gson.fromJson(reader, JsonObject::class.java)
        }
    }
}
