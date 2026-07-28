package com.example.ttsapp

import com.example.ttsapp.core.notifications.DailyLearningScheduler
import java.time.ZoneId
import java.time.ZonedDateTime
import org.junit.Assert.assertEquals
import org.junit.Test

class DailyLearningSchedulerTest {
    @Test
    fun schedulesNextMorningWhenTimeAlreadyPassed() {
        val now = ZonedDateTime.of(2026, 7, 25, 9, 0, 0, 0, ZoneId.of("Asia/Shanghai"))
        assertEquals(23 * 60L, DailyLearningScheduler.initialDelayMinutes(now, 8, 0))
    }

    @Test
    fun schedulesSameDayWhenTimeIsAhead() {
        val now = ZonedDateTime.of(2026, 7, 25, 7, 30, 0, 0, ZoneId.of("Asia/Shanghai"))
        assertEquals(30L, DailyLearningScheduler.initialDelayMinutes(now, 8, 0))
    }
}
