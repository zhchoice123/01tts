package com.example.ttsapp

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.ttsapp.network.AnswerResponse
import com.example.ttsapp.network.ContentResponse
import com.example.ttsapp.network.CreateLongLessonRequest
import com.example.ttsapp.network.CreateTaskRequest
import com.example.ttsapp.network.DailyPlanResponse
import com.example.ttsapp.network.LearningDashboardResponse
import com.example.ttsapp.network.LearningProgressRequest
import com.example.ttsapp.network.TaskApi
import com.example.ttsapp.network.TaskResponse
import com.example.ttsapp.network.TtsDemoRequest
import com.example.ttsapp.network.CreateSpeakingSessionRequest
import com.example.ttsapp.network.LookupVocabularyRequest
import com.example.ttsapp.network.LookupVocabularyResponse
import com.example.ttsapp.network.SaveUserVocabularyRequest
import com.example.ttsapp.network.SpeakingSessionResponse
import com.example.ttsapp.network.SpeakingTurnDetail
import com.example.ttsapp.network.TopicRecommendationResponse
import com.example.ttsapp.network.UserVocabularyCardResponse
import com.example.ttsapp.network.VocabularyProgressRequest
import com.example.ttsapp.review.LessonReviewReportResponse
import com.example.ttsapp.review.ReviewContentState
import com.example.ttsapp.review.ReviewQueueItem
import com.example.ttsapp.review.ReviewQueueResponse
import com.example.ttsapp.review.asContentState
import java.io.File
import java.time.Instant
import java.time.LocalDate
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import retrofit2.HttpException

enum class LearningStep {
    CREATE,
    LISTEN,
    SPEAK,
    REPORT,
}

enum class GenerationStage {
    IDLE,
    SUBMITTING,
    PROCESSING,
}

private val ONBOARDING_GOALS = setOf("TECHNICAL_ENGLISH", "GENERAL_ENGLISH", "SPEAKING")
private val ONBOARDING_LEVELS = setOf("A2", "B1", "B2", "C1")
private val ONBOARDING_MINUTES = setOf(10, 20, 30)

fun normalizeTtsVoice(rawVoice: String, fallbackProvider: String): Pair<String, String> {
    val clean = rawVoice.trim()
    val parts = clean.split(":").filter { it.isNotBlank() }
    val validProviders = setOf("openai", "aliyun")

    return when {
        parts.isEmpty() -> {
            val provider = if (fallbackProvider.lowercase() in validProviders) fallbackProvider.lowercase() else "openai"
            val defaultName = if (provider == "aliyun") "loongdavid_v2" else "nova"
            provider to "$provider:$defaultName"
        }
        parts.size == 1 -> {
            val provider = if (fallbackProvider.lowercase() in validProviders) fallbackProvider.lowercase() else "openai"
            val voiceName = parts[0]
            provider to "$provider:$voiceName"
        }
        else -> {
            val declaredProvider = parts[0].lowercase()
            if (declaredProvider in validProviders) {
                val voiceName = parts.last()
                declaredProvider to "$declaredProvider:$voiceName"
            } else {
                val provider = if (fallbackProvider.lowercase() in validProviders) fallbackProvider.lowercase() else "openai"
                val voiceName = parts.last()
                provider to "$provider:$voiceName"
            }
        }
    }
}

data class LearningUiState(
    val prompt: String = "",
    val voice: String = "en-US-AvaNeural",
    val ttsProvider: String = "openai",
    val ttsPreviewUrl: String? = null,
    val ttsPreviewVoice: String? = null,
    val ttsPreviewLoading: Boolean = false,
    val ttsPreviewError: String? = null,
    val difficulty: String = "medium",
    val loading: Boolean = false,
    val generationStage: GenerationStage = GenerationStage.IDLE,
    val step: LearningStep = LearningStep.CREATE,
    val task: TaskResponse? = null,
    val answer: AnswerResponse? = null,
    val quizCorrect: Int? = null,
    val quizTotal: Int? = null,
    val history: List<LessonHistoryEntry> = emptyList(),
    val dailyPlan: DailyPlanResponse? = null,
    val dailyLoading: Boolean = false,
    val dailyError: String? = null,
    val evaluating: Boolean = false,
    val promptError: String? = null,
    val error: String? = null,
    val selectedThemeId: String = "cyber",
    val selectedLanguageId: String = "en",
    val onboarding: OnboardingState = OnboardingState(),
    val libraryContents: List<ContentResponse> = emptyList(),
    val libraryLoading: Boolean = false,
    val libraryError: String? = null,
    val longLessonSubmitting: Boolean = false,
    val longLessonTaskUuid: String? = null,
    val longLessonMessage: String? = null,
    val longLessonError: String? = null,
    val topics: List<TopicRecommendationResponse> = emptyList(),
    val topicsLoading: Boolean = false,
    val topicsError: String? = null,
    val clientId: String = "",
    val currentProgress: LearningProgressRequest? = null,
    val todayProgress: LearningProgressRequest? = null,
    val dashboard: LearningDashboardResponse? = null,
    val dashboardLoading: Boolean = false,
    val learningSyncMessage: String? = null,
    val vocabularyStatuses: Map<String, String> = emptyMap(),
    val lessonReviewState: ReviewContentState<LessonReviewReportResponse> = ReviewContentState.Empty,
    val lessonReviewContentUuid: String? = null,
    val reviewQueueState: ReviewContentState<ReviewQueueResponse> = ReviewContentState.Empty,
    val reviewQueueMessage: String? = null,
    val selectedLookupWord: LookupVocabularyResponse? = null,
    val lookupLoading: Boolean = false,
    val lookupError: String? = null,
    val activeSpeakingSession: SpeakingSessionResponse? = null,
    val speakingSessionTurns: List<SpeakingTurnDetail> = emptyList(),
    val speakingCoachLoading: Boolean = false,
    val speakingCoachFeedback: String? = null,
    val userWordbook: List<UserVocabularyCardResponse> = emptyList(),
)

class MainViewModel(
    private val api: TaskApi,
    private val historyStore: LessonHistoryStore = InMemoryLessonHistoryStore(),
    private val themeStore: ThemePreferenceStore = InMemoryThemePreferenceStore(),
    private val languageStore: LanguagePreferenceStore = InMemoryLanguagePreferenceStore(),
    private val clientIdStore: ClientIdStore = InMemoryClientIdStore(),
    private val progressStore: LearningProgressStore = InMemoryLearningProgressStore(),
    private val currentDate: () -> String = { LocalDate.now().toString() },
    private val ttsStore: TtsPreferenceStore = InMemoryTtsPreferenceStore(),
    private val onboardingStore: OnboardingPreferenceStore = InMemoryOnboardingPreferenceStore(),
) : ViewModel() {
    private val clientId = clientIdStore.loadOrCreate()
    private val initialHistory = historyStore.load()
    private val initialOnboarding = onboardingStore.load(initialHistory.isNotEmpty())
    private var progressSaveJob: Job? = null
    private val mutableState = MutableStateFlow(
        LearningUiState(
            history = initialHistory,
            selectedThemeId = themeStore.load(),
            selectedLanguageId = languageStore.load(),
            onboarding = initialOnboarding,
            clientId = clientId,
            ttsProvider = ttsStore.load().provider,
            voice = ttsStore.load().voice,
        )
    )
    val state: StateFlow<LearningUiState> = mutableState.asStateFlow()

    fun setOnboardingGoal(goal: String) {
        updateOnboarding { current ->
            current.copy(goal = goal.takeIf { it in ONBOARDING_GOALS } ?: current.goal)
        }
    }

    fun setOnboardingLevel(level: String) {
        updateOnboarding { current ->
            current.copy(level = level.takeIf { it in ONBOARDING_LEVELS } ?: current.level)
        }
    }

    fun setOnboardingMinutes(minutes: Int) {
        updateOnboarding { current ->
            current.copy(
                dailyMinutes = minutes.takeIf { it in ONBOARDING_MINUTES } ?: current.dailyMinutes,
            )
        }
    }

    fun completeOnboarding() {
        updateOnboarding { current ->
            current.copy(completed = true, completedAt = Instant.now().toString())
        }
    }

    fun skipOnboarding() {
        updateOnboarding {
            it.copy(
                completed = true,
                goal = "TECHNICAL_ENGLISH",
                level = "B1",
                dailyMinutes = 20,
                completedAt = Instant.now().toString(),
            )
        }
    }

    private fun updateOnboarding(transform: (OnboardingState) -> OnboardingState) {
        val updated = transform(state.value.onboarding)
        onboardingStore.save(updated)
        mutableState.value = state.value.copy(onboarding = updated)
    }

    fun setTheme(themeId: String) {
        val validThemeId = AppThemeStyle.fromId(themeId).id
        themeStore.save(validThemeId)
        mutableState.value = state.value.copy(selectedThemeId = validThemeId)
    }

    fun setLanguage(languageId: String) {
        val validLanguageId = AppLanguage.fromId(languageId).id
        languageStore.save(validLanguageId)
        mutableState.value = state.value.copy(selectedLanguageId = validLanguageId)
    }

    fun setPrompt(prompt: String) {
        mutableState.value = state.value.copy(prompt = prompt, promptError = null)
    }

    fun setVoice(voice: String) {
        val (provider, normalizedVoice) = normalizeTtsVoice(voice, state.value.ttsProvider)
        ttsStore.save(TtsPreference(provider, normalizedVoice))
        mutableState.value = state.value.copy(
            ttsProvider = provider,
            voice = normalizedVoice,
            ttsPreviewUrl = null,
            ttsPreviewVoice = null,
            ttsPreviewError = null,
        )
    }

    fun setTtsProvider(provider: String) {
        val normalized = provider.lowercase().takeIf { it == "openai" || it == "aliyun" } ?: "openai"
        val defaultVoice = if (normalized == "aliyun") {
            "aliyun:loongdavid_v2"
        } else {
            "openai:nova"
        }
        ttsStore.save(TtsPreference(normalized, defaultVoice))
        mutableState.value = state.value.copy(
            ttsProvider = normalized,
            voice = defaultVoice,
            ttsPreviewUrl = null,
            ttsPreviewVoice = null,
            ttsPreviewError = null,
        )
    }

    fun setTtsVoice(voice: String) {
        setVoice(voice)
    }

    fun previewTtsVoice() {
        if (state.value.ttsPreviewLoading) return
        val requestedVoice = state.value.voice
        val requestedProvider = state.value.ttsProvider
        viewModelScope.launch {
            mutableState.value = state.value.copy(
                ttsPreviewLoading = true,
                ttsPreviewUrl = null,
                ttsPreviewVoice = requestedVoice,
                ttsPreviewError = null,
            )
            runCatching { api.previewTts(TtsDemoRequest(requestedVoice)) }
                .onSuccess { response ->
                    val actualVoice = normalizeTtsVoice(
                        response.voice.ifBlank { requestedVoice },
                        requestedProvider,
                    ).second
                    mutableState.value = if (state.value.voice == requestedVoice) {
                        if (response.audioUrl.isBlank()) {
                            state.value.copy(
                                ttsPreviewLoading = false,
                                ttsPreviewUrl = null,
                                ttsPreviewError = "The TTS service returned no playable audio.",
                            )
                        } else {
                            state.value.copy(
                                ttsPreviewLoading = false,
                                ttsPreviewUrl = response.audioUrl,
                                ttsPreviewVoice = actualVoice,
                            )
                        }
                    } else {
                        state.value.copy(ttsPreviewLoading = false)
                    }
                }
                .onFailure { error ->
                    mutableState.value = if (state.value.voice == requestedVoice) {
                        state.value.copy(
                            ttsPreviewLoading = false,
                            ttsPreviewUrl = null,
                            ttsPreviewError = ttsPreviewErrorMessage(error),
                        )
                    } else {
                        state.value.copy(ttsPreviewLoading = false)
                    }
                }
        }
    }

    fun setDifficulty(difficulty: String) {
        mutableState.value = state.value.copy(difficulty = difficulty)
    }

    fun refreshDaily() {
        if (state.value.dailyLoading) return
        refreshReviewQueue()
        viewModelScope.launch {
            mutableState.value = state.value.copy(dailyLoading = true, dailyError = null)
            runCatching { api.today() }
                .onSuccess {
                    mutableState.value = state.value.copy(
                        dailyPlan = it,
                        dailyLoading = false,
                        dailyError = null,
                    )
                    restoreProgress(it.contentUuid)
                }
                .onFailure {
                    mutableState.value = state.value.copy(
                        dailyLoading = false,
                        dailyError = it.message ?: "Today's lesson could not be synchronized.",
                    )
                }
            refreshLibrary()
            refreshDashboard()
        }
    }

    fun generateDailyPlan() {
        if (state.value.dailyLoading) return
        viewModelScope.launch {
            mutableState.value = state.value.copy(dailyLoading = true, dailyError = null)
            runCatching { api.generateDailyPlan(currentDate()) }
                .onSuccess {
                    mutableState.value = state.value.copy(
                        dailyPlan = it,
                        dailyLoading = false,
                        dailyError = null,
                    )
                    restoreProgress(it.contentUuid)
                }
                .onFailure {
                    mutableState.value = state.value.copy(
                        dailyLoading = false,
                        dailyError = it.message ?: "Today's lesson could not be generated.",
                    )
                }
            refreshLibrary()
            refreshDashboard()
        }
    }

    fun refreshReviewQueue() {
        if (state.value.reviewQueueState is ReviewContentState.Loading) return
        val date = currentDate()
        mutableState.value = state.value.copy(
            reviewQueueState = ReviewContentState.Loading,
            reviewQueueMessage = null,
        )
        viewModelScope.launch {
            runCatching { api.reviewQueue(clientId, date, 10) }
                .onSuccess { queue ->
                    mutableState.value = state.value.copy(
                        reviewQueueState = queue.asContentState(),
                        reviewQueueMessage = null,
                    )
                }
                .onFailure { error ->
                    mutableState.value = state.value.copy(
                        reviewQueueState = ReviewContentState.Error(
                            error.message ?: localizedReviewMessage(
                                english = "Today's review queue could not be loaded.",
                                chinese = "今日复习队列加载失败。",
                            ),
                        ),
                    )
                }
        }
    }

    fun refreshLessonReview() {
        val contentUuid = state.value.lessonReviewContentUuid
            ?: state.value.task?.taskUuid
            ?: state.value.dailyPlan?.contentUuid
            ?: return
        loadLessonReview(contentUuid, force = true)
    }

    fun openReviewQueueItem(item: ReviewQueueItem): Boolean {
        val contentUuid = item.contentUuid.trim()
        val dailyContent = state.value.dailyPlan?.content
            ?.takeIf { it.uuid == contentUuid && it.status == "READY" }
        val libraryContent = state.value.libraryContents
            .firstOrNull { it.uuid == contentUuid && it.status == "READY" }
        val historyEntry = state.value.history
            .firstOrNull { it.task.taskUuid == contentUuid }
        val opened = when {
            dailyContent != null -> openContent(dailyContent)
            libraryContent != null -> openContent(libraryContent)
            historyEntry != null -> {
                openLesson(historyEntry)
                true
            }
            else -> false
        }
        mutableState.value = state.value.copy(
            reviewQueueMessage = if (opened) {
                null
            } else {
                localizedReviewMessage(
                    english = "This review lesson is not available on this device yet.",
                    chinese = "这项复习对应的课程暂未同步到本机。",
                )
            },
        )
        return opened
    }

    fun refreshDashboard() {
        if (state.value.dashboardLoading) return
        viewModelScope.launch {
            mutableState.value = state.value.copy(dashboardLoading = true)
            runCatching { api.learningDashboard(clientId, 7) }
                .onSuccess {
                    mutableState.value = state.value.copy(
                        dashboard = it,
                        dashboardLoading = false,
                        learningSyncMessage = null,
                    )
                }
                .onFailure {
                    mutableState.value = state.value.copy(
                        dashboardLoading = false,
                        learningSyncMessage = offlineMessage(),
                    )
                }
        }
    }

    fun refreshLibrary() {
        if (state.value.libraryLoading) return
        viewModelScope.launch {
            mutableState.value = state.value.copy(libraryLoading = true, libraryError = null)
            runCatching { api.library() }
                .onSuccess { contents ->
                    val visibleContents = contents.filterNot { it.status == "FAILED" }
                    val readyEntries = visibleContents
                        .filter { it.status == "READY" }
                        .map { LessonHistoryEntry(it.asTaskResponse()) }
                    val localByUuid = state.value.history.associateBy { it.task.taskUuid }
                    val merged = (
                        readyEntries.map { cloud ->
                            localByUuid[cloud.task.taskUuid]?.copy(task = cloud.task) ?: cloud
                        } + state.value.history.filterNot { local ->
                            readyEntries.any { it.task.taskUuid == local.task.taskUuid }
                        }
                    ).distinctBy { it.task.taskUuid }.take(40)
                    historyStore.save(merged)
                    mutableState.value = state.value.copy(
                        libraryContents = visibleContents,
                        libraryLoading = false,
                        libraryError = null,
                        history = merged,
                    )
                }
                .onFailure {
                    mutableState.value = state.value.copy(
                        libraryLoading = false,
                        libraryError = it.message ?: "The cloud library could not be loaded.",
                    )
                }
        }
    }

    fun requestLongLesson(topic: String, category: String?) {
        if (state.value.longLessonSubmitting) return
        viewModelScope.launch {
            mutableState.value = state.value.copy(
                longLessonSubmitting = true,
                longLessonTaskUuid = null,
                longLessonMessage = null,
                longLessonError = null,
            )
            runCatching {
                api.createLongLesson(
                    CreateLongLessonRequest(
                        topic = topic.trim().ifBlank { null },
                        category = category?.trim()?.ifBlank { null },
                        voice = state.value.voice,
                        level = "B1",
                        sourceMode = "AUTO",
                    )
                )
            }.onSuccess { content ->
                val languageId = state.value.selectedLanguageId
                mutableState.value = state.value.copy(
                    longLessonSubmitting = false,
                    longLessonTaskUuid = content.uuid,
                    longLessonMessage = if (languageId == AppLanguage.CHINESE.id) {
                        "已提交后台生成。完成后会出现在课程库中。"
                    } else {
                        "Background generation started. It will appear in Library when ready."
                    },
                    libraryContents = listOf(content) +
                        state.value.libraryContents.filterNot { it.uuid == content.uuid },
                )
            }.onFailure {
                mutableState.value = state.value.copy(
                    longLessonSubmitting = false,
                    longLessonError = it.message ?: if (
                        state.value.selectedLanguageId == AppLanguage.CHINESE.id
                    ) {
                        "无法提交长课程任务，请检查网络后重试。"
                    } else {
                        "The long lesson request could not be submitted."
                    },
                )
            }
        }
    }

    fun refreshTopics() {
        if (state.value.topicsLoading) return
        viewModelScope.launch {
            mutableState.value = state.value.copy(topicsLoading = true, topicsError = null)
            runCatching { api.topics(limit = 3) }
                .onSuccess {
                    mutableState.value = state.value.copy(
                        topics = it,
                        topicsLoading = false,
                        topicsError = null,
                    )
                }
                .onFailure {
                    mutableState.value = state.value.copy(
                        topicsLoading = false,
                        topicsError = it.message ?: "Daily topics could not be loaded.",
                    )
                }
        }
    }

    fun openTopic(topic: TopicRecommendationResponse) {
        if (state.value.topicsLoading) return
        viewModelScope.launch {
            mutableState.value = state.value.copy(topicsLoading = true, topicsError = null)
            runCatching {
                withTimeout(180_000) {
                    var content = api.topicLesson(topic.uuid).content
                    while (content.status == "GENERATING") {
                        delay(1_500)
                        content = api.getContent(content.uuid)
                    }
                    check(content.status == "READY") {
                        content.failureReason ?: "Topic lesson generation failed."
                    }
                    content
                }
            }.onSuccess { openReadyContent(it, topicsLoading = false) }
                .onFailure {
                    mutableState.value = state.value.copy(
                        topicsLoading = false,
                        topicsError = it.message ?: "Topic lesson could not be opened.",
                    )
                }
        }
    }

    fun openContent(content: ContentResponse): Boolean {
        if (content.status != "READY") return false
        openReadyContent(content)
        return true
    }

    private fun openReadyContent(content: ContentResponse, topicsLoading: Boolean? = null) {
        val task = content.asTaskResponse()
        val restoredProgress = progressStore.load(task.taskUuid)
        val history = (
            listOf(LessonHistoryEntry(task)) +
                state.value.history.filterNot { it.task.taskUuid == task.taskUuid }
        ).take(40)
        historyStore.save(history)
        mutableState.value = state.value.copy(
            topicsLoading = topicsLoading ?: state.value.topicsLoading,
            task = task,
            history = history,
            step = if (restoredProgress?.completed == true) LearningStep.REPORT else LearningStep.LISTEN,
            currentProgress = restoredProgress,
        )
        restoreProgress(task.taskUuid)
    }

    fun openTodayLesson(): Boolean {
        val content = state.value.dailyPlan?.content ?: return false
        if (content.status != "READY") return false
        val task = content.asTaskResponse()
        val entry = state.value.history.firstOrNull { it.task.taskUuid == task.taskUuid }
            ?: LessonHistoryEntry(task)
        openLesson(entry)
        return true
    }

    fun createLesson() {
        val prompt = state.value.prompt.trim()
        if (prompt.isEmpty()) {
            mutableState.value = state.value.copy(
                promptError = "Enter a topic before generating a lesson.",
            )
            return
        }
        if (state.value.loading) return
        viewModelScope.launch {
            mutableState.value = state.value.copy(
                loading = true,
                generationStage = GenerationStage.SUBMITTING,
                task = null,
                answer = null,
                quizCorrect = null,
                quizTotal = null,
                promptError = null,
                error = null,
            )
            runCatching {
                withTimeout(240_000) {
                    var task = api.create(
                        CreateTaskRequest(
                            prompt = prompt,
                            voice = state.value.voice,
                            difficulty = state.value.difficulty,
                        )
                    )
                    mutableState.value = state.value.copy(
                        generationStage = GenerationStage.PROCESSING,
                    )
                    var failedPolls = 0
                    while (task.status == "PENDING") {
                        delay(1_500)
                        try {
                            task = api.get(task.taskUuid)
                            failedPolls = 0
                        } catch (error: Exception) {
                            failedPolls++
                            if (failedPolls > 5) throw error
                        }
                    }
                    check(task.status == "COMPLETED") {
                        if (task.status == "FAILED") "Lesson generation failed on server."
                        else "Lesson generation finished with status ${task.status}"
                    }
                    task
                }
            }.onSuccess {
                val history = (
                    listOf(LessonHistoryEntry(it)) +
                        state.value.history.filterNot { old -> old.task.taskUuid == it.taskUuid }
                ).take(40)
                historyStore.save(history)
                mutableState.value = state.value.copy(
                    loading = false,
                    generationStage = GenerationStage.IDLE,
                    step = LearningStep.LISTEN,
                    task = it,
                    history = history,
                )
            }.onFailure {
                val message = if (it is TimeoutCancellationException) {
                    if (state.value.selectedLanguageId == "zh") {
                        "课程生成时间较长，任务仍可能在云端处理中。请稍后到课程库查看。"
                    } else {
                        "Generation is taking longer than expected. Check the Library shortly."
                    }
                } else {
                    it.message ?: if (state.value.selectedLanguageId == "zh") {
                        "课程生成失败，请检查网络后重试。"
                    } else {
                        "The lesson could not be generated. Check your connection and try again."
                    }
                }
                mutableState.value = state.value.copy(
                    loading = false,
                    generationStage = GenerationStage.IDLE,
                    error = message,
                )
            }
        }
    }

    fun retryLesson() = createLesson()

    fun openLesson(entry: LessonHistoryEntry) {
        val task = entry.task
        val restoredProgress = progressStore.load(task.taskUuid)
        mutableState.value = state.value.copy(
            prompt = task.prompt,
            voice = task.voice,
            difficulty = task.difficulty,
            task = task,
            answer = entry.answer,
            quizCorrect = entry.quizCorrect,
            quizTotal = entry.quizTotal,
            step = if (restoredProgress?.completed == true) LearningStep.REPORT else LearningStep.LISTEN,
            currentProgress = restoredProgress,
            error = null,
        )
        restoreProgress(task.taskUuid)
    }

    fun recordQuizResult(correct: Int, total: Int) {
        val taskUuid = state.value.task?.taskUuid ?: return
        updateHistory(taskUuid) { it.copy(quizCorrect = correct, quizTotal = total) }
        mutableState.value = state.value.copy(quizCorrect = correct, quizTotal = total)
        updateLearningProgress {
            it.copy(quizCorrect = correct, quizTotal = total)
        }
    }

    fun markVocabularyDone() = updateLearningProgress { it.copy(vocabularyDone = true) }

    fun reviewVocabulary(word: String, status: String) {
        val taskUuid = state.value.task?.taskUuid ?: return
        val normalized = status.uppercase().takeIf { it in setOf("LEARNING", "KNOWN") }
            ?: "LEARNING"
        mutableState.value = state.value.copy(
            vocabularyStatuses = state.value.vocabularyStatuses + (word to normalized),
        )
        viewModelScope.launch {
            runCatching {
                api.saveVocabularyProgress(
                    VocabularyProgressRequest(
                        clientId = clientId,
                        contentUuid = taskUuid,
                        word = word,
                        status = normalized,
                    )
                )
            }.onFailure {
                mutableState.value = state.value.copy(learningSyncMessage = offlineMessage())
            }
        }
    }

    fun markReadingDone() = updateLearningProgress { it.copy(readingDone = true) }

    fun onPlaybackProgress(positionMs: Long, durationMs: Long) {
        val taskUuid = state.value.task?.taskUuid ?: return
        val current = progressFor(taskUuid)
        val listeningDone = durationMs > 0 &&
            (positionMs >= durationMs * 85 / 100 || durationMs - positionMs <= 30_000)
        val updated = current.copy(
            positionMs = positionMs.coerceAtLeast(0),
            durationMs = durationMs.coerceAtLeast(0),
            listeningDone = current.listeningDone || listeningDone,
        ).withCompletion()
        progressStore.save(updated)
        mutableState.value = state.value.copy(
            currentProgress = updated,
            todayProgress = if (state.value.dailyPlan?.contentUuid == taskUuid) {
                updated
            } else {
                state.value.todayProgress
            },
        )
        if (progressSaveJob?.isActive != true) {
            progressSaveJob = viewModelScope.launch {
                delay(2_000)
                state.value.currentProgress
                    ?.takeIf { it.contentUuid == taskUuid }
                    ?.let { syncProgress(it) }
            }
        }
    }

    fun continueToSpeaking() {
        if (state.value.task != null) {
            mutableState.value = state.value.copy(step = LearningStep.SPEAK)
        }
    }

    fun showCompletionReport() {
        val progress = state.value.currentProgress ?: return
        if (progress.completed) {
            mutableState.value = state.value.copy(step = LearningStep.REPORT)
            loadLessonReview(progress.contentUuid)
        }
    }

    fun returnToLesson() {
        mutableState.value = state.value.copy(step = LearningStep.LISTEN)
    }

    fun startNewLesson() {
        mutableState.value = state.value.copy(
            step = LearningStep.CREATE,
            task = null,
            answer = null,
            quizCorrect = null,
            quizTotal = null,
            error = null,
        )
    }

    fun submitAnswer(recording: File) {
        val taskUuid = state.value.task?.taskUuid ?: return
        if (state.value.evaluating) return
        viewModelScope.launch {
            mutableState.value = state.value.copy(evaluating = true, error = null)
            runCatching {
                withTimeout(90_000) {
                    val body = recording.asRequestBody("audio/mp4".toMediaType())
                    var answer = api.uploadAnswer(
                        taskUuid,
                        MultipartBody.Part.createFormData("audio", recording.name, body),
                    )
                    while (answer.status == "PENDING") {
                        delay(1_000)
                        answer = api.getAnswer(answer.answerUuid)
                    }
                    check(answer.status == "COMPLETED") {
                        answer.failureReason
                            ?: "Speaking evaluation finished with status ${answer.status}"
                    }
                    answer
                }
            }.onSuccess {
                updateHistory(taskUuid) { entry -> entry.copy(answer = it) }
                mutableState.value = state.value.copy(evaluating = false, answer = it)
                updateLearningProgress { progress ->
                    progress.copy(speakingScore = it.score)
                }
                if (state.value.currentProgress?.completed == true) {
                    mutableState.value = state.value.copy(step = LearningStep.REPORT)
                }
            }.onFailure {
                mutableState.value = state.value.copy(
                    evaluating = false,
                    error = it.message ?: "The speaking answer could not be evaluated.",
                )
            }
        }
    }

    fun dismissError() {
        mutableState.value = state.value.copy(error = null)
    }

    private fun updateHistory(
        taskUuid: String,
        transform: (LessonHistoryEntry) -> LessonHistoryEntry,
    ) {
        val history = state.value.history.map { entry ->
            if (entry.task.taskUuid == taskUuid) transform(entry) else entry
        }
        historyStore.save(history)
        mutableState.value = state.value.copy(history = history)
    }

    private fun restoreProgress(contentUuid: String) {
        val local = progressFor(contentUuid)
        val isOpenLesson = state.value.task?.taskUuid == contentUuid
        val isTodayLesson = state.value.dailyPlan?.contentUuid == contentUuid
        val isNewReviewTarget = state.value.lessonReviewContentUuid != contentUuid
        mutableState.value = state.value.copy(
            currentProgress = if (isOpenLesson || state.value.task == null) {
                local
            } else {
                state.value.currentProgress
            },
            todayProgress = if (isTodayLesson) {
                local
            } else {
                state.value.todayProgress
            },
            learningSyncMessage = null,
            lessonReviewState = if (isNewReviewTarget) {
                ReviewContentState.Empty
            } else {
                state.value.lessonReviewState
            },
            lessonReviewContentUuid = contentUuid,
        )
        viewModelScope.launch {
            runCatching { api.learningProgress(clientId, contentUuid) }
                .onSuccess { remote ->
                    val merged = remote.asRequest().copy(
                        positionMs = maxOf(remote.positionMs, local.positionMs),
                        durationMs = maxOf(remote.durationMs, local.durationMs),
                        vocabularyDone = remote.vocabularyDone || local.vocabularyDone,
                        listeningDone = remote.listeningDone || local.listeningDone,
                        readingDone = remote.readingDone || local.readingDone,
                        quizCorrect = maxOf(remote.quizCorrect, local.quizCorrect),
                        quizTotal = maxOf(remote.quizTotal, local.quizTotal),
                        speakingScore = remote.speakingScore ?: local.speakingScore,
                        completed = remote.completed || local.completed,
                    ).withCompletion()
                    progressStore.save(merged)
                    val openNow = state.value.task?.taskUuid == contentUuid
                    val todayNow = state.value.dailyPlan?.contentUuid == contentUuid
                    if (openNow || todayNow) {
                        mutableState.value = state.value.copy(
                            currentProgress = if (openNow || state.value.task == null) {
                                merged
                            } else {
                                state.value.currentProgress
                            },
                            todayProgress = if (todayNow) {
                                merged
                            } else {
                                state.value.todayProgress
                            },
                            learningSyncMessage = null,
                            step = if (
                                openNow && merged.completed && state.value.step == LearningStep.LISTEN
                            ) {
                                LearningStep.REPORT
                            } else {
                                state.value.step
                            },
                        )
                    }
                    if (merged.completed) {
                        loadLessonReview(contentUuid)
                    }
                }
                .onFailure { error ->
                    val progressDoesNotExist = error is HttpException && error.code() == 404
                    if (!progressDoesNotExist && state.value.task?.taskUuid == contentUuid) {
                        mutableState.value = state.value.copy(
                            learningSyncMessage = offlineMessage(),
                        )
                    }
                }
        }
        viewModelScope.launch {
            runCatching { api.learningVocabulary(clientId, null) }
                .onSuccess { words ->
                    if (state.value.task?.taskUuid == contentUuid) {
                        mutableState.value = state.value.copy(
                            vocabularyStatuses = words
                                .filter { it.contentUuid == contentUuid }
                                .associate { it.word to it.status },
                        )
                    }
                }
        }
    }

    private fun updateLearningProgress(
        transform: (LearningProgressRequest) -> LearningProgressRequest,
    ) {
        val taskUuid = state.value.task?.taskUuid ?: return
        val updated = transform(progressFor(taskUuid)).withCompletion()
        progressStore.save(updated)
        mutableState.value = state.value.copy(
            currentProgress = updated,
            todayProgress = if (state.value.dailyPlan?.contentUuid == taskUuid) {
                updated
            } else {
                state.value.todayProgress
            },
        )
        progressSaveJob?.cancel()
        progressSaveJob = viewModelScope.launch { syncProgress(updated) }
    }

    private fun progressFor(contentUuid: String): LearningProgressRequest =
        state.value.currentProgress?.takeIf { it.contentUuid == contentUuid }
            ?: progressStore.load(contentUuid)
            ?: LearningProgressRequest(clientId = clientId, contentUuid = contentUuid)

    private suspend fun syncProgress(progress: LearningProgressRequest) {
        val safeProgress = if (progress.durationMs <= 0) {
            progress.copy(positionMs = 0)
        } else {
            progress.copy(positionMs = progress.positionMs.coerceAtMost(progress.durationMs))
        }
        runCatching { api.saveLearningProgress(safeProgress) }
            .onSuccess { saved ->
                mutableState.value = state.value.copy(learningSyncMessage = null)
                if (saved.completed) {
                    val completedProgress = safeProgress.copy(completed = true)
                    progressStore.save(completedProgress)
                    val isOpenLesson = state.value.task?.taskUuid == saved.contentUuid
                    val isTodayLesson = state.value.dailyPlan?.contentUuid == saved.contentUuid
                    mutableState.value = state.value.copy(
                        currentProgress = if (isOpenLesson) {
                            completedProgress
                        } else {
                            state.value.currentProgress
                        },
                        todayProgress = if (isTodayLesson) {
                            completedProgress
                        } else {
                            state.value.todayProgress
                        },
                    )
                    loadLessonReview(saved.contentUuid)
                }
            }
            .onFailure {
                mutableState.value = state.value.copy(learningSyncMessage = offlineMessage())
            }
    }

    private fun LearningProgressRequest.withCompletion(): LearningProgressRequest = copy(
        completed = completed || (
            vocabularyDone && listeningDone && readingDone &&
                quizTotal > 0 && speakingScore != null
            ),
    )

    private fun ttsPreviewErrorMessage(error: Throwable): String = when {
        error is HttpException && error.code() == 429 ->
            "Voice preview is temporarily rate-limited. Please try again shortly."
        error is HttpException && error.code() in setOf(400, 404, 422) ->
            "This voice is currently unavailable. Select another voice and try again."
        error is HttpException && error.code() >= 500 ->
            "The TTS service is temporarily unavailable. Please try again later."
        error.message.orEmpty().contains("timeout", ignoreCase = true) ->
            "Voice preview timed out. Check your connection and try again."
        else -> error.message?.takeIf { it.isNotBlank() }
            ?: "Voice preview failed. Check your connection and try again."
    }

    private fun loadLessonReview(contentUuid: String, force: Boolean = false) {
        val progress = progressStore.load(contentUuid)
            ?: state.value.currentProgress?.takeIf { it.contentUuid == contentUuid }
            ?: state.value.todayProgress?.takeIf { it.contentUuid == contentUuid }
        if (progress?.completed != true) return
        if (!force && state.value.lessonReviewContentUuid == contentUuid) {
            when (state.value.lessonReviewState) {
                ReviewContentState.Loading,
                is ReviewContentState.Data -> return
                else -> Unit
            }
        }
        mutableState.value = state.value.copy(
            lessonReviewState = ReviewContentState.Loading,
            lessonReviewContentUuid = contentUuid,
        )
        viewModelScope.launch {
            runCatching { api.lessonReviewReport(clientId, contentUuid) }
                .onSuccess { report ->
                    if (state.value.lessonReviewContentUuid == contentUuid) {
                        mutableState.value = state.value.copy(
                            lessonReviewState = report.asContentState(),
                        )
                    }
                }
                .onFailure { error ->
                    if (state.value.lessonReviewContentUuid == contentUuid) {
                        mutableState.value = state.value.copy(
                            lessonReviewState = ReviewContentState.Error(
                                error.message ?: localizedReviewMessage(
                                    english = "The lesson review could not be loaded.",
                                    chinese = "课程复盘加载失败。",
                                ),
                            ),
                        )
                    }
                }
        }
    }

    fun lookupWord(word: String, context: String? = null) {
        val clean = word.trim().trim(',', '.', '!', '?', '"', '\'', ';', ':')
        if (clean.isBlank()) return
        mutableState.value = state.value.copy(
            lookupLoading = true,
            lookupError = null,
            selectedLookupWord = LookupVocabularyResponse(word = clean, definitionCn = "Loading definition..."),
        )
        viewModelScope.launch {
            try {
                val resp = api.lookupVocabulary(LookupVocabularyRequest(word = clean, contextSentence = context))
                mutableState.value = state.value.copy(
                    lookupLoading = false,
                    selectedLookupWord = resp,
                )
            } catch (e: Exception) {
                mutableState.value = state.value.copy(
                    lookupLoading = false,
                    selectedLookupWord = LookupVocabularyResponse(
                        word = clean,
                        definitionCn = "Word: $clean",
                        contextExplanation = context,
                    ),
                    lookupError = e.message,
                )
            }
        }
    }

    fun dismissWordLookup() {
        mutableState.value = state.value.copy(selectedLookupWord = null, lookupLoading = false, lookupError = null)
    }

    fun saveWordToBook(
        word: String,
        definitionCn: String,
        definitionEn: String? = null,
        phoneticUs: String? = null,
        context: String? = null,
        contentUuid: String? = null,
        startMs: Int? = null,
        endMs: Int? = null,
    ) {
        viewModelScope.launch {
            try {
                api.saveUserVocabulary(
                    SaveUserVocabularyRequest(
                        clientId = clientId,
                        word = word,
                        definitionCn = definitionCn,
                        definitionEn = definitionEn,
                        phoneticUs = phoneticUs,
                        contextSentence = context,
                        contentUuid = contentUuid,
                        sentenceStartMs = startMs,
                        sentenceEndMs = endMs,
                    )
                )
                loadUserWordbook()
            } catch (_: Exception) {}
        }
    }

    fun loadUserWordbook() {
        viewModelScope.launch {
            try {
                val list = api.getUserVocabulary(clientId)
                mutableState.value = state.value.copy(userWordbook = list)
            } catch (_: Exception) {}
        }
    }

    fun startSpeakingSession(contentUuid: String, scenario: String = "SYSTEM_DESIGN_INTERVIEW", role: String = "TECH_LEAD") {
        mutableState.value = state.value.copy(speakingCoachLoading = true, speakingCoachFeedback = null)
        viewModelScope.launch {
            try {
                val session = api.createSpeakingSession(
                    CreateSpeakingSessionRequest(
                        clientId = clientId,
                        contentUuid = contentUuid,
                        scenario = scenario,
                        role = role,
                    )
                )
                mutableState.value = state.value.copy(
                    activeSpeakingSession = session,
                    speakingSessionTurns = listOf(
                        SpeakingTurnDetail(
                            turnIndex = 1,
                            aiPromptText = session.aiPromptText,
                            aiAudioUrl = session.aiAudioUrl,
                        )
                    ),
                    speakingCoachLoading = false,
                )
            } catch (e: Exception) {
                mutableState.value = state.value.copy(
                    speakingCoachLoading = false,
                    speakingCoachFeedback = "Could not start session: ${e.message}",
                )
            }
        }
    }

    fun submitSpeakingSessionAudio(audioFile: File, turnIndex: Int) {
        val currentSession = state.value.activeSpeakingSession ?: return
        mutableState.value = state.value.copy(speakingCoachLoading = true)
        viewModelScope.launch {
            try {
                val reqBody = audioFile.asRequestBody("audio/mp4".toMediaType())
                val part = MultipartBody.Part.createFormData("audio", audioFile.name, reqBody)
                val resp = api.submitSpeakingTurn(currentSession.sessionId, turnIndex, part)
                val updatedTurns = state.value.speakingSessionTurns.toMutableList()
                val turnIdx = updatedTurns.indexOfFirst { it.turnIndex == turnIndex }
                if (turnIdx != -1) {
                    updatedTurns[turnIdx] = updatedTurns[turnIdx].copy(
                        userTranscript = resp.userTranscript,
                        pronunciationScore = resp.pronunciationScore,
                        grammarScore = resp.grammarScore,
                        quickFeedback = resp.quickFeedback,
                    )
                }
                resp.nextTurn?.let { next ->
                    updatedTurns.add(
                        SpeakingTurnDetail(
                            turnIndex = next.turnIndex,
                            aiPromptText = next.aiPromptText,
                            aiAudioUrl = next.aiAudioUrl,
                        )
                    )
                }
                mutableState.value = state.value.copy(
                    speakingSessionTurns = updatedTurns,
                    speakingCoachLoading = false,
                    speakingCoachFeedback = resp.quickFeedback,
                )
            } catch (e: Exception) {
                mutableState.value = state.value.copy(
                    speakingCoachLoading = false,
                    speakingCoachFeedback = "Submission error: ${e.message}",
                )
            }
        }
    }

    fun dismissSpeakingSession() {
        mutableState.value = state.value.copy(activeSpeakingSession = null, speakingSessionTurns = emptyList(), speakingCoachLoading = false)
    }

    private fun localizedReviewMessage(english: String, chinese: String): String =
        if (state.value.selectedLanguageId == AppLanguage.CHINESE.id) chinese else english

    private fun offlineMessage(): String =
        if (state.value.selectedLanguageId == AppLanguage.CHINESE.id) {
            "云端暂不可用，当前进度已保存在本机，联网后可继续学习。"
        } else {
            "Cloud sync is unavailable. Progress is saved on this device so you can keep learning."
        }
}
