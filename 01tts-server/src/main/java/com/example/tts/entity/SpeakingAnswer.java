package com.example.tts.entity;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.EnumType;
import javax.persistence.Enumerated;
import javax.persistence.Id;
import javax.persistence.Lob;
import javax.persistence.Table;

@Entity
@Table(name = "speaking_answer")
public class SpeakingAnswer {
    @Id
    private String answerUuid;
    @Column(nullable = false)
    private String taskUuid;
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private AnswerStatus status;
    @Column(nullable = false)
    private String audioUrl;
    @Lob
    private String transcript;
    private Integer score;
    @Lob
    private String feedback;

    protected SpeakingAnswer() {}

    public SpeakingAnswer(String answerUuid, String taskUuid, String audioUrl) {
        this.answerUuid = answerUuid;
        this.taskUuid = taskUuid;
        this.audioUrl = audioUrl;
        this.status = AnswerStatus.PENDING;
    }

    public void complete(String transcript, Integer score, String feedback) {
        this.transcript = transcript;
        this.score = score;
        this.feedback = feedback;
        this.status = AnswerStatus.COMPLETED;
    }

    public String getAnswerUuid() { return answerUuid; }
    public String getTaskUuid() { return taskUuid; }
    public AnswerStatus getStatus() { return status; }
    public String getAudioUrl() { return audioUrl; }
    public String getTranscript() { return transcript; }
    public Integer getScore() { return score; }
    public String getFeedback() { return feedback; }
}
