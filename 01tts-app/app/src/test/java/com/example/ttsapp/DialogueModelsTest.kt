package com.example.ttsapp

import androidx.compose.ui.graphics.Color
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
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

    @Test
    fun parsesTopLevelWordTimingsAndLocatesActiveWord() {
        val passage = "Connection pools improve throughput."
        val words = parseLessonWordTimings(
            """{"timingVersion":1,"wordTimings":[
                {"text":"Connection","startMs":100,"endMs":600,"charStart":0,"charEnd":10},
                {"text":"pools","startMs":650,"endMs":950,"charStart":11,"charEnd":16},
                {"text":"invalid","startMs":950,"endMs":900,"charStart":17,"charEnd":24}
            ]}""",
            passage,
        )

        assertEquals(2, words.size)
        assertEquals(0, activeWordIndex(words, 400))
        assertEquals(1, activeWordIndex(words, 700))

        // Default gap smoothing only bridges a short rendering gap; it must not make a word sticky.
        assertEquals(0, activeWordIndex(words, 625))
        assertEquals(1, activeWordIndex(words, 1_000))
        assertEquals(1, activeWordIndex(words, 1_070))
        assertEquals(-1, activeWordIndex(words, 1_071))
        assertEquals(-1, activeWordIndex(words, 2_500))

        // Strict exact matching when maxGapMs = 0L
        assertEquals(-1, activeWordIndex(words, 625, maxGapMs = 0L))
        assertEquals(-1, activeWordIndex(words, 1_000, maxGapMs = 0L))
    }

    @Test
    fun parsesDialogueWordsUsingGlobalMilliseconds() {
        val turns = parseDialogue(
            """{"dialogue":[{
                "speaker":"EXPERT",
                "text":"Use Redis.",
                "startMs":2000,
                "endMs":3200,
                "words":[
                    {"text":"Use","startMs":2100,"endMs":2400,"charStart":0,"charEnd":3},
                    {"text":"Redis","startMs":2450,"endMs":3000,"charStart":4,"charEnd":9}
                ]
            }]}"""
        )

        assertEquals(2, turns.single().words.size)
        assertEquals(1, activeWordIndex(turns.single().words, 2_700))
    }

    @Test
    fun dialogueHighlightOnlyUsesTheCurrentTurn() {
        val turns = parseDialogue(
            """{"dialogue":[
                {"speaker":"HOST","text":"Old word","startMs":0,"endMs":1000,"words":[
                    {"text":"word","startMs":700,"endMs":950,"charStart":4,"charEnd":8}
                ]},
                {"speaker":"EXPERT","text":"New word","startMs":1000,"endMs":2000,"words":[
                    {"text":"New","startMs":1000,"endMs":1300,"charStart":0,"charEnd":3}
                ]}
            ]}"""
        )

        val activeTurn = activeDialogueIndex(turns, 1_020)

        assertEquals(1, activeTurn)
        assertEquals(0, activeDialogueWordIndex(turns, activeTurn, 1_020))
    }

    @Test
    fun timedTranscriptCrossfadesWithoutChangingFontWeight() {
        val transcript = buildTimedTranscript(
            text = "Old New",
            words = listOf(
                WordTiming("Old", 0, 300, 0, 3),
                WordTiming("New", 320, 620, 4, 7),
            ),
            activeIndex = 1,
            previousActiveIndex = 0,
            transitionProgress = 0.25f,
            highlightColor = Color.Red,
            highlightedTextColor = Color.White,
            normalTextColor = Color.DarkGray,
        )

        val oldStyle = transcript.spanStyles.single { it.start == 0 && it.end == 3 }.item
        val newStyle = transcript.spanStyles.single { it.start == 4 && it.end == 7 }.item
        assertEquals(0.75f, oldStyle.background.alpha, 0.001f)
        assertEquals(0.25f, newStyle.background.alpha, 0.001f)
        assertNull(oldStyle.fontWeight)
        assertNull(newStyle.fontWeight)
    }

    @Test
    fun oldDialogueWithoutWordsStillUsesTurnTiming() {
        val turns = parseDialogue(
            """{"dialogue":[
                {"speaker":"HOST","text":"Old content","startMs":0,"endMs":1000}
            ]}"""
        )

        assertTrue(turns.single().words.isEmpty())
        assertEquals(0, activeDialogueIndex(turns, 500))
        assertEquals(-1, activeWordIndex(turns.single().words, 500))
    }

    @Test
    fun longTranscriptIsSplitIntoParagraphsWithLocalCharacterOffsets() {
        val text = "First paragraph.\n\nSecond word."
        val words = listOf(
            WordTiming("First", 0, 300, 0, 5),
            WordTiming("Second", 500, 900, 18, 24),
            WordTiming("word", 900, 1_200, 25, 29),
        )

        val blocks = splitTimedTranscript(text, words)

        assertEquals(listOf("First paragraph.", "Second word."), blocks.map { it.text })
        assertEquals(0, blocks[1].words[0].charStart)
        assertEquals(7, blocks[1].words[1].charStart)
    }
}
