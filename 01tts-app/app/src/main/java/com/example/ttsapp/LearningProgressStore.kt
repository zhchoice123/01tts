package com.example.ttsapp

import android.content.Context
import com.example.ttsapp.network.LearningProgressRequest
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.util.UUID

internal fun newInstallationClientId(): String = UUID.randomUUID().toString()

interface ClientIdStore {
    fun loadOrCreate(): String
}

class InMemoryClientIdStore(
    private var value: String = "00000000-0000-4000-8000-000000000001",
) : ClientIdStore {
    override fun loadOrCreate(): String = value
}

class PreferencesClientIdStore(context: Context) : ClientIdStore {
    private val preferences =
        context.getSharedPreferences("learning-profile", Context.MODE_PRIVATE)

    override fun loadOrCreate(): String {
        preferences.getString(CLIENT_ID_KEY, null)?.let { return it }
        return newInstallationClientId().also {
            preferences.edit().putString(CLIENT_ID_KEY, it).commit()
        }
    }

    private companion object {
        const val CLIENT_ID_KEY = "installation-client-id"
    }
}

interface LearningProgressStore {
    fun load(contentUuid: String): LearningProgressRequest?
    fun save(progress: LearningProgressRequest)
}

class InMemoryLearningProgressStore : LearningProgressStore {
    private val progressByContent = mutableMapOf<String, LearningProgressRequest>()

    override fun load(contentUuid: String): LearningProgressRequest? =
        progressByContent[contentUuid]

    override fun save(progress: LearningProgressRequest) {
        progressByContent[progress.contentUuid] = progress
    }
}

class PreferencesLearningProgressStore(context: Context) : LearningProgressStore {
    private val preferences =
        context.getSharedPreferences("learning-progress", Context.MODE_PRIVATE)
    private val gson = Gson()

    override fun load(contentUuid: String): LearningProgressRequest? =
        all()[contentUuid]

    override fun save(progress: LearningProgressRequest) {
        val updated = all().toMutableMap().apply { put(progress.contentUuid, progress) }
        preferences.edit().putString(PROGRESS_KEY, gson.toJson(updated)).apply()
    }

    private fun all(): Map<String, LearningProgressRequest> {
        val json = preferences.getString(PROGRESS_KEY, null) ?: return emptyMap()
        return runCatching {
            gson.fromJson<Map<String, LearningProgressRequest>>(
                json,
                object : TypeToken<Map<String, LearningProgressRequest>>() {}.type,
            )
        }.getOrDefault(emptyMap())
    }

    private companion object {
        const val PROGRESS_KEY = "progress-by-content"
    }
}
