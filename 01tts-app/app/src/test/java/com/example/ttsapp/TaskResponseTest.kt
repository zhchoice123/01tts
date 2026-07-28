package com.example.ttsapp

import com.example.ttsapp.network.ApiClient
import com.example.ttsapp.network.ContentResponse
import com.example.ttsapp.network.TaskResponse
import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Test

class TaskResponseTest {
    @Test
    fun apiUsesCloudServer() {
        assertEquals("https://api.zhchoice.xyz/", ApiClient.BASE_URL)
    }

    @Test
    fun completedTaskKeepsAudioUrl() {
        val task = TaskResponse(
            "id", "prompt", "voice", "medium", "COMPLETED", "/audio/id.mp3")
        assertEquals("/audio/id.mp3", task.audioUrl)
    }

    @Test
    fun questionsKeepCorrectAnswerForFeedback() {
        val questions = parseQuestions(
            """[{"type":"multiple_choice","question":"Pick one","options":["A","B"],"answer":"B"}]"""
        )

        assertEquals("B", questions.single().answer)
        assertEquals(listOf("A", "B"), questions.single().availableOptions)
    }

    @Test
    fun acceptedLongLessonResponseUsesSafeContentDefaults() {
        val content = Gson().fromJson(
            """{
                "uuid":"long-1",
                "title":"Backend English",
                "status":"GENERATING",
                "profile":"BACKEND_DAILY_10MIN",
                "category":"BACKEND",
                "voice":"en-US-AvaNeural",
                "sourceMode":"AUTO",
                "estimatedMinutes":10
            }""".trimIndent(),
            ContentResponse::class.java,
        )

        assertEquals("LONG_LESSON", content.sourceType)
        assertEquals("B1", content.level)
        assertEquals(10, content.estimatedMinutes)
    }
}
