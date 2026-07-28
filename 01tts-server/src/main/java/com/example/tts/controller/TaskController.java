package com.example.tts.controller;

import com.example.tts.entity.Task;
import com.example.tts.service.TaskService;
import java.io.IOException;
import javax.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/v1/tasks")
public class TaskController {
    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    @PostMapping
    public Task create(@Valid @RequestBody CreateTaskRequest request) {
        return service.create(
                request.getPrompt(), request.getVoice(), request.getDifficulty());
    }

    @GetMapping("/{uuid}")
    public Task get(@PathVariable String uuid) {
        return service.get(uuid);
    }

    @PostMapping("/{uuid}/complete")
    public Task complete(
            @PathVariable String uuid,
            @RequestParam MultipartFile audio,
            @RequestParam String questions) throws IOException {
        return service.complete(uuid, audio, questions);
    }

    @PostMapping("/{uuid}/fail")
    public Task fail(
            @PathVariable String uuid,
            @RequestParam(required = false, defaultValue = "Task execution failed") String reason) {
        return service.fail(uuid, reason);
    }

    @ResponseStatus(HttpStatus.NOT_FOUND)
    @org.springframework.web.bind.annotation.ExceptionHandler
    public String notFound(com.example.tts.service.TaskNotFoundException exception) {
        return exception.getMessage();
    }
}
