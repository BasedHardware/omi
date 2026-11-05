import AppIntents
import Foundation
import OmiCore
import OmiService

// Siri and Shortcuts actions, as in Flutter's `SiriIntegration/SiriIntents.swift`. They run in the
// app's process on the app's stores (`AppIntentsBridge`); asking and saving work without opening the app.

/// A string from `AppIntents.xcstrings` (what Siri says; the phrases are in `AppShortcuts.xcstrings`).
func siriText(_ key: String.LocalizationValue) -> LocalizedStringResource {
    LocalizedStringResource(key, table: "AppIntents")
}

/// Omi's answer, spoken. The whole answer also lands in the chat, as when asked in the app.
struct AskOmiIntent: AppIntent {
    static let title = LocalizedStringResource("Ask Omi", table: "AppIntents")
    static let description = IntentDescription(
        LocalizedStringResource("Ask Omi about your conversations, memories and tasks and hear the answer.", table: "AppIntents")
    )
    // Personal answers need an unlocked device, also from the Lock Screen.
    static let authenticationPolicy: IntentAuthenticationPolicy = .requiresAuthentication
    static let openAppWhenRun = false

    @Parameter(
        title: LocalizedStringResource("Question", table: "AppIntents"),
        requestValueDialog: IntentDialog(LocalizedStringResource("What would you like to ask Omi?", table: "AppIntents"))
    )
    var question: String

    init() {}

    init(question: String) {
        self.question = question
    }

    @MainActor
    func perform() async throws -> some IntentResult & ReturnsValue<String> & ProvidesDialog {
        let (answer, dialog) = try await Self.answer(question, limit: SiriText.spokenLimit)
        return .result(value: answer, dialog: dialog)
    }

    /// The answer and what Siri says; a question Omi could not answer waits in the chat instead.
    @MainActor
    static func answer(_ question: String, limit: Int) async throws -> (String, IntentDialog) {
        let catalog = try await AppIntentsBridge.catalog()
        switch await catalog.ask(question) {
        case let .answered(answer):
            let more = String(localized: siriText("Open Omi chat for the rest."))
            return (answer, IntentDialog("\(SiriText.spoken(answer, more: more, limit: limit))"))
        case .empty:
            return ("", IntentDialog(siriText("What would you like to ask Omi?")))
        case .useRemember:
            return ("", IntentDialog(siriText("To save that, say “Remember something in Omi”.")))
        case .busy:
            return ("", IntentDialog(siriText("Omi is still answering another question. Try again in a moment.")))
        case .failed:
            AppIntentsBridge.open(.chatDraft(SiriText.question(question)))
            return ("", IntentDialog(siriText("Omi couldn't answer right now. Your question is waiting in Omi's chat.")))
        }
    }
}

/// A short answer for Shortcuts ("what did I promise Anna?"), the same question Omi answers in chat.
struct SearchOmiIntent: AppIntent {
    static let title = LocalizedStringResource("Search Omi and answer", table: "AppIntents")
    static let description = IntentDescription(
        LocalizedStringResource("Search your conversations, memories and tasks and get a short answer.", table: "AppIntents")
    )
    static let authenticationPolicy: IntentAuthenticationPolicy = .requiresAuthentication
    static let openAppWhenRun = false

    @Parameter(
        title: LocalizedStringResource("Search", table: "AppIntents"),
        requestValueDialog: IntentDialog(LocalizedStringResource("What should Omi look for?", table: "AppIntents"))
    )
    var query: String

    @MainActor
    func perform() async throws -> some IntentResult & ReturnsValue<String> & ProvidesDialog {
        let (answer, dialog) = try await AskOmiIntent.answer(query, limit: SiriText.shortLimit)
        let more = String(localized: siriText("Open Omi chat for the rest."))
        return .result(value: SiriText.spoken(answer, more: more, limit: SiriText.shortLimit), dialog: dialog)
    }
}

struct OpenChatIntent: AppIntent {
    static let title = LocalizedStringResource("Open Omi chat", table: "AppIntents")
    static let description = IntentDescription(LocalizedStringResource("Open the chat with Omi.", table: "AppIntents"))
    static let openAppWhenRun = true

    @Parameter(title: LocalizedStringResource("Draft", table: "AppIntents"))
    var draft: String?

    @MainActor
    func perform() async throws -> some IntentResult {
        let text = draft?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        AppIntentsBridge.open(text.isEmpty ? .chat : .chatDraft(text))
        return .result()
    }
}

/// Flutter's "Remember in Omi": a private memory, saved without opening the app.
struct RememberIntent: AppIntent {
    static let title = LocalizedStringResource("Remember in Omi", table: "AppIntents")
    static let description = IntentDescription(LocalizedStringResource("Save a memory in Omi.", table: "AppIntents"))
    static let authenticationPolicy: IntentAuthenticationPolicy = .requiresLocalDeviceAuthentication
    static let openAppWhenRun = false

    @Parameter(
        title: LocalizedStringResource("Memory", table: "AppIntents"),
        requestValueDialog: IntentDialog(LocalizedStringResource("What should Omi remember?", table: "AppIntents"))
    )
    var content: String

    @MainActor
    func perform() async throws -> some IntentResult & ReturnsValue<MemoryEntity> & ProvidesDialog {
        let catalog = try await AppIntentsBridge.catalog()
        let memory: Memory
        do { memory = try await catalog.remember(content) } catch { throw IntentMessage(error) }
        return .result(value: MemoryEntity(memory), dialog: IntentDialog(siriText("Saved to Omi.")))
    }
}

struct CreateTaskIntent: AppIntent {
    static let title = LocalizedStringResource("Create an Omi task", table: "AppIntents")
    static let description = IntentDescription(
        LocalizedStringResource("Add a task to Omi, with a due date if you like.", table: "AppIntents")
    )
    static let authenticationPolicy: IntentAuthenticationPolicy = .requiresLocalDeviceAuthentication
    static let openAppWhenRun = false

    @Parameter(
        title: LocalizedStringResource("Task", table: "AppIntents"),
        requestValueDialog: IntentDialog(LocalizedStringResource("What's the task?", table: "AppIntents"))
    )
    var title: String

    @Parameter(title: LocalizedStringResource("Due", table: "AppIntents"))
    var dueDate: Date?

    @MainActor
    func perform() async throws -> some IntentResult & ReturnsValue<TaskEntity> & ProvidesDialog {
        let catalog = try await AppIntentsBridge.catalog()
        let task: ActionItem
        do { task = try await catalog.createTask(title, dueAt: dueDate) } catch { throw IntentMessage(error) }
        return .result(value: TaskEntity(task), dialog: IntentDialog(siriText("Added the task to Omi.")))
    }
}

struct CompleteTaskIntent: AppIntent {
    static let title = LocalizedStringResource("Complete an Omi task", table: "AppIntents")
    static let description = IntentDescription(LocalizedStringResource("Mark one of your Omi tasks as done.", table: "AppIntents"))
    static let authenticationPolicy: IntentAuthenticationPolicy = .requiresLocalDeviceAuthentication
    static let openAppWhenRun = false

    @Parameter(
        title: LocalizedStringResource("Task", table: "AppIntents"),
        requestValueDialog: IntentDialog(LocalizedStringResource("Which task is done?", table: "AppIntents"))
    )
    var task: TaskEntity

    @MainActor
    func perform() async throws -> some IntentResult & ReturnsValue<TaskEntity> & ProvidesDialog {
        let catalog = try await AppIntentsBridge.catalog()
        do { try await catalog.complete(taskID: task.id) } catch { throw IntentMessage(error) }
        let done = task
        done.isCompleted = true
        return .result(value: done, dialog: IntentDialog(siriText("Marked the task done in Omi.")))
    }
}

/// Records with the iPhone; opens Omi, since iOS only lets the microphone start in the foreground.
struct StartListeningIntent: AppIntent {
    static let title = LocalizedStringResource("Start listening with Omi", table: "AppIntents")
    static let description = IntentDescription(
        LocalizedStringResource("Start recording a conversation with your iPhone.", table: "AppIntents")
    )
    static let openAppWhenRun = true

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let capture = try await AppIntentsBridge.signedIn().capture
        if capture.isLive {
            if capture.source == .device { return .result(dialog: IntentDialog(siriText("Omi is already listening from your device."))) }
            if capture.isPaused { return .result(dialog: IntentDialog(siriText("Omi is paused. Open Omi to resume."))) }
            return .result(dialog: IntentDialog(siriText("Omi is listening.")))
        }
        await capture.startPhone()
        guard capture.isLive else {
            return .result(dialog: IntentDialog(siriText("Omi couldn't start listening. Check microphone access for Omi.")))
        }
        return .result(dialog: IntentDialog(siriText("Omi is listening.")))
    }
}

/// Stops the iPhone or Watch recording; with the Omi, ends its conversation (as a double tap does).
struct StopListeningIntent: AppIntent {
    static let title = LocalizedStringResource("Stop listening with Omi", table: "AppIntents")
    static let description = IntentDescription(
        LocalizedStringResource("Stop recording and save the conversation. With your Omi, start a new one.", table: "AppIntents")
    )
    static let openAppWhenRun = false

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let capture = try await AppIntentsBridge.signedIn().capture
        guard capture.isLive else { return .result(dialog: IntentDialog(siriText("Omi isn't listening right now."))) }
        if capture.source == .device {
            await capture.endDeviceConversation()
            return .result(dialog: IntentDialog(siriText("Omi saved the conversation and keeps listening.")))
        }
        await capture.stop()
        return .result(dialog: IntentDialog(siriText("Omi stopped listening.")))
    }
}
