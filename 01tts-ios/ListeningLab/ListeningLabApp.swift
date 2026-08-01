import SwiftUI

@main
struct ListeningLabApp: App {
    @StateObject private var store = AppStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .preferredColorScheme(store.colorScheme)
                .tint(AppPalette.accent)
        }
    }
}

enum AppPalette {
    static let accent = Color(red: 0.16, green: 0.52, blue: 0.47)
    static let ink = Color(red: 0.09, green: 0.13, blue: 0.15)
    static let host = Color(red: 0.14, green: 0.47, blue: 0.58)
    static let expert = Color(red: 0.67, green: 0.38, blue: 0.25)
}
