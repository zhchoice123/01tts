import SwiftUI

struct SpeakingPanel: View {
    @EnvironmentObject private var store: AppStore
    @StateObject private var recorder = RecorderController()
    @Binding var progress: LearningProgress
    let content: ContentItem

    @State private var task: TaskItem?
    @State private var answer: AnswerItem?
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            VStack(alignment: .leading, spacing: 8) {
                Text(store.localized("60-second spoken summary", "60 秒英文总结"))
                    .font(.title2.bold())
                Text(store.localized(
                    "Explain the main idea, one technical detail and one practical takeaway.",
                    "概括主要观点、一个技术细节和一个实践建议。"
                ))
                .foregroundStyle(.secondary)
            }

            if let evaluation = answer?.evaluation {
                evaluationView(evaluation)
            } else {
                recordingView
            }

            if let errorMessage {
                InlineError(message: errorMessage, retry: nil)
            }
        }
        .task { await prepareTask() }
    }

    private var recordingView: some View {
        VStack(spacing: 18) {
            ZStack {
                Circle()
                    .stroke(AppPalette.accent.opacity(0.18), lineWidth: 12)
                    .frame(width: 142, height: 142)
                Circle()
                    .fill(recorder.isRecording ? Color.red.opacity(0.88) : AppPalette.accent)
                    .frame(width: 104, height: 104)
                    .overlay {
                        Image(systemName: recorder.isRecording ? "stop.fill" : "mic.fill")
                            .font(.system(size: 34))
                            .foregroundStyle(.white)
                    }
                    .scaleEffect(recorder.isRecording ? 1.04 : 1)
                    .animation(.easeInOut(duration: 0.7).repeatForever(autoreverses: true), value: recorder.isRecording)
            }
            .onTapGesture {
                if recorder.isRecording {
                    let url = recorder.stop()
                    if let url { Task { await submit(url) } }
                } else {
                    Task { await recorder.start() }
                }
            }

            Text(recorder.isRecording ? time(recorder.elapsed) : store.localized("Tap to start recording", "点击开始录音"))
                .font(.headline.monospacedDigit())
            if task == nil {
                Label(store.localized("Preparing evaluation task…", "正在准备评测任务…"), systemImage: "hourglass")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if isSubmitting {
                VStack(spacing: 8) {
                    ProgressView()
                    Text(store.localized("AI is reviewing pronunciation, fluency and content.", "AI 正在评价发音、流利度与内容。"))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 18)
    }

    private func evaluationView(_ value: SpeakingEvaluation) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .firstTextBaseline) {
                Text("\(value.overallScore ?? answer?.score ?? 0)")
                    .font(.system(size: 54, weight: .bold, design: .rounded))
                    .foregroundStyle(AppPalette.accent)
                Text("/100").foregroundStyle(.secondary)
                Spacer()
                Image(systemName: "checkmark.seal.fill").font(.title).foregroundStyle(AppPalette.accent)
            }
            Text(value.summary ?? answer?.feedback ?? "").font(.body).lineSpacing(5)
            scoreRow("Pronunciation", value.pronunciationScore)
            scoreRow("Fluency", value.fluencyScore)
            scoreRow("Intonation", value.intonationScore)
            scoreRow("Relevance", value.relevanceScore)
            feedbackList(store.localized("Strengths", "表现较好"), value.strengths, "checkmark")
            feedbackList(store.localized("Next improvements", "提升方向"), value.improvements, "arrow.up.right")
            feedbackList(store.localized("Practice plan", "练习计划"), value.practicePlan, "figure.walk")
            Button(store.localized("Record again", "重新录音")) {
                answer = nil
                errorMessage = nil
            }
            .buttonStyle(.bordered)
        }
        .padding(18)
        .background(AppPalette.accent.opacity(0.09), in: RoundedRectangle(cornerRadius: 22))
    }

    private func scoreRow(_ title: String, _ score: Int?) -> some View {
        HStack {
            Text(title).font(.subheadline)
            Spacer()
            Text("\(score ?? 0)").font(.subheadline.bold().monospacedDigit())
        }
    }

    private func feedbackList(_ title: String, _ values: [String]?, _ icon: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.headline)
            ForEach(values ?? [], id: \.self) { text in
                Label(text, systemImage: icon).font(.subheadline)
            }
        }
    }

    private func prepareTask() async {
        guard task == nil else { return }
        do {
            task = try await APIClient.shared.createTask(
                prompt: content.lesson.passage.isEmpty ? content.sourceText : content.lesson.passage,
                voice: store.voice,
                difficulty: store.level.lowercased()
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func submit(_ url: URL) async {
        if task == nil { await prepareTask() }
        guard let task else {
            errorMessage = store.localized("The evaluation task could not be created.", "无法创建口语评测任务。")
            return
        }
        isSubmitting = true
        errorMessage = nil
        do {
            var response = try await APIClient.shared.uploadRecording(taskID: task.taskUuid, fileURL: url)
            for _ in 0..<30 where response.status != "COMPLETED" && response.status != "FAILED" {
                try await Task.sleep(for: .seconds(2))
                response = try await APIClient.shared.answer(response.answerUuid)
            }
            answer = response
            if response.status == "FAILED" {
                errorMessage = response.failureReason ?? store.localized("Evaluation failed.", "评测失败。")
            } else {
                progress.speakingScore = response.evaluation?.overallScore ?? response.score
            }
        } catch {
            errorMessage = error.localizedDescription
        }
        isSubmitting = false
    }

    private func time(_ seconds: Int) -> String {
        String(format: "%02d:%02d", seconds / 60, seconds % 60)
    }
}
