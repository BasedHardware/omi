import AppIntents
import Foundation

@MainActor
enum SiriIntentTelemetry {
  static func perform<T>(
    _ name: String, operation: @MainActor () async throws -> T
  ) async throws -> T {
    let started = Date()
    do {
      let result = try await operation()
      record(name, outcome: "ok", started: started)
      return result
    } catch {
      let failure = SiriFailure.classify(error)
      record(name, outcome: failure.outcome, started: started)
      if let scoped = error as? SiriActionFailure { throw scoped }
      let action =
        name == "complete_task"
        ? "complete"
        : name == "open" || name == "open_chat"
          ? "open"
          : name == "ask_omi"
            ? "ask"
            : name == "start_listening" || name == "stop_listening" ? name : "create"
      throw SiriActionFailure(action: action, failure: failure)
    }
  }

  @MainActor
  private static func record(_ name: String, outcome: String, started: Date) {
    var properties: [String: Any] = [
      "platform": "macos", "outcome": outcome,
      "latency_ms": Int(Date().timeIntervalSince(started) * 1_000),
      "invoked_via": "unknown",
    ]
    if name != "ask_omi" { properties["intent"] = name }
    PostHogManager.shared.track(
      name == "ask_omi" ? "Siri Ask Omi Performed" : "Siri Intent Performed",
      properties: properties)
  }
}

struct RememberIntent: AppIntent {
  static let title: LocalizedStringResource = "Remember in Omi"
  static let description = IntentDescription("Save a personal memory in Omi.")
  static let authenticationPolicy: IntentAuthenticationPolicy = .requiresLocalDeviceAuthentication
  static let openAppWhenRun = false

  @Parameter(title: "What should Omi remember?") var text: String

  func perform() async throws -> some IntentResult & ProvidesDialog {
    let saved = try await SiriIntentTelemetry.perform("remember") {
      try await SiriIntentService.remember(text)
    }
    let content = SiriIntentService.normalizedMemory(saved.content)
    return .result(dialog: IntentDialog("Got it. I'll remember that \(content)."))
  }
}

struct OpenOmiChatIntent: AppIntent {
  static let title: LocalizedStringResource = "Open Omi chat"
  static let description = IntentDescription("Open Omi's chat without asking a new question.")
  static let isDiscoverable = false
  static let openAppWhenRun = true
  @Parameter(title: "Draft") var draft: String?
  @Parameter(title: "Draft submission was attempted") var draftWasAttempted: Bool?
  @Parameter(title: "Owner") var ownerID: String?

  static func shouldAutoSend(draft: String?, wasAttempted: Bool?) -> Bool {
    !SiriIntentService.normalizedQuestion(draft ?? "").isEmpty && wasAttempted != true
  }

  @MainActor
  func perform() async throws -> some IntentResult {
    try await SiriIntentTelemetry.perform("open_chat") {
      guard let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
      else { throw SiriFailure.auth }
      let question = SiriIntentService.normalizedQuestion(draft ?? "")
      if question.isEmpty {
        AppDelegate.summonWindowTarget()?.openMainAppChat()
      } else if Self.shouldAutoSend(draft: draft, wasAttempted: draftWasAttempted) {
        AppDelegate.summonWindowTarget()?.openMainAppChat(
          siriQuestion: question, authorization: authorization)
      } else {
        AppDelegate.summonWindowTarget()?.openMainAppChat(
          appendingDraft: question, authorization: authorization)
      }
    }
    return .result()
  }
}

/// Siri can open chat directly without a free-text slot that competes with Ask Omi.
struct OpenOmiChatActionIntent: AppIntent {
  static let title: LocalizedStringResource = "Open Omi chat"
  static let description = IntentDescription("Open Omi chat to view or continue a conversation.")
  static let openAppWhenRun = true

  @MainActor
  func perform() async throws -> some IntentResult {
    try await OpenOmiChatIntent().perform()
  }
}

struct AskOmiIntent: AppIntent {
  static let title: LocalizedStringResource = "Ask Omi"
  static let description = IntentDescription(
    "Ask Omi a question about your conversations, memories, and tasks and get a spoken answer."
  )
  // Siri must authenticate before reading personal answers aloud.
  static let authenticationPolicy: IntentAuthenticationPolicy = .requiresAuthentication
  static let openAppWhenRun = false

  static var parameterSummary: some ParameterSummary {
    Summary("Ask Omi \(\.$question)")
  }

  @Parameter(
    title: "Question",
    description: "A question for Omi to answer from your conversations, memories, and tasks.",
    requestValueDialog: "What would you like to ask Omi?"
  )
  var question: String

  static func continuation(
    after result: SiriAskResult, question: String, ownerID: String?
  ) -> OpenOmiChatIntent {
    let openChat = OpenOmiChatIntent()
    openChat.ownerID = ownerID
    // A draft exists only when the live provider rejected the send before it
    // started. Pending and answered turns may already be in the chat journal.
    if case .draft = result {
      openChat.draft = question
      openChat.draftWasAttempted = false
    }
    return openChat
  }

  /// Remember saves require local-device authentication (contracts/siri). Ask
  /// runs under the weaker companion-device `.requiresAuthentication` policy,
  /// so a remember phrase is redirected to the strict Remember shortcut
  /// instead of persisting a private memory under the weaker policy. No save
  /// is attempted here, so no success is claimed.
  static func rememberRedirectDialog(for question: String) -> String? {
    let lower = question.lowercased()
    guard lower.hasPrefix("remember ") || lower.hasPrefix("to remember ") else { return nil }
    return "To save that, say 'Remember something in Omi' instead."
  }

  @MainActor
  func perform() async throws -> IntentResultContainer<Never, Never, Never, IntentDialog> {
    let value = SiriIntentService.normalizedQuestion(question)
    let ownerID = RuntimeOwnerIdentity.captureAuthorizationSnapshot()?.ownerID
    let openChat = OpenOmiChatIntent()
    openChat.ownerID = ownerID
    if let redirect = Self.rememberRedirectDialog(for: value) {
      // Record the redirect as a cancelled ask (no write, no answer), matching
      // the iOS outcome for the same phrase.
      _ = try? await SiriIntentTelemetry.perform("ask_omi") { throw SiriFailure.cancelled }
      return .result(dialog: IntentDialog("\(redirect)"))
    }
    let result = try await SiriIntentTelemetry.perform("ask_omi") {
      try await SiriIntentService.ask(value)
    }
    switch result {
    case .draft:
      let continuation = Self.continuation(after: result, question: value, ownerID: ownerID)
      if #available(macOS 15.2, *) {
        return .result(opensIntent: continuation, dialog: "Open Omi to finish your question in chat.")
      }
      _ = try await continuation.perform()
      return .result(dialog: "Open Omi to finish your question in chat.")
    case .pending:
      let continuation = Self.continuation(after: result, question: value, ownerID: ownerID)
      if #available(macOS 15.2, *) {
        return .result(
          opensIntent: continuation, dialog: "Omi couldn't finish the answer here. Open Omi chat to check it.")
      }
      _ = try await continuation.perform()
      return .result(dialog: "Omi couldn't finish the answer here. Open Omi chat to check it.")
    case .answered(let answer):
      guard !answer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
        let continuation = Self.continuation(after: result, question: value, ownerID: ownerID)
        if #available(macOS 15.2, *) {
          return .result(opensIntent: continuation, dialog: "Open Omi chat to continue.")
        }
        _ = try await continuation.perform()
        return .result(dialog: "Open Omi chat to continue.")
      }
      // The full answer is persisted to the owner's chat, so a truncated spoken
      // answer must still say where the remainder can be read.
      let spoken = answer.count > 450 ? String(answer.prefix(447)) + "… Open Omi chat for the rest." : answer
      return .result(dialog: IntentDialog("\(spoken)"))
    }
  }
}

@available(macOS 27, *)
@AppIntent(schema: .notes.createNote)
struct OmiCreateNoteIntent {
  static let title: LocalizedStringResource = "Save a Memory in Omi"
  static let authenticationPolicy: IntentAuthenticationPolicy = .requiresLocalDeviceAuthentication
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

  func perform() async throws -> some ReturnsValue<ConversationEntity> {
    let value = String(content?.characters ?? AttributedString(name).characters)
    let saved = try await SiriIntentTelemetry.perform("create_note") {
      guard folder == nil || folder?.id == "memories", attachments.isEmpty,
        tags.isEmpty, !isPinned
      else { throw SiriActionFailure(action: "create_note_fields", failure: .unsupported) }
      return try await SiriIntentService.remember(value)
    }
    return .result(value: ConversationEntity(saved))
  }
}

@available(macOS 27, *)
@AppIntent(schema: .reminders.createReminder)
struct OmiCreateTaskIntent {
  static let title: LocalizedStringResource = "Add an Omi Task"
  static let authenticationPolicy: IntentAuthenticationPolicy = .requiresLocalDeviceAuthentication
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
    title = ""
    list = nil
    note = nil
    isFlagged = nil
    images = []
    tags = []
    urls = []
    dueDate = nil
    recurrence = nil
    locationTrigger = nil
    section = nil
  }

  func perform() async throws -> some ReturnsValue<TaskEntity> {
    let due = dueDate.flatMap { Calendar.current.date(from: $0) }
    let created = try await SiriIntentTelemetry.perform("create_task") {
      guard list == nil || list?.id == "omi",
        note.map({ String($0.characters).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) ?? true,
        isFlagged != true, images.isEmpty, tags.isEmpty, urls.isEmpty,
        recurrence == nil, locationTrigger == nil, section == nil,
        dueDate == nil || due != nil
      else { throw SiriActionFailure(action: "create_task_fields", failure: .unsupported) }
      return try await SiriIntentService.createTask(title: title, dueDate: due)
    }
    // The backend receipt is authoritative. A subsequent sync populates the
    // local cache; use the receipt to return a schema entity immediately.
    return .result(value: TaskEntity(created))
  }
}

@available(macOS 27, *)
@AppIntent(schema: .reminders.updateReminder)
struct OmiCompleteTaskIntent {
  static let title: LocalizedStringResource = "Complete an Omi Task"
  static let authenticationPolicy: IntentAuthenticationPolicy = .requiresLocalDeviceAuthentication
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

  func perform() async throws -> some ReturnsValue<TaskEntity> {
    guard isCompleted == true, title == nil, note == nil, tags == nil, urls == nil,
      dueDate == nil, recurrence == nil, isFlagged == nil, list == nil, locationTrigger == nil
    else { throw SiriActionFailure(action: "complete", failure: .unsupported) }
    let result = try await SiriIntentTelemetry.perform("complete_task") {
      try await SiriIntentService.completeTask(id: target.id)
    }
    return .result(value: TaskEntity(result))
  }
}

@available(macOS 27, *)
@AppEntity(schema: .reminders.section)
struct OmiSectionEntity: IndexedEntity {
  static let defaultQuery = OmiSectionQuery()
  static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Omi Task Section")
  let id: String
  var name: String
  var list: OmiListEntity
  var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(name)") }
}

@available(macOS 27, *)
struct OmiSectionQuery: EntityQuery {
  func entities(for identifiers: [String]) async throws -> [OmiSectionEntity] { [] }
}

struct StartListeningIntent: AppIntent {
  static let title: LocalizedStringResource = "Start Listening in Omi"
  static let openAppWhenRun = true

  @MainActor
  func perform() async throws -> some IntentResult & ProvidesDialog {
    try await SiriIntentTelemetry.perform("start_listening") {
      guard let app = AppState.current else { throw SiriFailure.server }
      guard app.audioRecordingMode != .off else { throw SiriFailure.recordingOff }
      guard app.hasMicrophonePermission else { throw SiriFailure.micDenied }
      app.startTranscription()
      try SiriListeningState.requireActive(isTranscribing: app.isTranscribing, isAwaitingMeeting: app.isAwaitingMeeting)
    }
    return .result(dialog: "Omi is listening.")
  }
}

struct StopListeningIntent: AppIntent {
  static let title: LocalizedStringResource = "Stop Listening in Omi"
  static let openAppWhenRun = true

  @MainActor
  func perform() async throws -> some IntentResult & ProvidesDialog {
    try await SiriIntentTelemetry.perform("stop_listening") {
      guard let app = AppState.current, app.isTranscribing else { throw SiriFailure.nothingToStop }
      let completion = app.stopTranscription()
      await completion?.value
    }
    return .result(dialog: "Omi stopped listening.")
  }
}

@available(macOS 26, *)
extension RememberIntent {
  static var supportedModes: IntentModes { .background }
}

@available(macOS 26, *)
extension StartListeningIntent {
  static var supportedModes: IntentModes { .foreground(.immediate) }
}

@available(macOS 26, *)
extension StopListeningIntent {
  static var supportedModes: IntentModes { .foreground(.immediate) }
}

struct OmiAppShortcuts: AppShortcutsProvider {
  static var appShortcuts: [AppShortcut] {
    AppShortcut(
      intent: AskOmiIntent(),
      phrases: [
        "Ask \(.applicationName)",
        "Ask \(.applicationName) a question",
        "Question for \(.applicationName)",
        "\(.applicationName) question",
        "Check \(.applicationName)",
        "Ask a question in \(.applicationName)",
        "Ask \(.applicationName) something",
        "I have a question for \(.applicationName)",
      ], shortTitle: "Ask Omi", systemImageName: "bubble.left.and.text.bubble.right")
    AppShortcut(
      intent: OpenOmiChatActionIntent(),
      phrases: [
        "Open \(.applicationName) chat",
        "Open chat in \(.applicationName)",
      ], shortTitle: "Open Omi chat", systemImageName: "bubble.left.and.bubble.right")
    AppShortcut(
      intent: RememberIntent(),
      phrases: [
        "Remember something in \(.applicationName)",
        "Tell \(.applicationName) to remember",
        "Add a memory to \(.applicationName)",
      ], shortTitle: "Remember", systemImageName: "brain.head.profile")
    AppShortcut(
      intent: StartListeningIntent(),
      phrases: [
        "Start listening with \(.applicationName)"
      ], shortTitle: "Start Listening", systemImageName: "mic")
    AppShortcut(
      intent: StopListeningIntent(),
      phrases: [
        "Stop \(.applicationName)"
      ], shortTitle: "Stop Listening", systemImageName: "mic.slash")
  }
}
