package com.example.ttsapp

import com.example.ttsapp.network.LearningDashboardResponse
import com.example.ttsapp.network.LearningProgressRequest
import com.example.ttsapp.network.TaskApi
import com.google.gson.Gson
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

class LearningApiContractTest {
    @Test
    fun progressPutUsesPlannedPathAndJsonBody() = runTest {
        MockWebServer().use { server ->
            server.enqueue(
                MockResponse().setBody(
                    """{"clientId":"00000000-0000-4000-8000-000000000042","contentUuid":"10000000-0000-4000-8000-000000000042","positionMs":24000,"durationMs":90000}"""
                ).addHeader("Content-Type", "application/json")
            )
            val api = Retrofit.Builder()
                .baseUrl(server.url("/"))
                .addConverterFactory(GsonConverterFactory.create())
                .build()
                .create(TaskApi::class.java)

            api.saveLearningProgress(
                LearningProgressRequest(
                    clientId = "00000000-0000-4000-8000-000000000042",
                    contentUuid = "10000000-0000-4000-8000-000000000042",
                    positionMs = 24_000,
                    durationMs = 90_000,
                )
            )

            val request = server.takeRequest()
            assertEquals("PUT", request.method)
            assertEquals("/api/v1/learning/progress", request.path)
            assertTrue(request.body.readUtf8().contains("\"positionMs\":24000"))
        }
    }

    @Test
    fun dashboardDefaultsKeepOlderOrPartialResponsesSafe() {
        val dashboard = Gson().fromJson(
            """{"days":7,"listeningMinutes":47,"completedLessons":4}""",
            LearningDashboardResponse::class.java,
        )

        assertEquals(47, dashboard.listeningMinutes)
        assertEquals(0, dashboard.quizTotal)
        assertEquals(0L, dashboard.latestPositionMs)
    }
}
