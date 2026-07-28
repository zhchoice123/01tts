package com.example.ttsapp.core.notifications

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.example.ttsapp.MainActivity
import com.example.ttsapp.R
import java.time.Duration
import java.time.ZonedDateTime
import java.util.concurrent.TimeUnit

class DailyLearningWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val manager =
            applicationContext.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    "Daily English learning",
                    NotificationManager.IMPORTANCE_DEFAULT,
                )
            )
        }
        val intent = Intent(applicationContext, MainActivity::class.java)
            .putExtra("openDestination", "TODAY")
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val pendingIntent = PendingIntent.getActivity(
            applicationContext,
            1001,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(applicationContext, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_listening_lab)
            .setContentTitle("Your technical English is ready")
            .setContentText("Open Listening Lab for today's reading, listening and speaking session.")
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()
        manager.notify(NOTIFICATION_ID, notification)
        return Result.success()
    }

    companion object {
        const val CHANNEL_ID = "daily-learning"
        const val UNIQUE_WORK_NAME = "daily-learning-plan"
        private const val NOTIFICATION_ID = 1001
    }
}

object DailyLearningScheduler {
    fun schedule(context: Context, hour: Int = 8, minute: Int = 0) {
        val request = PeriodicWorkRequestBuilder<DailyLearningWorker>(24, TimeUnit.HOURS)
            .setInitialDelay(initialDelayMinutes(ZonedDateTime.now(), hour, minute), TimeUnit.MINUTES)
            .build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            DailyLearningWorker.UNIQUE_WORK_NAME,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }

    fun initialDelayMinutes(now: ZonedDateTime, hour: Int, minute: Int): Long {
        var next = now.withHour(hour).withMinute(minute).withSecond(0).withNano(0)
        if (!next.isAfter(now)) next = next.plusDays(1)
        return Duration.between(now, next).toMinutes().coerceAtLeast(1)
    }
}
