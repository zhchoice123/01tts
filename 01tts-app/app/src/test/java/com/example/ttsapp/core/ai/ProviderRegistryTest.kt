package com.example.ttsapp.core.ai

import org.junit.Assert.assertEquals
import org.junit.Test

class ProviderRegistryTest {
    @Test
    fun deepSeekUsesSupportedModel() {
        assertEquals("deepseek-v4-flash", ProviderRegistry.DEEPSEEK_MODEL)
    }
}
