import SwiftUI

struct TodayView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 24) {
                ScreenHeader(
                    eyebrow: store.localized("Listening Lab", "Listening Lab"),
                    title: store.localized("Your English session", "今日英语训练"),
                    subtitle: store.localized(
                        "Read it. Hear it. Explain it in your own words.",
                        "阅读、聆听，再用自己的话表达。"
                    )
                )

                if store.isLoading && store.dailyPlan == nil {
                    LoadingRows()
                } else if let message = store.errorMessage {
                    InlineError(message: message) { Task { await store.refresh() } }
                }

                if let plan = store.dailyPlan {
                    dailyCard(plan)
                } else if !store.isLoading {
                    emptyPlan
                }

                progressStrip

                if !store.topics.isEmpty {
                    VStack(alignment: .leading, spacing: 14) {
                        Text(store.localized("Continue exploring", "继续探索"))
                            .font(.title3.bold())
                        ForEach(store.topics.prefix(3)) { topic in
                            Button {
                                Task { await store.generate(topic: topic.title, category: topic.category) }
                            } label: {
                                HStack(alignment: .top, spacing: 14) {
                                    Image(systemName: topicIcon(topic.category))
                                        .font(.title3)
                                        .foregroundStyle(AppPalette.accent)
                                        .frame(width: 34)
                                    VStack(alignment: .leading, spacing: 5) {
                                        Text(topic.title).font(.headline).foregroundStyle(.primary)
                                        Text(topic.summary).font(.subheadline).foregroundStyle(.secondary).lineLimit(2)
                                    }
                                    Spacer()
                                }
                                .padding(.vertical, 8)
                            }
                            .buttonStyle(.plain)
                            Divider()
                        }
                    }
                }
            }
            .padding(.horizontal, 20)
            .padding(.top, 18)
            .padding(.bottom, 28)
        }
        .refreshable { await store.refresh() }
        .navigationBarTitleDisplayMode(.inline)
    }

    private func dailyCard(_ plan: DailyPlan) -> some View {
        Button(action: store.openToday) {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Text(plan.planDate)
                        .font(.caption.monospacedDigit().weight(.semibold))
                        .foregroundStyle(.secondary)
                    Spacer()
                    Label("\(plan.estimatedMinutes) min", systemImage: "clock")
                        .font(.caption.weight(.semibold))
                }
                Text(plan.content.title)
                    .font(.system(.title2, design: .rounded, weight: .bold))
                    .multilineTextAlignment(.leading)
                HStack(spacing: 18) {
                    step("headphones", store.localized("Listen", "听力"))
                    step("text.book.closed", store.localized("Read", "阅读"))
                    step("mic", store.localized("Speak", "口语"))
                }
                Label(
                    store.localized("Start today's learning", "开始今日学习"),
                    systemImage: "arrow.right.circle.fill"
                )
                .font(.headline)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 13)
                .background(AppPalette.accent, in: RoundedRectangle(cornerRadius: 15))
                .foregroundStyle(.white)
            }
            .padding(20)
            .foregroundStyle(.primary)
            .background(
                LinearGradient(
                    colors: [AppPalette.accent.opacity(0.18), AppPalette.accent.opacity(0.06)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                ),
                in: RoundedRectangle(cornerRadius: 26)
            )
            .overlay {
                RoundedRectangle(cornerRadius: 26)
                    .stroke(AppPalette.accent.opacity(0.22), lineWidth: 1)
            }
        }
        .buttonStyle(PressButtonStyle())
    }

    private func step(_ icon: String, _ label: String) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Image(systemName: icon).foregroundStyle(AppPalette.accent)
            Text(label).font(.caption.weight(.medium))
        }
    }

    private var progressStrip: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(store.localized("This week", "本周进度")).font(.title3.bold())
            HStack {
                metric("\(store.dashboard.listeningMinutes)", store.localized("minutes", "分钟"))
                Divider().frame(height: 38)
                metric("\(store.dashboard.completedLessons)", store.localized("lessons", "课程"))
                Divider().frame(height: 38)
                metric("\(store.dashboard.currentStreak)", store.localized("day streak", "连续天数"))
            }
        }
    }

    private func metric(_ value: String, _ label: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value).font(.title2.bold().monospacedDigit())
            Text(label).font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var emptyPlan: some View {
        VStack(alignment: .leading, spacing: 12) {
            Image(systemName: "sun.max").font(.largeTitle).foregroundStyle(AppPalette.accent)
            Text(store.localized("Today's lesson is being prepared.", "今日课程正在准备中。"))
                .font(.headline)
            Text(store.localized("Pull down to check again or choose a reading topic below.", "下拉刷新，或者从下方选择阅读主题。"))
                .foregroundStyle(.secondary)
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 24))
    }

    private func topicIcon(_ category: String) -> String {
        switch category.uppercased() {
        case "DATABASE": "cylinder.split.1x2"
        case "CLOUD", "CLOUD_NATIVE": "cloud"
        case "AI": "brain"
        case "SPORT": "figure.run"
        default: "server.rack"
        }
    }
}

struct ReadingView: View {
    @EnvironmentObject private var store: AppStore
    @State private var topic = ""
    @State private var category = "BACKEND"
    private let categories = ["BACKEND", "DATABASE", "CLOUD_NATIVE", "AI", "CULTURE"]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                ScreenHeader(
                    eyebrow: store.localized("Read", "阅读"),
                    title: store.localized("Reading center", "阅读训练"),
                    subtitle: store.localized(
                        "Choose a useful topic, then turn it into a focused English lesson.",
                        "选择一个实用主题，生成专注的英文课程。"
                    )
                )
                VStack(alignment: .leading, spacing: 10) {
                    Text(store.localized("Topic", "主题")).font(.headline)
                    TextField(
                        store.localized("e.g. Debugging a Redis latency spike", "例如：排查 Redis 延迟问题"),
                        text: $topic,
                        axis: .vertical
                    )
                    .lineLimit(3...6)
                    .textFieldStyle(.plain)
                    .padding(15)
                    .background(.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 16))
                }
                VStack(alignment: .leading, spacing: 12) {
                    Text(store.localized("Focus", "方向")).font(.headline)
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack {
                            ForEach(categories, id: \.self) { item in
                                Button(item.replacingOccurrences(of: "_", with: " ")) { category = item }
                                    .buttonStyle(FilterButtonStyle(selected: category == item))
                            }
                        }
                    }
                }
                Button {
                    Task {
                        await store.generate(
                            topic: topic.isEmpty ? "A practical \(category.lowercased()) lesson for a backend engineer" : topic,
                            category: category
                        )
                    }
                } label: {
                    Label(
                        store.isLoading ? store.localized("Preparing…", "正在准备…") : store.localized("Generate in the cloud", "在云端生成"),
                        systemImage: "sparkles"
                    )
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(store.isLoading)

                if let message = store.errorMessage { InlineError(message: message, retry: nil) }

                if !store.topics.isEmpty {
                    Text(store.localized("Recommended today", "今日推荐")).font(.title3.bold())
                    ForEach(store.topics) { item in
                        Button {
                            topic = item.title
                            category = item.category
                        } label: {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(item.category.replacingOccurrences(of: "_", with: " "))
                                    .font(.caption.weight(.bold))
                                    .foregroundStyle(AppPalette.accent)
                                Text(item.title).font(.headline).foregroundStyle(.primary)
                                Text(item.summary).font(.subheadline).foregroundStyle(.secondary).lineLimit(3)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.vertical, 8)
                        }
                        .buttonStyle(.plain)
                        Divider()
                    }
                }
            }
            .padding(20)
        }
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct PracticeView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                ScreenHeader(
                    eyebrow: store.localized("Speak", "口语"),
                    title: store.localized("Practice from context", "基于课程练口语"),
                    subtitle: store.localized(
                        "Open a completed lesson, listen first, then record a 60-second summary for AI feedback.",
                        "打开已完成课程，先听后录制 60 秒总结，获得 AI 反馈。"
                    )
                )
                if let latest = store.library.first(where: \.isReady) {
                    Button { store.open(latest) } label: {
                        VStack(alignment: .leading, spacing: 14) {
                            Image(systemName: "mic.and.signal.meter")
                                .font(.largeTitle)
                                .foregroundStyle(AppPalette.accent)
                            Text(store.localized("Recommended practice", "推荐练习"))
                                .font(.caption.bold())
                                .foregroundStyle(.secondary)
                            Text(latest.title).font(.title2.bold()).multilineTextAlignment(.leading)
                            Text(store.localized("Open lesson and record summary", "打开课程并录制总结"))
                                .font(.headline)
                                .foregroundStyle(AppPalette.accent)
                        }
                        .padding(20)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(AppPalette.accent.opacity(0.1), in: RoundedRectangle(cornerRadius: 25))
                        .foregroundStyle(.primary)
                    }
                    .buttonStyle(PressButtonStyle())
                } else {
                    InlineError(
                        message: store.localized("No ready lesson yet. Generate one in Read.", "还没有可练习课程，请先在“阅读”中生成。"),
                        retry: nil
                    )
                }
                Text(store.localized("Recent lessons", "最近课程")).font(.title3.bold())
                ForEach(store.library.filter(\.isReady).prefix(6)) { item in
                    Button { store.open(item) } label: { ContentRow(content: item) }
                        .buttonStyle(.plain)
                    Divider()
                }
            }
            .padding(20)
        }
    }
}

struct LibraryView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 18) {
                ScreenHeader(
                    eyebrow: store.localized("Archive", "内容"),
                    title: store.localized("Library", "课程库"),
                    subtitle: store.localized("Resume audio, reread transcripts and repeat speaking practice.", "继续播放、重读文本并重复口语练习。")
                )
                if store.isLoading && store.library.isEmpty { LoadingRows() }
                if store.library.isEmpty && !store.isLoading {
                    ContentUnavailableView(
                        store.localized("No lessons yet", "暂无课程"),
                        systemImage: "rectangle.stack.badge.plus",
                        description: Text(store.localized("Generate a lesson from the Read tab.", "请从“阅读”页面生成课程。"))
                    )
                }
                ForEach(store.library) { item in
                    Button { store.open(item) } label: { ContentRow(content: item) }
                        .buttonStyle(.plain)
                    Divider()
                }
            }
            .padding(20)
        }
        .refreshable { await store.refresh() }
    }
}

struct SettingsView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        Form {
            Section {
                Picker(store.localized("Language", "语言"), selection: $store.language) {
                    Text("English").tag("en")
                    Text("中文").tag("zh")
                }
                Picker(store.localized("Appearance", "主题"), selection: $store.theme) {
                    Text(store.localized("System", "跟随系统")).tag("system")
                    Text(store.localized("Light", "浅色")).tag("light")
                    Text(store.localized("Dark", "深色")).tag("dark")
                }
            } header: {
                Text(store.localized("Experience", "使用体验"))
            }
            Section {
                Picker(store.localized("English level", "英语等级"), selection: $store.level) {
                    ForEach(["A2", "B1", "B2", "C1"], id: \.self) { Text($0).tag($0) }
                }
                Picker(store.localized("Voice", "语音"), selection: $store.voice) {
                    Text("Ava · US").tag("en-US-AvaNeural")
                    Text("Andrew · US").tag("en-US-AndrewNeural")
                    Text("Sonia · UK").tag("en-GB-SoniaNeural")
                }
            } header: {
                Text(store.localized("Learning profile", "学习偏好"))
            } footer: {
                Text(store.localized("These preferences are used for new cloud-generated lessons.", "这些选项会应用于新生成的云端课程。"))
            }
            Section {
                LabeledContent(store.localized("API", "接口"), value: "api.zhchoice.xyz")
                LabeledContent(store.localized("Client ID", "客户端标识"), value: String(store.clientID.prefix(8)))
                LabeledContent(store.localized("App version", "版本"), value: "1.0.0")
            } header: {
                Text(store.localized("About", "关于"))
            }
        }
        .navigationTitle(store.localized("Settings", "设置"))
    }
}

struct PressButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .opacity(configuration.isPressed ? 0.88 : 1)
            .animation(.spring(response: 0.25, dampingFraction: 0.78), value: configuration.isPressed)
    }
}

struct FilterButtonStyle: ButtonStyle {
    let selected: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            .background(selected ? AppPalette.accent : Color.secondary.opacity(0.1), in: Capsule())
            .foregroundStyle(selected ? .white : .primary)
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
    }
}
