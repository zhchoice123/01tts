package com.example.ttsapp

import com.example.ttsapp.network.AnswerResponse
import com.example.ttsapp.network.AppReleaseResponse
import com.example.ttsapp.network.ContentResponse
import com.example.ttsapp.network.CreateLongLessonRequest
import com.example.ttsapp.network.CreateTaskRequest
import com.example.ttsapp.network.DailyPlanResponse
import com.example.ttsapp.network.LearningDashboardResponse
import com.example.ttsapp.network.LearningProgressRequest
import com.example.ttsapp.network.LearningProgressResponse
import com.example.ttsapp.network.TaskApi
import com.example.ttsapp.network.TaskResponse
import com.example.ttsapp.network.TtsDemoRequest
import com.example.ttsapp.network.TtsDemoResponse
import com.example.ttsapp.network.TopicLessonResponse
import com.example.ttsapp.network.TopicRecommendationResponse
import com.example.ttsapp.network.CreateSpeakingSessionRequest
import com.example.ttsapp.network.LookupVocabularyRequest
import com.example.ttsapp.network.LookupVocabularyResponse
import com.example.ttsapp.network.SaveUserVocabularyRequest
import com.example.ttsapp.network.SpeakingSessionResponse
import com.example.ttsapp.network.SpeakingSessionDetailResponse
import com.example.ttsapp.network.SpeakingTurnDetail
import com.example.ttsapp.network.SpeakingTurnResponse
import com.example.ttsapp.network.UserVocabularyCardResponse
import com.example.ttsapp.network.VocabularyProgressRequest
import com.example.ttsapp.network.VocabularyProgressResponse
import com.example.ttsapp.review.LessonReviewReportResponse
import com.example.ttsapp.review.ReviewContentState
import com.example.ttsapp.review.ReviewDimension
import com.example.ttsapp.review.ReviewQueueItem
import com.example.ttsapp.review.ReviewQueueResponse
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import okhttp3.MultipartBody
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

@OptIn(ExperimentalCoroutinesApi::class)
class MainViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    @Before
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun createLessonPollsUntilCompleted() = runTest(dispatcher) {
        val api = FakeTaskApi()
        val model = MainViewModel(api)
        model.setPrompt("Explain locks")
        model.setDifficulty("hard")
        model.setVoice("en-US-AndrewNeural")

        model.createLesson()
        advanceUntilIdle()

        assertEquals("COMPLETED", model.state.value.task?.status)
        assertEquals(LearningStep.LISTEN, model.state.value.step)
        assertEquals(GenerationStage.IDLE, model.state.value.generationStage)
        assertEquals(1, model.state.value.history.size)
        assertEquals(1, api.pollCount)
        assertEquals("hard", api.created?.difficulty)
        assertEquals("openai:en-US-AndrewNeural", api.created?.voice)
    }

    @Test
    fun emptyPromptShowsInlineValidation() {
        val model = MainViewModel(FakeTaskApi())

        model.createLesson()

        assertNotNull(model.state.value.promptError)
        assertNull(model.state.value.task)
    }

    @Test
    fun completedLessonIsPersistedAndCanBeReopened() = runTest(dispatcher) {
        val store = InMemoryLessonHistoryStore()
        val model = MainViewModel(FakeTaskApi(), store)
        model.setPrompt("Explain locks")
        model.createLesson()
        advanceUntilIdle()

        val restored = MainViewModel(FakeTaskApi(), store)
        restored.openLesson(restored.state.value.history.first())

        assertEquals(LearningStep.LISTEN, restored.state.value.step)
        assertEquals("task-1", restored.state.value.task?.taskUuid)
    }

    @Test
    fun quizAndSpeakingResultsArePersistedWithLesson() = runTest(dispatcher) {
        val store = InMemoryLessonHistoryStore()
        val model = MainViewModel(FakeTaskApi(), store)
        model.setPrompt("Explain locks")
        model.createLesson()
        advanceUntilIdle()

        model.recordQuizResult(correct = 2, total = 3)
        val recording = File.createTempFile("answer", ".m4a").apply {
            writeBytes(ByteArray(1024))
            deleteOnExit()
        }
        model.submitAnswer(recording)
        advanceUntilIdle()

        val restored = MainViewModel(FakeTaskApi(), store)
        val entry = restored.state.value.history.first()
        assertEquals(2, entry.quizCorrect)
        assertEquals(3, entry.quizTotal)
        assertEquals(86, entry.answer?.score)
    }

    @Test
    fun refreshDailyLoadsTodayAndAllCloudStatuses() = runTest(dispatcher) {
        val model = MainViewModel(FakeTaskApi())

        model.refreshDaily()
        advanceUntilIdle()

        assertEquals("daily-1", model.state.value.dailyPlan?.contentUuid)
        assertEquals(listOf("READY", "GENERATING"), model.state.value.libraryContents.map { it.status })
        assertEquals(1, model.state.value.history.size)
        assertTrue(model.openTodayLesson())
    }

    @Test
    fun generateDailyPlanUsesClientDateAndRestoresTheGeneratedLesson() = runTest(dispatcher) {
        val api = FakeTaskApi()
        val model = MainViewModel(
            api = api,
            currentDate = { "2026-08-18" },
        )

        model.generateDailyPlan()
        advanceUntilIdle()

        assertEquals(listOf("2026-08-18"), api.generatedPlanDates)
        assertEquals("daily-1", model.state.value.dailyPlan?.contentUuid)
        assertFalse(model.state.value.dailyLoading)
        assertNull(model.state.value.dailyError)
    }

    @Test
    fun longLessonSubmissionReturnsImmediatelyWithoutPolling() = runTest(dispatcher) {
        val api = FakeTaskApi()
        val model = MainViewModel(api)
        model.setVoice("en-US-AvaNeural")

        model.requestLongLesson("Spring transaction boundaries", "JAVA")
        advanceUntilIdle()

        assertEquals("long-1", model.state.value.longLessonTaskUuid)
        assertNotNull(model.state.value.longLessonMessage)
        assertFalse(model.state.value.longLessonSubmitting)
        assertEquals("GENERATING", model.state.value.libraryContents.first().status)
        assertEquals("Spring transaction boundaries", api.createdLong?.topic)
        assertEquals("JAVA", api.createdLong?.category)
        assertEquals("B1", api.createdLong?.level)
        assertEquals("AUTO", api.createdLong?.sourceMode)
        assertEquals(0, api.contentPollCount)
    }

    @Test
    fun blankLongLessonTopicIsSentAsNullForRandomSelection() = runTest(dispatcher) {
        val api = FakeTaskApi()
        val model = MainViewModel(api)

        model.requestLongLesson("   ", "BACKEND")
        advanceUntilIdle()

        assertNull(api.createdLong?.topic)
        assertEquals("BACKEND", api.createdLong?.category)
    }

    @Test
    fun selectedThemeAndLanguagePersistAcrossViewModels() {
        val themeStore = InMemoryThemePreferenceStore()
        val languageStore = InMemoryLanguagePreferenceStore()
        val model = MainViewModel(
            api = FakeTaskApi(),
            themeStore = themeStore,
            languageStore = languageStore,
        )

        model.setTheme("nordic")
        model.setLanguage("zh")

        val restored = MainViewModel(
            api = FakeTaskApi(),
            themeStore = themeStore,
            languageStore = languageStore,
        )
        assertEquals("nordic", restored.state.value.selectedThemeId)
        assertEquals("zh", restored.state.value.selectedLanguageId)
    }

    @Test
    fun onboardingSelectionsPersistAndCompletionDoesNotRepeat() {
        val onboardingStore = InMemoryOnboardingPreferenceStore()
        val model = MainViewModel(
            api = FakeTaskApi(),
            onboardingStore = onboardingStore,
        )

        assertFalse(model.state.value.onboarding.completed)
        model.setOnboardingGoal("SPEAKING")
        model.setOnboardingLevel("B2")
        model.setOnboardingMinutes(30)
        model.completeOnboarding()

        val restored = MainViewModel(
            api = FakeTaskApi(),
            onboardingStore = onboardingStore,
        )
        assertTrue(restored.state.value.onboarding.completed)
        assertEquals("SPEAKING", restored.state.value.onboarding.goal)
        assertEquals("B2", restored.state.value.onboarding.level)
        assertEquals(30, restored.state.value.onboarding.dailyMinutes)
        assertNotNull(restored.state.value.onboarding.completedAt)
    }

    @Test
    fun existingHistoryAutomaticallySkipsNewOnboarding() {
        val historyStore = InMemoryLessonHistoryStore().apply {
            save(listOf(LessonHistoryEntry(task = TaskResponse(
                taskUuid = "legacy-1",
                prompt = "Explain locks",
                voice = "openai:nova",
                difficulty = "B1",
                status = "COMPLETED",
            ))))
        }
        val model = MainViewModel(
            api = FakeTaskApi(),
            historyStore = historyStore,
            onboardingStore = InMemoryOnboardingPreferenceStore(),
        )

        assertTrue(model.state.value.onboarding.completed)
    }

    @Test
    fun dailyTopicsCanBeLoadedAndOpened() = runTest(dispatcher) {
        val api = FakeTaskApi()
        val model = MainViewModel(api)

        model.refreshTopics()
        advanceUntilIdle()
        assertEquals(1, model.state.value.topics.size)

        model.openTopic(model.state.value.topics.single())
        advanceUntilIdle()
        assertEquals("topic-content-1", model.state.value.task?.taskUuid)
    }

    @Test
    fun readyLessonRestoresRemotePlaybackAndSavesFiveStepProgress() = runTest(dispatcher) {
        val api = FakeTaskApi()
        val model = MainViewModel(
            api = api,
            clientIdStore = InMemoryClientIdStore("00000000-0000-4000-8000-000000000042"),
        )

        model.refreshDaily()
        advanceUntilIdle()
        assertEquals(42_000L, model.state.value.currentProgress?.positionMs)
        assertEquals(31, model.state.value.dashboard?.listeningMinutes)

        assertTrue(model.openTodayLesson())
        advanceUntilIdle()
        model.markVocabularyDone()
        model.markReadingDone()
        model.recordQuizResult(4, 5)
        model.onPlaybackProgress(90_000, 100_000)
        advanceUntilIdle()

        assertTrue(api.savedProgress.any { it.vocabularyDone })
        assertTrue(model.state.value.currentProgress?.readingDone == true)
        assertTrue(model.state.value.currentProgress?.listeningDone == true)
        assertEquals(5, model.state.value.currentProgress?.quizTotal)
    }

    @Test
    fun cloudFailureKeepsLocalProgressAndShowsOfflineMessage() = runTest(dispatcher) {
        val api = FakeTaskApi().apply { failLearningApi = true }
        val local = InMemoryLearningProgressStore().apply {
            save(
                LearningProgressRequest(
                    clientId = "offline-client",
                    contentUuid = "daily-1",
                    positionMs = 73_000,
                )
            )
        }
        val model = MainViewModel(
            api = api,
            clientIdStore = InMemoryClientIdStore("offline-client"),
            progressStore = local,
        )

        model.refreshDaily()
        advanceUntilIdle()

        assertEquals(73_000L, model.state.value.currentProgress?.positionMs)
        assertNotNull(model.state.value.learningSyncMessage)
        assertTrue(model.openTodayLesson())
    }

    @Test
    fun missingRemoteProgressIsNotReportedAsOffline() = runTest(dispatcher) {
        val api = FakeTaskApi().apply { missingLearningProgress = true }
        val model = MainViewModel(api)

        model.refreshDaily()
        advanceUntilIdle()

        assertNull(model.state.value.learningSyncMessage)
        assertEquals(0L, model.state.value.currentProgress?.positionMs)
    }

    @Test
    fun refreshDailyLoadsReviewQueueWithoutCouplingItsFailureToDailyLesson() = runTest(dispatcher) {
        val api = FakeTaskApi().apply { failReviewQueue = true }
        val model = MainViewModel(
            api = api,
            currentDate = { "2026-08-01" },
        )

        model.refreshDaily()
        assertTrue(model.state.value.reviewQueueState is ReviewContentState.Loading)
        advanceUntilIdle()

        assertEquals("daily-1", model.state.value.dailyPlan?.contentUuid)
        assertNull(model.state.value.dailyError)
        assertTrue(model.state.value.reviewQueueState is ReviewContentState.Error)
        assertEquals(listOf("2026-08-01"), api.reviewQueueDates)
    }

    @Test
    fun reviewQueueSupportsDataEmptyAndIndependentRetry() = runTest(dispatcher) {
        val api = FakeTaskApi()
        val model = MainViewModel(api = api, currentDate = { "2026-08-02" })

        model.refreshReviewQueue()
        advanceUntilIdle()
        val data = model.state.value.reviewQueueState as ReviewContentState.Data
        assertEquals("daily-1", data.value.items.single().contentUuid)

        api.emptyReviewQueue = true
        model.refreshReviewQueue()
        advanceUntilIdle()
        assertTrue(model.state.value.reviewQueueState is ReviewContentState.Empty)
        assertEquals(2, api.reviewQueueDates.size)
    }

    @Test
    fun lessonReviewIsRequestedOnlyAfterCompletedProgressIsRestored() = runTest(dispatcher) {
        val incompleteApi = FakeTaskApi()
        val incomplete = MainViewModel(incompleteApi)
        incomplete.refreshDaily()
        advanceUntilIdle()
        assertTrue(incompleteApi.reportRequests.isEmpty())
        assertTrue(incomplete.state.value.lessonReviewState is ReviewContentState.Empty)

        val completedApi = FakeTaskApi().apply { remoteProgressCompleted = true }
        val completed = MainViewModel(completedApi)
        completed.refreshDaily()
        advanceUntilIdle()

        assertEquals(listOf("daily-1"), completedApi.reportRequests)
        assertTrue(completed.state.value.lessonReviewState is ReviewContentState.Data)
    }

    @Test
    fun lessonReviewFailureRemainsLocalAndCanBeRetried() = runTest(dispatcher) {
        val api = FakeTaskApi().apply {
            remoteProgressCompleted = true
            failLessonReview = true
        }
        val model = MainViewModel(api)

        model.refreshDaily()
        advanceUntilIdle()

        assertEquals("daily-1", model.state.value.dailyPlan?.contentUuid)
        assertNull(model.state.value.error)
        assertTrue(model.state.value.lessonReviewState is ReviewContentState.Error)

        api.failLessonReview = false
        model.refreshLessonReview()
        assertTrue(model.state.value.lessonReviewState is ReviewContentState.Loading)
        advanceUntilIdle()
        assertTrue(model.state.value.lessonReviewState is ReviewContentState.Data)
        assertEquals(2, api.reportRequests.size)
    }

    @Test
    fun successfulCompletedSyncLoadsLessonReview() = runTest(dispatcher) {
        val api = FakeTaskApi().apply { missingLearningProgress = true }
        val model = MainViewModel(api)
        model.refreshDaily()
        advanceUntilIdle()
        assertTrue(model.openTodayLesson())
        advanceUntilIdle()

        model.markVocabularyDone()
        model.markReadingDone()
        model.recordQuizResult(4, 5)
        model.onPlaybackProgress(90_000, 100_000)
        val recording = File.createTempFile("review-answer", ".m4a").apply {
            writeBytes(ByteArray(1024))
            deleteOnExit()
        }
        model.submitAnswer(recording)
        advanceUntilIdle()

        assertTrue(model.state.value.currentProgress?.completed == true)
        assertEquals(LearningStep.REPORT, model.state.value.step)
        assertEquals(listOf("daily-1"), api.reportRequests)
        assertTrue(model.state.value.lessonReviewState is ReviewContentState.Data)
    }

    @Test
    fun reviewQueueItemOpensAvailableLessonAndMissingLessonFailsSafely() = runTest(dispatcher) {
        val model = MainViewModel(FakeTaskApi())
        model.refreshDaily()
        advanceUntilIdle()
        val item = (model.state.value.reviewQueueState as ReviewContentState.Data)
            .value.items.single()

        assertTrue(model.openReviewQueueItem(item))
        assertEquals("daily-1", model.state.value.task?.taskUuid)
        assertEquals(LearningStep.LISTEN, model.state.value.step)

        assertFalse(
            model.openReviewQueueItem(
                ReviewQueueItem(id = "missing", contentUuid = "not-local"),
            )
        )
        assertNotNull(model.state.value.reviewQueueMessage)
        assertEquals("daily-1", model.state.value.task?.taskUuid)
    }

    @Test
    fun lookupAndSaveVocabularyFlow() = runTest(dispatcher) {
        val api = FakeTaskApi()
        val model = MainViewModel(api)

        model.lookupWord("throughput", "Connection pools improve throughput.")
        advanceUntilIdle()

        assertEquals("throughput", model.state.value.selectedLookupWord?.word)
        assertEquals("测试定义", model.state.value.selectedLookupWord?.definitionCn)

        model.saveWordToBook("throughput", "测试定义")
        advanceUntilIdle()

        assertEquals(1, model.state.value.userWordbook.size)
        assertEquals("concurrency", model.state.value.userWordbook[0].word)

        model.dismissWordLookup()
        assertNull(model.state.value.selectedLookupWord)
    }

    @Test
    fun startAndDismissSpeakingSession() = runTest(dispatcher) {
        val api = FakeTaskApi()
        val model = MainViewModel(api)

        model.startSpeakingSession("daily-1")
        advanceUntilIdle()

        assertNotNull(model.state.value.activeSpeakingSession)
        assertEquals("sess-1", model.state.value.activeSpeakingSession?.sessionId)
        assertEquals(1, model.state.value.speakingSessionTurns.size)

        model.dismissSpeakingSession()
        assertNull(model.state.value.activeSpeakingSession)
    }

    @Test
    fun normalizeTtsVoiceHandlesPrefixesCorrectly() {
        val (p1, v1) = normalizeTtsVoice("openai:nova", "openai")
        assertEquals("openai", p1)
        assertEquals("openai:nova", v1)

        val (p2, v2) = normalizeTtsVoice("aliyun:loongdavid_v2", "openai")
        assertEquals("aliyun", p2)
        assertEquals("aliyun:loongdavid_v2", v2)

        val (p3, v3) = normalizeTtsVoice("nova", "openai")
        assertEquals("openai", p3)
        assertEquals("openai:nova", v3)

        val (p4, v4) = normalizeTtsVoice("loongdavid_v2", "aliyun")
        assertEquals("aliyun", p4)
        assertEquals("aliyun:loongdavid_v2", v4)

        val (p5, v5) = normalizeTtsVoice("openai:openai:nova", "openai")
        assertEquals("openai", p5)
        assertEquals("openai:nova", v5)
    }

    @Test
    fun setTtsVoiceNeverDuplicatesPrefix() = runTest(dispatcher) {
        val api = FakeTaskApi()
        val model = MainViewModel(api)

        model.setTtsVoice("openai:nova")
        assertEquals("openai:nova", model.state.value.voice)
        assertEquals("openai", model.state.value.ttsProvider)

        model.setTtsVoice("openai:nova")
        assertEquals("openai:nova", model.state.value.voice)

        model.setTtsVoice("nova")
        assertEquals("openai:nova", model.state.value.voice)

        model.setTtsVoice("aliyun:loongdavid_v2")
        assertEquals("aliyun:loongdavid_v2", model.state.value.voice)
        assertEquals("aliyun", model.state.value.ttsProvider)
    }

    @Test
    fun ttsPreviewKeepsRequestedAndActualVoiceAligned() = runTest(dispatcher) {
        val api = FakeTaskApi().apply {
            previewResponseVoice = "aliyun:loongabby_v2"
        }
        val model = MainViewModel(api)
        model.setTtsProvider("aliyun")
        model.setTtsVoice("aliyun:loongabby_v2")

        model.previewTtsVoice()
        advanceUntilIdle()

        assertEquals("aliyun:loongabby_v2", api.lastPreviewRequest?.voice)
        assertEquals("aliyun:loongabby_v2", model.state.value.ttsPreviewVoice)
        assertEquals("/api/v1/tts/demo/preview.mp3", model.state.value.ttsPreviewUrl)
        assertNull(model.state.value.ttsPreviewError)

        model.setTtsVoice("aliyun:loongdavid_v2")
        assertNull(model.state.value.ttsPreviewVoice)
        assertNull(model.state.value.ttsPreviewUrl)
    }

    @Test
    fun completedLessonReopensAtCompletionReport() {
        val progressStore = InMemoryLearningProgressStore().apply {
            save(
                LearningProgressRequest(
                    clientId = "client",
                    contentUuid = "task-1",
                    vocabularyDone = true,
                    listeningDone = true,
                    readingDone = true,
                    quizCorrect = 4,
                    quizTotal = 5,
                    speakingScore = 86,
                    completed = true,
                )
            )
        }
        val entry = LessonHistoryEntry(
            task = TaskResponse(
                taskUuid = "task-1",
                prompt = "Explain locks",
                voice = "openai:nova",
                difficulty = "medium",
                status = "COMPLETED",
            )
        )
        val model = MainViewModel(FakeTaskApi(), progressStore = progressStore)

        model.openLesson(entry)

        assertEquals(LearningStep.REPORT, model.state.value.step)
        assertTrue(model.state.value.currentProgress?.completed == true)
    }

    private class FakeTaskApi : TaskApi {
        var created: CreateTaskRequest? = null
        var createdLong: CreateLongLessonRequest? = null
        var pollCount = 0
        var contentPollCount = 0
        var failLearningApi = false
        var missingLearningProgress = false
        var failReviewQueue = false
        var emptyReviewQueue = false
        var remoteProgressCompleted = false
        var failLessonReview = false
        val savedProgress = mutableListOf<LearningProgressRequest>()
        val reviewQueueDates = mutableListOf<String>()
        val reportRequests = mutableListOf<String>()
        val generatedPlanDates = mutableListOf<String>()
        var previewResponseVoice: String? = null
        var lastPreviewRequest: TtsDemoRequest? = null

        override suspend fun previewTts(request: TtsDemoRequest): TtsDemoResponse {
            lastPreviewRequest = request
            return TtsDemoResponse(
                voice = previewResponseVoice ?: request.voice,
                audioUrl = "/api/v1/tts/demo/preview.mp3",
            )
        }

        override suspend fun create(request: CreateTaskRequest): TaskResponse {
            created = request
            return task("PENDING")
        }

        override suspend fun get(uuid: String): TaskResponse {
            pollCount += 1
            return task("COMPLETED")
        }

        override suspend fun uploadAnswer(
            uuid: String,
            audio: MultipartBody.Part,
        ): AnswerResponse = AnswerResponse(
            answerUuid = "answer-1",
            taskUuid = uuid,
            status = "COMPLETED",
            audioUrl = "/audio/answer-1.m4a",
            transcript = "Locks protect shared state.",
            score = 86,
            feedback = "Clear explanation.",
        )

        override suspend fun getAnswer(uuid: String): AnswerResponse = error("not used")

        override suspend fun today(): DailyPlanResponse = DailyPlanResponse(
            planDate = "2026-07-28",
            contentUuid = "daily-1",
            content = dailyContent(),
        )

        override suspend fun generateDailyPlan(planDate: String): DailyPlanResponse =
            DailyPlanResponse(
                planDate = planDate,
                contentUuid = "daily-1",
                content = dailyContent(),
            ).also { generatedPlanDates += planDate }

        override suspend fun library(): List<ContentResponse> = listOf(
            dailyContent(),
            longContent(),
            failedContent(),
        )

        override suspend fun createLongLesson(
            request: CreateLongLessonRequest,
        ): ContentResponse {
            createdLong = request
            return longContent()
        }

        override suspend fun topics(
            planDate: String?,
            limit: Int,
        ): List<TopicRecommendationResponse> = listOf(topic())

        override suspend fun topicLesson(uuid: String): TopicLessonResponse =
            TopicLessonResponse(topic(), topicContent())

        override suspend fun getContent(uuid: String): ContentResponse {
            contentPollCount += 1
            return topicContent()
        }

        override suspend fun saveLearningProgress(
            request: LearningProgressRequest,
        ): LearningProgressResponse {
            if (failLearningApi) error("offline")
            savedProgress += request
            return request.asResponse()
        }

        override suspend fun learningProgress(
            clientId: String,
            contentUuid: String,
        ): LearningProgressResponse {
            if (failLearningApi) error("offline")
            if (missingLearningProgress) {
                throw HttpException(
                    Response.error<LearningProgressResponse>(
                        404,
                        "missing".toResponseBody(),
                    )
                )
            }
            return LearningProgressResponse(
                clientId = clientId,
                contentUuid = contentUuid,
                positionMs = 42_000,
                durationMs = 100_000,
                vocabularyDone = remoteProgressCompleted,
                listeningDone = remoteProgressCompleted,
                readingDone = remoteProgressCompleted,
                quizCorrect = if (remoteProgressCompleted) 4 else 0,
                quizTotal = if (remoteProgressCompleted) 5 else 0,
                speakingScore = if (remoteProgressCompleted) 86 else null,
                completed = remoteProgressCompleted,
            )
        }

        override suspend fun learningDashboard(
            clientId: String,
            days: Int,
        ): LearningDashboardResponse {
            if (failLearningApi) error("offline")
            return LearningDashboardResponse(
                days = days,
                listeningMinutes = 31,
                completedLessons = 2,
                quizCorrect = 8,
                quizTotal = 10,
                speakingAverage = 84,
                currentStreak = 3,
                wordsReviewed = 17,
            )
        }

        override suspend fun saveVocabularyProgress(
            request: VocabularyProgressRequest,
        ): VocabularyProgressResponse = VocabularyProgressResponse(
            clientId = request.clientId,
            contentUuid = request.contentUuid,
            word = request.word,
            status = request.status,
        )

        override suspend fun learningVocabulary(
            clientId: String,
            status: String?,
        ): List<VocabularyProgressResponse> = emptyList()

        override suspend fun lessonReviewReport(
            clientId: String,
            contentUuid: String,
        ): LessonReviewReportResponse {
            reportRequests += contentUuid
            if (failLessonReview) error("review report unavailable")
            return LessonReviewReportResponse(
                clientId = clientId,
                contentUuid = contentUuid,
                overallScore = 88,
                dimensions = listOf(
                    ReviewDimension("listening", "Listening", 88, "STRONG"),
                ),
                nextActions = listOf("Continue learning"),
                generatedAt = "2026-08-01T08:00:00Z",
            )
        }

        override suspend fun reviewQueue(
            clientId: String,
            date: String,
            limit: Int,
        ): ReviewQueueResponse {
            reviewQueueDates += date
            if (failReviewQueue) error("review service unavailable")
            val items = if (emptyReviewQueue) emptyList() else listOf(
                ReviewQueueItem(
                    id = "review-1",
                    type = "VOCABULARY",
                    contentUuid = "daily-1",
                    title = "Review virtual threads",
                    priority = 1,
                )
            )
            return ReviewQueueResponse(
                clientId = clientId,
                date = date,
                totalCount = items.size,
                estimatedMinutes = items.size,
                items = items,
            )
        }

        override suspend fun latestAppRelease(): AppReleaseResponse = error("not used")

        override suspend fun lookupVocabulary(request: LookupVocabularyRequest): LookupVocabularyResponse =
            LookupVocabularyResponse(
                word = request.word,
                phoneticUs = "/test/",
                definitionCn = "测试定义",
            )

        override suspend fun saveUserVocabulary(request: SaveUserVocabularyRequest): UserVocabularyCardResponse =
            UserVocabularyCardResponse(
                id = 1,
                clientId = request.clientId,
                word = request.word,
                definitionCn = request.definitionCn,
            )

        override suspend fun getUserVocabulary(
            clientId: String,
            limit: Int,
        ): List<UserVocabularyCardResponse> = listOf(
            UserVocabularyCardResponse(
                id = 1,
                clientId = clientId,
                word = "concurrency",
                definitionCn = "并发",
            )
        )

        override suspend fun createSpeakingSession(request: CreateSpeakingSessionRequest): SpeakingSessionResponse =
            SpeakingSessionResponse(
                sessionId = "sess-1",
                turnIndex = 1,
                totalTurns = 3,
                scenario = request.scenario,
                role = request.role,
                aiPromptText = "Tell me about your architecture.",
            )

        override suspend fun submitSpeakingTurn(
            sessionId: String,
            turnIndex: Int,
            audio: MultipartBody.Part,
        ): SpeakingTurnResponse = SpeakingTurnResponse(
            sessionId = sessionId,
            turnIndex = turnIndex,
            userTranscript = "I used event queues.",
            pronunciationScore = 90,
            grammarScore = 92,
            quickFeedback = "Great clarity.",
            isFinished = false,
        )

        override suspend fun getSpeakingSession(sessionId: String): SpeakingSessionDetailResponse =
            SpeakingSessionDetailResponse(
                sessionId = sessionId,
                clientId = "client-1",
                contentUuid = "daily-1",
                scenario = "SYSTEM_DESIGN_INTERVIEW",
                role = "TECH_LEAD",
            )

        private fun dailyContent() = ContentResponse(
            uuid = "daily-1",
            title = "Virtual threads in practice",
            sourceType = "TECH_DOC",
            sourceText = "Virtual threads make blocking code easier to scale.",
            level = "B1",
            status = "READY",
            audioUrl = "/audio/daily-1.mp3",
            lessonContent = """{"passage":"Virtual threads make blocking code easier to scale.","questions":[],"dialogue":[{"speaker":"HOST","text":"Why virtual threads?","startMs":0,"endMs":2100},{"speaker":"EXPERT","text":"They simplify blocking I/O.","startMs":2100,"endMs":4900}]}""",
        )

        private fun longContent() = ContentResponse(
            uuid = "long-1",
            title = "10-minute backend lesson",
            sourceType = "LONG_LESSON",
            sourceText = "",
            level = "B1",
            status = "GENERATING",
        )

        private fun failedContent() = ContentResponse(
            uuid = "failed-1",
            title = "Broken cloud lesson",
            sourceType = "NEWS",
            sourceText = "",
            level = "B1",
            status = "FAILED",
            failureReason = "SCRIPT_GENERATION: malformed JSON",
        )

        private fun topicContent() = ContentResponse(
            uuid = "topic-content-1",
            title = "Daily source article",
            sourceType = "NEWS",
            sourceUrl = "https://news.example.com/item",
            sourceText = "A source-backed article.",
            level = "B1",
            status = "READY",
            audioUrl = "/api/v1/audio/content/topic-content-1.mp3",
            lessonContent = """{"passage":"A source-backed article.","questions":[]}""",
        )

        private fun topic() = TopicRecommendationResponse(
            uuid = "topic-1",
            planDate = "2026-07-28",
            kind = "SOURCE_ARTICLE",
            category = "NEWS",
            title = "Daily source article",
            summary = "A source-backed article.",
            sourceName = "Example News",
            sourceUrl = "https://news.example.com/item",
            publishedAt = "2026-07-28T05:00:00+08:00",
            provider = "source",
            score = 1.0,
            status = "READY",
            contentUuid = "topic-content-1",
            audioUrl = "/api/v1/audio/content/topic-content-1.mp3",
        )

        private fun task(status: String) = TaskResponse(
            taskUuid = "task-1",
            prompt = "Explain locks",
            voice = "en-US-AndrewNeural",
            difficulty = "hard",
            status = status,
        )

        private fun LearningProgressRequest.asResponse() = LearningProgressResponse(
            clientId = clientId,
            contentUuid = contentUuid,
            positionMs = positionMs,
            durationMs = durationMs,
            vocabularyDone = vocabularyDone,
            listeningDone = listeningDone,
            readingDone = readingDone,
            quizCorrect = quizCorrect,
            quizTotal = quizTotal,
            speakingScore = speakingScore,
            completed = completed,
        )
    }
}
