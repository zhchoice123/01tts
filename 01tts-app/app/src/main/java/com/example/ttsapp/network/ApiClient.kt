package com.example.ttsapp.network

import com.example.ttsapp.BuildConfig
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

object ApiClient {
    val BASE_URL: String = BuildConfig.API_BASE_URL.ensureTrailingSlash()
    private val baseHttpUrl = BASE_URL.toHttpUrl()

    val httpClient: OkHttpClient by lazy {
        OkHttpClient.Builder().build()
    }

    val tasks: TaskApi by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(httpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(TaskApi::class.java)
    }

    fun resolveMediaUrl(url: String): String = resolveApiUrl(url)

    fun resolveApiUrl(url: String): String =
        if (url.startsWith("http://") || url.startsWith("https://")) {
            url
        } else {
            baseHttpUrl.resolve(url)?.toString()
            ?: error("Invalid API URL: $url")
        }

    private fun String.ensureTrailingSlash(): String = if (endsWith("/")) this else "$this/"
}
