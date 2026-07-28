package com.example.tts;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class TtsServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(TtsServerApplication.class, args);
    }
}
