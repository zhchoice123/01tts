package com.example.tts.service;

import com.example.tts.entity.ContentItem;
import com.example.tts.entity.DailyPlan;
import com.example.tts.entity.LearningAttempt;
import com.example.tts.repository.ContentItemRepository;
import com.example.tts.repository.DailyPlanRepository;
import com.example.tts.repository.LearningAttemptRepository;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.time.LocalDate;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

@Service
public class ContentService {
    private static final List<String[]> DAILY_TOPICS = Arrays.asList(
            new String[] {
                "TECHNOLOGY",
                "Java Records and Immutable Data",
                "Create a B1 English reading about Java records, immutability, and one practical use."
            },
            new String[] {
                "SPORT",
                "How Team Sports Build Communication",
                "Create a B1 English reading about communication and decision-making in team sports."
            },
            new String[] {
                "CULTURE",
                "Clear Communication Across Cultures",
                "Create a B1 English reading about respectful communication across different cultures."
            },
            new String[] {
                "SCIENCE",
                "Small Habits and the Learning Brain",
                "Create a B1 English reading about memory, deliberate practice, and small daily habits."
            },
            new String[] {
                "WORKPLACE",
                "Explaining Technical Ideas Clearly",
                "Create a B1 English reading about explaining a software design to non-technical colleagues."
            });
    private final ContentItemRepository contentRepository;
    private final LearningAttemptRepository attemptRepository;
    private final DailyPlanRepository dailyPlanRepository;
    private final QueuePublisher publisher;
    private final Path contentAudioDir;

    public ContentService(
            ContentItemRepository contentRepository,
            LearningAttemptRepository attemptRepository,
            DailyPlanRepository dailyPlanRepository,
            QueuePublisher publisher,
            @Value("${tts.storage-dir:./storage}") String storageDir) {
        this.contentRepository = contentRepository;
        this.attemptRepository = attemptRepository;
        this.dailyPlanRepository = dailyPlanRepository;
        this.publisher = publisher;
        this.contentAudioDir = Paths.get(storageDir).toAbsolutePath().normalize().resolve("content");
    }

    @Transactional
    public ContentItem create(
            String sourceType, String sourceUrl, String text, String title, String level) {
        String normalizedType = sourceType.trim().toUpperCase(Locale.ROOT);
        if (!java.util.Arrays.asList("TEXT", "URL", "NEWS", "TECH_DOC").contains(normalizedType)) {
            throw new IllegalArgumentException("unsupported sourceType");
        }
        String input = text == null ? "" : text.trim();
        String url = sourceUrl == null ? "" : sourceUrl.trim();
        if ("TEXT".equals(normalizedType) && input.isEmpty()) {
            throw new IllegalArgumentException("text is required for TEXT content");
        }
        if (!"TEXT".equals(normalizedType) && url.isEmpty() && input.isEmpty()) {
            throw new IllegalArgumentException("sourceUrl or text is required");
        }
        String uuid = UUID.randomUUID().toString();
        String resolvedTitle = title == null || title.trim().isEmpty()
                ? ("TEXT".equals(normalizedType) ? input.substring(0, Math.min(60, input.length())) : "English learning content")
                : title.trim();
        ContentItem content = contentRepository.save(new ContentItem(
                uuid, resolvedTitle, normalizedType, url,
                input.isEmpty() ? url : input, level == null ? "B1" : level));
        publisher.publishContentAfterCommit(uuid);
        return content;
    }

    public ContentItem get(String uuid) {
        return contentRepository.findById(uuid)
                .orElseThrow(() -> new TaskNotFoundException("content " + uuid));
    }

    public List<ContentItem> library() {
        return contentRepository.findAllByOrderByCreatedAtDesc();
    }

    @Transactional
    public ContentItem complete(String uuid, MultipartFile audio, String lessonContent) throws IOException {
        ContentItem content = get(uuid);
        Files.createDirectories(contentAudioDir);
        Path destination = contentAudioDir.resolve(uuid + ".mp3").normalize();
        if (!destination.startsWith(contentAudioDir)) {
            throw new IOException("Invalid content audio path");
        }
        Files.copy(audio.getInputStream(), destination, StandardCopyOption.REPLACE_EXISTING);
        content.complete("/api/v1/audio/content/" + uuid + ".mp3", lessonContent);
        return contentRepository.save(content);
    }

    @Transactional
    public ContentItem fail(String uuid, String reason) {
        ContentItem content = get(uuid);
        content.fail(reason);
        return contentRepository.save(content);
    }

    @Transactional
    public LearningAttempt createAttempt(String uuid, String answersJson, Integer correctCount) {
        get(uuid);
        return attemptRepository.save(new LearningAttempt(uuid, answersJson, correctCount));
    }

    public DailyPlan getPlan(LocalDate date) {
        return dailyPlanRepository.findById(date)
                .orElseThrow(() -> new TaskNotFoundException("daily plan " + date));
    }

    @Transactional
    public DailyPlan generatePlan(LocalDate date) {
        return dailyPlanRepository.findById(date).orElseGet(() -> {
            String[] topic = DAILY_TOPICS.get(
                    Math.floorMod((int) date.toEpochDay(), DAILY_TOPICS.size()));
            ContentItem content = create(
                    "TECH_DOC", "", topic[2]
                            + " Include 8 to 12 core vocabulary items, three comprehension questions, "
                            + "one speaking prompt, and one short writing prompt. Category: " + topic[0] + ".",
                    topic[1], "B1");
            return dailyPlanRepository.save(new DailyPlan(date, content.getUuid()));
        });
    }

    public ContentItem getPlanContent(DailyPlan plan) {
        return get(plan.getContentUuid());
    }

    public Path resolveAudio(String fileName) {
        if (fileName == null || !fileName.matches("[0-9a-fA-F-]{36}\\.mp3")) {
            throw new IllegalArgumentException("invalid audio file name");
        }
        Path path = contentAudioDir.resolve(fileName).normalize();
        if (!path.startsWith(contentAudioDir) || !Files.isRegularFile(path)) {
            throw new TaskNotFoundException("audio " + fileName);
        }
        return path;
    }
}
