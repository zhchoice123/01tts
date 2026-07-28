package com.example.ttsapp.core.ai

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

class HttpAiProvider(
    override val kind: ProviderKind,
    private val baseUrl: String,
    private val model: String,
    private val apiKey: String,
    client: OkHttpClient? = null,
) : AiProvider {
    private val http = client ?: OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .build()

    override fun streamChat(prompt: String): Flow<String> = flow {
        emit(generateText(prompt))
    }

    override suspend fun generateStructured(prompt: String): GeneratedLesson {
        val instruction = """
            Return only valid JSON with fields title, level, sourceType, passage,
            simplifiedPassage, vocabulary, questions and speakingPrompts.
            User request: $prompt
        """.trimIndent()
        val text = generateText(instruction)
        val json = extractJsonObject(text)
        return GeneratedLesson(json)
    }

    override suspend fun testConnection(): ProviderHealth =
        runCatching { generateText("Reply with only OK.") }
            .fold(
                onSuccess = { ProviderHealth(true, "Connection successful") },
                onFailure = { ProviderHealth(false, it.message ?: "Connection failed") },
            )

    private suspend fun generateText(prompt: String): String = withContext(Dispatchers.IO) {
        if (apiKey.isBlank()) {
            throw AiProviderException(
                AiProviderException.Category.UNAUTHORIZED,
                "${kind.name} API key is missing",
            )
        }
        val openAiResponses = kind == ProviderKind.OPENAI
        val body = if (openAiResponses) {
            JsonObject().apply {
                addProperty("model", model)
                addProperty("input", prompt)
            }
        } else {
            JsonObject().apply {
                addProperty("model", model)
                add("messages", com.google.gson.JsonArray().apply {
                    add(JsonObject().apply {
                        addProperty("role", "user")
                        addProperty("content", prompt)
                    })
                })
            }
        }
        val endpoint = if (openAiResponses) "responses" else "chat/completions"
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/$endpoint")
            .header("Authorization", "Bearer $apiKey")
            .header("Content-Type", "application/json")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()
        val response = try {
            http.newCall(request).execute()
        } catch (error: java.net.SocketTimeoutException) {
            throw AiProviderException(AiProviderException.Category.TIMEOUT, "Provider timed out", error)
        } catch (error: IOException) {
            throw AiProviderException(AiProviderException.Category.NETWORK, "Provider network error", error)
        }
        response.use {
            val responseBody = it.body.string()
            when (it.code) {
                401, 403 -> throw AiProviderException(
                    AiProviderException.Category.UNAUTHORIZED,
                    "Provider rejected the API key",
                )
                429 -> throw AiProviderException(
                    AiProviderException.Category.RATE_LIMITED,
                    "Provider rate limit reached",
                )
            }
            if (!it.isSuccessful) {
                throw AiProviderException(
                    AiProviderException.Category.NETWORK,
                    "Provider returned HTTP ${it.code}",
                )
            }
            parseText(responseBody, openAiResponses)
        }
    }

    private fun parseText(body: String, responsesApi: Boolean): String {
        return runCatching {
            val root = JsonParser.parseString(body).asJsonObject
            if (responsesApi) {
                root.get("output_text")?.asString
                    ?: root.getAsJsonArray("output")
                        .first().asJsonObject
                        .getAsJsonArray("content").first().asJsonObject
                        .get("text").asString
            } else {
                root.getAsJsonArray("choices").first().asJsonObject
                    .getAsJsonObject("message").get("content").asString
            }
        }.getOrElse {
            throw AiProviderException(
                AiProviderException.Category.INVALID_RESPONSE,
                "Provider returned malformed JSON",
                it,
            )
        }
    }

    private fun extractJsonObject(text: String): String {
        val start = text.indexOf('{')
        val end = text.lastIndexOf('}')
        if (start < 0 || end <= start) {
            throw AiProviderException(
                AiProviderException.Category.INVALID_RESPONSE,
                "Provider did not return a JSON object",
            )
        }
        val json = text.substring(start, end + 1)
        runCatching { JsonParser.parseString(json).asJsonObject }.getOrElse {
            throw AiProviderException(
                AiProviderException.Category.INVALID_RESPONSE,
                "Provider returned invalid lesson JSON",
                it,
            )
        }
        return json
    }
}
