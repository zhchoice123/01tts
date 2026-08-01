package com.example.ttsapp.network

import com.example.ttsapp.review.LessonReviewReportResponse
import com.example.ttsapp.review.ReviewQueueResponse
import com.google.gson.JsonParser
import okhttp3.MultipartBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Part
import retrofit2.http.Query

data class CreateTaskRequest(
    val prompt: String,
    val voice: String = "en-US-AvaNeural",
    val difficulty: String = "medium",
)

data class TaskResponse(
    val taskUuid: String,
    val prompt: String,
    val voice: String,
    val difficulty: String,
    val status: String,
    val audioUrl: String? = null,
    val questions: String? = null,
    val vocabulary: String? = null,
    val lessonContent: String? = null,
)

data class AnswerResponse(
    val answerUuid: String,
    val taskUuid: String,
    val status: String,
    val audioUrl: String,
    val transcript: String? = null,
    val score: Int? = null,
    val feedback: String? = null,
    val failureReason: String? = null,
    val evaluation: SpeakingEvaluation? = null,
)

data class SpeakingEvaluation(
    val overallScore: Int = 0,
    val pronunciationScore: Int = 0,
    val fluencyScore: Int = 0,
    val intonationScore: Int = 0,
    val pacingScore: Int = 0,
    val relevanceScore: Int = 0,
    val grammarScore: Int = 0,
    val vocabularyScore: Int = 0,
    val summary: String = "",
    val strengths: List<String> = emptyList(),
    val improvements: List<String> = emptyList(),
    val practicePlan: List<String> = emptyList(),
    val mode: String = "",
    val model: String = "",
)

data class ContentResponse(
    val uuid: String = "",
    val title: String = "",
    val sourceType: String = "LONG_LESSON",
    val sourceUrl: String? = null,
    val sourceText: String = "",
    val level: String = "B1",
    val status: String = "GENERATING",
    val audioUrl: String? = null,
    val lessonContent: String? = null,
    val failureReason: String? = null,
    val createdAt: String? = null,
    val profile: String? = null,
    val category: String? = null,
    val voice: String? = null,
    val sourceMode: String? = null,
    val estimatedMinutes: Int? = null,
) {
    fun asTaskResponse(): TaskResponse {
        val lesson = runCatching {
            lessonContent?.let { JsonParser.parseString(it).asJsonObject }
        }.getOrNull()
        val passage = lesson?.get("passage")?.asString.orEmpty().ifBlank { sourceText }
        val questions = lesson?.getAsJsonArray("questions")?.toString()
        val vocabulary = lesson?.getAsJsonArray("vocabulary")?.toString()
        return TaskResponse(
            taskUuid = uuid,
            prompt = passage,
            voice = voice ?: "en-US-AvaNeural",
            difficulty = level,
            status = if (status == "READY") "COMPLETED" else status,
            audioUrl = audioUrl,
            questions = questions,
            vocabulary = vocabulary,
            lessonContent = lessonContent,
        )
    }
}

data class LearningProgressRequest(
    val clientId: String,
    val contentUuid: String,
    val positionMs: Long = 0,
    val durationMs: Long = 0,
    val vocabularyDone: Boolean = false,
    val listeningDone: Boolean = false,
    val readingDone: Boolean = false,
    val quizCorrect: Int = 0,
    val quizTotal: Int = 0,
    val speakingScore: Int? = null,
    val completed: Boolean = false,
)

data class LearningProgressResponse(
    val clientId: String = "",
    val contentUuid: String = "",
    val positionMs: Long = 0,
    val durationMs: Long = 0,
    val vocabularyDone: Boolean = false,
    val listeningDone: Boolean = false,
    val readingDone: Boolean = false,
    val quizCorrect: Int = 0,
    val quizTotal: Int = 0,
    val speakingScore: Int? = null,
    val completed: Boolean = false,
    val updatedAt: String? = null,
) {
    fun asRequest() = LearningProgressRequest(
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

data class LearningDashboardResponse(
    val days: Int = 7,
    val listeningMinutes: Int = 0,
    val completedLessons: Int = 0,
    val quizCorrect: Int = 0,
    val quizTotal: Int = 0,
    val speakingAverage: Int = 0,
    val currentStreak: Int = 0,
    val wordsReviewed: Int = 0,
    val latestContentUuid: String? = null,
    val latestPositionMs: Long = 0,
)

data class VocabularyProgressRequest(
    val clientId: String,
    val contentUuid: String,
    val word: String,
    val status: String = "LEARNING",
)

data class VocabularyProgressResponse(
    val clientId: String = "",
    val contentUuid: String = "",
    val word: String = "",
    val status: String = "LEARNING",
    val updatedAt: String? = null,
)

data class DailyPlanResponse(
    val planDate: String,
    val contentUuid: String,
    val estimatedMinutes: Int = 25,
    val content: ContentResponse,
)

data class CreateLongLessonRequest(
    val topic: String? = null,
    val category: String? = null,
    val voice: String = "en-US-AvaNeural",
    val level: String = "B1",
    val sourceMode: String = "AUTO",
)

data class TopicRecommendationResponse(
    val uuid: String,
    val planDate: String,
    val kind: String,
    val category: String,
    val title: String,
    val summary: String,
    val sourceName: String? = null,
    val sourceUrl: String? = null,
    val publishedAt: String? = null,
    val provider: String,
    val score: Double,
    val status: String,
    val contentUuid: String,
    val audioUrl: String? = null,
    val failureReason: String? = null,
)

data class TopicLessonResponse(
    val topic: TopicRecommendationResponse,
    val content: ContentResponse,
)

data class AppReleaseResponse(
    val versionCode: Int,
    val versionName: String,
    val minimumVersionCode: Int = 1,
    val mandatory: Boolean = false,
    val title: String = "Listening Lab update",
    val changelog: List<String> = emptyList(),
    val apkUrl: String,
    val sha256: String,
    val sizeBytes: Long,
    val publishedAt: String,
)

interface TaskApi {
    @POST("api/v1/tasks")
    suspend fun create(@Body request: CreateTaskRequest): TaskResponse

    @GET("api/v1/tasks/{uuid}")
    suspend fun get(@Path("uuid") uuid: String): TaskResponse

    @Multipart
    @POST("api/v1/tasks/{uuid}/answers")
    suspend fun uploadAnswer(
        @Path("uuid") uuid: String,
        @Part audio: MultipartBody.Part,
    ): AnswerResponse

    @GET("api/v1/answers/{uuid}")
    suspend fun getAnswer(@Path("uuid") uuid: String): AnswerResponse

    @GET("api/v1/daily-plans/today")
    suspend fun today(): DailyPlanResponse

    @GET("api/v1/library")
    suspend fun library(): List<ContentResponse>

    @POST("api/v1/long-lessons")
    suspend fun createLongLesson(
        @Body request: CreateLongLessonRequest,
    ): ContentResponse

    @GET("api/v1/topics/recommendations")
    suspend fun topics(
        @Query("planDate") planDate: String? = null,
        @Query("limit") limit: Int = 3,
    ): List<TopicRecommendationResponse>

    @POST("api/v1/topics/{uuid}/lessons")
    suspend fun topicLesson(
        @Path("uuid") uuid: String,
    ): TopicLessonResponse

    @GET("api/v1/content/{uuid}")
    suspend fun getContent(
        @Path("uuid") uuid: String,
    ): ContentResponse

    @PUT("api/v1/learning/progress")
    suspend fun saveLearningProgress(
        @Body request: LearningProgressRequest,
    ): LearningProgressResponse

    @GET("api/v1/learning/progress/{clientId}/{contentUuid}")
    suspend fun learningProgress(
        @Path("clientId") clientId: String,
        @Path("contentUuid") contentUuid: String,
    ): LearningProgressResponse

    @GET("api/v1/learning/dashboard/{clientId}")
    suspend fun learningDashboard(
        @Path("clientId") clientId: String,
        @Query("days") days: Int = 7,
    ): LearningDashboardResponse

    @PUT("api/v1/learning/vocabulary")
    suspend fun saveVocabularyProgress(
        @Body request: VocabularyProgressRequest,
    ): VocabularyProgressResponse

    @GET("api/v1/learning/vocabulary/{clientId}")
    suspend fun learningVocabulary(
        @Path("clientId") clientId: String,
        @Query("status") status: String? = null,
    ): List<VocabularyProgressResponse>

    @GET("api/v1/learning/reports/{clientId}/{contentUuid}")
    suspend fun lessonReviewReport(
        @Path("clientId") clientId: String,
        @Path("contentUuid") contentUuid: String,
    ): LessonReviewReportResponse

    @GET("api/v1/learning/review-queue/{clientId}")
    suspend fun reviewQueue(
        @Path("clientId") clientId: String,
        @Query("date") date: String,
        @Query("limit") limit: Int = 10,
    ): ReviewQueueResponse

    @GET("api/v1/app/releases/latest")
    suspend fun latestAppRelease(): AppReleaseResponse
}
