package com.example.tts.controller;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.tts.entity.Task;
import com.example.tts.service.TaskService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(TaskController.class)
class TaskControllerTest {
    @Autowired MockMvc mvc;
    @MockBean TaskService service;

    @Test
    void getsTaskByUuid() throws Exception {
        when(service.get("task-1"))
                .thenReturn(
                        new Task(
                                "task-1", "Generate a lesson", "en-US-AvaNeural", "medium"));

        mvc.perform(get("/api/v1/tasks/task-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.taskUuid").value("task-1"))
                .andExpect(jsonPath("$.status").value("PENDING"));
    }
}
