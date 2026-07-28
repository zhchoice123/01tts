package com.example.ttsapp.network

import okhttp3.MultipartBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Part
import retrofit2.http.Query
import com.google.gson.JsonParser

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
)

data class AnswerResponse(
    val answerUuid: String,
    val taskUuid: String,
    val status: String,
    val audioUrl: String,
    val transcript: String? = null,
    val score: Int? = null,
    val feedback: String? = null,
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
        )
    }
}

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
}
