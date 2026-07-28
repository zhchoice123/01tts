package com.example.tts.entity;

import java.time.Instant;
import java.time.LocalDate;
import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "daily_plan")
public class DailyPlan {
    @Id
    private LocalDate planDate;
    @Column(nullable = false)
    private String contentUuid;
    @Column(nullable = false)
    private Instant createdAt;

    protected DailyPlan() {}

    public DailyPlan(LocalDate planDate, String contentUuid) {
        this.planDate = planDate;
        this.contentUuid = contentUuid;
        this.createdAt = Instant.now();
    }

    public LocalDate getPlanDate() { return planDate; }
    public String getContentUuid() { return contentUuid; }
    public Instant getCreatedAt() { return createdAt; }
}
