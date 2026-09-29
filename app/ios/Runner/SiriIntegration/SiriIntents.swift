#if compiler(>=6.4)
import Foundation
import AppIntents

private func cleanedMemory(_ text: String) -> String {
    var result = text.trimmingCharacters(in: .whitespacesAndNewlines)
    if result.lowercased().hasPrefix("that ") { result = String(result.dropFirst(5)) }
    return result.trimmingCharacters(in: .whitespacesAndNewlines)
}

func cleanedSiriQuestion(_ text: String) -> String {
    var result = text.trimmingCharacters(in: .whitespacesAndNewlines)
    let prefixes = ["ask omi about ", "ask omi ", "ask about ", "ask "]
    if let prefix = prefixes.first(where: { result.lowercased().hasPrefix($0) }) {
        result = String(result.dropFirst(prefix.count)).trimmingCharacters(in: .whitespacesAndNewlines)
    }
    return result
}

private func requireSignedInSiriSession() throws {
    guard let config = SiriSession.shared.currentConfig() else { throw SiriSession.Failure.auth }
    try SiriSession.shared.validateOwner(config)
}

private func persistConfirmedWrite(owner: SiriSession.Config,
                                   _ operation: () async throws -> Void) async {
    do { try await operation() }
    catch {
        NSLog("[SiriIndex] Backend write confirmed; local snapshot repair scheduled")
        SiriTelemetry.index(outcome: "server", started: Date(), count: 0)
        SiriSnapshotStore.shared.scheduleConfirmedRepair(owner: owner)
    }
}

private func saveSiriMemory(_ value: String, owner: SiriSession.Config) async throws {
    let response = try await OmiNativeAPI().request(method: "POST", path: "/v3/memories", body: [
        "content": value, "category": "manual", "visibility": "private", "tags": ["siri"]
    ], owner: owner)
    guard let id = response["id"] as? String, !id.isEmpty else { throw SiriSession.Failure.server }
    await persistConfirmedWrite(owner: owner) {
        try await SiriSnapshotStore.shared.applyConfirmedMemory(
            id: id, content: response["content"] as? String ?? value, owner: owner)
    }
    SiriBridge.shared.memoryCreated(id)
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

private struct SiriUnsupportedInput: LocalizedError {
    enum Kind { case note, createTask, completeTask, open }
    let kind: Kind
    var errorDescription: String? {
        switch kind {
        case .note: "Omi can only save note text to Memories."
        case .createTask: "Omi can only create tasks with a title, due date, and the Omi list."
        case .completeTask: "Omi can only change task completion through Siri."
        case .open: "That item is no longer available in Omi."
        }
    }
}

@available(iOS 16.0, *)
struct RememberIntent: AppIntent {
    static var title: LocalizedStringResource = "Remember in Omi"
    static var description = IntentDescription("Save a private memory in Omi.")
    static var authenticationPolicy: IntentAuthenticationPolicy = .requiresLocalDeviceAuthentication
    static var openAppWhenRun: Bool = false
    @Parameter(title: "What should Omi remember?") var content: String

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let started = Date()
        var outcome = "server"
        defer { SiriTelemetry.intent("remember", outcome: outcome, started: started) }
        let value = cleanedMemory(content)
        guard !value.isEmpty else { outcome = "cancelled"; return .result(dialog: "What should Omi remember?") }
        do {
            guard let owner = SiriSession.shared.currentConfig() else { throw SiriSession.Failure.auth }
            try await saveSiriMemory(value, owner: owner)
            outcome = "ok"
            return .result(dialog: "Saved to Omi")
        } catch SiriSession.Failure.auth { outcome = "auth"; return .result(dialog: "Open Omi and sign in first.") }
        catch SiriSession.Failure.network { outcome = "network"; return .result(dialog: "I couldn't reach Omi, so nothing was saved.") }
        catch SiriSession.Failure.quota { outcome = "quota"; return .result(dialog: "Your Omi limit has been reached, so nothing was saved.") }
        catch SiriSession.Failure.rateLimited { outcome = "rateLimited"; return .result(dialog: "Omi is receiving too many requests. Try again shortly.") }
        catch { return .result(dialog: "Omi couldn't save that right now.") }
    }
}

/// This navigation helper is an output of AskOmiIntent and an app-internal
/// fallback. Keeping it out of discovery prevents Siri from treating its
/// optional draft as the primary one-breath question surface.
@available(iOS 16.0, *)
struct OpenOmiChatIntent: AppIntent {
    static var title: LocalizedStringResource = "Open Omi chat"
    static var description = IntentDescription("Open Omi's chat without asking a new question.")
    static var isDiscoverable = false
    static var openAppWhenRun = true
    @Parameter(title: "Draft") var draft: String?
    @Parameter(title: "Owner") var ownerUID: String?
    @Parameter(title: "Owner generation") var ownerGeneration: String?

    static func route(draft: String?) throws -> String {
        guard let draft else { return "omi://chat" }
        var components = URLComponents()
        components.scheme = "omi"
        components.host = "chat"
        components.queryItems = [URLQueryItem(name: "draft", value: draft)]
        // URLComponents leaves a literal plus in a query value. Dart treats it
        // as a space, so encode it explicitly after URLQueryItem escapes the
        // other reserved characters.
        components.percentEncodedQuery = components.percentEncodedQuery?
            .replacingOccurrences(of: "+", with: "%2B")
        guard let route = components.string else { throw SiriSession.Failure.invalidConfiguration }
        return route
    }

    func perform() async throws -> some IntentResult {
        let started = Date()
        var outcome = "server"
        defer { SiriTelemetry.intent("openChat", outcome: outcome, started: started) }
        guard let config = SiriSession.shared.currentConfig(),
              ownerUID == nil || config.uid == ownerUID,
              ownerGeneration == nil || String(config.generation ?? 0) == ownerGeneration
        else {
            outcome = "auth"
            throw SiriSession.Failure.auth
        }
        try SiriSession.shared.validateOwner(config)
        let question = cleanedSiriQuestion(draft ?? "")
        guard !question.isEmpty else {
            SiriBridge.shared.navigate(try Self.route(draft: nil))
            outcome = "ok"
            return .result()
        }
        do {
            _ = try await OmiNativeAPI().ask(question: question, owner: config)
            SiriBridge.shared.navigate(try Self.route(draft: nil))
            outcome = "ok"
        } catch SiriSession.Failure.auth {
            outcome = "auth"
            throw SiriSession.Failure.auth
        } catch {
            outcome = SiriTelemetry.outcome(error)
            // Preserve the cleaned question when the one automatic send fails.
            SiriBridge.shared.navigate(try Self.route(draft: question))
        }
        return .result()
    }
}

@available(iOS 16.0, *)
struct AskOmiIntent: AppIntent {
    static var title: LocalizedStringResource = "Ask Omi"
    static var description = IntentDescription(
        "Ask Omi a question about your conversations, memories, and tasks and get a spoken answer."
    )
    static var authenticationPolicy: IntentAuthenticationPolicy = .requiresLocalDeviceAuthentication
    static var openAppWhenRun = false
    static var parameterSummary: some ParameterSummary {
        Summary("Ask Omi \(\.$question)")
    }
    @Parameter(
        title: "Question",
        description: "A question for Omi to answer from your conversations, memories, and tasks.",
        requestValueDialog: "What would you like to ask Omi?"
    )
    var question: String

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let started = Date()
        var outcome = "server"
        defer { SiriTelemetry.intent("askOmi", outcome: outcome, started: started) }
        let value = cleanedSiriQuestion(question)
        let openChat = OpenOmiChatIntent()
        guard !value.isEmpty else {
            outcome = "cancelled"
            return .result(opensIntent: openChat, dialog: "What would you like to ask Omi?")
        }
        let lower = value.lowercased()
        let memoryPrefix = lower.hasPrefix("to remember ") ? "to remember " :
            (lower.hasPrefix("remember ") ? "remember " : "")
        do {
            guard let owner = SiriSession.shared.currentConfig() else { throw SiriSession.Failure.auth }
            try SiriSession.shared.validateOwner(owner)
            openChat.ownerUID = owner.uid
            openChat.ownerGeneration = String(owner.generation ?? 0)
            // Only the exact imperative is delegated to Remember; other questions
            // containing "remember" remain chat questions.
            if !memoryPrefix.isEmpty {
                let memory = cleanedMemory(String(value.dropFirst(memoryPrefix.count)))
                guard !memory.isEmpty else {
                    outcome = "cancelled"
                    return .result(opensIntent: openChat, dialog: "What should Omi remember?")
                }
                try await saveSiriMemory(memory, owner: owner)
                outcome = "ok"
                return .result(opensIntent: openChat, dialog: "Saved to Omi")
            }
            let answer = try await OmiNativeAPI().ask(question: value, owner: owner)
            outcome = "ok"
            return .result(opensIntent: openChat,
                           dialog: IntentDialog("\(Self.spokenAnswer(answer)) Open Omi to continue."))
        } catch SiriSession.Failure.auth {
            outcome = "auth"
            return .result(opensIntent: openChat, dialog: "Open Omi and sign in first.")
        } catch SiriSession.Failure.network {
            outcome = "network"
            if !memoryPrefix.isEmpty {
                return .result(opensIntent: openChat, dialog: "I couldn't reach Omi, so nothing was saved.")
            }
            openChat.draft = value
            return .result(opensIntent: openChat,
                           dialog: "Omi couldn't finish the answer here. Open Omi to ask in chat.")
        } catch {
            outcome = SiriTelemetry.outcome(error)
            if !memoryPrefix.isEmpty {
                return .result(opensIntent: openChat, dialog: "Omi couldn't save that right now.")
            }
            openChat.draft = value
            return .result(opensIntent: openChat, dialog: "Omi couldn't answer right now. Open Omi and try again.")
        }
    }

    static func spokenAnswer(_ answer: String) -> String {
        let trimmed = answer.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count > 450 else { return trimmed }
        return String(trimmed.prefix(447)) + "…"
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
        guard !value.isEmpty, folder == nil || folder?.id == "memories",
              attachments.isEmpty, tags.isEmpty, !isPinned else {
            throw SiriUnsupportedInput(kind: .note)
        }
        guard let owner = SiriSession.shared.currentConfig() else { throw SiriSession.Failure.auth }
        let response = try await OmiNativeAPI().request(method: "POST", path: "/v3/memories", body: [
            "content": value, "category": "manual", "visibility": "private", "tags": ["siri"]
        ], owner: owner)
        guard let id = response["id"] as? String, !id.isEmpty else { throw SiriSession.Failure.server }
        await persistConfirmedWrite(owner: owner) {
            try await SiriSnapshotStore.shared.applyConfirmedMemory(
                id: id, content: response["content"] as? String ?? value, owner: owner)
        }
        SiriBridge.shared.memoryCreated(id)
        SiriTelemetry.intent("createNote", outcome: "ok", started: started)
        return .result(value: ConversationEntity(memoryId: id, content: value, creationDate: Date()), dialog: "Saved to Omi")
        } catch {
            SiriTelemetry.intent("createNote", outcome: SiriTelemetry.outcome(error), started: started)
            if let unsupported = error as? SiriUnsupportedInput { throw unsupported }
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
        guard SiriSnapshotStore.shared.containsCurrentEntity(type: kind, id: target.id) else {
            throw SiriUnsupportedInput(kind: .open)
        }
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
        guard SiriSnapshotStore.shared.containsCurrentEntity(type: "memory", id: target.id) else {
            throw SiriUnsupportedInput(kind: .open)
        }
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
        guard SiriSnapshotStore.shared.containsCurrentEntity(type: "task", id: target.id) else {
            throw SiriUnsupportedInput(kind: .open)
        }
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
        try requireSignedInSiriSession()
        guard target.id == "memories" || target.id == "conversations" else {
            throw SiriUnsupportedInput(kind: .open)
        }
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
        try requireSignedInSiriSession()
        guard target.id == "omi" else { throw SiriUnsupportedInput(kind: .open) }
        SiriBridge.shared.navigate("omi://action-items")
        SiriTelemetry.intent("open", outcome: "ok", started: started)
        return .result()
    }
}

@available(iOS 27.0, *)
@AppIntent(schema: .system.searchInApp)
struct SearchOmiIntent: ShowInAppSearchResultsIntent {
    static var searchScopes: [StringSearchScope] = [.general]
    static var title: LocalizedStringResource = "Search Omi and answer"
    static var authenticationPolicy: IntentAuthenticationPolicy = .requiresLocalDeviceAuthentication
    @Parameter(title: "Search") var criteria: StringSearchCriteria
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let ask = AskOmiIntent()
        ask.question = criteria.term
        return try await ask.perform()
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
        else { throw SiriUnsupportedInput(kind: .completeTask) }
        let id = target.id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? target.id
        guard let owner = SiriSession.shared.currentConfig() else { throw SiriSession.Failure.auth }
        let response = try await OmiNativeAPI().request(method: "PATCH", path: "/v1/action-items/\(id)",
            body: ["completed": true], owner: owner)
        guard let returnedId = response["id"] as? String, returnedId == target.id else { throw SiriSession.Failure.server }
        await persistConfirmedWrite(owner: owner) {
            try await SiriSnapshotStore.shared.applyConfirmedTask(id: target.id,
                title: response["description"] as? String ?? target.title,
                completed: true, dueAt: target.dueDate.flatMap { Calendar.current.date(from: $0) }, owner: owner)
        }
        SiriBridge.shared.taskChanged(target.id)
        let entity = TaskEntity(id: target.id, title: target.title, isCompleted: true,
                                creationDate: target.creationDate ?? Date(),
                                dueDate: target.dueDate.flatMap { Calendar.current.date(from: $0) },
                                completionDate: Date())
        SiriTelemetry.intent("completeTask", outcome: "ok", started: started)
        return .result(value: entity, dialog: "Marked the task done in Omi.")
        } catch {
            SiriTelemetry.intent("completeTask", outcome: SiriTelemetry.outcome(error), started: started)
            if let unsupported = error as? SiriUnsupportedInput { throw unsupported }
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
        guard !value.isEmpty, list == nil || list?.id == "omi",
              note.map({ String($0.characters).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) ?? true,
              isFlagged != true, images.isEmpty, tags.isEmpty, urls.isEmpty,
              recurrence == nil, locationTrigger == nil, section == nil else {
            throw SiriUnsupportedInput(kind: .createTask)
        }
        let due = dueDate.flatMap { Calendar.current.date(from: $0) }
        guard dueDate == nil || due != nil else { throw SiriUnsupportedInput(kind: .createTask) }
        var body: [String: Any] = ["description": value]
        if let due {
            body["due_at"] = ISO8601DateFormatter().string(from: due)
        }
        guard let owner = SiriSession.shared.currentConfig() else { throw SiriSession.Failure.auth }
        let response = try await OmiNativeAPI().request(method: "POST", path: "/v1/action-items",
            body: body, owner: owner)
        guard let id = response["id"] as? String, !id.isEmpty else { throw SiriSession.Failure.server }
        await persistConfirmedWrite(owner: owner) {
            try await SiriSnapshotStore.shared.applyConfirmedTask(id: id,
                title: response["description"] as? String ?? value,
                completed: false, dueAt: due, owner: owner)
        }
        SiriBridge.shared.taskChanged(id)
        let entity = TaskEntity(id: id, title: value, isCompleted: false, creationDate: Date(),
                                dueDate: due, completionDate: nil)
        SiriTelemetry.intent("createTask", outcome: "ok", started: started)
        return .result(value: entity, dialog: "Added the task to Omi.")
        } catch {
            SiriTelemetry.intent("createTask", outcome: SiriTelemetry.outcome(error), started: started)
            if let unsupported = error as? SiriUnsupportedInput { throw unsupported }
            throw SiriSpokenError(error, action: "the task wasn't created", serverAction: "create the task")
        }
    }
}

@available(iOS 16.0, *)
struct StartOmiListeningIntent: AppIntent {
    static var title: LocalizedStringResource = "Start listening with Omi"
    static var openAppWhenRun: Bool = true
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let started = Date()
        do {
            try requireSignedInSiriSession()
            try await SiriBridge.shared.setListening(true)
            SiriTelemetry.intent("startListening", outcome: "ok", started: started)
            return .result(dialog: "Omi is listening.")
        } catch SiriListeningFailure.deviceAlreadyListening {
            SiriTelemetry.intent("startListening", outcome: "ok", started: started)
            return .result(dialog: "Omi is already listening from your device.")
        } catch let failure as SiriListeningFailure {
            SiriTelemetry.intent("startListening", outcome: SiriTelemetry.outcome(failure), started: started)
            return .result(dialog: IntentDialog("\(failure.spokenDialog(starting: true))"))
        } catch SiriSession.Failure.auth {
            SiriTelemetry.intent("startListening", outcome: "auth", started: started)
            return .result(dialog: "Open Omi and sign in first.")
        } catch {
            SiriTelemetry.intent("startListening", outcome: SiriTelemetry.outcome(error), started: started)
            return .result(dialog: "Open Omi to start listening.")
        }
    }
}

@available(iOS 16.0, *)
struct StopOmiListeningIntent: AppIntent {
    static var title: LocalizedStringResource = "Stop listening with Omi"
    static var openAppWhenRun: Bool = true
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let started = Date()
        do {
            try requireSignedInSiriSession()
            try await SiriBridge.shared.setListening(false)
            SiriTelemetry.intent("stopListening", outcome: "ok", started: started)
            return .result(dialog: "Omi stopped listening.")
        } catch let failure as SiriListeningFailure {
            SiriTelemetry.intent("stopListening", outcome: SiriTelemetry.outcome(failure), started: started)
            return .result(dialog: IntentDialog("\(failure.spokenDialog(starting: false))"))
        } catch SiriSession.Failure.auth {
            SiriTelemetry.intent("stopListening", outcome: "auth", started: started)
            return .result(dialog: "Open Omi and sign in first.")
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
        guard SiriSnapshotStore.shared.containsCurrentEntity(type: kind, id: id) else {
            throw SiriUnsupportedInput(kind: .open)
        }
        let route = kind == "conversation" ? "omi://conversation/\(id)" :
            (kind == "memory" ? "omi://memory/\(id)" : "omi://task/\(id)")
        SiriBridge.shared.navigate(route)
        return .result()
    }
}

@available(iOS 16.0, *)
struct OmiAppShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: AskOmiIntent(), phrases: [
            "Ask \(.applicationName)",
            "Ask \(.applicationName) a question",
            "Ask a question in \(.applicationName)",
            "Ask \(.applicationName) something",
            "I have a question for \(.applicationName)",
            "Ask \(.applicationName) to do something"
        ], shortTitle: "Ask Omi", systemImageName: "bubble.left.and.text.bubble.right")
        AppShortcut(intent: RememberIntent(), phrases: [
            "Remember something in \(.applicationName)",
            "Tell \(.applicationName) to remember",
            "Add a memory to \(.applicationName)",
            "Ask \(.applicationName) to remember"
        ], shortTitle: "Remember", systemImageName: "brain.head.profile")
        AppShortcut(intent: StartOmiListeningIntent(), phrases: ["Start listening with \(.applicationName)"],
                    shortTitle: "Start listening", systemImageName: "waveform")
        AppShortcut(intent: StopOmiListeningIntent(), phrases: ["Stop \(.applicationName)"],
                    shortTitle: "Stop listening", systemImageName: "stop.fill")
    }
}

@available(iOS 26.0, *)
extension RememberIntent {
    static var supportedModes: IntentModes { .background }
}

@available(iOS 26.0, *)
extension StartOmiListeningIntent {
    static var supportedModes: IntentModes { .foreground(.dynamic) }
}

@available(iOS 26.0, *)
extension StopOmiListeningIntent {
    static var supportedModes: IntentModes { .foreground(.dynamic) }
}
#endif
