package com.example.tts.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.tts.entity.Task;
import com.example.tts.entity.TaskStatus;
import com.example.tts.repository.TaskRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.Mockito;

class TaskServiceTest {
    @TempDir java.nio.file.Path storage;

    @Test
    void createPersistsAndQueuesTask() {
        TaskRepository repository = Mockito.mock(TaskRepository.class);
        QueuePublisher publisher = Mockito.mock(QueuePublisher.class);
        when(repository.save(Mockito.any(Task.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));
        TaskService service = new TaskService(repository, publisher, storage.toString());

        Task task = service.create("Generate a lesson", "en-US-AvaNeural", "medium");

        assertEquals(TaskStatus.PENDING, task.getStatus());
        verify(publisher).publishAfterCommit(task.getTaskUuid());
    }
}
