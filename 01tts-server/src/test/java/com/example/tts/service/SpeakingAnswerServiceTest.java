package com.example.tts.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.tts.entity.AnswerStatus;
import com.example.tts.entity.SpeakingAnswer;
import com.example.tts.repository.SpeakingAnswerRepository;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.Mockito;
import org.springframework.data.redis.core.ListOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.mock.web.MockMultipartFile;

class SpeakingAnswerServiceTest {
    @TempDir java.nio.file.Path storage;

    @Test
    void uploadPersistsAndQueuesAnswer() throws Exception {
        SpeakingAnswerRepository repository = Mockito.mock(SpeakingAnswerRepository.class);
        StringRedisTemplate redis = Mockito.mock(StringRedisTemplate.class);
        @SuppressWarnings("unchecked")
        ListOperations<String, String> list = Mockito.mock(ListOperations.class);
        when(redis.opsForList()).thenReturn(list);
        when(repository.save(Mockito.any(SpeakingAnswer.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));
        SpeakingAnswerService service =
                new SpeakingAnswerService(repository, redis, storage.toString());

        SpeakingAnswer answer = service.create(
                "task-1",
                new MockMultipartFile(
                        "audio", "answer.m4a", "audio/mp4",
                        "audio".getBytes(StandardCharsets.UTF_8)));

        assertEquals(AnswerStatus.PENDING, answer.getStatus());
        verify(list).leftPush("queue:speaking_answers", answer.getAnswerUuid());
    }
}
