package com.example.tts.controller;

import com.example.tts.entity.ContentItem;
import com.example.tts.entity.DailyPlan;
import com.example.tts.entity.LearningAttempt;
import com.example.tts.service.ContentService;
import java.io.IOException;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import javax.validation.Valid;
import org.springframework.core.io.FileSystemResource;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
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
public class ContentController {
    private final ContentService service;

    public ContentController(ContentService service) {
        this.service = service;
    }

    @PostMapping("/content/import")
    public ContentItem create(@Valid @RequestBody ImportContentRequest request) {
        return service.create(
                request.getSourceType(), request.getSourceUrl(), request.getText(),
                request.getTitle(), request.getLevel());
    }

    @GetMapping("/content/{uuid}")
    public ContentItem get(@PathVariable String uuid) {
        return service.get(uuid);
    }

    @PostMapping("/content/{uuid}/complete")
    public ContentItem complete(
            @PathVariable String uuid,
            @RequestParam MultipartFile audio,
            @RequestParam String lessonContent) throws IOException {
        return service.complete(uuid, audio, lessonContent);
    }

    @PostMapping("/content/{uuid}/fail")
    public ContentItem fail(
            @PathVariable String uuid,
            @RequestParam(defaultValue = "Content generation failed") String reason) {
        return service.fail(uuid, reason);
    }

    @PostMapping("/content/{uuid}/attempts")
    public LearningAttempt attempt(
            @PathVariable String uuid, @Valid @RequestBody CreateAttemptRequest request) {
        return service.createAttempt(uuid, request.getAnswersJson(), request.getCorrectCount());
    }

    @GetMapping("/daily-plans/{date}")
    public DailyPlanResponse plan(
            @PathVariable @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date) {
        DailyPlan plan = service.getPlan(date);
        return new DailyPlanResponse(plan, service.getPlanContent(plan));
    }

    @GetMapping("/daily-plans/today")
    public DailyPlanResponse today() {
        DailyPlan plan = service.getPlan(LocalDate.now(ZoneId.of("Asia/Shanghai")));
        return new DailyPlanResponse(plan, service.getPlanContent(plan));
    }

    @PostMapping("/daily-plans/{date}/generate")
    public DailyPlan generatePlan(
            @PathVariable @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date) {
        return service.generatePlan(date);
    }

    @GetMapping("/library")
    public List<ContentItem> library() {
        return service.library();
    }

    @GetMapping("/audio/content/{fileName:.+}")
    public ResponseEntity<FileSystemResource> audio(@PathVariable String fileName) throws IOException {
        FileSystemResource resource = new FileSystemResource(service.resolveAudio(fileName));
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache())
                .contentType(MediaType.valueOf("audio/mpeg"))
                .contentLength(resource.contentLength())
                .body(resource);
    }
}
