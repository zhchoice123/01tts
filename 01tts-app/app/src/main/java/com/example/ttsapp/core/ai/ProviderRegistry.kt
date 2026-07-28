package com.example.ttsapp.core.ai

import com.example.ttsapp.BuildConfig

object ProviderRegistry {
    internal const val DEEPSEEK_MODEL = "deepseek-v4-flash"
    internal const val MOONSHOT_MODEL = "kimi-k3"

    fun create(kind: ProviderKind): AiProvider = when (kind) {
        ProviderKind.DEEPSEEK -> HttpAiProvider(
            kind,
            "https://api.deepseek.com/v1",
            DEEPSEEK_MODEL,
            BuildConfig.DEEPSEEK_API_KEY,
        )
        ProviderKind.MOONSHOT -> HttpAiProvider(
            kind,
            "https://api.moonshot.cn/v1",
            MOONSHOT_MODEL,
            BuildConfig.MOONSHOT_API_KEY,
        )
        ProviderKind.OPENAI -> HttpAiProvider(
            kind,
            "https://api.openai.com/v1",
            "gpt-4.1-mini",
            BuildConfig.OPENAI_API_KEY,
        )
    }
}
