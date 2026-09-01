import Foundation

struct ContextReminderKey: Codable, Equatable, Sendable {
  let bundleID: String
  let normalizedTitle: String
  let bucketID: String?

  func matches(_ context: FirstRunObservedContext) -> Bool {
    if let bucketID, let observedBucketID = context.bucketID, bucketID == observedBucketID {
      return true
    }
    return bundleID == context.bundleID && normalizedTitle == context.normalizedTitle
  }
}

struct ContextReminder: Codable, Equatable, Identifiable, Sendable {
  let id: String
  let text: String
  let contextKey: ContextReminderKey
  let createdAt: Date
  var snoozeUntil: Date?
  var doneAt: Date?
  var actionItemID: String?
}

actor ContextReminderStore {
  static let shared = ContextReminderStore()

  private let fileManager: FileManager
  private let fileURLProvider: @Sendable () -> URL
  private let ownerIDProvider: @Sendable () -> String?
  private let requiresRuntimeAuthorization: Bool
  private let beforeMutationSave: (@Sendable () -> Void)?

  init(
    fileManager: FileManager = .default,
    fileURLProvider: (@Sendable () -> URL)? = nil,
    ownerIDProvider: @escaping @Sendable () -> String? = { RuntimeOwnerIdentity.currentOwnerId() },
    beforeMutationSave: (@Sendable () -> Void)? = nil
  ) {
    self.fileManager = fileManager
    self.ownerIDProvider = ownerIDProvider
    requiresRuntimeAuthorization = fileURLProvider == nil
    self.beforeMutationSave = beforeMutationSave
    self.fileURLProvider =
      fileURLProvider ?? {
        let root =
          FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
          ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support")
        let owner = RuntimeOwnerIdentity.currentOwnerId() ?? "signed-out"
        return
          root
          .appendingPathComponent("Omi", isDirectory: true)
          .appendingPathComponent("users", isDirectory: true)
          .appendingPathComponent(owner, isDirectory: true)
          .appendingPathComponent("FirstRun", isDirectory: true)
          .appendingPathComponent("context-reminders.json")
      }
  }

  @discardableResult
  func create(
    text: String,
    for context: ContextReminderKey,
    actionItemID: String? = nil,
    now: Date = Date(),
    id: String = UUID().uuidString.lowercased(),
    expectedOwnerID: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) throws -> ContextReminder {
    let loaded = try loadForMutation(
      expectedOwnerID: expectedOwnerID,
      authorizationSnapshot: authorizationSnapshot)
    var reminders = loaded.reminders
    let reminder = ContextReminder(
      id: id,
      text: text,
      contextKey: context,
      createdAt: now,
      snoozeUntil: nil,
      doneAt: nil,
      actionItemID: actionItemID)
    reminders.append(reminder)
    try save(reminders, loadedFor: loaded.ownerID, authorization: loaded.authorization)
    return reminder
  }

  func dueReminders(for context: FirstRunObservedContext, now: Date = Date()) throws -> [ContextReminder] {
    try load().filter { reminder in
      reminder.doneAt == nil
        && (reminder.snoozeUntil.map { $0 <= now } ?? true)
        && reminder.contextKey.matches(context)
    }
  }

  @discardableResult
  func markDone(id: String, at date: Date = Date()) throws -> ContextReminder? {
    let loaded = try loadForMutation()
    var reminders = loaded.reminders
    guard let index = reminders.firstIndex(where: { $0.id == id }) else { return nil }
    reminders[index].doneAt = date
    reminders[index].snoozeUntil = nil
    try save(reminders, loadedFor: loaded.ownerID, authorization: loaded.authorization)
    return reminders[index]
  }

  @discardableResult
  func snooze(id: String, until date: Date) throws -> ContextReminder? {
    let loaded = try loadForMutation()
    var reminders = loaded.reminders
    guard let index = reminders.firstIndex(where: { $0.id == id }) else { return nil }
    reminders[index].snoozeUntil = date
    try save(reminders, loadedFor: loaded.ownerID, authorization: loaded.authorization)
    return reminders[index]
  }

  func allReminders() throws -> [ContextReminder] {
    try load()
  }

  @MainActor
  @discardableResult
  func deliver(_ reminder: ContextReminder) -> Bool {
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return false }
    NotificationService.shared.sendNotification(
      ownerID: ownerID,
      title: reminder.contextKey.normalizedTitle,
      message: "Welcome back. You asked me to remind you: \(reminder.text)",
      assistantId: "first_run_card",
      action: FirstRunCardActions.make(.contextReminder(reminderID: reminder.id)),
      respectFrequency: false,
      isPersistent: true)
    return true
  }

  private func load() throws -> [ContextReminder] {
    let url = fileURLProvider()
    guard fileManager.fileExists(atPath: url.path) else { return [] }
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return try decoder.decode([ContextReminder].self, from: Data(contentsOf: url))
  }

  private func loadForMutation(
    expectedOwnerID: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) throws -> (
    reminders: [ContextReminder], ownerID: String, authorization: RuntimeOwnerAuthorizationSnapshot?
  ) {
    guard let ownerID = resolvedOwnerID() else {
      throw CocoaError(.userCancelled)
    }
    guard expectedOwnerID == nil || expectedOwnerID == ownerID else { throw CocoaError(.userCancelled) }
    let authorization =
      authorizationSnapshot
      ?? RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
    if requiresRuntimeAuthorization, authorization == nil { throw CocoaError(.userCancelled) }
    return (try load(), ownerID, authorization)
  }

  private func save(
    _ reminders: [ContextReminder],
    loadedFor ownerID: String,
    authorization: RuntimeOwnerAuthorizationSnapshot?
  ) throws {
    beforeMutationSave?()
    guard resolvedOwnerID() == ownerID,
      authorization.map(RuntimeOwnerIdentity.isAuthorizationCurrent) ?? !requiresRuntimeAuthorization
    else {
      log("ContextReminderStore: refusing write after runtime owner changed")
      throw CocoaError(.userCancelled)
    }
    let url = fileURLProvider()
    try fileManager.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    let encoder = JSONEncoder()
    encoder.dateEncodingStrategy = .iso8601
    try encoder.encode(reminders).write(to: url, options: .atomic)
  }

  private func resolvedOwnerID() -> String? {
    if let ownerID = ownerIDProvider()?.trimmingCharacters(in: .whitespacesAndNewlines), !ownerID.isEmpty {
      return ownerID
    }
    return requiresRuntimeAuthorization ? nil : "test-owner"
  }
}
