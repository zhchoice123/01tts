import SwiftUI

struct RootView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        TabView(selection: $store.tab) {
            NavigationStack { TodayView() }
                .tabItem { Label(store.localized("Today", "今日"), systemImage: "house") }
                .tag(AppStore.Tab.today)
            NavigationStack { ReadingView() }
                .tabItem { Label(store.localized("Read", "阅读"), systemImage: "book.pages") }
                .tag(AppStore.Tab.read)
            NavigationStack { PracticeView() }
                .tabItem { Label(store.localized("Practice", "练习"), systemImage: "mic") }
                .tag(AppStore.Tab.practice)
            NavigationStack { LibraryView() }
                .tabItem { Label(store.localized("Library", "课程库"), systemImage: "rectangle.stack") }
                .tag(AppStore.Tab.library)
            NavigationStack { SettingsView() }
                .tabItem { Label(store.localized("Settings", "设置"), systemImage: "gearshape") }
                .tag(AppStore.Tab.settings)
        }
        .task { await store.bootstrap() }
        .sheet(item: $store.selectedContent) { content in
            NavigationStack { LessonView(content: content) }
        }
        .alert(
            store.localized("Notice", "提示"),
            isPresented: Binding(
                get: { store.generationMessage != nil },
                set: { if !$0 { store.generationMessage = nil } }
            )
        ) {
            Button("OK") { store.generationMessage = nil }
        } message: {
            Text(store.generationMessage ?? "")
        }
    }
}

struct ScreenHeader: View {
    let eyebrow: String
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(eyebrow.uppercased())
                .font(.caption.weight(.semibold))
                .tracking(1.6)
                .foregroundStyle(AppPalette.accent)
            Text(title)
                .font(.system(.largeTitle, design: .rounded, weight: .bold))
                .foregroundStyle(.primary)
            Text(subtitle)
                .font(.body)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct InlineError: View {
    let message: String
    let retry: (() -> Void)?

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            VStack(alignment: .leading, spacing: 8) {
                Text(message).font(.subheadline)
                if let retry {
                    Button("Try again", action: retry)
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                }
            }
            Spacer()
        }
        .padding(16)
        .background(.orange.opacity(0.09), in: RoundedRectangle(cornerRadius: 18))
    }
}

struct LoadingRows: View {
    var body: some View {
        VStack(spacing: 12) {
            ForEach(0..<3, id: \.self) { index in
                RoundedRectangle(cornerRadius: 18)
                    .fill(.secondary.opacity(0.12))
                    .frame(height: index == 0 ? 150 : 86)
                    .overlay(alignment: .leading) {
                        VStack(alignment: .leading, spacing: 9) {
                            Capsule().fill(.secondary.opacity(0.14)).frame(width: 96, height: 10)
                            Capsule().fill(.secondary.opacity(0.14)).frame(width: 210, height: 14)
                        }
                        .padding()
                    }
            }
        }
        .redacted(reason: .placeholder)
    }
}

struct ContentRow: View {
    let content: ContentItem

    var body: some View {
        HStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 15)
                    .fill(content.isReady ? AppPalette.accent.opacity(0.13) : Color.secondary.opacity(0.1))
                    .frame(width: 54, height: 54)
                Image(systemName: content.sourceType.contains("DIALOGUE") ? "person.2.wave.2" : "waveform")
                    .foregroundStyle(content.isReady ? AppPalette.accent : .secondary)
            }
            VStack(alignment: .leading, spacing: 5) {
                Text(content.title).font(.headline).lineLimit(2)
                HStack(spacing: 6) {
                    Text(content.category ?? content.sourceType)
                    Text("·")
                    Text(content.level)
                    if let minutes = content.estimatedMinutes {
                        Text("· \(minutes) min")
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            Spacer()
            if content.isReady {
                Image(systemName: "chevron.right").foregroundStyle(.tertiary)
            } else {
                ProgressView().controlSize(.small)
            }
        }
        .contentShape(Rectangle())
    }
}
