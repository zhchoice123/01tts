package com.example.tts.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.tts.entity.ContentItem;
import com.example.tts.entity.DailyPlan;
import com.example.tts.entity.LearningAttempt;
import com.example.tts.repository.ContentItemRepository;
import com.example.tts.repository.DailyPlanRepository;
import com.example.tts.repository.LearningAttemptRepository;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.Mockito;

class ContentServiceTest {
    @TempDir
    Path tempDir;

    @Test
    void createsTextContentAndPublishesContentQueue() {
        ContentItemRepository contents = Mockito.mock(ContentItemRepository.class);
        LearningAttemptRepository attempts = Mockito.mock(LearningAttemptRepository.class);
        DailyPlanRepository plans = Mockito.mock(DailyPlanRepository.class);
        QueuePublisher publisher = Mockito.mock(QueuePublisher.class);
        when(contents.save(any(ContentItem.class))).thenAnswer(invocation -> invocation.getArgument(0));
        ContentService service = new ContentService(contents, attempts, plans, publisher, tempDir.toString());

        ContentItem content = service.create("text", "", "Virtual threads are lightweight.", "", "B1");

        assertEquals("TEXT", content.getSourceType());
        assertEquals(com.example.tts.entity.ContentStatus.GENERATING, content.getStatus());
        verify(publisher).publishContentAfterCommit(content.getUuid());
    }

    @Test
    void rejectsUnsupportedSourceType() {
        ContentService service = serviceWithMocks();
        assertThrows(
                IllegalArgumentException.class,
                () -> service.create("FILE", "", "text", "title", "B1"));
    }

    @Test
    void dailyPlanGenerationIsIdempotent() {
        ContentItemRepository contents = Mockito.mock(ContentItemRepository.class);
        LearningAttemptRepository attempts = Mockito.mock(LearningAttemptRepository.class);
        DailyPlanRepository plans = Mockito.mock(DailyPlanRepository.class);
        QueuePublisher publisher = Mockito.mock(QueuePublisher.class);
        LocalDate date = LocalDate.of(2026, 7, 25);
        DailyPlan existing = new DailyPlan(date, "content-id");
        when(plans.findById(date)).thenReturn(Optional.of(existing));
        ContentService service = new ContentService(contents, attempts, plans, publisher, tempDir.toString());

        assertEquals("content-id", service.generatePlan(date).getContentUuid());
    }

    @Test
    void blocksTraversalAndMissingAudio() throws Exception {
        ContentService service = serviceWithMocks();
        Files.createDirectories(tempDir.resolve("content"));

        assertThrows(IllegalArgumentException.class, () -> service.resolveAudio("../secret.mp3"));
        assertThrows(TaskNotFoundException.class,
                () -> service.resolveAudio("00000000-0000-0000-0000-000000000000.mp3"));
    }

    private ContentService serviceWithMocks() {
        return new ContentService(
                Mockito.mock(ContentItemRepository.class),
                Mockito.mock(LearningAttemptRepository.class),
                Mockito.mock(DailyPlanRepository.class),
                Mockito.mock(QueuePublisher.class),
                tempDir.toString());
    }
}
