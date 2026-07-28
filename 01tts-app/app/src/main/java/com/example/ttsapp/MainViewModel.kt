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
import com.example.ttsapp.network.TopicRecommendationResponse
import com.example.ttsapp.network.VocabularyProgressRequest
import java.io.File
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
}

enum class GenerationStage {
    IDLE,
    SUBMITTING,
    PROCESSING,
}

data class LearningUiState(
    val prompt: String = "",
    val voice: String = "en-US-AvaNeural",
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
)

class MainViewModel(
    private val api: TaskApi,
    private val historyStore: LessonHistoryStore = InMemoryLessonHistoryStore(),
    private val themeStore: ThemePreferenceStore = InMemoryThemePreferenceStore(),
    private val languageStore: LanguagePreferenceStore = InMemoryLanguagePreferenceStore(),
    private val clientIdStore: ClientIdStore = InMemoryClientIdStore(),
    private val progressStore: LearningProgressStore = InMemoryLearningProgressStore(),
) : ViewModel() {
    private val clientId = clientIdStore.loadOrCreate()
    private var progressSaveJob: Job? = null
    private val mutableState = MutableStateFlow(
        LearningUiState(
            history = historyStore.load(),
            selectedThemeId = themeStore.load(),
            selectedLanguageId = languageStore.load(),
            clientId = clientId,
        )
    )
    val state: StateFlow<LearningUiState> = mutableState.asStateFlow()

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
        mutableState.value = state.value.copy(voice = voice)
    }

    fun setDifficulty(difficulty: String) {
        mutableState.value = state.value.copy(difficulty = difficulty)
    }

    fun refreshDaily() {
        if (state.value.dailyLoading) return
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
                    val readyEntries = contents
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
                        libraryContents = contents,
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
        val history = (
            listOf(LessonHistoryEntry(task)) +
                state.value.history.filterNot { it.task.taskUuid == task.taskUuid }
        ).take(40)
        historyStore.save(history)
        mutableState.value = state.value.copy(
            topicsLoading = topicsLoading ?: state.value.topicsLoading,
            task = task,
            history = history,
            step = LearningStep.LISTEN,
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
        mutableState.value = state.value.copy(
            prompt = task.prompt,
            voice = task.voice,
            difficulty = task.difficulty,
            task = task,
            answer = entry.answer,
            quizCorrect = entry.quizCorrect,
            quizTotal = entry.quizTotal,
            step = LearningStep.LISTEN,
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
                        "Speaking evaluation finished with status ${answer.status}"
                    }
                    answer
                }
            }.onSuccess {
                updateHistory(taskUuid) { entry -> entry.copy(answer = it) }
                mutableState.value = state.value.copy(evaluating = false, answer = it)
                updateLearningProgress { progress ->
                    progress.copy(speakingScore = it.score)
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
                        )
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
            .onSuccess {
                mutableState.value = state.value.copy(learningSyncMessage = null)
            }
            .onFailure {
                mutableState.value = state.value.copy(learningSyncMessage = offlineMessage())
            }
    }

    private fun LearningProgressRequest.withCompletion(): LearningProgressRequest = copy(
        completed = vocabularyDone && listeningDone && readingDone &&
            quizTotal > 0 && speakingScore != null,
    )

    private fun offlineMessage(): String =
        if (state.value.selectedLanguageId == AppLanguage.CHINESE.id) {
            "云端暂不可用，当前进度已保存在本机，联网后可继续学习。"
        } else {
            "Cloud sync is unavailable. Progress is saved on this device so you can keep learning."
        }
}
