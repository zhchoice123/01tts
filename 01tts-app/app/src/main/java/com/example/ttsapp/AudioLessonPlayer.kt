package com.example.ttsapp

import com.example.ttsapp.network.ApiClient
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Forward10
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Replay10
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import kotlinx.coroutines.delay

data class PlaybackSeekRequest(val id: Long, val positionMs: Long)

internal fun nextPlaybackSpeed(current: Float): Float = when (current) {
    0.8f -> 1f
    1f -> 1.2f
    else -> 0.8f
}

@androidx.annotation.OptIn(UnstableApi::class)
@Composable
fun AudioLessonPlayer(
    url: String,
    initialPositionMs: Long = 0,
    transcriptVisible: Boolean = true,
    seekRequest: PlaybackSeekRequest? = null,
    onToggleTranscript: () -> Unit = {},
    onPositionChanged: (positionMs: Long) -> Unit = {},
    onProgress: (positionMs: Long, durationMs: Long) -> Unit = { _, _ -> },
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    var position by remember(url) { mutableLongStateOf(0L) }
    var duration by remember(url) { mutableLongStateOf(0L) }
    var playing by remember(url) { mutableStateOf(false) }
    var dragging by remember(url) { mutableStateOf(false) }
    var speed by remember(url) { mutableFloatStateOf(1f) }
    var playbackError by remember(url) { mutableStateOf<String?>(null) }
    var lastReportedPosition by remember(url) { mutableLongStateOf(-1L) }
    var lastReportedDuration by remember(url) { mutableLongStateOf(-1L) }
    val player = remember(url) {
        val mediaSourceFactory = DefaultMediaSourceFactory(
            OkHttpDataSource.Factory(ApiClient.httpClient),
        )
        ExoPlayer.Builder(context)
            .setMediaSourceFactory(mediaSourceFactory)
            .build()
            .apply {
                setMediaItem(MediaItem.fromUri(url))
                prepare()
                if (initialPositionMs > 0) seekTo(initialPositionMs)
            }
    }

    DisposableEffect(player) {
        val listener = object : Player.Listener {
            override fun onIsPlayingChanged(isPlaying: Boolean) {
                playing = isPlaying
            }

            override fun onPlayerError(error: PlaybackException) {
                playbackError = "Audio could not be played. Check the network and retry."
            }
        }
        player.addListener(listener)
        onDispose {
            player.removeListener(listener)
            player.release()
        }
    }

    LaunchedEffect(seekRequest?.id) {
        seekRequest?.let {
            player.seekTo(it.positionMs.coerceAtLeast(0))
            position = it.positionMs.coerceAtLeast(0)
        }
    }

    LaunchedEffect(player) {
        while (true) {
            if (!dragging) {
                position = player.currentPosition.coerceAtLeast(0)
                onPositionChanged(position)
            }
            duration = player.duration.takeUnless { it == C.TIME_UNSET }?.coerceAtLeast(0) ?: 0
            if (
                lastReportedDuration != duration ||
                lastReportedPosition < 0 ||
                kotlin.math.abs(position - lastReportedPosition) >= 1_000
            ) {
                lastReportedPosition = position
                lastReportedDuration = duration
                onProgress(position, duration)
            }
            delay(if (playing) 100 else 250)
        }
    }

    Surface(
        modifier = modifier.fillMaxWidth(),
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = MaterialTheme.shapes.large,
        tonalElevation = 0.dp,
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("Lesson audio", style = MaterialTheme.typography.titleMedium)
            Text(
                "Streamed from your cloud library",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Slider(
                value = if (duration > 0) position.toFloat().coerceAtMost(duration.toFloat()) else 0f,
                onValueChange = {
                    dragging = true
                    position = it.toLong()
                    onPositionChanged(position)
                },
                onValueChangeFinished = {
                    player.seekTo(position)
                    dragging = false
                    onPositionChanged(position)
                },
                valueRange = 0f..duration.coerceAtLeast(1).toFloat(),
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "${formatTime(position)} / ${formatTime(duration)}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = { player.seekTo((position - 10_000).coerceAtLeast(0)) }) {
                        Icon(Icons.Default.Replay10, contentDescription = "Back ten seconds")
                    }
                    IconButton(
                        onClick = {
                            if (player.isPlaying) player.pause() else player.play()
                        }
                    ) {
                        Icon(
                            if (playing) Icons.Default.Pause else Icons.Default.PlayArrow,
                            contentDescription = if (playing) "Pause" else "Play",
                            tint = MaterialTheme.colorScheme.primary,
                        )
                    }
                    IconButton(
                        onClick = {
                            player.seekTo((position + 10_000).coerceAtMost(duration.coerceAtLeast(0)))
                        }
                    ) {
                        Icon(Icons.Default.Forward10, contentDescription = "Forward ten seconds")
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = onToggleTranscript) {
                        Icon(
                            if (transcriptVisible) Icons.Default.VisibilityOff else Icons.Default.Visibility,
                            contentDescription = if (transcriptVisible) {
                                "Hide transcript for blind listening"
                            } else {
                                "Show transcript"
                            },
                        )
                    }
                    AssistChip(
                        onClick = {
                            speed = nextPlaybackSpeed(speed)
                            player.setPlaybackSpeed(speed)
                        },
                        label = { Text("${speed}x") },
                        colors = AssistChipDefaults.assistChipColors(labelColor = MaterialTheme.colorScheme.primary),
                    )
                }
            }
            playbackError?.let {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        it,
                        modifier = Modifier.weight(1f),
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    TextButton(
                        onClick = {
                            playbackError = null
                            player.prepare()
                            player.play()
                        },
                    ) {
                        Text("Retry")
                    }
                }
            }
        }
    }
}

private fun formatTime(milliseconds: Long): String {
    val totalSeconds = milliseconds.coerceAtLeast(0) / 1_000
    return "%d:%02d".format(totalSeconds / 60, totalSeconds % 60)
}
