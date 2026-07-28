package com.example.ttsapp

import com.example.ttsapp.core.ai.AiProviderException
import com.example.ttsapp.core.ai.HttpAiProvider
import com.example.ttsapp.core.ai.ProviderKind
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class HttpAiProviderTest {
    @Test
    fun parsesStructuredChatCompletion() = runTest {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setResponseCode(200).setBody(
                """{"choices":[{"message":{"content":"```json\n{\"title\":\"Threads\"}\n```"}}]}"""
            ))
            val provider = HttpAiProvider(
                ProviderKind.DEEPSEEK,
                server.url("/v1/").toString(),
                "model",
                "test-key",
            )

            assertTrue(provider.generateStructured("topic").rawJson.contains("\"Threads\""))
        }
    }

    @Test
    fun classifiesUnauthorizedResponse() = runTest {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setResponseCode(401).setBody("{}"))
            val provider = HttpAiProvider(
                ProviderKind.MOONSHOT,
                server.url("/v1/").toString(),
                "model",
                "bad-key",
            )

            val error = runCatching { provider.generateStructured("topic") }.exceptionOrNull()
            assertTrue(error is AiProviderException)
            assertEquals(
                AiProviderException.Category.UNAUTHORIZED,
                (error as AiProviderException).category,
            )
        }
    }
}
