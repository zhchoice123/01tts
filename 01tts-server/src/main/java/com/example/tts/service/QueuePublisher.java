package com.example.tts.service;

import org.springframework.transaction.support.TransactionSynchronizationAdapter;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public interface QueuePublisher {
    void publish(String taskUuid);

    default void publishContent(String contentUuid) {
        publish(contentUuid);
    }

    default void publishAfterCommit(String taskUuid) {
        runAfterCommit(() -> publish(taskUuid));
    }

    default void publishContentAfterCommit(String contentUuid) {
        runAfterCommit(() -> publishContent(contentUuid));
    }

    static void runAfterCommit(Runnable action) {
        if (!TransactionSynchronizationManager.isActualTransactionActive()) {
            action.run();
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronizationAdapter() {
                    @Override
                    public void afterCommit() {
                        action.run();
                    }
                });
    }
}
