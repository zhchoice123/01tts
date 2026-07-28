package com.example.tts.entity;

import java.time.Instant;
import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.GenerationType;
import javax.persistence.Id;
import javax.persistence.Lob;
import javax.persistence.Table;

@Entity
@Table(name = "learning_attempt")
public class LearningAttempt {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(nullable = false)
    private String contentUuid;
    @Lob
    @Column(nullable = false)
    private String answersJson;
    private Integer correctCount;
    @Column(nullable = false)
    private Instant submittedAt;

    protected LearningAttempt() {}

    public LearningAttempt(String contentUuid, String answersJson, Integer correctCount) {
        this.contentUuid = contentUuid;
        this.answersJson = answersJson;
        this.correctCount = correctCount;
        this.submittedAt = Instant.now();
    }

    public Long getId() { return id; }
    public String getContentUuid() { return contentUuid; }
    public String getAnswersJson() { return answersJson; }
    public Integer getCorrectCount() { return correctCount; }
    public Instant getSubmittedAt() { return submittedAt; }
}
