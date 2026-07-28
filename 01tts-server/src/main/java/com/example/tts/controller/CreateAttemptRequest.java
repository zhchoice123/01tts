package com.example.tts.controller;

import javax.validation.constraints.NotBlank;

public class CreateAttemptRequest {
    @NotBlank
    private String answersJson;
    private Integer correctCount;

    public String getAnswersJson() { return answersJson; }
    public void setAnswersJson(String answersJson) { this.answersJson = answersJson; }
    public Integer getCorrectCount() { return correctCount; }
    public void setCorrectCount(Integer correctCount) { this.correctCount = correctCount; }
}
