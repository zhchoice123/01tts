package com.example.ttsapp

import com.example.ttsapp.network.AnswerResponse
import com.example.ttsapp.network.ContentResponse
import com.example.ttsapp.network.CreateLongLessonRequest
import com.example.ttsapp.network.CreateTaskRequest
import com.example.ttsapp.network.DailyPlanResponse
import com.example.ttsapp.network.TaskApi
import com.example.ttsapp.network.TaskResponse
import com.example.ttsapp.network.TopicLessonResponse
import com.example.ttsapp.network.TopicRecommendationResponse
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import okhttp3.MultipartBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

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
        assertEquals("en-US-AndrewNeural", api.created?.voice)
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

    private class FakeTaskApi : TaskApi {
        var created: CreateTaskRequest? = null
        var createdLong: CreateLongLessonRequest? = null
        var pollCount = 0
        var contentPollCount = 0

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

        override suspend fun library(): List<ContentResponse> = listOf(
            dailyContent(),
            longContent(),
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

        private fun dailyContent() = ContentResponse(
            uuid = "daily-1",
            title = "Virtual threads in practice",
            sourceType = "TECH_DOC",
            sourceText = "Virtual threads make blocking code easier to scale.",
            level = "B1",
            status = "READY",
            audioUrl = "/audio/daily-1.mp3",
            lessonContent = """{"passage":"Virtual threads make blocking code easier to scale.","questions":[]}""",
        )

        private fun longContent() = ContentResponse(
            uuid = "long-1",
            title = "10-minute backend lesson",
            sourceType = "LONG_LESSON",
            sourceText = "",
            level = "B1",
            status = "GENERATING",
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
    }
}
