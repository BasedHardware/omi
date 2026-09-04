import Foundation

/// The frontmost place a context-bound reminder can match: an app window,
/// optionally clustered into a context bucket when that feature is on.
struct ContextReminderObservedContext: Equatable, Sendable {
  let appName: String
  let bundleID: String
  let normalizedTitle: String
  let bucketID: String?

  var reminderKey: ContextReminderKey {
    ContextReminderKey(bundleID: bundleID, normalizedTitle: normalizedTitle, bucketID: bucketID)
  }

  /// Omi describing its own window is not a place the user asked to come back to.
  var isOmiBundle: Bool {
    let bundle = bundleID.lowercased()
    return bundle == AppBuild.productionBundleIdentifier.lowercased()
      || bundle == AppBuild.betaProductionBundleIdentifier.lowercased()
      || bundle == AppBuild.desktopDevBundleIdentifier.lowercased()
      || bundle.hasPrefix("com.omi.omi-")
      || bundle.hasPrefix(AppBuild.externalPreviewBundleIdentifierPrefix)
  }
}

struct ContextReminderKey: Codable, Equatable, Sendable {
  let bundleID: String
  let normalizedTitle: String
  let bucketID: String?

  /// Prefer a bucket-id match when both sides have one, otherwise fall back
  /// to (bundle id, normalized title). A renamed window in the same bucket
  /// still fires; a different app with the same title does not unless they
  /// share a bucket.
  func matches(_ context: ContextReminderObservedContext) -> Bool {
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

/// Owner-scoped JSON persistence for place-bound reminders.
///
/// Path: `Application Support/Omi/users/<ownerID>/ContextReminders/context-reminders.json`.
/// Nothing ever shipped under the abandoned `FirstRun/` segment this was extracted
/// from, so there is no file to migrate.
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
          .appendingPathComponent("ContextReminders", isDirectory: true)
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

  /// Owner-bound read: resolves the owner first, reads that owner's file, and
  /// discards the results if the owner changed while the read was in flight so
  /// one account's reminders can never be presented under a newer owner.
  func dueReminders(
    for context: ContextReminderObservedContext,
    now: Date = Date(),
    expectedOwnerID: String? = nil
  ) throws -> [ContextReminder] {
    // No owner means no reminders can exist (mutation paths already refuse
    // ownerless writes in production), so read as empty instead of throwing on
    // every context switch while signed out.
    guard let ownerID = resolvedOwnerID() else { return [] }
    guard expectedOwnerID == nil || expectedOwnerID == ownerID else { throw CocoaError(.userCancelled) }
    let reminders = try load()
    guard resolvedOwnerID() == ownerID else { throw CocoaError(.userCancelled) }
    return reminders.filter { reminder in
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

  @discardableResult
  func attachActionItem(id: String, actionItemID: String) throws -> ContextReminder? {
    let loaded = try loadForMutation()
    var reminders = loaded.reminders
    guard let index = reminders.firstIndex(where: { $0.id == id }) else { return nil }
    reminders[index].actionItemID = actionItemID
    try save(reminders, loadedFor: loaded.ownerID, authorization: loaded.authorization)
    return reminders[index]
  }

  func allReminders() throws -> [ContextReminder] {
    try load()
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
