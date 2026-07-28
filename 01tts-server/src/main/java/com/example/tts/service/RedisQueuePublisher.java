package com.example.tts.service;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class RedisQueuePublisher implements QueuePublisher {
    private final StringRedisTemplate redis;

    public RedisQueuePublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @Override
    public void publish(String taskUuid) {
        redis.opsForList().leftPush("queue:tts_tasks", taskUuid);
    }

    @Override
    public void publishContent(String contentUuid) {
        redis.opsForList().leftPush("queue:content_tasks", contentUuid);
    }
}
