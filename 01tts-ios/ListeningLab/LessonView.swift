import AVFoundation
import SwiftUI

struct LessonView: View {
    enum Stage: String, CaseIterable, Identifiable {
        case listen, read, quiz, words, speak
        var id: String { rawValue }
    }

    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var store: AppStore
    @StateObject private var audio = AudioController()
    @State private var stage: Stage = .listen
    @State private var transcriptVisible = true
    @State private var progress: LearningProgress
    @State private var answers: [String: String] = [:]
    @State private var showVocabulary: LessonVocabulary?
    let content: ContentItem

    init(content: ContentItem) {
        self.content = content
        _progress = State(
            initialValue: LearningProgress(
                clientId: "",
                contentUuid: content.uuid
            )
        )
    }

    private var lesson: LessonContent { content.lesson }
    private var timings: [WordTiming] {
        if !lesson.wordTimings.isEmpty { return lesson.wordTimings }
        return lesson.dialogue.flatMap { $0.words ?? [] }.sorted { $0.startMs < $1.startMs }
    }

    var body: some View {
        VStack(spacing: 0) {
            stagePicker
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        lessonHeader
                        switch stage {
                        case .listen: listenStage
                        case .read: readStage
                        case .quiz: quizStage
                        case .words: wordsStage
                        case .speak: SpeakingPanel(progress: $progress, content: content)
                        }
                    }
                    .padding(20)
                }
                .onChange(of: audio.positionMs) { _, _ in
                    guard stage == .listen,
                          let index = activeDialogueIndex,
                          lesson.dialogue.indices.contains(index) else { return }
                    withAnimation(.easeOut(duration: 0.25)) {
                        proxy.scrollTo(lesson.dialogue[index].id, anchor: .center)
                    }
                }
            }
            if content.audioUrl != nil { playerBar }
        }
        .navigationTitle(store.localized("Lesson", "课程"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(store.localized("Done", "完成")) { dismiss() }
            }
        }
        .task {
            progress.clientId = store.clientID
            if let saved = try? await APIClient.shared.progress(clientID: store.clientID, contentID: content.uuid) {
                progress = saved
            }
            if let url = APIClient.shared.mediaURL(content.audioUrl) {
                audio.load(url)
                if progress.positionMs > 0 { audio.seek(to: progress.positionMs) }
            }
        }
        .onDisappear {
            progress.positionMs = audio.positionMs
            progress.durationMs = max(audio.durationMs, audio.positionMs)
            Task { await store.updateProgress(progress) }
        }
        .sheet(item: $showVocabulary) { word in
            VocabularySheet(word: word)
        }
    }

    private var stagePicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                stageButton(.listen, "headphones", store.localized("Listen", "盲听"))
                stageButton(.read, "text.book.closed", store.localized("Read", "原文"))
                stageButton(.quiz, "checkmark.circle", store.localized("Quiz", "答题"))
                stageButton(.words, "character.book.closed", store.localized("Words", "词汇"))
                stageButton(.speak, "mic", store.localized("Speak", "口语"))
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
        }
        .background(.bar)
    }

    private func stageButton(_ value: Stage, _ icon: String, _ title: String) -> some View {
        Button {
            stage = value
            if value == .read { progress.readingDone = true }
            if value == .words { progress.vocabularyDone = true }
        } label: {
            Label(title, systemImage: icon)
                .font(.caption.weight(.semibold))
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(stage == value ? AppPalette.accent : Color.secondary.opacity(0.1), in: Capsule())
                .foregroundStyle(stage == value ? .white : .primary)
        }
        .buttonStyle(.plain)
    }

    private var lessonHeader: some View {
        VStack(alignment: .leading, spacing: 9) {
            Text((content.category ?? content.sourceType).replacingOccurrences(of: "_", with: " "))
                .font(.caption.bold())
                .foregroundStyle(AppPalette.accent)
            Text(content.title)
                .font(.system(.title, design: .rounded, weight: .bold))
            HStack(spacing: 10) {
                Label(content.level, systemImage: "chart.bar")
                if let minutes = content.estimatedMinutes {
                    Label("\(minutes) min", systemImage: "clock")
                }
                if !lesson.dialogue.isEmpty {
                    Label(store.localized("Dialogue", "对话"), systemImage: "person.2")
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
    }

    private var listenStage: some View {
        VStack(alignment: .leading, spacing: 16) {
            Toggle(isOn: $transcriptVisible) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(store.localized("Show transcript", "显示原文")).font(.headline)
                    Text(store.localized("Turn it off for a blind listening pass.", "关闭后进行盲听训练。"))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .tint(AppPalette.accent)

            if transcriptVisible {
                if !lesson.dialogue.isEmpty {
                    ForEach(Array(lesson.dialogue.enumerated()), id: \.element.id) { index, turn in
                        DialogueBubble(
                            turn: turn,
                            isActive: index == activeDialogueIndex,
                            positionMs: audio.positionMs
                        ) {
                            if let start = turn.startMs { audio.seek(to: start) }
                        }
                        .id(turn.id)
                    }
                } else {
                    highlightedPassage
                }
            } else {
                blindListening
            }
        }
    }

    private var blindListening: some View {
        VStack(spacing: 18) {
            Image(systemName: audio.isPlaying ? "waveform.circle.fill" : "ear")
                .font(.system(size: 64))
                .foregroundStyle(AppPalette.accent)
                .symbolEffect(.variableColor.iterative, isActive: audio.isPlaying)
            Text(store.localized("Listen for structure, not every word.", "先听懂结构，不必追求每个单词。"))
                .font(.title3.bold())
            Text(store.localized("Notice the problem, the explanation, the example and the conclusion.", "关注问题、原理、案例和结论。"))
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 44)
    }

    private var readStage: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(lesson.passage)
                .font(.body)
                .textSelection(.enabled)
                .lineSpacing(7)
            if lesson.passage.isEmpty && !lesson.dialogue.isEmpty {
                ForEach(lesson.dialogue) { turn in
                    VStack(alignment: .leading, spacing: 5) {
                        Text(turn.speaker).font(.caption.bold()).foregroundStyle(AppPalette.accent)
                        Text(turn.text).lineSpacing(6)
                    }
                }
            }
        }
    }

    private var highlightedPassage: some View {
        Text(attributedPassage)
            .font(.body)
            .lineSpacing(7)
            .textSelection(.enabled)
    }

    private var attributedPassage: AttributedString {
        var value = AttributedString(lesson.passage)
        guard let active = timings.activeIndex(at: audio.positionMs),
              timings.indices.contains(active) else { return value }
        let timing = timings[active]
        guard timing.charStart >= 0,
              timing.charEnd <= value.characters.count,
              timing.charStart < timing.charEnd else { return value }
        let start = value.index(value.startIndex, offsetByCharacters: timing.charStart)
        let end = value.index(value.startIndex, offsetByCharacters: timing.charEnd)
        value[start..<end].backgroundColor = AppPalette.accent.opacity(0.28)
        value[start..<end].foregroundColor = AppPalette.ink
        value[start..<end].font = .body.bold()
        return value
    }

    private var quizStage: some View {
        VStack(alignment: .leading, spacing: 22) {
            if lesson.questions.isEmpty {
                ContentUnavailableView(
                    store.localized("No questions", "暂无题目"),
                    systemImage: "questionmark.bubble",
                    description: Text(store.localized("This imported lesson does not include a quiz.", "该课程未包含阅读理解题。"))
                )
            }
            ForEach(Array(lesson.questions.enumerated()), id: \.element.id) { index, question in
                VStack(alignment: .leading, spacing: 12) {
                    Text("\(index + 1). \(question.wording)").font(.headline)
                    ForEach(question.availableOptions, id: \.self) { option in
                        let selected = answers[question.id] == option
                        Button {
                            answers[question.id] = option
                            updateQuizProgress()
                        } label: {
                            HStack {
                                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                                Text(option).multilineTextAlignment(.leading)
                                Spacer()
                            }
                            .padding(13)
                            .background(selected ? AppPalette.accent.opacity(0.12) : Color.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: 14))
                            .foregroundStyle(.primary)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            if !answers.isEmpty {
                let score = quizScore
                Label(
                    store.localized("\(score)/\(lesson.questions.count) correct", "答对 \(score)/\(lesson.questions.count) 题"),
                    systemImage: "chart.bar.fill"
                )
                .font(.headline)
                .foregroundStyle(AppPalette.accent)
            }
        }
    }

    private var wordsStage: some View {
        VStack(alignment: .leading, spacing: 12) {
            if lesson.vocabulary.isEmpty {
                ContentUnavailableView(
                    store.localized("No vocabulary list", "暂无核心词汇"),
                    systemImage: "character.book.closed",
                    description: Text(store.localized("Tap words in future generated lessons to build review history.", "后续生成的课程会包含可复习的核心词汇。"))
                )
            }
            ForEach(lesson.vocabulary) { word in
                Button { showVocabulary = word } label: {
                    HStack(alignment: .top, spacing: 14) {
                        Image(systemName: "speaker.wave.2.fill")
                            .foregroundStyle(AppPalette.accent)
                            .frame(width: 32, height: 32)
                            .background(AppPalette.accent.opacity(0.1), in: Circle())
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(word.word).font(.headline)
                                if let phonetic = word.phonetic, !phonetic.isEmpty {
                                    Text(phonetic).font(.caption).foregroundStyle(.secondary)
                                }
                            }
                            Text((store.language == "zh" ? word.meaningZh : word.definition) ?? word.definition ?? "")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.leading)
                        }
                        Spacer()
                        Image(systemName: "chevron.right").foregroundStyle(.tertiary)
                    }
                    .padding(.vertical, 8)
                    .foregroundStyle(.primary)
                }
                .buttonStyle(.plain)
                Divider()
            }
        }
    }

    private var playerBar: some View {
        VStack(spacing: 8) {
            Slider(
                value: Binding(
                    get: { Double(audio.positionMs) },
                    set: { audio.seek(to: Int($0)) }
                ),
                in: 0...Double(max(1, audio.durationMs))
            )
            .tint(AppPalette.accent)
            HStack {
                Button { audio.skip(-10) } label: { Image(systemName: "gobackward.10") }
                Spacer()
                Button { audio.toggle() } label: {
                    Image(systemName: audio.isPlaying ? "pause.fill" : "play.fill")
                        .font(.title2)
                        .frame(width: 48, height: 42)
                        .background(AppPalette.accent, in: Capsule())
                        .foregroundStyle(.white)
                }
                Spacer()
                Button { audio.skip(10) } label: { Image(systemName: "goforward.10") }
                Menu {
                    ForEach([0.8, 1.0, 1.2], id: \.self) { rate in
                        Button("\(rate, specifier: "%.1f")×") { audio.setRate(Float(rate)) }
                    }
                } label: {
                    Text("\(audio.rate, specifier: "%.1f")×")
                        .font(.caption.bold().monospacedDigit())
                        .frame(width: 44)
                }
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 10)
        .background(.ultraThinMaterial)
        .overlay(alignment: .top) { Divider() }
    }

    private var activeDialogueIndex: Int? {
        lesson.dialogue.lastIndex { turn in
            guard let start = turn.startMs else { return false }
            return audio.positionMs >= start && (turn.endMs == nil || audio.positionMs < turn.endMs!)
        }
    }

    private var quizScore: Int {
        lesson.questions.reduce(0) { result, question in
            let selected = answers[question.id]?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            let correct = question.answer?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            return result + (selected == correct && correct?.isEmpty == false ? 1 : 0)
        }
    }

    private func updateQuizProgress() {
        progress.quizTotal = lesson.questions.count
        progress.quizCorrect = quizScore
        progress.completed = progress.listeningDone && progress.readingDone && progress.quizTotal > 0
    }
}

struct DialogueBubble: View {
    let turn: DialogueTurn
    let isActive: Bool
    let positionMs: Int
    let seek: () -> Void

    private var color: Color { turn.speaker.uppercased() == "HOST" ? AppPalette.host : AppPalette.expert }

    var body: some View {
        Button(action: seek) {
            HStack(alignment: .top, spacing: 12) {
                Text(String(turn.speaker.prefix(1)))
                    .font(.caption.bold())
                    .frame(width: 34, height: 34)
                    .background(color, in: Circle())
                    .foregroundStyle(.white)
                VStack(alignment: .leading, spacing: 6) {
                    Text(turn.speaker.uppercased())
                        .font(.caption.bold())
                        .tracking(1)
                        .foregroundStyle(color)
                    Text(highlightedText)
                        .font(.body)
                        .lineSpacing(5)
                        .multilineTextAlignment(.leading)
                }
                Spacer(minLength: 0)
            }
            .padding(14)
            .background(isActive ? color.opacity(0.11) : Color.secondary.opacity(0.055), in: RoundedRectangle(cornerRadius: 18))
            .overlay {
                RoundedRectangle(cornerRadius: 18)
                    .stroke(isActive ? color.opacity(0.42) : .clear, lineWidth: 1)
            }
            .foregroundStyle(.primary)
        }
        .buttonStyle(PressButtonStyle())
    }

    private var highlightedText: AttributedString {
        var value = AttributedString(turn.text)
        guard isActive, let words = turn.words,
              let active = words.activeIndex(at: positionMs),
              words.indices.contains(active) else { return value }
        let word = words[active]
        guard word.charStart >= 0,
              word.charEnd <= value.characters.count,
              word.charStart < word.charEnd else { return value }
        let start = value.index(value.startIndex, offsetByCharacters: word.charStart)
        let end = value.index(value.startIndex, offsetByCharacters: word.charEnd)
        value[start..<end].backgroundColor = color.opacity(0.25)
        value[start..<end].font = .body.bold()
        return value
    }
}

struct VocabularySheet: View {
    @Environment(\.dismiss) private var dismiss
    let word: LessonVocabulary
    private let synthesizer = AVSpeechSynthesizer()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    HStack {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(word.word).font(.largeTitle.bold())
                            if let phonetic = word.phonetic { Text(phonetic).foregroundStyle(.secondary) }
                        }
                        Spacer()
                        Button(action: speak) {
                            Image(systemName: "speaker.wave.2.fill")
                                .font(.title2)
                                .frame(width: 50, height: 50)
                                .background(AppPalette.accent, in: Circle())
                                .foregroundStyle(.white)
                        }
                    }
                    detail("Definition", word.definition)
                    detail("中文释义", word.meaningZh)
                    detail("Example", word.example)
                    detail("Usage", word.usageNotes)
                    if let collocations = word.collocations, !collocations.isEmpty {
                        detail("Collocations", collocations.joined(separator: " · "))
                    }
                }
                .padding(20)
            }
            .navigationTitle("Vocabulary")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("Done") { dismiss() } }
        }
    }

    private func detail(_ title: String, _ value: String?) -> some View {
        Group {
            if let value, !value.isEmpty {
                VStack(alignment: .leading, spacing: 7) {
                    Text(title.uppercased()).font(.caption.bold()).foregroundStyle(AppPalette.accent)
                    Text(value).lineSpacing(5)
                }
            }
        }
    }

    private func speak() {
        let utterance = AVSpeechUtterance(string: word.word)
        utterance.voice = AVSpeechSynthesisVoice(language: "en-US")
        utterance.rate = 0.42
        synthesizer.speak(utterance)
    }
}
