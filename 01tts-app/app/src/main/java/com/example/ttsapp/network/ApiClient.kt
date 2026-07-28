package com.example.ttsapp.network

import com.example.ttsapp.BuildConfig
import java.io.IOException
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Response
import okhttp3.HttpUrl.Companion.toHttpUrl
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

object ApiClient {
    val BASE_URL: String = BuildConfig.API_BASE_URL.ensureTrailingSlash()
    internal const val FALLBACK_BASE_URL = "http://42.192.62.145:8080/"

    val tasks: TaskApi by lazy {
        val client = OkHttpClient.Builder()
            .addInterceptor(
                DomainFallbackInterceptor(
                    primaryHost = BASE_URL.toHttpUrl().host,
                    fallbackBaseUrl = FALLBACK_BASE_URL,
                )
            )
            .build()
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(TaskApi::class.java)
    }

    fun resolveMediaUrl(url: String): String =
        if (url.startsWith("http://") || url.startsWith("https://")) {
            url
        } else {
            FALLBACK_BASE_URL + url.removePrefix("/")
        }

    private fun String.ensureTrailingSlash(): String = if (endsWith("/")) this else "$this/"
}

internal class DomainFallbackInterceptor(
    private val primaryHost: String,
    fallbackBaseUrl: String,
) : Interceptor {
    private val fallback = fallbackBaseUrl.toHttpUrl()

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        return try {
            chain.proceed(request)
        } catch (primaryError: IOException) {
            if (request.url.host != primaryHost) throw primaryError
            val fallbackUrl = request.url.newBuilder()
                .scheme(fallback.scheme)
                .host(fallback.host)
                .port(fallback.port)
                .build()
            chain.proceed(request.newBuilder().url(fallbackUrl).build())
        }
    }
}
