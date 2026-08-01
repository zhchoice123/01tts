import Foundation
import SwiftUI

@MainActor
final class AppStore: ObservableObject {
    enum Tab: Hashable { case today, read, practice, library, settings }

    @Published var tab: Tab = .today
    @Published var dailyPlan: DailyPlan?
    @Published var library: [ContentItem] = []
    @Published var topics: [TopicRecommendation] = []
    @Published var dashboard = LearningDashboard()
    @Published var selectedContent: ContentItem?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var generationMessage: String?

    @AppStorage("language") var language = "en"
    @AppStorage("theme") var theme = "system"
    @AppStorage("voice") var voice = "en-US-AvaNeural"
    @AppStorage("level") var level = "B1"
    @AppStorage("clientID") private var storedClientID = ""

    private let api = APIClient.shared

    var clientID: String {
        if UUID(uuidString: storedClientID) == nil { storedClientID = UUID().uuidString }
        return storedClientID
    }

    var colorScheme: ColorScheme? {
        switch theme {
        case "light": .light
        case "dark": .dark
        default: nil
        }
    }

    func localized(_ english: String, _ chinese: String) -> String {
        language == "zh" ? chinese : english
    }

    func bootstrap() async {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil
        async let planResult = try? api.today()
        async let libraryResult = try? api.library()
        async let topicResult = try? api.topics()
        async let dashboardResult = try? api.dashboard(clientID: clientID)
        dailyPlan = await planResult
        library = await libraryResult ?? []
        if dailyPlan?.content.isReady != true,
           let ready = library.first(where: \.isReady) {
            dailyPlan = DailyPlan(
                planDate: dailyPlan?.planDate ?? ISO8601DateFormatter().string(from: Date()).prefix(10).description,
                contentUuid: ready.uuid,
                estimatedMinutes: ready.estimatedMinutes ?? 10,
                content: ready
            )
        }
        topics = await topicResult ?? []
        dashboard = await dashboardResult ?? LearningDashboard()
        if dailyPlan == nil && library.isEmpty {
            errorMessage = localized("The learning service could not be reached.", "暂时无法连接学习服务。")
        }
        isLoading = false
    }

    func refresh() async {
        isLoading = false
        await bootstrap()
    }

    func open(_ content: ContentItem) {
        guard content.isReady else {
            generationMessage = localized("This lesson is still being generated.", "课程仍在生成中。")
            return
        }
        selectedContent = content
    }

    func openToday() {
        if let content = dailyPlan?.content { open(content) }
    }

    func generate(topic: String, category: String) async {
        isLoading = true
        errorMessage = nil
        do {
            let created = try await api.createLesson(topic: topic, category: category, voice: voice, level: level)
            library.insert(created, at: 0)
            generationMessage = localized(
                "Generation started. It will appear in Library when ready.",
                "已开始生成，完成后会出现在课程库。"
            )
            tab = .library
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func updateProgress(_ progress: LearningProgress) async {
        _ = try? await api.save(progress: progress)
    }
}
