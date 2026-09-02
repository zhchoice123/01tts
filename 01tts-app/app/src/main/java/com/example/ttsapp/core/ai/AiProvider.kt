package com.example.ttsapp.core.ai

import kotlinx.coroutines.flow.Flow

enum class ProviderKind {
    DEEPSEEK,
    OPENAI,
}

data class ProviderHealth(
    val available: Boolean,
    val message: String,
)

data class GeneratedLesson(
    val rawJson: String,
)

interface AiProvider {
    val kind: ProviderKind
    fun streamChat(prompt: String): Flow<String>
    suspend fun generateStructured(prompt: String): GeneratedLesson
    suspend fun testConnection(): ProviderHealth
}

class AiProviderException(
    val category: Category,
    message: String,
    cause: Throwable? = null,
) : RuntimeException(message, cause) {
    enum class Category {
        UNAUTHORIZED,
        RATE_LIMITED,
        TIMEOUT,
        INVALID_RESPONSE,
        NETWORK,
    }
}
