package com.example.tts.controller;

import com.example.tts.entity.SpeakingAnswer;
import com.example.tts.service.SpeakingAnswerService;
import java.io.IOException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/v1")
public class SpeakingAnswerController {
    private final SpeakingAnswerService service;

    public SpeakingAnswerController(SpeakingAnswerService service) {
        this.service = service;
    }

    @PostMapping("/tasks/{taskUuid}/answers")
    public SpeakingAnswer create(
            @PathVariable String taskUuid,
            @RequestParam MultipartFile audio) throws IOException {
        return service.create(taskUuid, audio);
    }

    @GetMapping("/answers/{uuid}")
    public SpeakingAnswer get(@PathVariable String uuid) {
        return service.get(uuid);
    }

    @PostMapping("/answers/{uuid}/complete")
    public SpeakingAnswer complete(
            @PathVariable String uuid,
            @RequestBody CompleteAnswerRequest request) {
        return service.complete(
                uuid, request.getTranscript(), request.getScore(), request.getFeedback());
    }
}
