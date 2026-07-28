package com.example.tts.service;

import com.example.tts.entity.SpeakingAnswer;
import com.example.tts.repository.SpeakingAnswerRepository;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

@Service
public class SpeakingAnswerService {
    private final SpeakingAnswerRepository repository;
    private final StringRedisTemplate redis;
    private final Path answerDir;

    public SpeakingAnswerService(
            SpeakingAnswerRepository repository,
            StringRedisTemplate redis,
            @Value("${tts.storage-dir:./storage}") String storageDir) {
        this.repository = repository;
        this.redis = redis;
        this.answerDir = Paths.get(storageDir).toAbsolutePath().normalize().resolve("answers");
    }

    @Transactional
    public SpeakingAnswer create(String taskUuid, MultipartFile audio) throws IOException {
        String answerUuid = UUID.randomUUID().toString();
        Files.createDirectories(answerDir);
        Path destination = answerDir.resolve(answerUuid + ".m4a").normalize();
        if (!destination.startsWith(answerDir)) {
            throw new IOException("Invalid answer path");
        }
        Files.copy(audio.getInputStream(), destination, StandardCopyOption.REPLACE_EXISTING);
        SpeakingAnswer answer = repository.save(
                new SpeakingAnswer(answerUuid, taskUuid, "/audio/answers/" + answerUuid + ".m4a"));
        redis.opsForList().leftPush("queue:speaking_answers", answerUuid);
        return answer;
    }

    public SpeakingAnswer get(String uuid) {
        return repository.findById(uuid)
                .orElseThrow(() -> new TaskNotFoundException("answer " + uuid));
    }

    @Transactional
    public SpeakingAnswer complete(
            String uuid, String transcript, Integer score, String feedback) {
        if (score == null || score < 0 || score > 100) {
            throw new IllegalArgumentException("score must be between 0 and 100");
        }
        SpeakingAnswer answer = get(uuid);
        answer.complete(transcript, score, feedback);
        return repository.save(answer);
    }
}
