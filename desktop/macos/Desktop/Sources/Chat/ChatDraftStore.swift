import Foundation

/// Stable identity for unsent text in one conversational composer.
///
/// Drafts are deliberately separate from chat/session persistence: they are local UI
/// intent and never become conversation history until a send is accepted.
struct ChatDraftKey: Hashable, Sendable {
  let scope: String
  let contextID: String

  static func mainChat(contextID: String = "default") -> Self {
    Self(scope: "main_chat", contextID: contextID)
  }

  static let floatingMain = Self(scope: "floating_chat", contextID: "main")
  static let onboardingMain = Self(scope: "onboarding_chat", contextID: "main")
  static let onboardingFloating = Self(scope: "onboarding_chat", contextID: "floating")

  static func floatingAgent(_ id: UUID) -> Self {
    Self(scope: "floating_agent", contextID: id.uuidString.lowercased())
  }

  static func taskChat(_ taskID: String) -> Self {
    Self(scope: "task_chat", contextID: taskID)
  }
}

private struct ChatDraftRecord: Codable, Sendable {
  let version: Int
  let ownerID: String
  let scope: String
  let contextID: String
  let text: String
  let updatedAt: Date
}

/// Lightweight local persistence for conversational drafts.
///
/// Each draft is an independent, atomically replaced record under Application
/// Support. Writes are coalesced on a serial background queue, so the typing path
/// only updates in-memory UI state. A corrupt record cannot affect another draft.
@MainActor
final class ChatDraftStore {
  static let shared = ChatDraftStore()

  private struct StorageID: Hashable, Sendable {
    let ownerID: String
    let key: ChatDraftKey
  }

  private let rootURL: URL
  private let fileManager: FileManager
  private let writeDelay: TimeInterval
  private let ownerIDProvider: () -> String?
  private let persistenceQueue = DispatchQueue(label: "com.omi.desktop.chat-drafts", qos: .utility)

  private var cache: [StorageID: String] = [:]
  private var loaded: Set<StorageID> = []
  private var pendingWrites: [StorageID: DispatchWorkItem] = [:]
  private var writeGenerations: [StorageID: Int] = [:]

  init(
    rootURL: URL? = nil,
    fileManager: FileManager = .default,
    writeDelay: TimeInterval = 0.2,
    ownerIDProvider: @escaping () -> String? = {
      UserDefaults.standard.string(forKey: .authUserId)
    }
  ) {
    self.fileManager = fileManager
    self.writeDelay = writeDelay
    self.ownerIDProvider = ownerIDProvider

    if let rootURL {
      self.rootURL = rootURL
    } else {
      let applicationSupport =
        fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
        ?? fileManager.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support")
      let bundleID = Bundle.main.bundleIdentifier ?? "com.omi.desktop"
      self.rootURL =
        applicationSupport
        .appendingPathComponent(bundleID, isDirectory: true)
        .appendingPathComponent("Drafts/v1", isDirectory: true)
    }
  }

  func text(for key: ChatDraftKey, ownerID: String? = nil) -> String {
    let id = storageID(for: key, ownerID: ownerID)
    if loaded.contains(id) {
      return cache[id] ?? ""
    }

    loaded.insert(id)
    guard let data = try? Data(contentsOf: fileURL(for: id)),
      let record = try? JSONDecoder().decode(ChatDraftRecord.self, from: data),
      record.version == 1,
      record.ownerID == id.ownerID,
      record.scope == key.scope,
      record.contextID == key.contextID
    else {
      cache[id] = ""
      return ""
    }

    cache[id] = record.text
    return record.text
  }

  func setText(_ text: String, for key: ChatDraftKey, ownerID: String? = nil) {
    let id = storageID(for: key, ownerID: ownerID)
    loaded.insert(id)
    cache[id] = text
    scheduleWrite(for: id, text: text)
  }

  func clear(_ key: ChatDraftKey, ownerID: String? = nil) {
    setText("", for: key, ownerID: ownerID)
  }

  /// Synchronously persists the latest in-memory values. Used for orderly app
  /// termination and tests; normal edits remain off the main thread.
  func flush() {
    let snapshots = pendingWrites.keys.map { id in (id, cache[id] ?? "") }
    pendingWrites.values.forEach { $0.cancel() }
    pendingWrites.removeAll()
    let rootURL = rootURL
    let flushWork: @Sendable () -> Void = {
      for (id, text) in snapshots {
        Self.persist(text: text, id: id, rootURL: rootURL)
      }
    }
    persistenceQueue.sync(execute: flushWork)
  }

  /// Explicit sign-out is destructive for that account's drafts. Light auth
  /// invalidation intentionally does not call this, so reauthentication retains text.
  func clearAll(ownerID: String?) {
    let normalizedOwnerID = Self.normalizedOwnerID(ownerID)
    let matchingIDs = Set(cache.keys.filter { $0.ownerID == normalizedOwnerID })
    for id in matchingIDs {
      pendingWrites[id]?.cancel()
      pendingWrites[id] = nil
      cache[id] = nil
      loaded.remove(id)
    }

    let ownerURL = rootURL.appendingPathComponent(Self.fileNameComponent(normalizedOwnerID), isDirectory: true)
    let removeWork: @Sendable () -> Void = {
      try? FileManager.default.removeItem(at: ownerURL)
    }
    persistenceQueue.sync(execute: removeWork)
  }

  private func storageID(for key: ChatDraftKey, ownerID: String?) -> StorageID {
    StorageID(
      ownerID: Self.normalizedOwnerID(ownerID ?? ownerIDProvider()),
      key: key
    )
  }

  private func fileURL(for id: StorageID) -> URL {
    let ownerURL = rootURL.appendingPathComponent(Self.fileNameComponent(id.ownerID), isDirectory: true)
    let key = "\(id.key.scope)\u{0}\(id.key.contextID)"
    return ownerURL.appendingPathComponent(Self.fileNameComponent(key)).appendingPathExtension("json")
  }

  private func scheduleWrite(for id: StorageID, text: String) {
    pendingWrites[id]?.cancel()
    let generation = (writeGenerations[id] ?? 0) + 1
    writeGenerations[id] = generation
    let rootURL = rootURL
    // The work item runs on `persistenceQueue` (not the main actor). Under Swift 6
    // the runtime asserts executor assumptions, so the block must be a non-isolated
    // `@Sendable` closure — an inferred `@MainActor` block dispatched off the main
    // queue would trap (`dispatch_assert_queue_fail`). `persist` is a static call;
    // the in-memory bookkeeping hops back to the main actor via a `Task`.
    let block: @Sendable () -> Void = {
      Self.persist(text: text, id: id, rootURL: rootURL)
      Task { @MainActor [weak self] in
        guard let self, self.writeGenerations[id] == generation else { return }
        self.pendingWrites[id] = nil
      }
    }
    let workItem = DispatchWorkItem(block: block)
    pendingWrites[id] = workItem
    persistenceQueue.asyncAfter(deadline: .now() + writeDelay, execute: workItem)
  }

  private nonisolated static func persist(
    text: String,
    id: StorageID,
    rootURL: URL
  ) {
    let fileManager = FileManager.default
    let ownerURL = rootURL.appendingPathComponent(fileNameComponent(id.ownerID), isDirectory: true)
    let key = "\(id.key.scope)\u{0}\(id.key.contextID)"
    let url = ownerURL.appendingPathComponent(fileNameComponent(key)).appendingPathExtension("json")

    if text.isEmpty {
      try? fileManager.removeItem(at: url)
      return
    }

    do {
      try fileManager.createDirectory(at: ownerURL, withIntermediateDirectories: true)
      let record = ChatDraftRecord(
        version: 1,
        ownerID: id.ownerID,
        scope: id.key.scope,
        contextID: id.key.contextID,
        text: text,
        updatedAt: Date()
      )
      let data = try JSONEncoder().encode(record)
      try data.write(to: url, options: .atomic)
    } catch {
      // Draft contents are private user text, so never include them in logs.
      logError("ChatDraftStore: failed to persist \(id.key.scope) draft", error: error)
    }
  }

  private static func normalizedOwnerID(_ ownerID: String?) -> String {
    let trimmed = ownerID?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return trimmed.isEmpty ? "local" : trimmed
  }

  private nonisolated static func fileNameComponent(_ value: String) -> String {
    Data(value.utf8).base64EncodedString()
      .replacingOccurrences(of: "/", with: "_")
      .replacingOccurrences(of: "+", with: "-")
      .replacingOccurrences(of: "=", with: "")
  }
}
