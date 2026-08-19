package com.example.ttsapp

import android.content.Context

data class TtsPreference(val provider: String, val voice: String)

interface TtsPreferenceStore {
    fun load(): TtsPreference
    fun save(preference: TtsPreference)
}

class InMemoryTtsPreferenceStore(
    private var preference: TtsPreference = TtsPreference("openai", "openai:nova"),
) : TtsPreferenceStore {
    override fun load(): TtsPreference = preference
    override fun save(preference: TtsPreference) { this.preference = preference }
}

class PreferencesTtsPreferenceStore(context: Context) : TtsPreferenceStore {
    private val preferences = context.getSharedPreferences("tts-settings", Context.MODE_PRIVATE)

    override fun load(): TtsPreference = TtsPreference(
        provider = preferences.getString("provider", "openai").orEmpty()
            .takeIf { it == "openai" || it == "aliyun" } ?: "openai",
        voice = preferences.getString("voice", "openai:nova").orEmpty(),
    )

    override fun save(preference: TtsPreference) {
        preferences.edit()
            .putString("provider", preference.provider)
            .putString("voice", preference.voice)
            .apply()
    }
}
