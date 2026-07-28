package com.example.tts.service;

import com.example.tts.entity.Task;
import com.example.tts.repository.TaskRepository;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

@Service
public class TaskService {
    private final TaskRepository repository;
    private final QueuePublisher publisher;
    private final Path storageDir;

    public TaskService(
            TaskRepository repository,
            QueuePublisher publisher,
            @Value("${tts.storage-dir:./storage}") String storageDir) {
        this.repository = repository;
        this.publisher = publisher;
        this.storageDir = Paths.get(storageDir).toAbsolutePath().normalize();
    }

    @Transactional
    public Task create(String prompt, String voice, String difficulty) {
        Task task = repository.save(
                new Task(UUID.randomUUID().toString(), prompt, voice, difficulty));
        publisher.publishAfterCommit(task.getTaskUuid());
        return task;
    }

    public Task get(String uuid) {
        return repository.findById(uuid)
                .orElseThrow(() -> new TaskNotFoundException(uuid));
    }

    @Transactional
    public Task complete(String uuid, MultipartFile audio, String questions) throws IOException {
        Task task = get(uuid);
        Files.createDirectories(storageDir);
        Path destination = storageDir.resolve(uuid + ".mp3").normalize();
        if (!destination.startsWith(storageDir)) {
            throw new IOException("Invalid storage path");
        }
        Files.copy(audio.getInputStream(), destination, StandardCopyOption.REPLACE_EXISTING);
        task.complete("/audio/" + uuid + ".mp3", questions);
        return repository.save(task);
    }

    @Transactional
    public Task fail(String uuid, String reason) {
        Task task = get(uuid);
        task.fail(reason);
        return repository.save(task);
    }
}
