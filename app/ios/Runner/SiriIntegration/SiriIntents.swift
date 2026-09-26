import Foundation
import AppIntents

private func cleanedMemory(_ text: String) -> String {
    var result = text.trimmingCharacters(in: .whitespacesAndNewlines)
    if result.lowercased().hasPrefix("that ") { result = String(result.dropFirst(5)) }
    return result.trimmingCharacters(in: .whitespacesAndNewlines)
}

/// Schema intents must return an entity on success. A typed LocalizedError
/// gives Siri a truthful spoken failure instead of returning a fake entity.
struct SiriSpokenError: LocalizedError {
    let failure: SiriSession.Failure
    let action: String
    let serverAction: String
    init(_ error: Error, action: String, serverAction: String) {
        failure = (error as? SiriSession.Failure) ?? .server
        self.action = action
        self.serverAction = serverAction
    }
    var errorDescription: String? {
        switch failure {
        case .auth, .invalidConfiguration: "Open Omi and sign in first."
        case .network: "I couldn't reach Omi, so \(action)."
        case .quota: "Your Omi limit has been reached, so \(action)."
        case .rateLimited: "Omi is receiving too many requests. Try again shortly."
        case .server: "Omi couldn't \(serverAction) right now."
        }
    }
}

@available(iOS 26.0, *)
struct RememberIntent: AppIntent {
    static var title: LocalizedStringResource = "Remember in Omi"
    static var description = IntentDescription("Save a private memory in Omi.")
    static var authenticationPolicy: IntentAuthenticationPolicy = .requiresLocalDeviceAuthentication
    static var supportedModes: IntentModes = .background
    @Parameter(title: "What should Omi remember?") var content: String

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let started = Date()
        var outcome = "server"
        defer { SiriTelemetry.intent("remember", outcome: outcome, started: started) }
        let value = cleanedMemory(content)
        guard !value.isEmpty else { outcome = "cancelled"; return .result(dialog: "What should Omi remember?") }
        do {
            let response = try await OmiNativeAPI().request(method: "POST", path: "/v3/memories", body: [
                "content": value, "category": "manual", "visibility": "private", "tags": ["siri"]
            ])
            guard let id = response["id"] as? String, !id.isEmpty else { throw SiriSession.Failure.server }
            SiriBridge.shared.memoryCreated(id)
            outcome = "ok"
            return .result(dialog: "Saved to Omi")
        } catch SiriSession.Failure.auth { outcome = "auth"; return .result(dialog: "Open Omi and sign in first.") }
        catch SiriSession.Failure.network { outcome = "network"; return .result(dialog: "I couldn't reach Omi, so nothing was saved.") }
        catch SiriSession.Failure.quota { outcome = "quota"; return .result(dialog: "Your Omi limit has been reached, so nothing was saved.") }
        catch SiriSession.Failure.rateLimited { outcome = "rateLimited"; return .result(dialog: "Omi is receiving too many requests. Try again shortly.") }
        catch { return .result(dialog: "Omi couldn't save that right now.") }
    }
}

@available(iOS 27.0, *)
@AppIntent(schema: .notes.createNote)
struct OmiCreateNoteIntent {
    static var title: LocalizedStringResource = "Save a memory in Omi"
    static var authenticationPolicy: IntentAuthenticationPolicy = .requiresLocalDeviceAuthentication
    var name: String
    var content: AttributedString?
    var attachments: [IntentFile]
    var tags: [String]
    var isPinned: Bool
    var folder: OmiFolderEntity?
    init() {
        tags = []
        name = ""
        content = nil
        attachments = []
        isPinned = false
        folder = nil
    }
    func perform() async throws -> some ReturnsValue<ConversationEntity> & ProvidesDialog {
        let started = Date()
        do {
        let raw = content.map { String($0.characters) } ?? name
        let value = cleanedMemory(raw)
        guard !value.isEmpty, folder == nil || folder?.id == "memories" else { throw SiriSession.Failure.server }
        let response = try await OmiNativeAPI().request(method: "POST", path: "/v3/memories", body: [
            "content": value, "category": "manual", "visibility": "private", "tags": ["siri"]
        ])
        guard let id = response["id"] as? String, !id.isEmpty else { throw SiriSession.Failure.server }
        SiriBridge.shared.memoryCreated(id)
        SiriTelemetry.intent("createNote", outcome: "ok", started: started)
        return .result(value: ConversationEntity(memoryId: id, content: value, creationDate: Date()), dialog: "Saved to Omi")
        } catch {
            SiriTelemetry.intent("createNote", outcome: SiriTelemetry.outcome(error), started: started)
            throw SiriSpokenError(error, action: "the memory wasn't saved", serverAction: "save the memory")
        }
    }
}

@available(iOS 27.0, *)
@AppIntent(schema: .system.open)
struct OpenOmiIntent: OpenIntent {
    static var title: LocalizedStringResource = "Open in Omi"
    static var supportedModes: IntentModes = .foreground(.immediate)
    @Parameter(title: "Conversation") var target: ConversationEntity
    func perform() async throws -> some IntentResult {
        let started = Date()
        let kind = target.folder?.id == "memories" ? "memory" : "conversation"
        SiriBridge.shared.navigate("omi://\(kind)/\(target.id)")
        SiriTelemetry.intent("open", outcome: "ok", started: started)
        return .result()
    }
}

@available(iOS 27.0, *)
@AppIntent(schema: .system.open)
struct OpenOmiMemoryIntent: OpenIntent {
    static var title: LocalizedStringResource = "Open Omi memory"
    static var supportedModes: IntentModes = .foreground(.immediate)
    @Parameter(title: "Memory") var target: MemoryEntity
    func perform() async throws -> some IntentResult {
        let started = Date()
        SiriBridge.shared.navigate("omi://memory/\(target.id)")
        SiriTelemetry.intent("open", outcome: "ok", started: started)
        return .result()
    }
}

@available(iOS 27.0, *)
@AppIntent(schema: .system.open)
struct OpenOmiTaskIntent: OpenIntent {
    static var title: LocalizedStringResource = "Open Omi task"
    static var supportedModes: IntentModes = .foreground(.immediate)
    @Parameter(title: "Task") var target: TaskEntity
    func perform() async throws -> some IntentResult {
        let started = Date()
        SiriBridge.shared.navigate("omi://task/\(target.id)")
        SiriTelemetry.intent("open", outcome: "ok", started: started)
        return .result()
    }
}

@available(iOS 27.0, *)
@AppIntent(schema: .system.open)
struct OpenOmiFolderIntent: OpenIntent {
    static var title: LocalizedStringResource = "Open Omi folder"
    static var supportedModes: IntentModes = .foreground(.immediate)
    @Parameter(title: "Folder") var target: OmiFolderEntity
    func perform() async throws -> some IntentResult {
        let started = Date()
        SiriBridge.shared.navigate(target.id == "memories" ? "omi://memories" : "omi://conversations")
        SiriTelemetry.intent("open", outcome: "ok", started: started)
        return .result()
    }
}

@available(iOS 27.0, *)
@AppIntent(schema: .system.open)
struct OpenOmiListIntent: OpenIntent {
    static var title: LocalizedStringResource = "Open Omi task list"
    static var supportedModes: IntentModes = .foreground(.immediate)
    @Parameter(title: "List") var target: OmiListEntity
    func perform() async throws -> some IntentResult {
        let started = Date()
        SiriBridge.shared.navigate("omi://action-items")
        SiriTelemetry.intent("open", outcome: "ok", started: started)
        return .result()
    }
}

@available(iOS 27.0, *)
@AppIntent(schema: .system.searchInApp)
struct SearchOmiIntent: ShowInAppSearchResultsIntent {
    static var searchScopes: [StringSearchScope] = [.general]
    static var title: LocalizedStringResource = "Search in Omi"
    static var supportedModes: IntentModes = .foreground(.immediate)
    @Parameter(title: "Search") var criteria: StringSearchCriteria
    func perform() async throws -> some IntentResult {
        let started = Date()
        SiriBridge.shared.navigate("omi://search?q=\(criteria.term.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? "")")
        SiriTelemetry.intent("search", outcome: "ok", started: started)
        return .result()
    }
}

@available(iOS 27.0, *)
@AppIntent(schema: .reminders.updateReminder)
struct CompleteOmiTaskIntent {
    static var title: LocalizedStringResource = "Complete an Omi task"
    static var authenticationPolicy: IntentAuthenticationPolicy = .requiresLocalDeviceAuthentication
    var target: TaskEntity
    var title: String?
    var note: AttributedString?
    var tags: Set<String>?
    var urls: [URL]?
    var dueDate: DateComponents?
    var recurrence: Calendar.RecurrenceRule?
    var isCompleted: Bool?
    var isFlagged: Bool?
    var list: OmiListEntity?
    var locationTrigger: OmiLocationTriggerEntity?
    init() {
        target = TaskEntity(id: "", title: "", isCompleted: false,
                            creationDate: Date(), dueDate: nil, completionDate: nil)
        title = nil; note = nil; tags = nil; urls = nil; dueDate = nil
        recurrence = nil; isCompleted = nil; isFlagged = nil; list = nil
        locationTrigger = nil
    }
    func perform() async throws -> some ReturnsValue<TaskEntity> & ProvidesDialog {
        let started = Date()
        do {
        guard isCompleted == true, title == nil, note == nil, tags == nil, urls == nil,
              dueDate == nil, recurrence == nil, isFlagged == nil, list == nil, locationTrigger == nil
        else { throw SiriSession.Failure.server }
        let id = target.id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? target.id
        let response = try await OmiNativeAPI().request(method: "PATCH", path: "/v1/action-items/\(id)", body: ["completed": true])
        guard let returnedId = response["id"] as? String, returnedId == target.id else { throw SiriSession.Failure.server }
        SiriBridge.shared.taskChanged(target.id)
        let entity = TaskEntity(id: target.id, title: target.title, isCompleted: true,
                                creationDate: target.creationDate ?? Date(),
                                dueDate: target.dueDate.flatMap { Calendar.current.date(from: $0) },
                                completionDate: Date())
        SiriTelemetry.intent("completeTask", outcome: "ok", started: started)
        return .result(value: entity, dialog: "Marked the task done in Omi.")
        } catch {
            SiriTelemetry.intent("completeTask", outcome: SiriTelemetry.outcome(error), started: started)
            throw SiriSpokenError(error, action: "the task wasn't completed", serverAction: "complete the task")
        }
    }
}

@available(iOS 27.0, *)
@AppIntent(schema: .reminders.createReminder)
struct CreateOmiTaskIntent {
    static var title: LocalizedStringResource = "Create an Omi task"
    static var authenticationPolicy: IntentAuthenticationPolicy = .requiresLocalDeviceAuthentication
    var title: String
    var list: OmiListEntity?
    var note: AttributedString?
    var isFlagged: Bool?
    var images: [IntentFile]
    var tags: Set<String>
    var urls: [URL]
    var dueDate: DateComponents?
    var recurrence: Calendar.RecurrenceRule?
    var locationTrigger: OmiLocationTriggerEntity?
    var section: OmiSectionEntity?
    init() {
        title = ""; list = nil; note = nil; isFlagged = nil; images = []
        tags = []; urls = []; dueDate = nil; recurrence = nil
        locationTrigger = nil; section = nil
    }
    func perform() async throws -> some ReturnsValue<TaskEntity> & ProvidesDialog {
        let started = Date()
        do {
        let value = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty, list == nil || list?.id == "omi" else { throw SiriSession.Failure.server }
        var body: [String: Any] = ["description": value]
        if let due = dueDate.flatMap({ Calendar.current.date(from: $0) }) {
            body["due_at"] = ISO8601DateFormatter().string(from: due)
        }
        let response = try await OmiNativeAPI().request(method: "POST", path: "/v1/action-items", body: body)
        guard let id = response["id"] as? String, !id.isEmpty else { throw SiriSession.Failure.server }
        SiriBridge.shared.taskChanged(id)
        let entity = TaskEntity(id: id, title: value, isCompleted: false, creationDate: Date(),
                                dueDate: dueDate.flatMap { Calendar.current.date(from: $0) }, completionDate: nil)
        SiriTelemetry.intent("createTask", outcome: "ok", started: started)
        return .result(value: entity, dialog: "Added the task to Omi.")
        } catch {
            SiriTelemetry.intent("createTask", outcome: SiriTelemetry.outcome(error), started: started)
            throw SiriSpokenError(error, action: "the task wasn't created", serverAction: "create the task")
        }
    }
}

@available(iOS 26.0, *)
struct StartOmiListeningIntent: AppIntent {
    static var title: LocalizedStringResource = "Start listening with Omi"
    static var supportedModes: IntentModes = .foreground(.dynamic)
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let started = Date()
        do {
            try await SiriBridge.shared.setListening(true)
            SiriTelemetry.intent("startListening", outcome: "ok", started: started)
            return .result(dialog: "Omi is listening.")
        } catch {
            SiriTelemetry.intent("startListening", outcome: SiriTelemetry.outcome(error), started: started)
            return .result(dialog: "Open Omi to start listening.")
        }
    }
}

@available(iOS 26.0, *)
struct StopOmiListeningIntent: AppIntent {
    static var title: LocalizedStringResource = "Stop listening with Omi"
    static var supportedModes: IntentModes = .foreground(.dynamic)
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let started = Date()
        do {
            try await SiriBridge.shared.setListening(false)
            SiriTelemetry.intent("stopListening", outcome: "ok", started: started)
            return .result(dialog: "Omi stopped listening.")
        } catch {
            SiriTelemetry.intent("stopListening", outcome: SiriTelemetry.outcome(error), started: started)
            return .result(dialog: "Open Omi to stop listening.")
        }
    }
}

/// UI donations carry only an opaque ID; no memory text, task title or transcript.
@available(iOS 26.0, *)
struct OmiUiActivityIntent: AppIntent {
    static var title: LocalizedStringResource = "Continue in Omi"
    static var supportedModes: IntentModes = .foreground(.immediate)
    @Parameter(title: "Item type") var kind: String
    @Parameter(title: "Item ID") var id: String

    func perform() async throws -> some IntentResult {
        guard ["conversation", "memory", "task"].contains(kind), !id.isEmpty else {
            throw SiriSession.Failure.server
        }
        let route = kind == "conversation" ? "omi://conversation/\(id)" :
            (kind == "memory" ? "omi://memory/\(id)" : "omi://task/\(id)")
        SiriBridge.shared.navigate(route)
        return .result()
    }
}

@available(iOS 26.0, *)
struct OmiAppShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: RememberIntent(), phrases: [
            "Remember something in \(.applicationName)",
            "Tell \(.applicationName) to remember",
            "Add a memory to \(.applicationName)"
        ], shortTitle: "Remember", systemImageName: "brain.head.profile")
        AppShortcut(intent: StartOmiListeningIntent(), phrases: ["Start listening with \(.applicationName)"],
                    shortTitle: "Start listening", systemImageName: "waveform")
        AppShortcut(intent: StopOmiListeningIntent(), phrases: ["Stop \(.applicationName)"],
                    shortTitle: "Stop listening", systemImageName: "stop.fill")
    }
}
