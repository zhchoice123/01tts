package com.example.tts.repository;

import com.example.tts.entity.LearningAttempt;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface LearningAttemptRepository extends JpaRepository<LearningAttempt, Long> {
    List<LearningAttempt> findByContentUuidOrderBySubmittedAtDesc(String contentUuid);
}
