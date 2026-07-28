package com.example.tts.service;

public class TaskNotFoundException extends RuntimeException {
    public TaskNotFoundException(String uuid) {
        super("Task not found: " + uuid);
    }
}
