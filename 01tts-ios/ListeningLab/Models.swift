import Foundation

struct DailyPlan: Codable, Equatable {
    let planDate: String
    let contentUuid: String
    let estimatedMinutes: Int
    let content: ContentItem
}

struct ContentItem: Codable, Identifiable, Equatable {
    let uuid: String
    var title: String
    var sourceType: String
    var sourceUrl: String?
    var sourceText: String
    var level: String
    var status: String
    var audioUrl: String?
    var lessonContent: String?
    var failureReason: String?
    var createdAt: String?
    var profile: String?
    var category: String?
    var voice: String?
    var sourceMode: String?
    var estimatedMinutes: Int?

    var id: String { uuid }
    var isReady: Bool { status == "READY" || status == "COMPLETED" }
    var lesson: LessonContent { LessonContent.decode(lessonContent, fallbackPassage: sourceText) }
}

struct LessonContent: Codable, Equatable {
    var passage: String = ""
    var dialogue: [DialogueTurn] = []
    var questions: [LessonQuestion] = []
    var vocabulary: [LessonVocabulary] = []
    var wordTimings: [WordTiming] = []

    enum CodingKeys: String, CodingKey {
        case passage, dialogue, questions, vocabulary, wordTimings
    }

    init(
        passage: String = "",
        dialogue: [DialogueTurn] = [],
        questions: [LessonQuestion] = [],
        vocabulary: [LessonVocabulary] = [],
        wordTimings: [WordTiming] = []
    ) {
        self.passage = passage
        self.dialogue = dialogue
        self.questions = questions
        self.vocabulary = vocabulary
        self.wordTimings = wordTimings
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        passage = try container.decodeIfPresent(String.self, forKey: .passage) ?? ""
        dialogue = try container.decodeIfPresent([DialogueTurn].self, forKey: .dialogue) ?? []
        questions = try container.decodeIfPresent([LessonQuestion].self, forKey: .questions) ?? []
        vocabulary = try container.decodeIfPresent([LessonVocabulary].self, forKey: .vocabulary) ?? []
        wordTimings = try container.decodeIfPresent([WordTiming].self, forKey: .wordTimings) ?? []
    }

    static func decode(_ raw: String?, fallbackPassage: String) -> LessonContent {
        guard let raw, let data = raw.data(using: .utf8),
              var value = try? JSONDecoder().decode(LessonContent.self, from: data) else {
            return LessonContent(passage: fallbackPassage)
        }
        if value.passage.isEmpty { value.passage = fallbackPassage }
        return value
    }
}

struct DialogueTurn: Codable, Identifiable, Equatable {
    var speaker: String
    var text: String
    var startMs: Int?
    var endMs: Int?
    var words: [WordTiming]?

    var id: String { "\(speaker)-\(startMs ?? 0)-\(text.prefix(24))" }
}

struct WordTiming: Codable, Identifiable, Equatable {
    var text: String
    var startMs: Int
    var endMs: Int
    var charStart: Int
    var charEnd: Int

    var id: String { "\(startMs)-\(charStart)-\(text)" }
}

struct LessonQuestion: Codable, Identifiable, Equatable {
    var type: String?
    var question: String?
    var prompt: String?
    var choices: [String]?
    var options: [String]?
    var answer: String?

    var id: String { wording }
    var wording: String { (question?.isEmpty == false ? question : prompt) ?? "" }
    var availableOptions: [String] { choices?.isEmpty == false ? choices! : (options ?? []) }
}

struct LessonVocabulary: Codable, Identifiable, Equatable {
    var word: String
    var phonetic: String?
    var definition: String?
    var meaningZh: String?
    var example: String?
    var collocations: [String]?
    var usageNotes: String?

    var id: String { word.lowercased() }
}

struct TopicRecommendation: Codable, Identifiable, Equatable {
    let uuid: String
    let planDate: String
    let kind: String
    let category: String
    let title: String
    let summary: String
    let sourceName: String?
    let sourceUrl: String?
    let publishedAt: String?
    let provider: String
    let score: Double
    let status: String
    let contentUuid: String
    let audioUrl: String?
    let failureReason: String?
    var id: String { uuid }
}

struct LearningDashboard: Codable, Equatable {
    var days = 7
    var listeningMinutes = 0
    var completedLessons = 0
    var quizCorrect = 0
    var quizTotal = 0
    var speakingAverage = 0
    var currentStreak = 0
    var wordsReviewed = 0
    var latestContentUuid: String?
    var latestPositionMs = 0
}

struct LearningProgress: Codable, Equatable {
    var clientId: String
    var contentUuid: String
    var positionMs = 0
    var durationMs = 0
    var vocabularyDone = false
    var listeningDone = false
    var readingDone = false
    var quizCorrect = 0
    var quizTotal = 0
    var speakingScore: Int?
    var completed = false
    var updatedAt: String?
}

struct TaskItem: Codable, Equatable {
    let taskUuid: String
    let prompt: String
    let voice: String
    let difficulty: String
    let status: String
    let audioUrl: String?
    let questions: String?
    let vocabulary: String?
    let lessonContent: String?
}

struct AnswerItem: Codable, Equatable {
    let answerUuid: String
    let taskUuid: String
    let status: String
    let audioUrl: String
    let transcript: String?
    let score: Int?
    let feedback: String?
    let failureReason: String?
    let evaluation: SpeakingEvaluation?
}

struct SpeakingEvaluation: Codable, Equatable {
    let overallScore: Int?
    let pronunciationScore: Int?
    let fluencyScore: Int?
    let intonationScore: Int?
    let pacingScore: Int?
    let relevanceScore: Int?
    let grammarScore: Int?
    let vocabularyScore: Int?
    let summary: String?
    let strengths: [String]?
    let improvements: [String]?
    let practicePlan: [String]?
    let mode: String?
    let model: String?
}

struct CreateTaskRequest: Codable {
    let prompt: String
    let voice: String
    let difficulty: String
}

struct CreateLongLessonRequest: Codable {
    let topic: String
    let category: String
    let voice: String
    let level: String
    let sourceMode: String
}

extension Array where Element == WordTiming {
    func activeIndex(at positionMs: Int) -> Int? {
        var low = 0
        var high = count - 1
        while low <= high {
            let middle = (low + high) / 2
            let item = self[middle]
            if positionMs < item.startMs { high = middle - 1 }
            else if positionMs >= item.endMs { low = middle + 1 }
            else { return middle }
        }
        return nil
    }
}
