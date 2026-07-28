package com.example.ttsapp

import android.content.Context
import com.example.ttsapp.network.AnswerResponse
import com.example.ttsapp.network.TaskResponse
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

data class LessonHistoryEntry(
    val task: TaskResponse,
    val answer: AnswerResponse? = null,
    val quizCorrect: Int? = null,
    val quizTotal: Int? = null,
)

interface LessonHistoryStore {
    fun load(): List<LessonHistoryEntry>
    fun save(entries: List<LessonHistoryEntry>)
}

class InMemoryLessonHistoryStore : LessonHistoryStore {
    private var entries = emptyList<LessonHistoryEntry>()

    override fun load(): List<LessonHistoryEntry> = entries

    override fun save(entries: List<LessonHistoryEntry>) {
        this.entries = entries
    }
}

class PreferencesLessonHistoryStore(context: Context) : LessonHistoryStore {
    private val preferences =
        context.getSharedPreferences("lesson-history", Context.MODE_PRIVATE)
    private val gson = Gson()

    override fun load(): List<LessonHistoryEntry> {
        preferences.getString("entries", null)?.let { json ->
            return runCatching {
                gson.fromJson<List<LessonHistoryEntry>>(
                    json,
                    object : TypeToken<List<LessonHistoryEntry>>() {}.type,
                )
            }.getOrDefault(emptyList())
        }

        // One-time compatibility path for APKs that stored only TaskResponse objects.
        val legacyJson = preferences.getString("tasks", null) ?: return emptyList()
        return runCatching {
            gson.fromJson<List<TaskResponse>>(
                legacyJson,
                object : TypeToken<List<TaskResponse>>() {}.type,
            ).map(::LessonHistoryEntry)
        }.getOrDefault(emptyList())
    }

    override fun save(entries: List<LessonHistoryEntry>) {
        preferences.edit()
            .putString("entries", gson.toJson(entries.take(20)))
            .remove("tasks")
            .apply()
    }
}
