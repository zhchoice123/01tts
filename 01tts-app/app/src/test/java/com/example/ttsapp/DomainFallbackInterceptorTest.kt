package com.example.ttsapp

import com.example.ttsapp.network.DomainFallbackInterceptor
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Test

class DomainFallbackInterceptorTest {
    @Test
    fun retriesFallbackServerWhenPrimaryConnectionCloses() {
        val primary = MockWebServer()
        val fallback = MockWebServer()
        primary.start()
        fallback.start()
        fallback.enqueue(MockResponse().setResponseCode(200).setBody("""{"status":"READY"}"""))
        val primaryUrl = primary.url("/api/v1/daily-plans/today")
        primary.shutdown()

        try {
            val client = OkHttpClient.Builder()
                .addInterceptor(
                    DomainFallbackInterceptor(
                        primaryHost = primaryUrl.host,
                        fallbackBaseUrl = fallback.url("/").toString(),
                    )
                )
                .build()

            client.newCall(Request.Builder().url(primaryUrl).build()).execute().use {
                assertEquals(200, it.code)
                assertEquals("/api/v1/daily-plans/today", fallback.takeRequest().path)
            }
        } finally {
            fallback.shutdown()
        }
    }
}
