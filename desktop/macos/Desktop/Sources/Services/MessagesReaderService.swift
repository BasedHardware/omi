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

  /// Whether the store is there, missing, or being withheld.
  ///
  /// `FileManager.fileExists` cannot tell the last two apart: when TCC refuses
  /// the lookup for a protected path it reports false for a file that is really
  /// there. Reading errno directly keeps a missing store ("Messages was never
  /// signed in here") distinct from a withheld one ("grant Full Disk Access"),
  /// which is the difference between a dead end and a fixable prompt.
  enum StorePresence {
    case present
    case absent
    case denied
  }

  static func storePresence(atPath path: String) -> StorePresence {
    if access(path, F_OK) == 0 { return .present }
    switch errno {
    case ENOENT, ENOTDIR: return .absent
    default:
      // EACCES/EPERM, and anything else TCC surfaces. Treating an unknown errno
      // as a denial points the user at a permission they can grant instead of
      // telling them their message history does not exist.
      return .denied
    }
  }

  /// Recovers a message body from `message.attributedBody`.
  ///
  /// Modern Messages stores leave `message.text` null on ordinary messages and
  /// keep the content here instead, so reading only `text` returns a thread that
  /// looks empty — worse than an error, because the agent believes it.
  ///
  /// The column holds an `NSArchiver` typedstream, not a keyed archive, so
  /// `NSKeyedUnarchiver` cannot read it and `NSUnarchiver` is unavailable in
  /// Swift. What is stable across versions is the layout around the archived
  /// `NSString`: the class name, a short header, then a length-prefixed UTF-8
  /// run. Lengths of 128 and over switch to a 16-bit little-endian count behind
  /// an `0x81` marker. Anything that does not match returns nil and the caller
  /// falls back to the empty body rather than guessing.
  static func decodeAttributedBody(_ data: Data) -> String? {
    guard let marker = data.range(of: Data("NSString".utf8)) else { return nil }
    var cursor = marker.upperBound + 5
    guard cursor < data.count else { return nil }

    var length = Int(data[cursor])
    cursor += 1
    if length == 0x81 {
      guard cursor + 1 < data.count else { return nil }
      length = Int(data[cursor]) | (Int(data[cursor + 1]) << 8)
      cursor += 2
    }

    guard length > 0, cursor + length <= data.count else { return nil }
    return String(data: data[cursor..<(cursor + length)], encoding: .utf8)
  }

  /// The body to show for a row, preferring `text` and falling back to the
  /// attributed blob.
  static func body(text: String?, attributedBody: Data?) -> String {
    if let text, !text.isEmpty { return text }
    guard let attributedBody, !attributedBody.isEmpty else { return "" }
    return decodeAttributedBody(attributedBody) ?? ""
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
        return storePresence(atPath: path) == .absent
          ? .storeNotFound(path: path) : .authorizationDenied(path: path)
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
    // Only an absent store short-circuits. A denial has to reach GRDB so the
    // error carries the full_disk_access permission and its recovery hint,
    // rather than being reported as a store that was never created.
    guard Self.storePresence(atPath: url.path) != .absent else {
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
                SELECT m2.text
                FROM message m2
                JOIN chat_message_join cmj2 ON cmj2.message_id = m2.ROWID
                WHERE cmj2.chat_id = chat.ROWID
                ORDER BY m2.date DESC
                LIMIT 1
              ) AS last_text,
              (
                SELECT m3.attributedBody
                FROM message m3
                JOIN chat_message_join cmj3 ON cmj3.message_id = m3.ROWID
                WHERE cmj3.chat_id = chat.ROWID
                ORDER BY m3.date DESC
                LIMIT 1
              ) AS last_attributed_body,
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
            lastMessagePreview: Self.body(
              text: row["last_text"] as String?,
              attributedBody: row["last_attributed_body"] as Data?))
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
          // A stale or invented chat_id used to read back as ok with an empty
          // message list, which is indistinguishable from a real quiet thread —
          // and the agent would answer as if it had the context it asked for.
          guard
            try Int64.fetchOne(db, sql: "SELECT ROWID FROM chat WHERE ROWID = ?", arguments: [chatID])
              != nil
          else { throw MessagesReaderError.chatNotFound(reference: "chat_id \(chatID)") }
          resolvedChatID = chatID
        } else if let handle, !handle.isEmpty {
          // One address can belong to a direct thread and any number of group
          // chats. LIMIT 1 with no ordering picked among them arbitrarily, so
          // "read my thread with Sam" could return an unrelated group — the
          // wrong people's messages, and the wrong context to reply from.
          //
          // Direct chats come first (one participant), then the most recently
          // active, so the choice is both right and repeatable.
          guard
            let found = try Int64.fetchOne(
              db,
              sql: """
                SELECT chat.ROWID
                FROM chat
                JOIN chat_handle_join chj ON chj.chat_id = chat.ROWID
                JOIN handle h ON h.ROWID = chj.handle_id
                WHERE h.id = ?
                GROUP BY chat.ROWID
                ORDER BY
                  (SELECT COUNT(*) FROM chat_handle_join c2 WHERE c2.chat_id = chat.ROWID) ASC,
                  (
                    SELECT MAX(m.date)
                    FROM message m
                    JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
                    WHERE cmj.chat_id = chat.ROWID
                  ) DESC,
                  chat.ROWID ASC
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
              message.text AS text,
              message.attributedBody AS attributed_body,
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
            text: Self.body(
              text: row["text"] as String?, attributedBody: row["attributed_body"] as Data?),
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
