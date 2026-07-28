package com.example.tts.entity;

import java.time.Instant;
import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.EnumType;
import javax.persistence.Enumerated;
import javax.persistence.Id;
import javax.persistence.Lob;
import javax.persistence.Table;

@Entity
@Table(name = "learning_content")
public class ContentItem {
    @Id
    private String uuid;
    @Column(nullable = false)
    private String title;
    @Column(nullable = false)
    private String sourceType;
    private String sourceUrl;
    @Lob
    @Column(nullable = false)
    private String sourceText;
    @Column(nullable = false)
    private String level;
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ContentStatus status;
    private String audioUrl;
    @Lob
    private String lessonContent;
    @Lob
    private String failureReason;
    @Column(nullable = false)
    private Instant createdAt;

    protected ContentItem() {}

    public ContentItem(
            String uuid, String title, String sourceType, String sourceUrl,
            String sourceText, String level) {
        this.uuid = uuid;
        this.title = title;
        this.sourceType = sourceType;
        this.sourceUrl = sourceUrl;
        this.sourceText = sourceText;
        this.level = level;
        this.status = ContentStatus.GENERATING;
        this.createdAt = Instant.now();
    }

    public void complete(String audioUrl, String lessonContent) {
        this.audioUrl = audioUrl;
        this.lessonContent = lessonContent;
        this.status = ContentStatus.READY;
        this.failureReason = null;
    }

    public void fail(String reason) {
        this.status = ContentStatus.FAILED;
        this.failureReason = reason;
    }

    public String getUuid() { return uuid; }
    public String getTitle() { return title; }
    public String getSourceType() { return sourceType; }
    public String getSourceUrl() { return sourceUrl; }
    public String getSourceText() { return sourceText; }
    public String getPrompt() { return sourceText; }
    public String getLevel() { return level; }
    public ContentStatus getStatus() { return status; }
    public String getAudioUrl() { return audioUrl; }
    public String getLessonContent() { return lessonContent; }
    public String getFailureReason() { return failureReason; }
    public Instant getCreatedAt() { return createdAt; }
}
