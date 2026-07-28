package com.example.ttsapp

import android.content.Context

enum class AppLanguage(val id: String) {
    ENGLISH("en"),
    CHINESE("zh");

    companion object {
        fun fromId(id: String): AppLanguage = entries.find { it.id == id } ?: ENGLISH
    }
}

interface LanguagePreferenceStore {
    fun load(): String
    fun save(languageId: String)
}

class InMemoryLanguagePreferenceStore(
    private var languageId: String = AppLanguage.ENGLISH.id,
) : LanguagePreferenceStore {
    override fun load(): String = languageId

    override fun save(languageId: String) {
        this.languageId = AppLanguage.fromId(languageId).id
    }
}

class PreferencesLanguagePreferenceStore(context: Context) : LanguagePreferenceStore {
    private val preferences =
        context.getSharedPreferences("language-settings", Context.MODE_PRIVATE)

    override fun load(): String =
        AppLanguage.fromId(
            preferences.getString("language-id", AppLanguage.ENGLISH.id).orEmpty(),
        ).id

    override fun save(languageId: String) {
        preferences.edit()
            .putString("language-id", AppLanguage.fromId(languageId).id)
            .apply()
    }
}
