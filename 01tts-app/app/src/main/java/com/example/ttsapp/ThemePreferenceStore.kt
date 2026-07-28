package com.example.ttsapp

import android.content.Context

interface ThemePreferenceStore {
    fun load(): String
    fun save(themeId: String)
}

class InMemoryThemePreferenceStore(
    private var themeId: String = AppThemeStyle.DEEP_SPACE_CYBER.id,
) : ThemePreferenceStore {
    override fun load(): String = themeId

    override fun save(themeId: String) {
        this.themeId = themeId
    }
}

class PreferencesThemePreferenceStore(context: Context) : ThemePreferenceStore {
    private val preferences =
        context.getSharedPreferences("appearance-settings", Context.MODE_PRIVATE)

    override fun load(): String =
        AppThemeStyle.fromId(
            preferences.getString("theme-id", AppThemeStyle.DEEP_SPACE_CYBER.id).orEmpty(),
        ).id

    override fun save(themeId: String) {
        preferences.edit()
            .putString("theme-id", AppThemeStyle.fromId(themeId).id)
            .apply()
    }
}
