import Foundation
@preconcurrency import GRDB

/// Read-only access to the local Messages store (`~/Library/Messages/chat.db`).
///
/// Mirrors `AppleNotesReaderService`: the store belongs to another app, so the
/// database is opened read-only and every failure is classified into a reason
/// code the agent can act on rather than a raw SQLite error. Full Disk Access is
/// the usual cause of a denial.
///
/// `OMI_MESSAGES_DB` overrides the store path so contract tests run against a
/// fixture database instead of the developer's real message history.
struct MessageChatRecord: Identifiable, Sendable {
  let id: Int64
  let displayName: String
  let handles: [String]
  let service: String
  let lastMessageAt: Date?
  let lastMessagePreview: String
}

struct MessageRecord: Identifiable, Sendable {
  let id: Int64
  let chatID: Int64
  let handle: String
  let text: String
  let isFromMe: Bool
  let sentAt: Date?
  let service: String
  let attachmentCount: Int
}

enum MessagesReaderError: LocalizedError {
  case storeNotFound(path: String)
  case authorizationDenied(path: String)
  case schemaUnavailable(path: String)
  case storeReadFailed(path: String, reason: String)
  case chatNotFound(reference: String)

  var errorDescription: String? {
    switch self {
    case .storeNotFound:
      return "The Messages database was not found. Messages.app may never have been signed in on this Mac."
    case .authorizationDenied:
      return
        "Omi needs Full Disk Access to read the Messages database. Grant it in System Settings > Privacy & Security > Full Disk Access, then quit and reopen Omi."
    case .schemaUnavailable:
      return "The Messages database format was not recognized."
    case .storeReadFailed(_, let reason):
      return "The Messages database could not be read: \(reason)"
    case .chatNotFound(let reference):
      return "No conversation matched \(reference)."
    }
  }

  var reasonCode: String {
    switch self {
    case .storeNotFound: return "store_not_found"
    case .authorizationDenied: return "authorization_denied"
    case .schemaUnavailable: return "schema_unavailable"
    case .storeReadFailed: return "store_read_failed"
    case .chatNotFound: return "chat_not_found"
    }
  }

  /// Full Disk Access is the only denial the user can fix from a permission prompt.
  var requiredPermission: String? {
    switch self {
    case .authorizationDenied: return "full_disk_access"
    case .storeNotFound, .schemaUnavailable, .storeReadFailed, .chatNotFound: return nil
    }
  }
}

actor MessagesReaderService {
  static let shared = MessagesReaderService()

  /// Apple stores message dates as nanoseconds since 2001-01-01 UTC.
  private static let appleEpochOffset: TimeInterval = 978_307_200
  private static let nanosecondsPerSecond: Double = 1_000_000_000

  static func storeURL() -> URL {
    if let override = ProcessInfo.processInfo.environment["OMI_MESSAGES_DB"], !override.isEmpty {
      return URL(fileURLWithPath: override)
    }
    return FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent("Library/Messages/chat.db")
  }

  /// Converts an Apple absolute timestamp to a `Date`.
  ///
  /// Older rows store seconds and newer rows store nanoseconds, so the
  /// magnitude decides the scale rather than the schema version.
  static func date(fromAppleTimestamp raw: Int64) -> Date? {
    guard raw != 0 else { return nil }
    let value = Double(raw)
    let seconds = value > 1_000_000_000_000 ? value / nanosecondsPerSecond : value
    return Date(timeIntervalSince1970: seconds + appleEpochOffset)
  }

  static func classifyReadError(_ error: Error, path: String) -> MessagesReaderError {
    if let readerError = error as? MessagesReaderError { return readerError }
    let nsError = error as NSError
    if nsError.domain == NSCocoaErrorDomain,
      nsError.code == NSFileReadNoPermissionError || nsError.code == NSFileReadNoSuchFileError
    {
      return nsError.code == NSFileReadNoPermissionError
        ? .authorizationDenied(path: path) : .storeNotFound(path: path)
    }
    if let dbError = error as? DatabaseError {
      // SQLITE_CANTOPEN/SQLITE_PERM/SQLITE_AUTH against an existing file is TCC
      // refusing the read, not a corrupt store.
      if [SQLITE_CANTOPEN, SQLITE_PERM, SQLITE_AUTH].contains(dbError.resultCode.rawValue) {
        return FileManager.default.fileExists(atPath: path)
          ? .authorizationDenied(path: path) : .storeNotFound(path: path)
      }
      if dbError.resultCode.rawValue == SQLITE_ERROR,
        dbError.message?.localizedCaseInsensitiveContains("no such table") == true
      {
        return .schemaUnavailable(path: path)
      }
      return .storeReadFailed(path: path, reason: dbError.message ?? "\(dbError)")
    }
    return .storeReadFailed(path: path, reason: error.localizedDescription)
  }

  private func openReadOnlyStore(at override: URL? = nil) throws -> DatabaseQueue {
    let url = override ?? Self.storeURL()
    guard FileManager.default.fileExists(atPath: url.path) else {
      throw MessagesReaderError.storeNotFound(path: url.path)
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
  /// fixture (or a deliberately absent) database without mutating process
  /// environment shared with the rest of the app.
  func listChats(limit: Int, storeOverride: URL? = nil) async throws -> [MessageChatRecord] {
    let bounded = max(1, min(limit, 100))
    let dbQueue = try openReadOnlyStore(at: storeOverride)
    let path = (storeOverride ?? Self.storeURL()).path
    do {
      return try await dbQueue.read { db in
        let rows = try Row.fetchAll(
          db,
          sql: """
            SELECT
              chat.ROWID AS chat_id,
              COALESCE(NULLIF(chat.display_name, ''), '') AS display_name,
              COALESCE(chat.service_name, '') AS service,
              MAX(message.date) AS last_date,
              (
                SELECT COALESCE(m2.text, '')
                FROM message m2
                JOIN chat_message_join cmj2 ON cmj2.message_id = m2.ROWID
                WHERE cmj2.chat_id = chat.ROWID
                ORDER BY m2.date DESC
                LIMIT 1
              ) AS last_text,
              (
                SELECT GROUP_CONCAT(h.id, ', ')
                FROM chat_handle_join chj
                JOIN handle h ON h.ROWID = chj.handle_id
                WHERE chj.chat_id = chat.ROWID
              ) AS handles
            FROM chat
            JOIN chat_message_join cmj ON cmj.chat_id = chat.ROWID
            JOIN message ON message.ROWID = cmj.message_id
            GROUP BY chat.ROWID
            ORDER BY last_date DESC
            LIMIT ?
            """,
          arguments: [bounded])
        return rows.map { row in
          let handles = (row["handles"] as String? ?? "")
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
          let displayName = row["display_name"] as String? ?? ""
          return MessageChatRecord(
            id: row["chat_id"],
            displayName: displayName.isEmpty ? handles.joined(separator: ", ") : displayName,
            handles: handles,
            service: row["service"] as String? ?? "",
            lastMessageAt: Self.date(fromAppleTimestamp: row["last_date"] as Int64? ?? 0),
            lastMessagePreview: row["last_text"] as String? ?? "")
        }
      }
    } catch {
      throw Self.classifyReadError(error, path: path)
    }
  }

  func readHistory(
    chatID: Int64?, handle: String?, limit: Int, storeOverride: URL? = nil
  ) async throws -> [MessageRecord] {
    let bounded = max(1, min(limit, 200))
    let dbQueue = try openReadOnlyStore(at: storeOverride)
    let path = (storeOverride ?? Self.storeURL()).path
    do {
      return try await dbQueue.read { db in
        let resolvedChatID: Int64
        if let chatID {
          resolvedChatID = chatID
        } else if let handle, !handle.isEmpty {
          guard
            let found = try Int64.fetchOne(
              db,
              sql: """
                SELECT chj.chat_id
                FROM chat_handle_join chj
                JOIN handle h ON h.ROWID = chj.handle_id
                WHERE h.id = ?
                LIMIT 1
                """,
              arguments: [handle])
          else { throw MessagesReaderError.chatNotFound(reference: handle) }
          resolvedChatID = found
        } else {
          throw MessagesReaderError.chatNotFound(reference: "no chat_id or handle")
        }

        let rows = try Row.fetchAll(
          db,
          sql: """
            SELECT
              message.ROWID AS message_id,
              COALESCE(message.text, '') AS text,
              message.is_from_me AS is_from_me,
              message.date AS date,
              COALESCE(message.service, '') AS service,
              COALESCE(handle.id, '') AS handle,
              (
                SELECT COUNT(*)
                FROM message_attachment_join maj
                WHERE maj.message_id = message.ROWID
              ) AS attachment_count
            FROM message
            JOIN chat_message_join cmj ON cmj.message_id = message.ROWID
            LEFT JOIN handle ON handle.ROWID = message.handle_id
            WHERE cmj.chat_id = ?
            ORDER BY message.date DESC
            LIMIT ?
            """,
          arguments: [resolvedChatID, bounded])

        // Query descends so the LIMIT keeps the newest rows; present oldest
        // first so the agent reads the thread in conversation order.
        return rows.reversed().map { row in
          MessageRecord(
            id: row["message_id"],
            chatID: resolvedChatID,
            handle: row["handle"] as String? ?? "",
            text: row["text"] as String? ?? "",
            isFromMe: (row["is_from_me"] as Int64? ?? 0) == 1,
            sentAt: Self.date(fromAppleTimestamp: row["date"] as Int64? ?? 0),
            service: row["service"] as String? ?? "",
            attachmentCount: Int(row["attachment_count"] as Int64? ?? 0))
        }
      }
    } catch {
      throw Self.classifyReadError(error, path: path)
    }
  }
}
