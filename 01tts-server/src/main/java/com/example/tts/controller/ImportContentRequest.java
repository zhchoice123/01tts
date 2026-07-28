package com.example.tts.controller;

import javax.validation.constraints.NotBlank;

public class ImportContentRequest {
    @NotBlank
    private String sourceType = "TEXT";
    private String sourceUrl = "";
    private String text = "";
    private String title = "";
    private String level = "B1";

    public String getSourceType() { return sourceType; }
    public void setSourceType(String sourceType) { this.sourceType = sourceType; }
    public String getSourceUrl() { return sourceUrl; }
    public void setSourceUrl(String sourceUrl) { this.sourceUrl = sourceUrl; }
    public String getText() { return text; }
    public void setText(String text) { this.text = text; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getLevel() { return level; }
    public void setLevel(String level) { this.level = level; }
}
