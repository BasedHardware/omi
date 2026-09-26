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
      let action = name == "complete_task" ? "complete" : name == "open" ? "open" : "create"
      throw SiriActionFailure(action: action, failure: failure)
    }
  }

  @MainActor
  private static func record(_ name: String, outcome: String, started: Date) {
    PostHogManager.shared.track(
      "Siri Intent Performed",
      properties: [
        "intent": name, "platform": "macos", "outcome": outcome,
        "latency_ms": Int(Date().timeIntervalSince(started) * 1_000),
        "invoked_via": "unknown",
      ])
  }
}

struct RememberIntent: AppIntent {
  static let title: LocalizedStringResource = "Remember in Omi"
  static let description = IntentDescription("Save a personal memory in Omi.")
  static let authenticationPolicy: IntentAuthenticationPolicy = .requiresLocalDeviceAuthentication

  @Parameter(title: "What should Omi remember?") var text: String

  func perform() async throws -> some IntentResult & ProvidesDialog {
    let saved = try await SiriIntentTelemetry.perform("remember") {
      try await SiriIntentService.remember(text)
    }
    let content = SiriIntentService.normalizedMemory(saved.content)
    return .result(dialog: IntentDialog("Got it. I'll remember that \(content)."))
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
      try await SiriIntentService.remember(value)
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

  func perform() async throws -> some ReturnsValue<TaskEntity> {
    guard list == nil || list?.id == "omi" else {
      throw SiriActionFailure(action: "create", failure: .unsupported)
    }
    let due = dueDate.flatMap { Calendar.current.date(from: $0) }
    let created = try await SiriIntentTelemetry.perform("create_task") {
      try await SiriIntentService.createTask(title: title, dueDate: due)
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

  @MainActor
  func perform() async throws -> some IntentResult & ProvidesDialog {
    try await SiriIntentTelemetry.perform("start_listening") {
      guard let app = AppState.current else { throw SiriFailure.server }
      app.startTranscription()
      guard app.isTranscribing else { throw SiriFailure.server }
    }
    return .result(dialog: "Omi is listening.")
  }
}

struct StopListeningIntent: AppIntent {
  static let title: LocalizedStringResource = "Stop Listening in Omi"

  @MainActor
  func perform() async throws -> some IntentResult & ProvidesDialog {
    try await SiriIntentTelemetry.perform("stop_listening") {
      guard let app = AppState.current, app.isTranscribing else { throw SiriFailure.server }
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
