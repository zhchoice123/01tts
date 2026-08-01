import XCTest
@testable import ListeningLab

final class ModelTests: XCTestCase {
    func testLessonContentDecodesWordTimings() {
        let raw = """
        {
          "passage":"Hello world",
          "wordTimings":[
            {"text":"Hello","startMs":0,"endMs":400,"charStart":0,"charEnd":5},
            {"text":"world","startMs":450,"endMs":900,"charStart":6,"charEnd":11}
          ],
          "questions":[],
          "vocabulary":[]
        }
        """
        let lesson = LessonContent.decode(raw, fallbackPassage: "")
        XCTAssertEqual(lesson.passage, "Hello world")
        XCTAssertEqual(lesson.wordTimings.count, 2)
        XCTAssertEqual(lesson.wordTimings.activeIndex(at: 500), 1)
        XCTAssertNil(lesson.wordTimings.activeIndex(at: 425))
    }

    func testContentReadyState() {
        let content = ContentItem(
            uuid: "lesson",
            title: "A lesson",
            sourceType: "LONG_LESSON",
            sourceText: "Text",
            level: "B1",
            status: "READY"
        )
        XCTAssertTrue(content.isReady)
        XCTAssertEqual(content.lesson.passage, "Text")
    }

    func testQuestionFallsBackToPromptAndOptions() {
        let question = LessonQuestion(
            prompt: "What changed?",
            options: ["Latency", "Color"],
            answer: "Latency"
        )
        XCTAssertEqual(question.wording, "What changed?")
        XCTAssertEqual(question.availableOptions, ["Latency", "Color"])
    }
}
