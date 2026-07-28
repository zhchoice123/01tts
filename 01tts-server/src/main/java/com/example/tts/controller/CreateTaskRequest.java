package com.example.tts.controller;

import javax.validation.constraints.NotBlank;

public class CreateTaskRequest {
    @NotBlank
    private String prompt;
    private String voice = "en-US-AvaNeural";
    private String difficulty = "medium";

    public String getPrompt() { return prompt; }
    public void setPrompt(String prompt) { this.prompt = prompt; }
    public String getVoice() { return voice; }
    public void setVoice(String voice) { this.voice = voice; }
    public String getDifficulty() { return difficulty; }
    public void setDifficulty(String difficulty) { this.difficulty = difficulty; }
}
