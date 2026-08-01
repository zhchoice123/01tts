package com.example.ttsapp.review

import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ReviewModelsTest {
    private val gson = Gson()

    @Test
    fun reportDeserializesFromApiJson() {
        val report = gson.fromJson(
            """
            {
              "clientId":"client-42",
              "contentUuid":"lesson-7",
              "overallScore":78,
              "dimensions":[
                {"key":"listening","label":"Listening","score":82,"status":"STRONG"},
                {"key":"speaking","label":"Speaking","score":null,"status":"NEEDS_WORK"}
              ],
              "weakPoints":[
                {"kind":"PHRASE","title":"Reduced sounds","detail":"Listen for weak forms.","priority":9}
              ],
              "nextActions":["Review reduced sounds"],
              "generatedAt":"2026-08-01T15:10:00+08:00"
            }
            """.trimIndent(),
            LessonReviewReportResponse::class.java,
        )

        assertEquals("lesson-7", report.contentUuid)
        assertEquals(78, report.overallScore)
        assertEquals(2, report.dimensions.size)
        assertNull(report.dimensions[1].score)
        assertEquals("Reduced sounds", report.weakPoints.single().title)
    }

    @Test
    fun queueDeserializationKeepsMissingOptionalFieldsSafe() {
        val queue = gson.fromJson(
            """
            {
              "clientId":"client-42",
              "date":"2026-08-01",
              "totalCount":1,
              "estimatedMinutes":4,
              "items":[{
                "id":"review-1",
                "type":"VOCABULARY",
                "contentUuid":"lesson-7",
                "title":"Technical phrase",
                "reason":"Missed twice",
                "priority":7
              }]
            }
            """.trimIndent(),
            ReviewQueueResponse::class.java,
        )

        val item = queue.items.single()
        assertNull(item.dueAt)
        assertNull(item.word)
        assertNull(item.status)
        assertNull(item.action)
        assertEquals("Technical phrase", item.displayTitle())
    }

    @Test
    fun emptyResponsesMapToEmptyContentState() {
        assertTrue(LessonReviewReportResponse().asContentState() is ReviewContentState.Empty)
        assertTrue(ReviewQueueResponse().asContentState() is ReviewContentState.Empty)
    }

    @Test
    fun prioritySortingUsesHighestPriorityFirstAndIsDeterministic() {
        val items = listOf(
            ReviewQueueItem(id = "late", title = "Late", priority = 1, dueAt = "2026-08-03"),
            ReviewQueueItem(id = "low", title = "Low", priority = 3, dueAt = "2026-08-01"),
            ReviewQueueItem(id = "early", title = "Early", priority = 1, dueAt = "2026-08-01"),
            ReviewQueueItem(id = "undated", title = "Undated", priority = 1),
        )

        assertEquals(
            listOf("early", "late", "undated", "low"),
            prioritizedReviewItems(items).map { it.id },
        )
    }

    @Test
    fun presentationTextHandlesScoresStatusesAndQueueSummary() {
        assertEquals(100, normalizedReviewScore(118))
        assertEquals(0, normalizedReviewScore(-6))
        assertNull(normalizedReviewScore(null))
        assertEquals("Needs work", reviewStatusText("needs_work", isChinese = false))
        assertEquals("已掌握", reviewStatusText("completed", isChinese = true))
        assertEquals(
            "2 items · about 6 min",
            queueSummaryText(
                ReviewQueueResponse(
                    totalCount = 8,
                    estimatedMinutes = 6,
                    items = listOf(ReviewQueueItem(id = "a"), ReviewQueueItem(id = "b")),
                ),
                isChinese = false,
            ),
        )
    }
}
