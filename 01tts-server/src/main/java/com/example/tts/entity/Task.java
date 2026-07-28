package com.example.tts.entity;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.EnumType;
import javax.persistence.Enumerated;
import javax.persistence.Id;
import javax.persistence.Lob;
import javax.persistence.Table;

@Entity
@Table(name = "tts_task")
public class Task {
    @Id
    private String taskUuid;
    @Lob
    @Column(nullable = false)
    private String prompt;
    @Column(nullable = false)
    private String voice;
    @Column(nullable = false, columnDefinition = "varchar(32) default 'medium'")
    private String difficulty;
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private TaskStatus status;
    private String audioUrl;
    @Lob
    private String questions;

    protected Task() {}

    public Task(String taskUuid, String prompt, String voice, String difficulty) {
        this.taskUuid = taskUuid;
        this.prompt = prompt;
        this.voice = voice;
        this.difficulty = difficulty;
        this.status = TaskStatus.PENDING;
    }

    public void complete(String audioUrl, String questions) {
        this.audioUrl = audioUrl;
        this.questions = questions;
        this.status = TaskStatus.COMPLETED;
    }

    public void fail(String reason) {
        this.status = TaskStatus.FAILED;
    }

    public String getTaskUuid() { return taskUuid; }
    public String getPrompt() { return prompt; }
    public String getVoice() { return voice; }
    public String getDifficulty() { return difficulty; }
    public TaskStatus getStatus() { return status; }
    public String getAudioUrl() { return audioUrl; }
    public String getQuestions() { return questions; }
}
