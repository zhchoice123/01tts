package com.example.ttsapp.review

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AssignmentTurnedIn
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.Inbox
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.School
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

@Composable
fun LessonReviewReportCard(
    state: ReviewContentState<LessonReviewReportResponse>,
    modifier: Modifier = Modifier,
    languageId: String = "en",
    onRetry: () -> Unit = {},
    onNextAction: (String) -> Unit = {},
) {
    val isChinese = languageId.startsWith("zh", ignoreCase = true)
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 20.dp, vertical = 18.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            ReviewSectionHeader(
                title = if (isChinese) "课程复盘" else "Lesson review",
                subtitle = if (isChinese) "看清薄弱点，再决定下一步" else "Turn weak points into the next practice",
            )
            when (state) {
                ReviewContentState.Loading -> ReviewLoadingContent(
                    label = if (isChinese) "正在整理本节表现…" else "Preparing your lesson review…",
                )
                ReviewContentState.Empty -> ReviewEmptyContent(
                    label = if (isChinese) "完成课程后，这里会生成学习报告。" else "Complete a lesson to generate your review.",
                )
                is ReviewContentState.Error -> ReviewErrorContent(
                    message = state.message,
                    retryLabel = if (isChinese) "重新加载" else "Try again",
                    onRetry = onRetry,
                )
                is ReviewContentState.Data -> ReviewReportData(
                    report = state.value,
                    isChinese = isChinese,
                    onNextAction = onNextAction,
                )
            }
        }
    }
}

@Composable
fun DailyReviewQueueSection(
    state: ReviewContentState<ReviewQueueResponse>,
    modifier: Modifier = Modifier,
    languageId: String = "en",
    onRetry: () -> Unit = {},
    onItemClick: (ReviewQueueItem) -> Unit = {},
) {
    val isChinese = languageId.startsWith("zh", ignoreCase = true)
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        ReviewSectionHeader(
            title = if (isChinese) "今日复习" else "Today's review",
            subtitle = if (isChinese) "优先处理最需要巩固的内容" else "Start with the skills that need reinforcement",
        )
        when (state) {
            ReviewContentState.Loading -> ReviewQueueLoading()
            ReviewContentState.Empty -> Surface(
                color = MaterialTheme.colorScheme.surfaceContainerLow,
                shape = RoundedCornerShape(18.dp),
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
            ) {
                ReviewEmptyContent(
                    label = if (isChinese) "今天没有待复习内容。" else "You're all caught up for today.",
                    modifier = Modifier.padding(18.dp),
                )
            }
            is ReviewContentState.Error -> Surface(
                color = MaterialTheme.colorScheme.errorContainer,
                shape = RoundedCornerShape(18.dp),
            ) {
                ReviewErrorContent(
                    message = state.message,
                    retryLabel = if (isChinese) "重新加载" else "Try again",
                    onRetry = onRetry,
                    modifier = Modifier.padding(18.dp),
                )
            }
            is ReviewContentState.Data -> ReviewQueueData(
                queue = state.value,
                isChinese = isChinese,
                onItemClick = onItemClick,
            )
        }
    }
}

@Composable
private fun ReviewReportData(
    report: LessonReviewReportResponse,
    isChinese: Boolean,
    onNextAction: (String) -> Unit,
) {
    Row(verticalAlignment = Alignment.Bottom) {
        Text(
            text = normalizedReviewScore(report.overallScore).toString(),
            style = MaterialTheme.typography.displaySmall,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.primary,
        )
        Text(
            text = "/100",
            modifier = Modifier.padding(bottom = 6.dp, start = 4.dp),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }

    if (report.dimensions.isNotEmpty()) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            report.dimensions.forEach { dimension ->
                DimensionRow(dimension = dimension, isChinese = isChinese)
            }
        }
    }

    if (report.weakPoints.isNotEmpty()) {
        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
        Text(
            text = if (isChinese) "需要巩固" else "Focus areas",
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.SemiBold,
        )
        report.weakPoints.sortedBy { it.priority.takeIf { value -> value > 0 } ?: Int.MAX_VALUE }.take(3).forEach { weakPoint ->
            Surface(
                color = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.45f),
                shape = RoundedCornerShape(12.dp),
            ) {
                Column(modifier = Modifier.padding(horizontal = 14.dp, vertical = 11.dp)) {
                    Text(weakPoint.title, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Medium)
                    if (weakPoint.detail.isNotBlank()) {
                        Text(
                            weakPoint.detail,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
    }

    report.nextActions.firstOrNull()?.let { action ->
        Button(onClick = { onNextAction(action) }, modifier = Modifier.fillMaxWidth()) {
            Icon(Icons.Outlined.School, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text(action, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun DimensionRow(dimension: ReviewDimension, isChinese: Boolean) {
    val score = normalizedReviewScore(dimension.score)
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                dimension.displayLabel(),
                modifier = Modifier.weight(1f),
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
            )
            Text(
                score?.let { "$it" } ?: reviewStatusText(dimension.status, isChinese),
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (score != null) {
            LinearProgressIndicator(
                progress = { score / 100f },
                modifier = Modifier.fillMaxWidth().height(5.dp),
                color = MaterialTheme.colorScheme.primary,
                trackColor = MaterialTheme.colorScheme.surfaceVariant,
            )
        }
    }
}

@Composable
private fun ReviewQueueData(
    queue: ReviewQueueResponse,
    isChinese: Boolean,
    onItemClick: (ReviewQueueItem) -> Unit,
) {
    Text(
        queueSummaryText(queue, isChinese),
        style = MaterialTheme.typography.labelLarge,
        color = MaterialTheme.colorScheme.primary,
    )
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        prioritizedReviewItems(queue.items).forEachIndexed { index, item ->
            Surface(
                color = MaterialTheme.colorScheme.surfaceContainerLow,
                shape = RoundedCornerShape(16.dp),
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
            ) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Surface(
                            color = MaterialTheme.colorScheme.primaryContainer,
                            shape = RoundedCornerShape(8.dp),
                        ) {
                            Text(
                                text = "${index + 1}",
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onPrimaryContainer,
                            )
                        }
                        Spacer(Modifier.width(10.dp))
                        Text(
                            item.displayTitle(),
                            modifier = Modifier.weight(1f),
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            reviewStatusText(item.status, isChinese),
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    if (item.reason.isNotBlank()) {
                        Text(
                            item.reason,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    OutlinedButton(
                        onClick = { onItemClick(item) },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(item.action?.takeIf { it.isNotBlank() } ?: if (isChinese) "开始复习" else "Start review")
                    }
                }
            }
        }
    }
}

@Composable
private fun ReviewSectionHeader(title: String, subtitle: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(
            Icons.Outlined.AssignmentTurnedIn,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(26.dp),
        )
        Spacer(Modifier.width(12.dp))
        Column {
            Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
            Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun ReviewLoadingContent(label: String, modifier: Modifier = Modifier) {
    Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        repeat(3) { index ->
            Surface(
                modifier = Modifier
                    .fillMaxWidth(if (index == 2) 0.62f else 1f)
                    .height(if (index == 0) 38.dp else 12.dp),
                color = MaterialTheme.colorScheme.surfaceVariant,
                shape = RoundedCornerShape(8.dp),
            ) {}
        }
    }
}

@Composable
private fun ReviewQueueLoading() {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        repeat(2) {
            Surface(
                modifier = Modifier.fillMaxWidth().height(104.dp),
                color = MaterialTheme.colorScheme.surfaceContainerLow,
                shape = RoundedCornerShape(16.dp),
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
            ) {
                ReviewLoadingContent(label = "", modifier = Modifier.padding(16.dp))
            }
        }
    }
}

@Composable
private fun ReviewEmptyContent(label: String, modifier: Modifier = Modifier) {
    Row(modifier = modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Icon(Icons.Outlined.Inbox, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.width(10.dp))
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun ReviewErrorContent(
    message: String,
    retryLabel: String,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.ErrorOutline, contentDescription = null, tint = MaterialTheme.colorScheme.error)
            Spacer(Modifier.width(10.dp))
            Text(
                message.ifBlank { retryLabel },
                modifier = Modifier.weight(1f),
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        OutlinedButton(onClick = onRetry, modifier = Modifier.fillMaxWidth()) {
            Icon(Icons.Outlined.Refresh, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text(retryLabel)
        }
    }
}
