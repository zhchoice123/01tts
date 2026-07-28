package com.example.tts.controller;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.tts.entity.ContentItem;
import com.example.tts.entity.DailyPlan;
import com.example.tts.service.ContentService;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(ContentController.class)
class ContentControllerTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    ContentService service;

    @Test
    void importsTextContent() throws Exception {
        ContentItem item = new ContentItem(
                "content-1", "Virtual Threads", "TEXT", "",
                "Virtual threads are lightweight.", "B1");
        when(service.create(eq("TEXT"), eq(""), any(), eq("Virtual Threads"), eq("B1")))
                .thenReturn(item);

        mvc.perform(post("/api/v1/content/import")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sourceType\":\"TEXT\",\"text\":\"Virtual threads are lightweight.\","
                                + "\"title\":\"Virtual Threads\",\"level\":\"B1\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.uuid").value("content-1"))
                .andExpect(jsonPath("$.status").value("GENERATING"));
    }

    @Test
    void invalidRequestUsesStructuredError() throws Exception {
        mvc.perform(post("/api/v1/content/import")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sourceType\":\"\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"))
                .andExpect(jsonPath("$.retryable").value(false));
    }

    @Test
    void acceptsIsoDateWhenGeneratingDailyPlan() throws Exception {
        LocalDate date = LocalDate.of(2026, 7, 26);
        when(service.generatePlan(date)).thenReturn(new DailyPlan(date, "content-2"));

        mvc.perform(post("/api/v1/daily-plans/2026-07-26/generate"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.planDate").value("2026-07-26"))
                .andExpect(jsonPath("$.contentUuid").value("content-2"));
    }
}
