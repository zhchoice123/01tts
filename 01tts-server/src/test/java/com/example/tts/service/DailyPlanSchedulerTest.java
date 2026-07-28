package com.example.tts.service;

import static org.mockito.Mockito.verify;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

class DailyPlanSchedulerTest {
    @Test
    void startupCatchUpGeneratesPlanForShanghaiDate() {
        ContentService service = Mockito.mock(ContentService.class);
        Clock clock = Clock.fixed(
                Instant.parse("2026-07-25T22:30:00Z"),
                ZoneId.of("Asia/Shanghai"));
        DailyPlanScheduler scheduler = new DailyPlanScheduler(service, clock);

        scheduler.ensureTodayOnStartup();

        verify(service).generatePlan(java.time.LocalDate.of(2026, 7, 26));
    }
}
