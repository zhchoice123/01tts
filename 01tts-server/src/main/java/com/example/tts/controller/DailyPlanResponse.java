package com.example.tts.controller;

import com.example.tts.entity.ContentItem;
import com.example.tts.entity.DailyPlan;
import java.time.Instant;
import java.time.LocalDate;

public class DailyPlanResponse {
    private final LocalDate planDate;
    private final String contentUuid;
    private final Instant createdAt;
    private final int estimatedMinutes;
    private final ContentItem content;

    public DailyPlanResponse(DailyPlan plan, ContentItem content) {
        this.planDate = plan.getPlanDate();
        this.contentUuid = plan.getContentUuid();
        this.createdAt = plan.getCreatedAt();
        this.estimatedMinutes = 25;
        this.content = content;
    }

    public LocalDate getPlanDate() { return planDate; }
    public String getContentUuid() { return contentUuid; }
    public Instant getCreatedAt() { return createdAt; }
    public int getEstimatedMinutes() { return estimatedMinutes; }
    public ContentItem getContent() { return content; }
}
