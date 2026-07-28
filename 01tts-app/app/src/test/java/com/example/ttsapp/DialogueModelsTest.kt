package com.example.ttsapp

import org.junit.Assert.assertEquals
import org.junit.Test

class DialogueModelsTest {
    @Test
    fun parsesTimedHostAndExpertDialogue() {
        val turns = parseDialogue(
            """{"dialogue":[
                {"speaker":"HOST","text":"What failed?","startMs":0,"endMs":1800},
                {"speaker":"EXPERT","text":"The pool was exhausted.","startMs":1800,"endMs":4300}
            ]}"""
        )

        assertEquals(listOf("HOST", "EXPERT"), turns.map { it.speaker })
        assertEquals(1800L, turns[1].startMs)
        assertEquals(1, activeDialogueIndex(turns, 2500))
    }

    @Test
    fun missingTimingKeepsTranscriptAndDisablesActiveTurn() {
        val turns = parseDialogue(
            """{"dialogue":[{"speaker":"HOST","text":"Untimed question"}]}"""
        )

        assertEquals("Untimed question", turns.single().text)
        assertEquals(-1, activeDialogueIndex(turns, 500))
    }

    @Test
    fun playbackSpeedCyclesThroughSupportedValues() {
        assertEquals(1f, nextPlaybackSpeed(0.8f))
        assertEquals(1.2f, nextPlaybackSpeed(1f))
        assertEquals(0.8f, nextPlaybackSpeed(1.2f))
    }
}
