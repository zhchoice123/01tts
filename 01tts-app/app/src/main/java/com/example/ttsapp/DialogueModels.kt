package com.example.ttsapp

import com.google.gson.JsonParser

data class DialogueTurn(
    val speaker: String,
    val text: String,
    val startMs: Long? = null,
    val endMs: Long? = null,
)

fun parseDialogue(lessonContent: String?): List<DialogueTurn> {
    if (lessonContent.isNullOrBlank()) return emptyList()
    return runCatching {
        val dialogue = JsonParser.parseString(lessonContent)
            .asJsonObject
            .getAsJsonArray("dialogue")
            ?: return@runCatching emptyList()
        dialogue.mapNotNull { element ->
            val item = element.asJsonObject
            val speaker = item.get("speaker")?.asString.orEmpty().uppercase()
            val text = item.get("text")?.asString.orEmpty().trim()
            if (text.isBlank()) return@mapNotNull null
            DialogueTurn(
                speaker = speaker.ifBlank { "SPEAKER" },
                text = text,
                startMs = item.get("startMs")?.takeUnless { it.isJsonNull }?.asLong,
                endMs = item.get("endMs")?.takeUnless { it.isJsonNull }?.asLong,
            )
        }
    }.getOrDefault(emptyList())
}

fun activeDialogueIndex(turns: List<DialogueTurn>, positionMs: Long): Int {
    if (turns.isEmpty()) return -1
    val timed = turns.withIndex().filter { it.value.startMs != null }
    if (timed.isEmpty()) return -1
    val containing = timed.lastOrNull { indexed ->
        val turn = indexed.value
        positionMs >= (turn.startMs ?: Long.MAX_VALUE) &&
            (turn.endMs == null || positionMs < turn.endMs)
    }
    if (containing != null) return containing.index
    return timed.lastOrNull {
        it.value.endMs == null && positionMs >= (it.value.startMs ?: Long.MAX_VALUE)
    }?.index ?: -1
}
