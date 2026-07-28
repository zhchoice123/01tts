package com.example.tts.repository;

import com.example.tts.entity.DailyPlan;
import java.time.LocalDate;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DailyPlanRepository extends JpaRepository<DailyPlan, LocalDate> {}
