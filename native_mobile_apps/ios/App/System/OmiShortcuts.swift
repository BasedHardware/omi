import AppIntents
import Foundation
import OmiCore

// "Open" for each entity: Siri and Shortcuts use them, and a tap on an Omi item in Spotlight runs the
// one for its type. They route through the deep-link router like a notification tap.

struct OpenConversationIntent: OpenIntent {
    static let title = LocalizedStringResource("Open conversation", table: "AppIntents")
    @Parameter(title: LocalizedStringResource("Conversation", table: "AppIntents")) var target: ConversationEntity

    @MainActor
    func perform() async throws -> some IntentResult {
        AppIntentsBridge.open(.conversation(id: target.id))
        return .result()
    }
}

struct OpenTaskIntent: OpenIntent {
    static let title = LocalizedStringResource("Open task", table: "AppIntents")
    @Parameter(title: LocalizedStringResource("Task", table: "AppIntents")) var target: TaskEntity

    @MainActor
    func perform() async throws -> some IntentResult {
        AppIntentsBridge.open(.task(id: target.id))
        return .result()
    }
}

struct OpenMemoryIntent: OpenIntent {
    static let title = LocalizedStringResource("Open memory", table: "AppIntents")
    @Parameter(title: LocalizedStringResource("Memory", table: "AppIntents")) var target: MemoryEntity

    @MainActor
    func perform() async throws -> some IntentResult {
        AppIntentsBridge.open(.memory(id: target.id))
        return .result()
    }
}

struct OpenFolderIntent: OpenIntent {
    static let title = LocalizedStringResource("Open folder", table: "AppIntents")
    @Parameter(title: LocalizedStringResource("Folder", table: "AppIntents")) var target: FolderEntity

    @MainActor
    func perform() async throws -> some IntentResult {
        AppIntentsBridge.open(.folder(id: target.id))
        return .result()
    }
}

/// The phrases Siri knows without setup (German in `AppShortcuts.xcstrings`). Every phrase names
/// the app; iOS allows ten shortcuts.
struct OmiShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: AskOmiIntent(), phrases: [
            "Ask \(.applicationName)",
            "Ask \(.applicationName) a question",
            "Question for \(.applicationName)",
            "I have a question for \(.applicationName)",
        ], shortTitle: LocalizedStringResource("Ask Omi", table: "AppIntents"), systemImageName: "bubble.left.and.text.bubble.right")
        AppShortcut(intent: SearchOmiIntent(), phrases: [
            "Search \(.applicationName)",
            "Search in \(.applicationName)",
        ], shortTitle: LocalizedStringResource("Search and answer", table: "AppIntents"), systemImageName: "magnifyingglass")
        AppShortcut(intent: OpenChatIntent(), phrases: [
            "Open \(.applicationName) chat",
            "Open chat in \(.applicationName)",
        ], shortTitle: LocalizedStringResource("Open chat", table: "AppIntents"), systemImageName: "bubble.left.and.bubble.right")
        AppShortcut(intent: RememberIntent(), phrases: [
            "Remember something in \(.applicationName)",
            "Tell \(.applicationName) to remember",
            "Add a memory to \(.applicationName)",
        ], shortTitle: LocalizedStringResource("Remember", table: "AppIntents"), systemImageName: "brain.head.profile")
        AppShortcut(intent: CreateTaskIntent(), phrases: [
            "Add a task to \(.applicationName)",
            "Create a task in \(.applicationName)",
        ], shortTitle: LocalizedStringResource("Create task", table: "AppIntents"), systemImageName: "plus.circle")
        AppShortcut(intent: CompleteTaskIntent(), phrases: [
            "Complete a task in \(.applicationName)",
            "Mark a task done in \(.applicationName)",
        ], shortTitle: LocalizedStringResource("Complete task", table: "AppIntents"), systemImageName: "checkmark.circle")
        AppShortcut(intent: OpenConversationIntent(), phrases: [
            "Open a conversation in \(.applicationName)",
            "Show my \(.applicationName) conversations",
        ], shortTitle: LocalizedStringResource("Open conversation", table: "AppIntents"), systemImageName: "text.bubble")
        AppShortcut(intent: StartListeningIntent(), phrases: [
            "Start listening with \(.applicationName)",
            "Start recording with \(.applicationName)",
        ], shortTitle: LocalizedStringResource("Start listening", table: "AppIntents"), systemImageName: "waveform")
        AppShortcut(intent: StopListeningIntent(), phrases: [
            "Stop \(.applicationName)",
            "Stop listening with \(.applicationName)",
        ], shortTitle: LocalizedStringResource("Stop listening", table: "AppIntents"), systemImageName: "stop.fill")
    }
}
