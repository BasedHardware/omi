import CryptoKit
import Foundation

/// Persisted incremental-sync bookkeeping: what Omi has already imported, and
/// enough per-note state to decide whether a note actually changed.
struct AppleNotesSyncState: Codable, Equatable, Sendable {
  struct Entry: Codable, Equatable, Sendable {
    let modifiedAt: Date
    /// sha256 of `title + "\n\n" + body`. Notes bumps a note's modification date
    /// on folder moves and other non-content edits, so the timestamp alone
    /// over-reports change; the hash is what decides whether to re-import.
    let contentHash: String
  }

  let schemaVersion: Int
  let lastSyncedAt: Date
  var entries: [String: Entry]

  init(
    schemaVersion: Int = AppleNotesScript.schemaVersion,
    lastSyncedAt: Date,
    entries: [String: Entry]
  ) {
    self.schemaVersion = schemaVersion
    self.lastSyncedAt = lastSyncedAt
    self.entries = entries
  }

  static func contentHash(title: String, body: String) -> String {
    let digest = SHA256.hash(data: Data((title + "\n\n" + body).utf8))
    return digest.map { String(format: "%02x", $0) }.joined()
  }

  /// The stable per-note key: the **last path component** of the AppleScript id.
  ///
  /// `x-coredata://<store-uuid>/ICNote/p1443` → `p1443`. The store UUID changes
  /// whenever CoreData rebuilds the store (iCloud re-sync, OS migration). Keying
  /// on the full id would silently reset every external id on that day and
  /// re-import the entire library as new evidence.
  static func noteKey(fromAppleScriptID appleScriptID: String) -> String {
    let trimmed = appleScriptID.trimmingCharacters(in: .whitespacesAndNewlines)
    guard let last = trimmed.split(separator: "/").last, !last.isEmpty else {
      return trimmed
    }
    return String(last)
  }
}

/// Storage seam for the sync state. `load()` returns `nil` for *any* unusable
/// state — missing, unreadable, or written by a different payload schema — so
/// callers have exactly one recovery path (a full resync) instead of a partial,
/// half-trusted diff.
protocol AppleNotesSyncStateStoring: Sendable {
  func load() async -> AppleNotesSyncState?
  func save(_ state: AppleNotesSyncState) async
  func clear() async
}

struct FileAppleNotesSyncStateStore: AppleNotesSyncStateStoring {
  private let directory: URL

  init(directory: URL? = nil) {
    if let directory {
      self.directory = directory
      return
    }
    let fileManager = FileManager.default
    let applicationSupport =
      fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
      ?? fileManager.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support")
    let bundleID = Bundle.main.bundleIdentifier ?? "com.omi.computer-macos"
    self.directory =
      applicationSupport
      .appendingPathComponent(bundleID, isDirectory: true)
      .appendingPathComponent("AppleNotes", isDirectory: true)
  }

  var fileURL: URL {
    directory.appendingPathComponent("sync-state.json", isDirectory: false)
  }

  // Dates use the default `.deferredToDate` strategy on purpose. The incremental
  // diff compares a persisted timestamp against a freshly parsed one for
  // *equality*, so the encoding has to be lossless; an ISO-8601 strategy drops
  // sub-second precision and would report every note as changed on every pass.
  func load() async -> AppleNotesSyncState? {
    guard let data = try? Data(contentsOf: fileURL) else { return nil }
    guard let state = try? JSONDecoder().decode(AppleNotesSyncState.self, from: data) else { return nil }
    guard state.schemaVersion == AppleNotesScript.schemaVersion else { return nil }
    return state
  }

  func save(_ state: AppleNotesSyncState) async {
    do {
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
      try JSONEncoder().encode(state).write(to: fileURL, options: .atomic)
    } catch {
      log("AppleNotesReaderService: failed to persist sync state: \(error.localizedDescription)")
    }
  }

  func clear() async {
    try? FileManager.default.removeItem(at: fileURL)
  }
}
