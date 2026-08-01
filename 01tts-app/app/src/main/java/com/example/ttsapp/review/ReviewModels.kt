package com.example.ttsapp.review

/** API response for the review generated after a lesson is completed. */
data class LessonReviewReportResponse(
    val clientId: String = "",
    val contentUuid: String = "",
    val overallScore: Int = 0,
    val dimensions: List<ReviewDimension> = emptyList(),
    val weakPoints: List<ReviewWeakPoint> = emptyList(),
    val nextActions: List<String> = emptyList(),
    val generatedAt: String = "",
)

data class ReviewDimension(
    val key: String = "",
    val label: String = "",
    val score: Int? = null,
    val status: String = "",
)

data class ReviewWeakPoint(
    val kind: String = "",
    val title: String = "",
    val detail: String = "",
    val priority: Int = 0,
)

/** API response for a learner's due review work on a given day. */
data class ReviewQueueResponse(
    val clientId: String = "",
    val date: String = "",
    val totalCount: Int = 0,
    val estimatedMinutes: Int = 0,
    val items: List<ReviewQueueItem> = emptyList(),
)

data class ReviewQueueItem(
    val id: String = "",
    val type: String = "",
    val contentUuid: String = "",
    val title: String = "",
    val reason: String = "",
    val priority: Int = 0,
    val dueAt: String? = null,
    val word: String? = null,
    val status: String? = null,
    val action: String? = null,
)

sealed interface ReviewContentState<out T> {
    data object Loading : ReviewContentState<Nothing>
    data object Empty : ReviewContentState<Nothing>
    data class Error(val message: String) : ReviewContentState<Nothing>
    data class Data<T>(val value: T) : ReviewContentState<T>
}

fun LessonReviewReportResponse.asContentState(): ReviewContentState<LessonReviewReportResponse> =
    if (dimensions.isEmpty() && weakPoints.isEmpty() && nextActions.isEmpty()) {
        ReviewContentState.Empty
    } else {
        ReviewContentState.Data(this)
    }

fun ReviewQueueResponse.asContentState(): ReviewContentState<ReviewQueueResponse> =
    if (items.isEmpty()) ReviewContentState.Empty else ReviewContentState.Data(this)

fun normalizedReviewScore(score: Int?): Int? = score?.coerceIn(0, 100)

/**
 * Lower positive integer values represent more urgent work (1 is highest).
 * Equal priorities keep a
 * deterministic order using due date and id so the UI does not jump on refresh.
 */
fun prioritizedReviewItems(items: List<ReviewQueueItem>): List<ReviewQueueItem> =
    items.sortedWith(
        compareBy<ReviewQueueItem> { it.priority.takeIf { value -> value > 0 } ?: Int.MAX_VALUE }
            .thenBy { it.dueAt.isNullOrBlank() }
            .thenBy { it.dueAt.orEmpty() }
            .thenBy { it.id },
    )

fun reviewStatusText(status: String?, isChinese: Boolean): String = when (status.orEmpty().trim().uppercase()) {
    "MASTERED", "COMPLETED", "DONE" -> if (isChinese) "已掌握" else "Mastered"
    "IN_PROGRESS", "LEARNING" -> if (isChinese) "复习中" else "In progress"
    "WEAK", "NEEDS_WORK" -> if (isChinese) "需要加强" else "Needs work"
    "STRONG" -> if (isChinese) "表现稳定" else "Strong"
    else -> if (isChinese) "待复习" else "To review"
}

fun ReviewDimension.displayLabel(): String = label.ifBlank {
    key.replace('_', ' ')
        .lowercase()
        .replaceFirstChar { it.titlecase() }
        .ifBlank { "Score" }
}

fun ReviewQueueItem.displayTitle(): String {
    val fallbackTitle = title.ifBlank { type.replace('_', ' ').ifBlank { "Review item" } }
    return word?.takeIf { it.isNotBlank() }
        ?.let { wordValue -> if (title.isBlank()) wordValue else "$fallbackTitle · $wordValue" }
        ?: fallbackTitle
}

fun queueSummaryText(queue: ReviewQueueResponse, isChinese: Boolean): String {
    val count = queue.items.size.takeIf { it > 0 } ?: queue.totalCount.coerceAtLeast(0)
    val minutes = queue.estimatedMinutes.coerceAtLeast(0)
    return if (isChinese) {
        "${count} 项 · 约 ${minutes} 分钟"
    } else {
        "$count items · about $minutes min"
    }
}
