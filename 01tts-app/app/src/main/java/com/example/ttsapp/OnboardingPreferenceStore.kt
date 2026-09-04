package com.example.ttsapp

import android.content.Context

data class OnboardingState(
    val completed: Boolean = false,
    val goal: String = "TECHNICAL_ENGLISH",
    val level: String = "B1",
    val dailyMinutes: Int = 20,
    val completedAt: String? = null,
)

interface OnboardingPreferenceStore {
    fun load(hasExistingUserData: Boolean = false): OnboardingState
    fun save(state: OnboardingState)
}

class InMemoryOnboardingPreferenceStore(
    private var state: OnboardingState = OnboardingState(),
) : OnboardingPreferenceStore {
    override fun load(hasExistingUserData: Boolean): OnboardingState {
        if (!state.completed && hasExistingUserData) {
            state = state.copy(completed = true)
        }
        return state
    }

    override fun save(state: OnboardingState) {
        this.state = state
    }
}

class PreferencesOnboardingPreferenceStore(context: Context) : OnboardingPreferenceStore {
    private val preferences =
        context.getSharedPreferences("onboarding-settings", Context.MODE_PRIVATE)

    override fun load(hasExistingUserData: Boolean): OnboardingState {
        val hasSavedState = preferences.contains(COMPLETED_KEY)
        if (!hasSavedState && hasExistingUserData) {
            val migrated = OnboardingState(completed = true)
            save(migrated)
            return migrated
        }
        return OnboardingState(
            completed = preferences.getBoolean(COMPLETED_KEY, false),
            goal = preferences.getString(GOAL_KEY, "TECHNICAL_ENGLISH").orEmpty()
                .takeIf { it in VALID_GOALS } ?: "TECHNICAL_ENGLISH",
            level = preferences.getString(LEVEL_KEY, "B1").orEmpty()
                .takeIf { it in VALID_LEVELS } ?: "B1",
            dailyMinutes = preferences.getInt(MINUTES_KEY, 20)
                .takeIf { it in VALID_MINUTES } ?: 20,
            completedAt = preferences.getString(COMPLETED_AT_KEY, null),
        )
    }

    override fun save(state: OnboardingState) {
        preferences.edit()
            .putBoolean(COMPLETED_KEY, state.completed)
            .putString(GOAL_KEY, state.goal)
            .putString(LEVEL_KEY, state.level)
            .putInt(MINUTES_KEY, state.dailyMinutes)
            .apply {
                state.completedAt?.let { putString(COMPLETED_AT_KEY, it) }
                    ?: remove(COMPLETED_AT_KEY)
            }
            .apply()
    }

    private companion object {
        const val COMPLETED_KEY = "completed"
        const val GOAL_KEY = "goal"
        const val LEVEL_KEY = "level"
        const val MINUTES_KEY = "daily-minutes"
        const val COMPLETED_AT_KEY = "completed-at"
        val VALID_GOALS = setOf("TECHNICAL_ENGLISH", "GENERAL_ENGLISH", "SPEAKING")
        val VALID_LEVELS = setOf("A2", "B1", "B2", "C1")
        val VALID_MINUTES = setOf(10, 20, 30)
    }
}
