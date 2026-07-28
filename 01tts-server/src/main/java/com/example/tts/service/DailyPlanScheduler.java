package com.example.tts.service;

import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DailyPlanScheduler {
    private static final Logger LOGGER = LoggerFactory.getLogger(DailyPlanScheduler.class);
    private static final ZoneId SHANGHAI = ZoneId.of("Asia/Shanghai");

    private final ContentService contentService;
    private final Clock clock;

    @Autowired
    public DailyPlanScheduler(ContentService contentService) {
        this(contentService, Clock.system(SHANGHAI));
    }

    DailyPlanScheduler(ContentService contentService, Clock clock) {
        this.contentService = contentService;
        this.clock = clock;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void ensureTodayOnStartup() {
        ensureDate(LocalDate.now(clock));
    }

    @Scheduled(
            cron = "${listening-lab.daily-plan.cron:0 30 5 * * *}",
            zone = "Asia/Shanghai")
    public void generateDailyPlan() {
        ensureDate(LocalDate.now(clock));
    }

    void ensureDate(LocalDate date) {
        try {
            contentService.generatePlan(date);
            LOGGER.info("Daily learning plan is available for {}", date);
        } catch (RuntimeException error) {
            LOGGER.error("Unable to prepare daily learning plan for {}", date, error);
        }
    }
}
