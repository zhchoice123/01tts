package com.example.ttsapp

import com.example.ttsapp.network.LearningProgressRequest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LearningProgressStoreTest {
    @Test
    fun inMemoryStoreKeepsProgressByContent() {
        val store = InMemoryLearningProgressStore()
        store.save(
            LearningProgressRequest(
                clientId = "client",
                contentUuid = "lesson",
                positionMs = 19_000,
            )
        )

        assertEquals(19_000L, store.load("lesson")?.positionMs)
    }

    @Test
    fun generatedInstallationIdIsOpaqueUuid() {
        val value = newInstallationClientId()

        assertTrue(
            value.matches(
                Regex("[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
            )
        )
    }
}
