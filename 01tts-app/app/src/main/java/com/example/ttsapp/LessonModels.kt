package com.example.ttsapp

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

data class LessonQuestion(
    val type: String = "",
    val question: String = "",
    val prompt: String = "",
    val choices: List<String> = emptyList(),
    val options: List<String> = emptyList(),
    val answer: String = "",
) {
    val wording: String
        get() = question.ifBlank { prompt }

    val availableOptions: List<String>
        get() = choices.ifEmpty { options }
}

fun parseQuestions(json: String?): List<LessonQuestion> {
    if (json.isNullOrBlank()) return emptyList()
    return runCatching {
        Gson().fromJson<List<LessonQuestion>>(
            json,
            object : TypeToken<List<LessonQuestion>>() {}.type,
        )
    }.getOrDefault(emptyList())
}

data class LessonVocabulary(
    val word: String = "",
    val phonetic: String = "",
    val definition: String = "",
    val meaningZh: String = "",
    val example: String = "",
    val collocations: List<String> = emptyList(),
    val usageNotes: String = "",
)

fun parseVocabulary(json: String?): List<LessonVocabulary> {
    if (json.isNullOrBlank()) return emptyList()
    return runCatching {
        Gson().fromJson<List<LessonVocabulary>>(
            json,
            object : TypeToken<List<LessonVocabulary>>() {}.type,
        )
    }.getOrDefault(emptyList()).filter { it.word.isNotBlank() }
}
