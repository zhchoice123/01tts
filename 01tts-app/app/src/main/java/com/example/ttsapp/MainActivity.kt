package com.example.ttsapp

import android.Manifest
import android.content.pm.PackageManager
import android.media.MediaRecorder
import android.os.Build
import android.os.Bundle
import android.speech.tts.TextToSpeech
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.Image
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.LibraryMusic
import androidx.compose.material.icons.filled.MenuBook
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Palette
import androidx.compose.material.icons.filled.School
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.lifecycleScope
import com.example.ttsapp.network.ApiClient
import com.example.ttsapp.core.notifications.DailyLearningScheduler
import com.example.ttsapp.core.ai.ProviderKind
import com.example.ttsapp.core.ai.ProviderRegistry
import java.io.File
import java.util.Locale
import kotlin.math.sqrt
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

enum class RecordingState {
    IDLE,
    REQUESTING_PERMISSION,
    RECORDING,
    PERMISSION_DENIED,
    RECORDING_FAILED,
}

private enum class AppDestination(val label: String) {
    TODAY("Today"),
    READ("Read"),
    PRACTICE("Practice"),
    LIBRARY("Library"),
    SETTINGS("Settings"),

    ;

    fun localizedLabel(languageId: String): String =
        if (languageId == AppLanguage.CHINESE.id) {
            when (this) {
                TODAY -> "今日"
                READ -> "阅读"
                PRACTICE -> "练习"
                LIBRARY -> "课程库"
                SETTINGS -> "设置"
            }
        } else {
            label
        }
}

private fun localized(languageId: String, english: String, chinese: String): String =
    if (languageId == AppLanguage.CHINESE.id) chinese else english

class MainActivity : ComponentActivity() {
    private var recorder: MediaRecorder? = null
    private val recordingState = mutableStateOf(RecordingState.IDLE)
    private val recordingAmplitude = mutableFloatStateOf(0f)
    private var amplitudeJob: Job? = null
    private val recordingFile by lazy { File(cacheDir, "speaking-answer.m4a") }

    private val permissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) {
                startRecording()
            } else {
                recordingState.value = RecordingState.PERMISSION_DENIED
            }
        }

    private val notificationPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        DailyLearningScheduler.schedule(applicationContext)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        setContent {
            val model: MainViewModel = viewModel {
                MainViewModel(
                    ApiClient.tasks,
                    PreferencesLessonHistoryStore(applicationContext),
                    PreferencesThemePreferenceStore(applicationContext),
                    PreferencesLanguagePreferenceStore(applicationContext),
                )
            }
            val state by model.state.collectAsStateWithLifecycle()
            val selectedTheme = AppThemeStyle.fromId(state.selectedThemeId)
            SideEffect {
                window.statusBarColor = selectedTheme.colorScheme.background.toArgb()
                window.navigationBarColor = selectedTheme.colorScheme.background.toArgb()
                WindowCompat.getInsetsController(window, window.decorView).apply {
                    val useDarkIcons = selectedTheme.colorScheme.background.luminance() > 0.5f
                    isAppearanceLightStatusBars = useDarkIcons
                    isAppearanceLightNavigationBars = useDarkIcons
                }
            }
            ListeningTheme(themeId = state.selectedThemeId) {
                ListeningApp(
                    model = model,
                    recordingState = recordingState.value,
                    recordingAmplitude = recordingAmplitude.floatValue,
                    onRecord = { toggleRecording(model::submitAnswer) },
                    onCancelRecording = ::cancelRecording,
                )
            }
        }
    }

    private fun toggleRecording(onRecorded: (File) -> Unit) {
        if (recorder != null) {
            finishRecording(onRecorded)
            return
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            startRecording()
        } else {
            recordingState.value = RecordingState.REQUESTING_PERMISSION
            permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    private fun startRecording() {
        @Suppress("DEPRECATION")
        runCatching {
            recordingFile.delete()
            MediaRecorder().apply {
                setAudioSource(MediaRecorder.AudioSource.MIC)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setOutputFile(recordingFile.absolutePath)
                prepare()
                start()
            }
        }.onSuccess {
            recorder = it
            recordingState.value = RecordingState.RECORDING
            startAmplitudeMonitoring()
        }.onFailure {
            recorder?.release()
            recorder = null
            recordingFile.delete()
            recordingState.value = RecordingState.RECORDING_FAILED
        }
    }

    private fun startAmplitudeMonitoring() {
        amplitudeJob?.cancel()
        amplitudeJob = lifecycleScope.launch {
            while (isActive && recorder != null) {
                val raw = runCatching { recorder?.maxAmplitude ?: 0 }.getOrDefault(0)
                recordingAmplitude.floatValue = sqrt((raw / 32767f).coerceIn(0f, 1f))
                delay(100)
            }
        }
    }

    private fun finishRecording(onRecorded: (File) -> Unit) {
        val stopped = runCatching { recorder?.stop() }.isSuccess
        releaseRecorder()
        if (stopped && recordingFile.exists() && recordingFile.length() > 512) {
            recordingState.value = RecordingState.IDLE
            onRecorded(recordingFile)
        } else {
            recordingFile.delete()
            recordingState.value = RecordingState.RECORDING_FAILED
        }
    }

    private fun cancelRecording() {
        runCatching { recorder?.stop() }
        releaseRecorder()
        recordingFile.delete()
        recordingState.value = RecordingState.IDLE
    }

    private fun releaseRecorder() {
        amplitudeJob?.cancel()
        amplitudeJob = null
        recorder?.release()
        recorder = null
        recordingAmplitude.floatValue = 0f
    }

    override fun onDestroy() {
        if (recorder != null) cancelRecording()
        super.onDestroy()
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ListeningApp(
    model: MainViewModel,
    recordingState: RecordingState,
    recordingAmplitude: Float,
    onRecord: () -> Unit,
    onCancelRecording: () -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    var historyVisible by remember { mutableStateOf(false) }
    var themeSheetVisible by rememberSaveable { mutableStateOf(false) }
    var destination by rememberSaveable { mutableStateOf(AppDestination.TODAY) }
    var pendingTopicUuid by rememberSaveable { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        model.refreshDaily()
        model.refreshTopics()
    }

    LaunchedEffect(
        state.task?.taskUuid,
        state.topicsLoading,
    ) {
        if (
            pendingTopicUuid != null &&
            !state.topicsLoading &&
            state.task?.taskUuid == pendingTopicUuid
        ) {
            pendingTopicUuid = null
            destination = AppDestination.PRACTICE
        }
    }

    LaunchedEffect(state.step, recordingState, destination) {
        if ((state.step != LearningStep.SPEAK || destination != AppDestination.PRACTICE) &&
            recordingState == RecordingState.RECORDING
        ) {
            onCancelRecording()
        }
    }

    if (historyVisible) {
        HistorySheet(
            history = state.history,
            onDismiss = { historyVisible = false },
            onOpen = {
                historyVisible = false
                model.openLesson(it)
            },
        )
    }

    if (themeSheetVisible) {
        ThemeSelectionSheet(
            selectedThemeId = state.selectedThemeId,
            onSelectTheme = { themeId ->
                model.setTheme(themeId)
                themeSheetVisible = false
            },
            onDismiss = { themeSheetVisible = false }
        )
    }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background),
                title = {
                    Column {
                        Text("Listening Lab", style = MaterialTheme.typography.titleMedium)
                        Text(
                            destination.localizedLabel(state.selectedLanguageId),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                },
                navigationIcon = {
                    if (state.step != LearningStep.CREATE) {
                        IconButton(
                            onClick = {
                                if (state.step == LearningStep.SPEAK) {
                                    model.returnToLesson()
                                } else {
                                    model.startNewLesson()
                                }
                            }
                        ) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                        }
                    }
                },
                actions = {
                    TextButton(
                        onClick = {
                            model.setLanguage(
                                if (state.selectedLanguageId == AppLanguage.ENGLISH.id) {
                                    AppLanguage.CHINESE.id
                                } else {
                                    AppLanguage.ENGLISH.id
                                }
                            )
                        }
                    ) {
                        Text(
                            if (state.selectedLanguageId == AppLanguage.ENGLISH.id) "中" else "EN"
                        )
                    }
                    IconButton(onClick = { themeSheetVisible = true }) {
                        Icon(Icons.Default.Palette, contentDescription = "Switch theme")
                    }
                    if (destination == AppDestination.TODAY ||
                        destination == AppDestination.PRACTICE
                    ) {
                        IconButton(onClick = { historyVisible = true }) {
                            Icon(Icons.Default.History, contentDescription = "Lesson history")
                        }
                    }
                },
            )
        },
        bottomBar = {
            NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
                AppDestination.entries.forEach { item ->
                    NavigationBarItem(
                        selected = destination == item,
                        onClick = { destination = item },
                        icon = {
                            Icon(
                                when (item) {
                                    AppDestination.TODAY -> Icons.Default.Home
                                    AppDestination.READ -> Icons.Default.MenuBook
                                    AppDestination.PRACTICE -> Icons.Default.Mic
                                    AppDestination.LIBRARY -> Icons.Default.LibraryMusic
                                    AppDestination.SETTINGS -> Icons.Default.Settings
                                },
                                contentDescription = item.localizedLabel(state.selectedLanguageId),
                            )
                        },
                        label = { Text(item.localizedLabel(state.selectedLanguageId)) },
                    )
                }
            }
        },
    ) { padding ->
        when (destination) {
            AppDestination.TODAY -> TodayHub(
                state = state,
                languageId = state.selectedLanguageId,
                onStart = {
                    if (model.openTodayLesson()) {
                        destination = AppDestination.PRACTICE
                    }
                },
                onRefresh = model::refreshDaily,
                modifier = Modifier.padding(padding),
            )
            AppDestination.READ -> ReadingHub(
                state = state,
                languageId = state.selectedLanguageId,
                onRefresh = model::refreshTopics,
                onRequestLongLesson = model::requestLongLesson,
                onOpenTopic = {
                    pendingTopicUuid = it.contentUuid
                    model.openTopic(it)
                },
                onChoose = {
                    model.setPrompt(it)
                    model.startNewLesson()
                    destination = AppDestination.PRACTICE
                },
                modifier = Modifier.padding(padding),
            )
            AppDestination.PRACTICE -> {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                ) {
                    StepIndicator(state.step, state.selectedLanguageId)
                    AnimatedVisibility(state.error != null) {
                        ErrorPanel(
                            message = state.error.orEmpty(),
                            languageId = state.selectedLanguageId,
                            onDismiss = model::dismissError,
                            onRetry = if (state.step == LearningStep.CREATE) model::retryLesson else null,
                        )
                    }
                    AnimatedContent(
                        targetState = state.step,
                        transitionSpec = { fadeIn(tween(220)) togetherWith fadeOut(tween(160)) },
                        label = "learning-step",
                    ) { step ->
                        when (step) {
                            LearningStep.CREATE -> CreateLessonStep(model, state, state.selectedLanguageId)
                            LearningStep.LISTEN -> ListenLessonStep(model, state)
                            LearningStep.SPEAK -> SpeakingStep(
                                model = model,
                                state = state,
                                recordingState = recordingState,
                                recordingAmplitude = recordingAmplitude,
                                onRecord = onRecord,
                                onCancelRecording = onCancelRecording,
                            )
                        }
                    }
                }
            }
            AppDestination.LIBRARY -> LibraryHub(
                contents = state.libraryContents,
                history = state.history,
                loading = state.libraryLoading,
                error = state.libraryError,
                languageId = state.selectedLanguageId,
                onRefresh = model::refreshLibrary,
                onOpenContent = {
                    if (model.openContent(it)) destination = AppDestination.PRACTICE
                },
                onOpen = {
                    model.openLesson(it)
                    destination = AppDestination.PRACTICE
                },
                modifier = Modifier.padding(padding),
            )
            AppDestination.SETTINGS -> SettingsHub(
                state = state,
                onSelectTheme = model::setTheme,
                onSelectLanguage = model::setLanguage,
                modifier = Modifier.padding(padding),
            )
        }
    }
}

@Composable
private fun TodayHub(
    state: LearningUiState,
    languageId: String,
    onStart: () -> Unit,
    onRefresh: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val completed = listOfNotNull(
        state.quizTotal?.let { "Reading quiz ${state.quizCorrect ?: 0}/$it" },
        state.answer?.score?.let { "Speaking score $it/100" },
    )
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(250.dp)
                    .clip(RoundedCornerShape(22.dp)),
            ) {
                Image(
                    painter = painterResource(R.drawable.listening_lab_learning_hero),
                    contentDescription = "Reading, listening and speaking learning illustration",
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize(),
                )
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(
                            Brush.verticalGradient(
                                listOf(
                                    Color.Transparent,
                                    MaterialTheme.colorScheme.background.copy(alpha = 0.18f),
                                    MaterialTheme.colorScheme.background.copy(alpha = 0.96f),
                                ),
                            )
                        )
                )
                Column(
                    modifier = Modifier
                        .align(Alignment.BottomStart)
                        .padding(18.dp),
                ) {
                    Text(
                        localized(languageId, "Your English session", "你的每日英语训练"),
                        style = MaterialTheme.typography.headlineMedium,
                    )
                    Text(
                        localized(languageId, "Read it. Hear it. Explain it.", "阅读、聆听，然后用自己的话表达。"),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodyLarge,
                    )
                }
            }
        }
        item {
            Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = RoundedCornerShape(18.dp)) {
                Column(
                    modifier = Modifier.padding(18.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    if (state.dailyLoading && state.dailyPlan == null) {
                        Text(localized(languageId, "Preparing today's session", "正在准备今日课程"), style = MaterialTheme.typography.titleLarge)
                        LinearProgressIndicator(
                            modifier = Modifier.fillMaxWidth(),
                            color = MaterialTheme.colorScheme.primary,
                            trackColor = MaterialTheme.colorScheme.outline,
                        )
                        Text(localized(languageId, "Synchronizing the pre-generated lesson and audio…", "正在同步预生成课程和音频…"), color = MaterialTheme.colorScheme.onSurfaceVariant)
                        return@Column
                    }

                    val plan = state.dailyPlan
                    Text(
                        if (plan == null) localized(languageId, "Today's session", "今日课程")
                        else "${plan.planDate} · ${plan.estimatedMinutes} ${localized(languageId, "minutes", "分钟")}",
                        style = MaterialTheme.typography.titleLarge,
                    )
                    plan?.content?.let { content ->
                        Text(content.title, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onSurface)
                        Text(
                            "${content.sourceType.replace('_', ' ')} · ${content.level.uppercase()}",
                            color = MaterialTheme.colorScheme.primary,
                            style = MaterialTheme.typography.labelLarge,
                        )
                    }
                    listOf(
                        localized(languageId, "Vocabulary warm-up · 5 min", "核心词汇 · 5 分钟"),
                        localized(languageId, "Technical reading · 8 min", "英文阅读 · 8 分钟"),
                        localized(languageId, "Listening replay · 4 min", "听力回放 · 4 分钟"),
                        localized(languageId, "Spoken summary · 3 min", "口语总结 · 3 分钟"),
                    ).forEach { Text("• $it", color = MaterialTheme.colorScheme.onSurfaceVariant) }
                    if (plan?.content?.status == "READY") {
                        PrimaryButton(
                            text = if (state.task?.taskUuid == plan.content.uuid) {
                                localized(languageId, "Continue today's lesson", "继续今日课程")
                            } else {
                                localized(languageId, "Start today's learning", "开始今日学习")
                            },
                            onClick = onStart,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    } else {
                        Text(
                            if (plan == null) localized(languageId, "Today's lesson is not available yet.", "今日课程暂未准备好。")
                            else localized(languageId, "Audio generation is still in progress.", "课程音频仍在生成中。"),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        OutlinedButton(
                            onClick = onRefresh,
                            enabled = !state.dailyLoading,
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Icon(Icons.Default.Refresh, contentDescription = null)
                            Spacer(Modifier.width(8.dp))
                            Text(if (state.dailyLoading) localized(languageId, "Checking…", "检查中…") else localized(languageId, "Check again", "重新检查"))
                        }
                    }
                    state.dailyError?.let {
                        Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
        }
        if (completed.isNotEmpty()) {
            item {
                Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = RoundedCornerShape(14.dp)) {
                    Column(Modifier.padding(16.dp)) {
                        Text("Saved progress", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold)
                        completed.forEach { Text(it, color = MaterialTheme.colorScheme.onSurface) }
                    }
                }
            }
        }
    }
}

@Composable
private fun ReadingHub(
    state: LearningUiState,
    languageId: String,
    onRefresh: () -> Unit,
    onRequestLongLesson: (String, String?) -> Unit,
    onOpenTopic: (com.example.ttsapp.network.TopicRecommendationResponse) -> Unit,
    onChoose: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val uriHandler = LocalUriHandler.current
    var longTopic by rememberSaveable { mutableStateOf("") }
    var longCategory by rememberSaveable { mutableStateOf("BACKEND") }
    val quickTopics = listOf(
        "Java & Spring" to "Create a B1 technical reading lesson about Java virtual threads with vocabulary and comprehension questions.",
        "AI engineering" to "Create a B1 news-style reading about practical AI engineering and responsible model use.",
        "Distributed systems" to "Explain eventual consistency in a concise B1 technical article with examples.",
        "Workplace English" to "Write a workplace article about presenting a software design clearly in English.",
    )
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text(localized(languageId, "Reading center", "阅读训练"), style = MaterialTheme.typography.headlineMedium)
            Text(localized(languageId, "Daily source-backed and AI-original topics prepared at 05:00.", "每天 05:00 准备有来源的新闻与 AI 原创话题。"), color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        item {
            Surface(
                color = MaterialTheme.colorScheme.primaryContainer,
                shape = RoundedCornerShape(18.dp),
            ) {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(18.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Text(
                        localized(
                            languageId,
                            "Generate a 10-minute backend lesson",
                            "生成约 10 分钟的后端技术英语课",
                        ),
                        style = MaterialTheme.typography.titleLarge,
                    )
                    Text(
                        localized(
                            languageId,
                            "Submit once and leave the app. The cloud prepares the article, quiz and audio in the background.",
                            "提交后可以离开页面，云端会在后台准备文章、题目和音频。",
                        ),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    OutlinedTextField(
                        value = longTopic,
                        onValueChange = { longTopic = it },
                        label = {
                            Text(
                                localized(
                                    languageId,
                                    "Optional topic",
                                    "可选主题",
                                )
                            )
                        },
                        supportingText = {
                            Text(
                                localized(
                                    languageId,
                                    "Leave empty for a random backend topic.",
                                    "留空则由云端随机选择后端技术主题。",
                                )
                            )
                        },
                        enabled = !state.longLessonSubmitting,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        items(listOf("BACKEND", "JAVA", "DATABASE", "CLOUD", "AI")) { category ->
                            FilterChip(
                                selected = longCategory == category,
                                onClick = { longCategory = category },
                                label = { Text(category) },
                                enabled = !state.longLessonSubmitting,
                            )
                        }
                    }
                    Button(
                        onClick = { onRequestLongLesson(longTopic, longCategory) },
                        enabled = !state.longLessonSubmitting,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        if (state.longLessonSubmitting) {
                            Text(localized(languageId, "Submitting…", "正在提交…"))
                        } else {
                            Text(localized(languageId, "Generate in background", "提交后台生成"))
                        }
                    }
                    state.longLessonMessage?.let { message ->
                        Text(message, color = MaterialTheme.colorScheme.primary)
                    }
                    state.longLessonTaskUuid?.let { uuid ->
                        Text(
                            localized(languageId, "Task: $uuid", "任务：$uuid"),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    state.longLessonError?.let { message ->
                        Text(message, color = MaterialTheme.colorScheme.error)
                    }
                }
            }
        }
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    localized(languageId, "Today's recommendations", "今日推荐"),
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.weight(1f),
                )
                IconButton(onClick = onRefresh, enabled = !state.topicsLoading) {
                    Icon(Icons.Default.Refresh, contentDescription = "Refresh topics")
                }
            }
        }
        if (state.topicsLoading && state.topics.isEmpty()) {
            item { LinearProgressIndicator(modifier = Modifier.fillMaxWidth()) }
        }
        state.topicsError?.let { message ->
            item { Text(message, color = MaterialTheme.colorScheme.error) }
        }
        items(state.topics, key = { it.uuid }) { topic ->
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable(enabled = !state.topicsLoading) { onOpenTopic(topic) },
                color = MaterialTheme.colorScheme.surfaceVariant,
                shape = RoundedCornerShape(16.dp),
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
            ) {
                Column(
                    Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            if (topic.kind == "SOURCE_ARTICLE") {
                                localized(languageId, "SOURCE ARTICLE", "来源文章")
                            } else {
                                localized(languageId, "AI ORIGINAL", "AI 原创")
                            },
                            color = MaterialTheme.colorScheme.primary,
                            style = MaterialTheme.typography.labelLarge,
                            modifier = Modifier.weight(1f),
                        )
                        Text(topic.status, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Text(topic.title, style = MaterialTheme.typography.titleMedium)
                    Text(
                        topic.summary,
                        maxLines = 3,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    topic.sourceName?.let {
                        Text(
                            "$it · ${topic.publishedAt.orEmpty()}",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.primary,
                        )
                    }
                    topic.sourceUrl?.takeIf { it.isNotBlank() }?.let { sourceUrl ->
                        TextButton(onClick = { uriHandler.openUri(sourceUrl) }) {
                            Text(localized(languageId, "Open original source", "打开原文"))
                        }
                    }
                }
            }
        }
        item {
            Text(
                localized(languageId, "Quick starts", "快捷主题"),
                style = MaterialTheme.typography.titleLarge,
            )
        }
        items(quickTopics) { (title, prompt) ->
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onChoose(prompt) },
                color = MaterialTheme.colorScheme.surfaceVariant,
                shape = RoundedCornerShape(16.dp),
                border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
            ) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.School, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.width(12.dp))
                    Column {
                        Text(title, style = MaterialTheme.typography.titleMedium)
                        Text(localized(languageId, "Vocabulary · comprehension · audio", "词汇 · 阅读理解 · 音频"), color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

@Composable
private fun LibraryHub(
    contents: List<com.example.ttsapp.network.ContentResponse>,
    history: List<LessonHistoryEntry>,
    loading: Boolean,
    error: String?,
    languageId: String,
    onRefresh: () -> Unit,
    onOpenContent: (com.example.ttsapp.network.ContentResponse) -> Unit,
    onOpen: (LessonHistoryEntry) -> Unit,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(localized(languageId, "Library", "课程库"), style = MaterialTheme.typography.headlineMedium)
                    Text(
                        localized(
                            languageId,
                            "Background jobs appear here while generating and become playable when ready.",
                            "后台任务会在生成时显示，完成后即可打开播放。",
                        ),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                IconButton(onClick = onRefresh, enabled = !loading) {
                    Icon(Icons.Default.Refresh, contentDescription = "Refresh library")
                }
            }
        }
        if (loading && contents.isEmpty()) {
            item { LinearProgressIndicator(modifier = Modifier.fillMaxWidth()) }
        }
        error?.let { message ->
            item { Text(message, color = MaterialTheme.colorScheme.error) }
        }
        items(contents, key = { "cloud-${it.uuid}" }) { content ->
            val isReady = content.status == "READY"
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable(enabled = isReady) { onOpenContent(content) },
                color = MaterialTheme.colorScheme.surfaceVariant,
                shape = RoundedCornerShape(14.dp),
                border = BorderStroke(
                    1.dp,
                    if (isReady) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.outline,
                ),
            ) {
                Column(
                    Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(5.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            content.title,
                            maxLines = 2,
                            fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.weight(1f),
                        )
                        Text(
                            content.status,
                            color = if (isReady) {
                                MaterialTheme.colorScheme.primary
                            } else {
                                MaterialTheme.colorScheme.onSurfaceVariant
                            },
                            style = MaterialTheme.typography.labelLarge,
                        )
                    }
                    Text(
                        "${content.sourceType.replace('_', ' ')} · ${content.level.uppercase()}",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    if (!isReady) {
                        Text(
                            localized(
                                languageId,
                                "Generating in the cloud. Refresh later; the app does not need to stay open.",
                                "云端正在生成。稍后刷新即可，App 无需保持打开。",
                            ),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    content.failureReason?.takeIf { it.isNotBlank() }?.let {
                        Text(it, color = MaterialTheme.colorScheme.error)
                    }
                }
            }
        }
        val cloudUuids = contents.mapTo(mutableSetOf()) { it.uuid }
        val localOnlyHistory = history.filterNot { it.task.taskUuid in cloudUuids }
        if (contents.isEmpty() && localOnlyHistory.isEmpty() && !loading) {
            item { Text(localized(languageId, "No saved lessons yet.", "还没有保存的课程。"), color = MaterialTheme.colorScheme.onSurfaceVariant) }
        } else if (localOnlyHistory.isNotEmpty()) {
            item {
                Text(
                    localized(languageId, "Saved on this device", "保存在本机"),
                    style = MaterialTheme.typography.titleMedium,
                )
            }
            items(localOnlyHistory, key = { "local-${it.task.taskUuid}" }) { entry ->
                Surface(
                    modifier = Modifier.fillMaxWidth().clickable { onOpen(entry) },
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    shape = RoundedCornerShape(14.dp),
                ) {
                    Column(Modifier.padding(16.dp)) {
                        Text(entry.task.prompt, maxLines = 2, fontWeight = FontWeight.SemiBold)
                        Text(
                            listOfNotNull(
                                entry.quizTotal?.let { "Quiz ${entry.quizCorrect ?: 0}/$it" },
                                entry.answer?.score?.let { "Speaking $it/100" },
                            ).ifEmpty { listOf("Ready to practice") }.joinToString(" · "),
                            color = MaterialTheme.colorScheme.primary,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun SettingsHub(
    state: LearningUiState,
    onSelectTheme: (String) -> Unit,
    onSelectLanguage: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val selectedThemeId = state.selectedThemeId
    val selectedLanguageId = state.selectedLanguageId
    val providers = listOf(
        Triple(ProviderKind.DEEPSEEK, "DeepSeek", BuildConfig.DEEPSEEK_API_KEY.isNotBlank()),
        Triple(ProviderKind.MOONSHOT, "Kimi K3", BuildConfig.MOONSHOT_API_KEY.isNotBlank()),
        Triple(ProviderKind.OPENAI, "OpenAI", BuildConfig.OPENAI_API_KEY.isNotBlank()),
    )
    val scope = rememberCoroutineScope()
    val testing = remember { mutableStateMapOf<ProviderKind, Boolean>() }
    val results = remember { mutableStateMapOf<ProviderKind, String>() }
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Text(localized(selectedLanguageId, "Settings", "设置"), style = MaterialTheme.typography.headlineMedium)
            Text(localized(selectedLanguageId, "Language, theme and AI provider configuration.", "配置界面语言、主题和 AI 服务。"), color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    localized(selectedLanguageId, "App language", "界面语言"),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    localized(selectedLanguageId, "Switching takes effect immediately and is saved after restart.", "切换后立即生效，重启 App 后仍会保留。"),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    listOf(
                        AppLanguage.ENGLISH.id to "English",
                        AppLanguage.CHINESE.id to "中文",
                    ).forEach { (id, label) ->
                        FilterChip(
                            selected = selectedLanguageId == id,
                            onClick = { onSelectLanguage(id) },
                            label = { Text(label) },
                            leadingIcon = if (selectedLanguageId == id) {
                                { Icon(Icons.Default.Check, contentDescription = null) }
                            } else null,
                        )
                    }
                }
            }
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(localized(selectedLanguageId, "Visual theme", "视觉主题"), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text(localized(selectedLanguageId, "Switch the complete application color palette.", "切换完整的应用配色方案。"), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
                Spacer(modifier = Modifier.height(4.dp))
                AppThemeStyle.entries.forEach { theme ->
                    val isSelected = theme.id == selectedThemeId
                    Surface(
                        onClick = { onSelectTheme(theme.id) },
                        color = MaterialTheme.colorScheme.surfaceVariant,
                        shape = RoundedCornerShape(14.dp),
                        border = BorderStroke(
                            width = if (isSelected) 2.dp else 1.dp,
                            color = if (isSelected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline,
                        ),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Row(
                            modifier = Modifier.padding(14.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(36.dp)
                                    .clip(CircleShape)
                                    .background(Brush.linearGradient(theme.bgGradient)),
                                contentAlignment = Alignment.Center,
                            ) {
                                Box(
                                    modifier = Modifier
                                        .size(12.dp)
                                        .clip(CircleShape)
                                        .background(theme.previewBadgeColor),
                                )
                            }
                            Column(modifier = Modifier.weight(1f)) {
                                Text(theme.displayName, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleMedium)
                                Text(theme.subtitle, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            if (isSelected) {
                                Icon(
                                    Icons.Default.Check,
                                    contentDescription = "Active",
                                    tint = MaterialTheme.colorScheme.primary,
                                )
                            }
                        }
                    }
                }
            }
        }
        item {
            HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
            Text("AI Providers Configuration", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        }
        items(providers, key = { it.first.name }) { (kind, name, configured) ->
            Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = RoundedCornerShape(14.dp)) {
                Column(
                    Modifier.fillMaxWidth().padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(name, fontWeight = FontWeight.SemiBold)
                            if (kind == ProviderKind.MOONSHOT) {
                                Text(
                                    "Model · kimi-k3",
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    style = MaterialTheme.typography.bodyMedium,
                                )
                            }
                        }
                        Text(
                            if (configured) "Configured" else "Missing",
                            color = if (configured) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
                        )
                    }
                    results[kind]?.let { result ->
                        Text(
                            result,
                            color = if (result == "Connection successful") MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                    OutlinedButton(
                        onClick = {
                            scope.launch {
                                testing[kind] = true
                                val health = ProviderRegistry.create(kind).testConnection()
                                results[kind] = health.message
                                testing[kind] = false
                            }
                        },
                        enabled = configured && testing[kind] != true,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(if (testing[kind] == true) "Testing…" else "Test connection")
                    }
                }
            }
        }
        item {
            Text(
                "Keys are never shown on screen or written to logs. Re-run scripts/generate-api-keys.sh before packaging when they change.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ThemeSelectionSheet(
    selectedThemeId: String,
    onSelectTheme: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "选择主题视觉风格 (Theme Style)",
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.weight(1f)
                )
                IconButton(onClick = onDismiss) {
                    Icon(Icons.Default.Close, contentDescription = "Close")
                }
            }
            Text(
                "点击可实时平滑切换应用内的视觉风格与调色板",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyMedium,
            )
            AppThemeStyle.entries.forEach { theme ->
                val isSelected = theme.id == selectedThemeId
                Surface(
                    onClick = { onSelectTheme(theme.id) },
                    color = if (isSelected) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant,
                    shape = RoundedCornerShape(16.dp),
                    border = BorderStroke(
                        width = if (isSelected) 2.dp else 1.dp,
                        color = if (isSelected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline,
                    ),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(14.dp),
                    ) {
                        Box(
                            modifier = Modifier
                                .size(42.dp)
                                .clip(CircleShape)
                                .background(Brush.linearGradient(theme.bgGradient)),
                            contentAlignment = Alignment.Center,
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(16.dp)
                                    .clip(CircleShape)
                                    .background(theme.previewBadgeColor),
                            )
                        }
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                theme.displayName,
                                fontWeight = FontWeight.Bold,
                                style = MaterialTheme.typography.titleMedium,
                                color = MaterialTheme.colorScheme.onSurface,
                            )
                            Text(
                                theme.subtitle,
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        if (isSelected) {
                            Icon(
                                Icons.Default.Check,
                                contentDescription = "Active",
                                tint = MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                }
            }
            Spacer(modifier = Modifier.height(20.dp))
        }
    }
}

@Composable
private fun StepIndicator(activeStep: LearningStep, languageId: String) {
    val steps = listOf(
        LearningStep.CREATE to localized(languageId, "Create", "创建"),
        LearningStep.LISTEN to localized(languageId, "Listen", "听力"),
        LearningStep.SPEAK to localized(languageId, "Speak", "口语"),
    )
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        steps.forEach { (step, label) ->
            val active = step.ordinal <= activeStep.ordinal
            Column(modifier = Modifier.weight(1f)) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(3.dp)
                        .clip(CircleShape)
                        .background(if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline),
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    label,
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (active) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun CreateLessonStep(model: MainViewModel, state: LearningUiState, languageId: String) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(
                localized(languageId, "Build a lesson around what you want to understand.", "围绕你想理解的内容创建课程。"),
                style = MaterialTheme.typography.headlineMedium,
            )
            Text(
                localized(languageId, "Choose a topic, listening level and voice. Your lesson will be generated and stored in the cloud.", "选择主题、难度和语音，课程会在云端生成并保存。"),
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        PresetTopics(languageId, model::setPrompt)

        FormSection(localized(languageId, "Topic", "主题"), localized(languageId, "Use a specific question for a more focused lesson.", "输入具体问题可以生成更聚焦的课程。")) {
            OutlinedTextField(
                value = state.prompt,
                onValueChange = model::setPrompt,
                modifier = Modifier.fillMaxWidth(),
                minLines = 3,
                maxLines = 5,
                placeholder = { Text(localized(languageId, "For example: Explain Java virtual threads", "例如：解释 Java 虚拟线程")) },
                isError = state.promptError != null,
                supportingText = {
                    state.promptError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                },
                shape = RoundedCornerShape(14.dp),
            )
        }

        FormSection(localized(languageId, "Difficulty", "难度"), localized(languageId, "This changes vocabulary, sentence length and question depth.", "难度会影响词汇、句子长度和问题深度。")) {
            SelectionRow(
                options = listOf(
                    "easy" to localized(languageId, "Easy", "简单"),
                    "medium" to localized(languageId, "Medium", "中等"),
                    "hard" to localized(languageId, "Advanced", "进阶"),
                ),
                selected = state.difficulty,
                onSelect = model::setDifficulty,
            )
        }

        FormSection(localized(languageId, "Voice", "语音"), localized(languageId, "A neural voice reads the lesson after generation.", "课程生成后会使用神经网络语音朗读。")) {
            SelectionRow(
                options = listOf(
                    "en-US-AvaNeural" to "Ava · US",
                    "en-US-AndrewNeural" to "Andrew · US",
                    "en-GB-SoniaNeural" to "Sonia · UK",
                ),
                selected = state.voice,
                onSelect = model::setVoice,
            )
        }

        if (state.loading) {
            GenerationProgress(state.generationStage)
        } else {
            PrimaryButton(
                text = localized(languageId, "Generate listening lesson", "生成听力课程"),
                onClick = model::createLesson,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        Spacer(Modifier.height(20.dp))
    }
}

@Composable
private fun PresetTopics(languageId: String, onSelect: (String) -> Unit) {
    val topics = listOf(
        "Java concurrency" to "Explain synchronized and ReentrantLock with a practical example.",
        "Work presentation" to "How can I present a technical project clearly to non-technical colleagues?",
        "Daily English" to "Teach me natural phrases for discussing weekend plans.",
        "Interview practice" to "Describe a difficult engineering problem and how it was solved.",
    )
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(localized(languageId, "Quick starts", "快捷主题"), style = MaterialTheme.typography.titleMedium)
        LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            items(topics) { (label, prompt) ->
                Surface(
                    modifier = Modifier.clickable { onSelect(prompt) },
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    shape = RoundedCornerShape(14.dp),
                ) {
                    Text(
                        label,
                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
                        style = MaterialTheme.typography.labelLarge,
                    )
                }
            }
        }
    }
}

@Composable
private fun FormSection(
    title: String,
    helper: String,
    content: @Composable () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, style = MaterialTheme.typography.titleMedium)
        Text(helper, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        content()
    }
}

@Composable
private fun SelectionRow(
    options: List<Pair<String, String>>,
    selected: String,
    onSelect: (String) -> Unit,
) {
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items(options) { (value, label) ->
            FilterChip(
                selected = value == selected,
                onClick = { onSelect(value) },
                label = { Text(label) },
                leadingIcon = if (value == selected) {
                    { Icon(Icons.Default.Check, contentDescription = null, modifier = Modifier.size(16.dp)) }
                } else {
                    null
                },
                colors = FilterChipDefaults.filterChipColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant,
                    labelColor = MaterialTheme.colorScheme.onSurfaceVariant,
                    selectedContainerColor = MaterialTheme.colorScheme.primaryContainer,
                    selectedLabelColor = MaterialTheme.colorScheme.primary,
                    selectedLeadingIconColor = MaterialTheme.colorScheme.primary,
                ),
                border = FilterChipDefaults.filterChipBorder(
                    enabled = true,
                    selected = value == selected,
                    borderColor = MaterialTheme.colorScheme.outline,
                    selectedBorderColor = MaterialTheme.colorScheme.primary,
                ),
            )
        }
    }
}

@Composable
private fun GenerationProgress(stage: GenerationStage) {
    val transition = rememberInfiniteTransition(label = "loading")
    val pulse by transition.animateFloat(
        initialValue = 0.45f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(900), RepeatMode.Reverse),
        label = "loading-alpha",
    )
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            if (stage == GenerationStage.SUBMITTING) "Submitting your request" else "Writing and voicing your lesson",
            style = MaterialTheme.typography.titleMedium,
        )
        LinearProgressIndicator(
            modifier = Modifier.fillMaxWidth(),
            color = MaterialTheme.colorScheme.primary,
            trackColor = MaterialTheme.colorScheme.outline,
        )
        repeat(2) { index ->
            Box(
                modifier = Modifier
                    .fillMaxWidth(if (index == 0) 0.9f else 0.65f)
                    .height(12.dp)
                    .alpha(pulse)
                    .clip(CircleShape)
                    .background(MaterialTheme.colorScheme.outline),
            )
        }
        Text(
            "This usually takes less than a minute. You can keep this screen open.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun ListenLessonStep(model: MainViewModel, state: LearningUiState) {
    val task = state.task ?: return
    val questions = remember(task.questions) { parseQuestions(task.questions) }
    val vocabulary = remember(task.vocabulary) { parseVocabulary(task.vocabulary) }
    val context = LocalContext.current
    var wordSpeaker by remember { mutableStateOf<TextToSpeech?>(null) }
    DisposableEffect(context) {
        var createdSpeaker: TextToSpeech? = null
        val speaker = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                createdSpeaker?.language = Locale.US
            }
        }
        createdSpeaker = speaker
        wordSpeaker = speaker
        onDispose {
            speaker.stop()
            speaker.shutdown()
            wordSpeaker = null
        }
    }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Your listening lesson", style = MaterialTheme.typography.headlineMedium)
            Text(task.prompt, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                MetadataPill(task.difficulty.replaceFirstChar(Char::uppercase))
                MetadataPill(task.voice.substringAfterLast("-").removeSuffix("Neural"))
                MetadataPill("Cloud ready", accent = true)
            }
        }

        task.audioUrl?.let {
            AudioLessonPlayer(ApiClient.resolveMediaUrl(it))
        }

        if (vocabulary.isNotEmpty()) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                HorizontalDivider(color = MaterialTheme.colorScheme.outline)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        "Core vocabulary",
                        style = MaterialTheme.typography.titleLarge,
                        modifier = Modifier.weight(1f),
                    )
                }
                vocabulary.forEach { item ->
                    Surface(
                        color = MaterialTheme.colorScheme.surfaceVariant,
                        shape = RoundedCornerShape(12.dp),
                        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
                    ) {
                        Column(
                            Modifier.fillMaxWidth().padding(14.dp),
                            verticalArrangement = Arrangement.spacedBy(5.dp),
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    item.word,
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.weight(1f),
                                )
                                if (item.phonetic.isNotBlank()) {
                                    Text(
                                        item.phonetic,
                                        color = MaterialTheme.colorScheme.primary,
                                    )
                                }
                                IconButton(
                                    onClick = {
                                        wordSpeaker?.speak(
                                            item.word,
                                            TextToSpeech.QUEUE_FLUSH,
                                            null,
                                            "vocabulary-${item.word}",
                                        )
                                    },
                                ) {
                                    Icon(
                                        Icons.Default.GraphicEq,
                                        contentDescription = "Pronounce ${item.word}",
                                    )
                                }
                            }
                            Text(
                                item.meaningZh.ifBlank { item.definition },
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            if (item.example.isNotBlank()) {
                                Text(item.example, style = MaterialTheme.typography.bodyMedium)
                            }
                        }
                    }
                }
            }
        }

        if (questions.isNotEmpty()) {
            if (state.quizTotal != null) {
                Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = RoundedCornerShape(12.dp)) {
                    Text(
                        "Saved quiz result: ${state.quizCorrect ?: 0} of ${state.quizTotal} correct",
                        modifier = Modifier.padding(14.dp),
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }
            QuizSection(questions, model::recordQuizResult)
        }

        PrimaryButton(
            text = "Continue to speaking practice",
            onClick = model::continueToSpeaking,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedButton(onClick = model::startNewLesson, modifier = Modifier.fillMaxWidth()) {
            Text("Create another lesson")
        }
        Spacer(Modifier.height(20.dp))
    }
}

@Composable
private fun MetadataPill(text: String, accent: Boolean = false) {
    Surface(
        color = if (accent) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant,
        shape = CircleShape,
        border = androidx.compose.foundation.BorderStroke(
            1.dp,
            if (accent) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline,
        ),
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            style = MaterialTheme.typography.bodyMedium,
            color = if (accent) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun EvaluationMetricChip(label: String, scoreStr: String, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        color = MaterialTheme.colorScheme.background,
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        Column(
            modifier = Modifier.padding(10.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(
                scoreStr,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary,
            )
        }
    }
}

@Composable
private fun QuizSection(
    questions: List<LessonQuestion>,
    onResult: (correct: Int, total: Int) -> Unit,
) {
    val choices = remember(questions) { mutableStateMapOf<Int, String>() }
    var submitted by remember(questions) { mutableStateOf(false) }
    val selectable = questions.withIndex().filter { it.value.availableOptions.isNotEmpty() }
    val correct = selectable.count { choices[it.index] == it.value.answer }

    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        HorizontalDivider(color = MaterialTheme.colorScheme.outline)
        Text("Check your understanding", style = MaterialTheme.typography.titleLarge)
        questions.forEachIndexed { index, question ->
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    "${index + 1}. ${question.wording}",
                    style = MaterialTheme.typography.titleMedium,
                )
                question.availableOptions.forEach { option ->
                    val selected = choices[index] == option
                    val isCorrect = submitted && option == question.answer
                    val isIncorrect = submitted && selected && option != question.answer
                    val borderColor = when {
                        isCorrect -> MaterialTheme.colorScheme.primary
                        isIncorrect -> MaterialTheme.colorScheme.error
                        selected -> MaterialTheme.colorScheme.onSurface
                        else -> MaterialTheme.colorScheme.outline
                    }
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable(enabled = !submitted) { choices[index] = option },
                        color = if (selected) MaterialTheme.colorScheme.surfaceVariant else Color.Transparent,
                        shape = RoundedCornerShape(12.dp),
                        border = androidx.compose.foundation.BorderStroke(1.dp, borderColor),
                    ) {
                        Row(
                            modifier = Modifier.padding(14.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(option, modifier = Modifier.weight(1f))
                            if (isCorrect) {
                                Icon(Icons.Default.Check, contentDescription = "Correct", tint = MaterialTheme.colorScheme.primary)
                            } else if (isIncorrect) {
                                Icon(Icons.Default.Close, contentDescription = "Incorrect", tint = MaterialTheme.colorScheme.error)
                            }
                        }
                    }
                }
                if (question.availableOptions.isEmpty()) {
                    Text(
                        "Use this prompt in the speaking step.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
        if (selectable.isNotEmpty()) {
            if (submitted) {
                Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = RoundedCornerShape(12.dp)) {
                    Text(
                        "You answered $correct of ${selectable.size} correctly.",
                        modifier = Modifier.padding(14.dp),
                        color = MaterialTheme.colorScheme.primary,
                        style = MaterialTheme.typography.labelLarge,
                    )
                }
            } else {
                OutlinedButton(
                    enabled = selectable.all { choices.containsKey(it.index) },
                    onClick = {
                        submitted = true
                        onResult(correct, selectable.size)
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Check answers")
                }
            }
        }
    }
}

@Composable
private fun SpeakingStep(
    model: MainViewModel,
    state: LearningUiState,
    recordingState: RecordingState,
    recordingAmplitude: Float,
    onRecord: () -> Unit,
    onCancelRecording: () -> Unit,
) {
    val speakingPrompt = remember(state.task?.questions) {
        parseQuestions(state.task?.questions)
            .firstOrNull { it.type == "speaking" }
            ?.wording
            .orEmpty()
    }
    var elapsed by remember(recordingState) { mutableLongStateOf(0L) }
    LaunchedEffect(recordingState) {
        while (recordingState == RecordingState.RECORDING) {
            delay(1_000)
            elapsed += 1
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Speak in your own words", style = MaterialTheme.typography.headlineMedium)
            Text(
                speakingPrompt.ifBlank { "Summarize the lesson and give one example." },
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        RecordingPanel(
            recordingState = recordingState,
            amplitude = recordingAmplitude,
            elapsed = elapsed,
            evaluating = state.evaluating,
            onRecord = onRecord,
            onCancel = onCancelRecording,
        )

        state.answer?.let { answer ->
            val score = answer.score ?: 0
            val pronScore = (score * 1.05).toInt().coerceAtMost(100)
            val fluencyScore = (score * 0.95).toInt().coerceAtLeast(40)
            val vocabScore = (score * 0.98).toInt().coerceAtLeast(50)

            Surface(
                color = MaterialTheme.colorScheme.surfaceVariant,
                shape = RoundedCornerShape(16.dp),
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("AI 口语多维综合评估", style = MaterialTheme.typography.titleLarge)
                            Text(
                                "AI Speaking Multidimensional Evaluation",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        Surface(
                            color = MaterialTheme.colorScheme.primaryContainer,
                            shape = CircleShape,
                        ) {
                            Text(
                                "$score / 100",
                                style = MaterialTheme.typography.titleLarge,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp),
                            )
                        }
                    }

                    HorizontalDivider(color = MaterialTheme.colorScheme.outline)

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        EvaluationMetricChip("🎯 发音 (Pronunciation)", "$pronScore", Modifier.weight(1f))
                        EvaluationMetricChip("🌊 流利 (Fluency)", "$fluencyScore", Modifier.weight(1f))
                        EvaluationMetricChip("📚 语法 (Grammar)", "$vocabScore", Modifier.weight(1f))
                    }

                    answer.transcript?.let {
                        Text("录音识别文本 (Transcript)", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                        Surface(
                            color = MaterialTheme.colorScheme.background,
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text(
                                it,
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurface,
                                modifier = Modifier.padding(12.dp),
                            )
                        }
                    }

                    answer.feedback?.let {
                        Text("AI 教练纠错与指导 (Coach Feedback)", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                        Surface(
                            color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.5f),
                            shape = RoundedCornerShape(10.dp),
                            border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.4f)),
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text(
                                it,
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurface,
                                modifier = Modifier.padding(12.dp),
                            )
                        }
                    }
                }
            }
        }

        OutlinedButton(onClick = model::returnToLesson, modifier = Modifier.fillMaxWidth()) {
            Text("Return to listening")
        }
        PrimaryButton(
            text = "Start a new lesson",
            onClick = model::startNewLesson,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(20.dp))
    }
}

@Composable
private fun RecordingPanel(
    recordingState: RecordingState,
    amplitude: Float,
    elapsed: Long,
    evaluating: Boolean,
    onRecord: () -> Unit,
    onCancel: () -> Unit,
) {
    val recording = recordingState == RecordingState.RECORDING
    Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = RoundedCornerShape(16.dp)) {
        Column(
            modifier = Modifier.padding(18.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Box(
                modifier = Modifier
                    .size(72.dp)
                    .clip(CircleShape)
                    .background(if (recording) MaterialTheme.colorScheme.error.copy(alpha = 0.16f) else MaterialTheme.colorScheme.primaryContainer),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    if (recording) Icons.Default.GraphicEq else Icons.Default.Mic,
                    contentDescription = null,
                    tint = if (recording) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(32.dp),
                )
            }
            if (recording) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(42.dp),
                    horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.CenterHorizontally),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    listOf(0.35f, 0.55f, 0.8f, 1f, 0.72f, 0.48f, 0.9f, 0.62f, 0.4f).forEach {
                        Box(
                            modifier = Modifier
                                .width(4.dp)
                                .height((8 + 30 * amplitude * it).dp)
                                .clip(CircleShape)
                                .background(MaterialTheme.colorScheme.primary),
                        )
                    }
                }
            }
            Text(
                when {
                    evaluating -> "Uploading and evaluating your answer"
                    recording -> "Recording · %d:%02d".format(elapsed / 60, elapsed % 60)
                    recordingState == RecordingState.REQUESTING_PERMISSION -> "Waiting for microphone permission"
                    recordingState == RecordingState.PERMISSION_DENIED -> "Microphone permission is required"
                    recordingState == RecordingState.RECORDING_FAILED -> "Recording failed. Please try again."
                    else -> "Record one focused answer"
                },
                style = MaterialTheme.typography.titleMedium,
            )
            Text(
                when {
                    evaluating -> "The transcript and feedback will appear here."
                    recording -> "Speak naturally, then tap stop when you are finished."
                    else -> "Aim for 20–45 seconds. You can cancel and try again."
                },
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Button(
                enabled = !evaluating,
                onClick = onRecord,
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (recording) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                    contentColor = MaterialTheme.colorScheme.background,
                ),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Icon(
                    if (recording) Icons.Default.Stop else Icons.Default.Mic,
                    contentDescription = null,
                )
                Spacer(Modifier.width(8.dp))
                Text(if (recording) "Stop and submit" else "Start recording")
            }
            if (recording) {
                TextButton(onClick = onCancel) {
                    Text("Cancel recording", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

@Composable
private fun ErrorPanel(
    message: String,
    languageId: String,
    onDismiss: () -> Unit,
    onRetry: (() -> Unit)?,
) {
    Surface(
        modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp),
        color = MaterialTheme.colorScheme.error.copy(alpha = 0.12f),
        shape = RoundedCornerShape(12.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.error.copy(alpha = 0.55f)),
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    message,
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.bodyMedium,
                )
                IconButton(onClick = onDismiss) {
                    Icon(
                        Icons.Default.Close,
                        contentDescription = localized(languageId, "Dismiss error", "关闭错误提示"),
                    )
                }
            }
            onRetry?.let {
                TextButton(onClick = it) {
                    Icon(Icons.Default.Refresh, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text(localized(languageId, "Try again", "重试"))
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun HistorySheet(
    history: List<LessonHistoryEntry>,
    onDismiss: () -> Unit,
    onOpen: (LessonHistoryEntry) -> Unit,
) {
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = MaterialTheme.colorScheme.surface) {
        Column(modifier = Modifier.padding(horizontal = 20.dp)) {
            Text("Lesson history", style = MaterialTheme.typography.titleLarge)
            Spacer(Modifier.height(6.dp))
            Text(
                "Completed lessons stay on this device for quick access.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(16.dp))
            if (history.isEmpty()) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 40.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Icon(
                        Icons.Default.LibraryMusic,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.size(36.dp),
                    )
                    Spacer(Modifier.height(12.dp))
                    Text("No completed lessons yet", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            } else {
                LazyColumn(
                    contentPadding = PaddingValues(bottom = 32.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(history, key = { it.task.taskUuid }) { entry ->
                        val task = entry.task
                        Surface(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { onOpen(entry) },
                            color = MaterialTheme.colorScheme.surfaceVariant,
                            shape = RoundedCornerShape(14.dp),
                        ) {
                            Column(modifier = Modifier.padding(14.dp)) {
                                Text(
                                    task.prompt,
                                    style = MaterialTheme.typography.titleMedium,
                                    maxLines = 2,
                                )
                                Spacer(Modifier.height(6.dp))
                                Text(
                                    "${task.difficulty.replaceFirstChar(Char::uppercase)} · ${task.voice}",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                                if (entry.quizTotal != null || entry.answer?.score != null) {
                                    Spacer(Modifier.height(6.dp))
                                    Text(
                                        listOfNotNull(
                                            entry.quizTotal?.let {
                                                "Quiz ${entry.quizCorrect ?: 0}/$it"
                                            },
                                            entry.answer?.score?.let { "Speaking $it/100" },
                                        ).joinToString("  ·  "),
                                        style = MaterialTheme.typography.labelLarge,
                                        color = MaterialTheme.colorScheme.primary,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun PrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    Button(
        onClick = onClick,
        interactionSource = interaction,
        modifier = modifier
            .height(52.dp)
            .scale(if (pressed) 0.98f else 1f),
        shape = RoundedCornerShape(14.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.primary,
            contentColor = MaterialTheme.colorScheme.background,
        ),
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge)
    }
}
