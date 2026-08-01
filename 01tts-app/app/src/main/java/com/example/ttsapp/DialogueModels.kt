package com.example.ttsapp

import com.google.gson.JsonParser

data class DialogueTurn(
    val speaker: String,
    val text: String,
    val startMs: Long? = null,
    val endMs: Long? = null,
    val words: List<WordTiming> = emptyList(),
)

data class WordTiming(
    val text: String,
    val startMs: Long,
    val endMs: Long,
    val charStart: Int,
    val charEnd: Int,
)

const val WORD_HIGHLIGHT_GAP_MS = 120L

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
                words = parseWordTimings(
                    item.get("words")?.takeIf { it.isJsonArray }?.asJsonArray,
                    text,
                ),
            )
        }
    }.getOrDefault(emptyList())
}

fun parseLessonWordTimings(lessonContent: String?, passage: String): List<WordTiming> {
    if (lessonContent.isNullOrBlank() || passage.isBlank()) return emptyList()
    return runCatching {
        val root = JsonParser.parseString(lessonContent).asJsonObject
        parseWordTimings(
            root.get("wordTimings")?.takeIf { it.isJsonArray }?.asJsonArray,
            passage,
        )
    }.getOrDefault(emptyList())
}

private fun parseWordTimings(
    values: com.google.gson.JsonArray?,
    sourceText: String,
): List<WordTiming> {
    if (values == null) return emptyList()
    return values.mapNotNull { element ->
        runCatching {
            val item = element.asJsonObject
            val text = item.get("text")?.asString.orEmpty()
            val startMs = item.get("startMs")?.asLong ?: return@runCatching null
            val endMs = item.get("endMs")?.asLong ?: return@runCatching null
            val charStart = item.get("charStart")?.asInt ?: return@runCatching null
            val charEnd = item.get("charEnd")?.asInt ?: return@runCatching null
            WordTiming(text, startMs, endMs, charStart, charEnd)
                .takeIf {
                    text.isNotBlank() &&
                        startMs >= 0 &&
                        endMs > startMs &&
                        charStart >= 0 &&
                        charEnd > charStart &&
                        charEnd <= sourceText.length
                }
        }.getOrNull()
    }.sortedBy { it.startMs }
}

fun activeWordIndex(
    words: List<WordTiming>,
    positionMs: Long,
    maxGapMs: Long = WORD_HIGHLIGHT_GAP_MS,
): Int {
    if (words.isEmpty()) return -1
    if (positionMs < words.first().startMs) return -1

    var low = 0
    var high = words.lastIndex
    var lastEndedIndex = -1
    while (low <= high) {
        val middle = (low + high).ushr(1)
        val word = words[middle]
        when {
            positionMs < word.startMs -> high = middle - 1
            positionMs >= word.endMs -> {
                lastEndedIndex = maxOf(lastEndedIndex, middle)
                low = middle + 1
            }
            else -> return middle
        }
    }

    if (lastEndedIndex != -1) {
        val elapsedSinceEnd = positionMs - words[lastEndedIndex].endMs
        if (elapsedSinceEnd <= maxGapMs) {
            return lastEndedIndex
        }
    }
    return -1
}

fun activeDialogueWordIndex(
    turns: List<DialogueTurn>,
    activeTurnIndex: Int,
    positionMs: Long,
): Int = turns.getOrNull(activeTurnIndex)?.words?.let { words ->
    activeWordIndex(words, positionMs)
} ?: -1

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
