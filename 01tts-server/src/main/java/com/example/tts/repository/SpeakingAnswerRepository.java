package com.example.tts.repository;

import com.example.tts.entity.SpeakingAnswer;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SpeakingAnswerRepository extends JpaRepository<SpeakingAnswer, String> {}
