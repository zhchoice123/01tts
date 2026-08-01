package com.example.ttsapp

import com.example.ttsapp.network.ApiClient
import com.example.ttsapp.network.AnswerResponse
import com.example.ttsapp.network.ContentResponse
import com.example.ttsapp.network.TaskResponse
import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Test

class TaskResponseTest {
    @Test
    fun apiUsesDirectIpServer() {
        assertEquals("http://42.192.62.145:8080/", ApiClient.BASE_URL)
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

    @Test
    fun speakingAnswerParsesDirectAudioEvaluation() {
        val answer = Gson().fromJson(
            """{
                "answerUuid":"answer-1",
                "taskUuid":"task-1",
                "status":"COMPLETED",
                "audioUrl":"/audio/answers/answer-1.m4a",
                "score":87,
                "evaluation":{
                    "overallScore":87,
                    "pronunciationScore":91,
                    "fluencyScore":86,
                    "intonationScore":82,
                    "pacingScore":85,
                    "relevanceScore":90,
                    "grammarScore":88,
                    "vocabularyScore":84,
                    "summary":"Clear and relevant.",
                    "strengths":["Clear consonants"],
                    "improvements":["Vary sentence stress"],
                    "practicePlan":["Shadow the model answer"],
                    "mode":"AUDIO_AND_TRANSCRIPT",
                    "model":"gpt-audio-1.5"
                }
            }""".trimIndent(),
            AnswerResponse::class.java,
        )

        assertEquals(91, answer.evaluation?.pronunciationScore)
        assertEquals("AUDIO_AND_TRANSCRIPT", answer.evaluation?.mode)
        assertEquals("Vary sentence stress", answer.evaluation?.improvements?.single())
    }
}
