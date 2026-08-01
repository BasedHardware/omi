import Foundation
@preconcurrency import GRDB

/// Read-only access to the local Apple Mail index (`~/Library/Mail/V*/MailData/Envelope Index`).
///
/// Mirrors `AppleNotesReaderService` and `MessagesReaderService`: the store
/// belongs to another app, so it is opened read-only and every failure is
/// classified into a reason code the agent can act on rather than a raw SQLite
/// error. Full Disk Access is the usual cause of a denial.
///
/// **Headers only, never bodies.** Message bodies live beside this index as
/// `.emlx` files on disk; this reader never opens them. Subject, sender, and
/// date are enough to say what is waiting for the user, and reading the full
/// text of their mail to answer that is a far larger disclosure than the
/// question needs.
///
/// `OMI_MAIL_ENVELOPE_DB` overrides the store path so contract tests run against
/// a fixture instead of the developer's real mail.
struct MailMessageRecord: Identifiable, Sendable {
  let id: Int64
  let subject: String
  let senderAddress: String
  let senderName: String
  let receivedAt: Date?
  let isRead: Bool
  let isFlagged: Bool
  let wasAnswered: Bool
}

enum AppleMailReaderError: LocalizedError {
  case storeNotFound(path: String)
  case authorizationDenied(path: String)
  case schemaUnavailable(path: String, detail: String)
  case storeReadFailed(path: String, reason: String)

  var errorDescription: String? {
    switch self {
    case .storeNotFound:
      return
        "The Apple Mail index was not found. Mail.app may never have been set up on this Mac."
    case .authorizationDenied:
      return
        "Omi needs Full Disk Access to read Apple Mail. Grant it in System Settings > Privacy & Security > Full Disk Access, then quit and reopen Omi."
    case .schemaUnavailable(_, let detail):
      return "The Apple Mail index format was not recognized: \(detail)"
    case .storeReadFailed(_, let reason):
      return "The Apple Mail index could not be read: \(reason)"
    }
  }

  var reasonCode: String {
    switch self {
    case .storeNotFound: return "store_not_found"
    case .authorizationDenied: return "authorization_denied"
    case .schemaUnavailable: return "schema_unavailable"
    case .storeReadFailed: return "store_read_failed"
    }
  }

  /// Full Disk Access is the only denial the user can fix from a permission prompt.
  var requiredPermission: String? {
    switch self {
    case .authorizationDenied: return "full_disk_access"
    case .storeNotFound, .schemaUnavailable, .storeReadFailed: return nil
    }
  }
}

/// Result of a functional connection probe, per INV-INT-1 §3/§4. Distinct from
/// a stored "connected" flag: it means the index was read just now.
enum AppleMailConnectionStatus: Equatable {
  case connected(messageCount: Int, verifiedAt: Date)
  case needsAccess(message: String, reasonCode: String)
  case error(message: String, reasonCode: String)

  var isConnected: Bool {
    if case .connected = self { return true }
    return false
  }
}

actor AppleMailReaderService {
  static let shared = AppleMailReaderService()

  /// Mail's `date_received` is plain Unix seconds, unlike the Core Data
  /// reference dates in Notes and the Apple absolute times in Messages. Getting
  /// this wrong shifts every message by 31 years, so it is stated rather than
  /// inherited from a sibling reader.
  static func date(fromEnvelopeTimestamp raw: Int64) -> Date? {
    guard raw != 0 else { return nil }
    return Date(timeIntervalSince1970: TimeInterval(raw))
  }

  /// `flags` is a bitfield on `messages`; only these two bits are read.
  private static let flagRead: Int64 = 0x1
  private static let flagAnswered: Int64 = 0x4
  private static let flagFlagged: Int64 = 0x10

  // MARK: - Store location

  static func mailRootURL() -> URL {
    FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Mail")
  }

  /// Finds the newest `V{n}` container's envelope index.
  ///
  /// Mail keeps one directory per major format version and leaves the old ones
  /// in place, so picking the highest version is what tracks the mailbox the
  /// user is actually reading. Hardcoding a version would silently read stale
  /// mail after an OS upgrade.
  static func locateEnvelopeIndex(
    fileManager: FileManager = .default,
    mailRoot: URL? = nil
  ) throws -> URL {
    if let override = ProcessInfo.processInfo.environment["OMI_MAIL_ENVELOPE_DB"], !override.isEmpty {
      return URL(fileURLWithPath: override)
    }

    let root = mailRoot ?? mailRootURL()
    let entries: [URL]
    do {
      entries = try fileManager.contentsOfDirectory(
        at: root, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles])
    } catch {
      // A TCC denial and a missing directory both surface here, and they mean
      // opposite things to the user: one is a permission they can grant, the
      // other is "you have never used Mail".
      let nsError = error as NSError
      if nsError.domain == NSCocoaErrorDomain, nsError.code == NSFileReadNoSuchFileError {
        throw AppleMailReaderError.storeNotFound(path: root.path)
      }
      throw AppleMailReaderError.authorizationDenied(path: root.path)
    }

    let versioned = entries.compactMap { url -> (Int, URL)? in
      let name = url.lastPathComponent
      guard name.hasPrefix("V"), let version = Int(name.dropFirst()) else { return nil }
      return (version, url)
    }

    guard let newest = versioned.max(by: { $0.0 < $1.0 })?.1 else {
      throw AppleMailReaderError.storeNotFound(path: root.path)
    }
    return newest.appendingPathComponent("MailData/Envelope Index")
  }

  // MARK: - Error classification

  static func classifyReadError(_ error: Error, path: String) -> AppleMailReaderError {
    if let readerError = error as? AppleMailReaderError { return readerError }
    let nsError = error as NSError
    if nsError.domain == NSCocoaErrorDomain,
      nsError.code == NSFileReadNoPermissionError || nsError.code == NSFileReadNoSuchFileError
    {
      return nsError.code == NSFileReadNoPermissionError
        ? .authorizationDenied(path: path) : .storeNotFound(path: path)
    }
    if let dbError = error as? DatabaseError {
      // SQLITE_CANTOPEN/SQLITE_PERM/SQLITE_AUTH against a file that is really
      // there is TCC refusing the read, not a corrupt store.
      if [SQLITE_CANTOPEN, SQLITE_PERM, SQLITE_AUTH].contains(dbError.resultCode.rawValue) {
        return MessagesReaderService.storePresence(atPath: path) == .absent
          ? .storeNotFound(path: path) : .authorizationDenied(path: path)
      }
      if dbError.resultCode.rawValue == SQLITE_ERROR,
        dbError.message?.localizedCaseInsensitiveContains("no such table") == true
      {
        return .schemaUnavailable(path: path, detail: dbError.message ?? "missing table")
      }
      return .storeReadFailed(path: path, reason: dbError.message ?? "\(dbError)")
    }
    return .storeReadFailed(path: path, reason: error.localizedDescription)
  }

  // MARK: - Schema probing

  /// Columns this reader needs, and the ones it can do without.
  ///
  /// Mail's schema is Apple's private business and has changed across releases.
  /// Probing it means an OS update degrades to a legible "format not
  /// recognized" instead of a raw SQLite error mid-query — and the optional
  /// columns let the reader keep working with less rather than fail outright.
  struct EnvelopeSchema: Sendable {
    let hasFlags: Bool
    let hasSenderComment: Bool
  }

  static func probeSchema(_ db: Database, path: String) throws -> EnvelopeSchema {
    func columns(of table: String) throws -> Set<String> {
      let rows = try Row.fetchAll(db, sql: "PRAGMA table_info(\(table))")
      return Set(rows.compactMap { $0["name"] as String? })
    }

    let messageColumns = try columns(of: "messages")
    for required in ["ROWID", "subject", "sender", "date_received"] where !messageColumns.contains(required) {
      throw AppleMailReaderError.schemaUnavailable(
        path: path, detail: "messages.\(required) is missing")
    }
    let subjectColumns = try columns(of: "subjects")
    guard subjectColumns.contains("subject") else {
      throw AppleMailReaderError.schemaUnavailable(path: path, detail: "subjects.subject is missing")
    }
    let addressColumns = try columns(of: "addresses")
    guard addressColumns.contains("address") else {
      throw AppleMailReaderError.schemaUnavailable(path: path, detail: "addresses.address is missing")
    }

    return EnvelopeSchema(
      hasFlags: messageColumns.contains("flags"),
      hasSenderComment: addressColumns.contains("comment"))
  }

  // MARK: - Reads

  private func openReadOnlyStore(at url: URL) throws -> DatabaseQueue {
    // Only a genuinely absent store short-circuits; a denial has to reach GRDB
    // so the error carries full_disk_access and its recovery hint.
    guard MessagesReaderService.storePresence(atPath: url.path) != .absent else {
      throw AppleMailReaderError.storeNotFound(path: url.path)
    }
    var configuration = Configuration()
    configuration.readonly = true
    do {
      return try DatabaseQueue(path: url.path, configuration: configuration)
    } catch {
      throw Self.classifyReadError(error, path: url.path)
    }
  }

  /// `storeOverride` exists so the automation-bridge probe can point at a
  /// fixture (or a deliberately absent) index without mutating process
  /// environment shared with the rest of the app.
  func readRecentMessages(limit: Int, storeOverride: URL? = nil) async throws -> [MailMessageRecord] {
    let bounded = max(1, min(limit, 200))
    let url = try storeOverride ?? Self.locateEnvelopeIndex()
    let dbQueue = try openReadOnlyStore(at: url)

    do {
      return try await dbQueue.read { db in
        let schema = try Self.probeSchema(db, path: url.path)
        let comment = schema.hasSenderComment ? "COALESCE(a.comment, '')" : "''"
        let flags = schema.hasFlags ? "COALESCE(m.flags, 0)" : "0"

        let rows = try Row.fetchAll(
          db,
          sql: """
            SELECT
              m.ROWID AS message_id,
              COALESCE(s.subject, '') AS subject,
              COALESCE(a.address, '') AS sender_address,
              \(comment) AS sender_name,
              m.date_received AS received_at,
              \(flags) AS flags
            FROM messages m
            LEFT JOIN subjects s ON m.subject = s.ROWID
            LEFT JOIN addresses a ON m.sender = a.ROWID
            ORDER BY m.date_received DESC
            LIMIT ?
            """,
          arguments: [bounded])

        return rows.map { row in
          let flagBits = row["flags"] as Int64? ?? 0
          return MailMessageRecord(
            id: row["message_id"],
            subject: row["subject"] as String? ?? "",
            senderAddress: row["sender_address"] as String? ?? "",
            senderName: row["sender_name"] as String? ?? "",
            receivedAt: Self.date(fromEnvelopeTimestamp: row["received_at"] as Int64? ?? 0),
            isRead: (flagBits & Self.flagRead) != 0,
            isFlagged: (flagBits & Self.flagFlagged) != 0,
            wasAnswered: (flagBits & Self.flagAnswered) != 0)
        }
      }
    } catch {
      throw Self.classifyReadError(error, path: url.path)
    }
  }

  /// The functional probe INV-INT-1 requires: "connected" means the index
  /// answered a query just now, not that it once did.
  func connectionStatus(storeOverride: URL? = nil) async -> AppleMailConnectionStatus {
    do {
      let messages = try await readRecentMessages(limit: 1, storeOverride: storeOverride)
      return .connected(messageCount: messages.count, verifiedAt: Date())
    } catch let error as AppleMailReaderError {
      let message = error.errorDescription ?? "The Apple Mail index could not be read."
      return error.requiredPermission == nil
        ? .error(message: message, reasonCode: error.reasonCode)
        : .needsAccess(message: message, reasonCode: error.reasonCode)
    } catch {
      let classified = Self.classifyReadError(error, path: "")
      return .error(
        message: classified.errorDescription ?? "The Apple Mail index could not be read.",
        reasonCode: classified.reasonCode)
    }
  }
}
