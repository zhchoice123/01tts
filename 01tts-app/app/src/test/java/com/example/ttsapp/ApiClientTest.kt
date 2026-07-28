package com.example.ttsapp

import com.example.ttsapp.network.ApiClient
import org.junit.Assert.assertEquals
import org.junit.Test

class ApiClientTest {
    @Test
    fun relativeMediaUrlUsesConfiguredServer() {
        assertEquals(
            "${ApiClient.FALLBACK_BASE_URL}audio/lesson.mp3",
            ApiClient.resolveMediaUrl("/audio/lesson.mp3"),
        )
    }

    @Test
    fun absoluteMediaUrlIsNotPrefixedAgain() {
        val url = "https://cdn.example.com/audio/lesson.mp3"
        assertEquals(url, ApiClient.resolveMediaUrl(url))
    }
}
