package com.example.ttsapp

import android.content.Context
import com.example.ttsapp.network.ApiClient
import com.example.ttsapp.network.AppReleaseResponse
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Request

sealed interface AppUpdateState {
    data object Idle : AppUpdateState
    data object Checking : AppUpdateState
    data object UpToDate : AppUpdateState
    data class Available(val release: AppReleaseResponse) : AppUpdateState
    data class Downloading(
        val release: AppReleaseResponse,
        val progress: Float,
    ) : AppUpdateState
    data class ReadyToInstall(
        val release: AppReleaseResponse,
        val apk: File,
    ) : AppUpdateState
    data class Error(val message: String) : AppUpdateState
}

class AppUpdateManager(private val context: Context) {
    suspend fun checkForUpdate(): AppUpdateState = runCatching {
        val release = ApiClient.tasks.latestAppRelease()
        validateManifest(release)
        if (release.versionCode > BuildConfig.VERSION_CODE) {
            AppUpdateState.Available(release)
        } else {
            AppUpdateState.UpToDate
        }
    }.getOrElse { error ->
        AppUpdateState.Error(error.userMessage("Unable to check for updates"))
    }

    suspend fun download(
        release: AppReleaseResponse,
        onProgress: suspend (Float) -> Unit,
    ): Result<File> = withContext(Dispatchers.IO) {
        runCatching {
            validateManifest(release)
            val updateDirectory = File(context.cacheDir, "updates").apply { mkdirs() }
            val finalFile = File(updateDirectory, "Listening-Lab-${release.versionName}.apk")
            val temporaryFile = File(updateDirectory, "${finalFile.name}.part")
            temporaryFile.delete()
            val digest = MessageDigest.getInstance("SHA-256")

            val request = Request.Builder()
                .url(ApiClient.resolveApiUrl(release.apkUrl))
                .get()
                .build()
            ApiClient.httpClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    throw IOException("Download returned HTTP ${response.code}")
                }
                val body = response.body
                var copied = 0L
                var lastReportedPercent = -1
                body.byteStream().use { input ->
                    temporaryFile.outputStream().buffered().use { output ->
                        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                        while (true) {
                            val count = input.read(buffer)
                            if (count < 0) break
                            output.write(buffer, 0, count)
                            digest.update(buffer, 0, count)
                            copied += count
                            val progress =
                                (copied.toFloat() / release.sizeBytes).coerceIn(0f, 1f)
                            val percent = (progress * 100).toInt()
                            if (percent != lastReportedPercent) {
                                lastReportedPercent = percent
                                onProgress(progress)
                            }
                        }
                    }
                }
            }
            if (temporaryFile.length() != release.sizeBytes) {
                temporaryFile.delete()
                throw IOException("Downloaded file size does not match the release manifest")
            }
            val actualSha256 = digest.digest().joinToString("") { "%02x".format(it) }
            if (!actualSha256.equals(release.sha256, ignoreCase = true)) {
                temporaryFile.delete()
                throw IOException("Downloaded file failed the SHA-256 integrity check")
            }
            finalFile.delete()
            if (!temporaryFile.renameTo(finalFile)) {
                temporaryFile.copyTo(finalFile, overwrite = true)
                temporaryFile.delete()
            }
            finalFile
        }
    }

    private fun validateManifest(release: AppReleaseResponse) {
        require(release.versionCode > 0) { "Invalid release version code" }
        require(release.versionName.matches(Regex("[A-Za-z0-9._-]{1,40}"))) {
            "Invalid release version name"
        }
        require(release.sha256.matches(Regex("[0-9a-fA-F]{64}"))) {
            "Invalid release checksum"
        }
        require(release.sizeBytes > 0) { "Invalid release file size" }
        require(release.apkUrl.substringBefore('?').endsWith(".apk")) {
            "Invalid release download URL"
        }
    }
}

private fun Throwable.userMessage(fallback: String): String =
    message?.takeIf { it.isNotBlank() }?.let { "$fallback: $it" } ?: fallback
