import AppKit
import Foundation
import GRDB

// MARK: - Models

/// A single iMessage/SMS correspondent, keyed by their handle (phone number or email).
/// chat.db has no per-contact display names (those live in the Contacts framework /
/// AddressBook, not the Messages store), so `displayName` falls back to the handle
/// unless the correspondent's chat carries a `display_name` (e.g. a named group thread).
struct IMessageContact: Identifiable, Sendable, Hashable {
  /// Stable identifier — the handle string (phone number or email).
  let id: String
  let displayName: String
  let messageCount: Int
}

/// A single message in a conversation.
struct IMessageMessage: Sendable {
  let isFromMe: Bool
  let text: String
  let date: Date
}

enum IMessageReaderError: LocalizedError {
  case chatDatabaseNotFound
  case fullDiskAccessDenied
  case storeUnavailable

  var errorDescription: String? {
    switch self {
    case .chatDatabaseNotFound:
      return "iMessage database (chat.db) not found."
    case .fullDiskAccessDenied:
      return "Full Disk Access is required to read your Messages history."
    case .storeUnavailable:
      return "The iMessage data store is unavailable."
    }
  }
}

// MARK: - Reader

actor IMessageReaderService {
  static let shared = IMessageReaderService()

  /// `~/Library/Messages/chat.db` — an FDA-protected SQLite (WAL) store.
  private var chatDatabaseURL: URL {
    FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent("Library/Messages/chat.db", isDirectory: false)
  }

  // MARK: Full Disk Access
  //
  // macOS provides NO API to *request* Full Disk Access programmatically — unlike
  // microphone/screen-recording/accessibility, there is no TCC prompt to trigger.
  // The only path is to open System Settings → Privacy → Full Disk Access and have
  // the user add the app manually. So "request" here == open that pane.
  //
  // We *detect* whether access is granted the same way AppState.checkFullDiskAccess()
  // does for the badge (probing protected paths), but scoped to what we actually need:
  // attempt a read-only open of chat.db and run a trivial query. If TCC blocks us the
  // open/read throws (SQLITE_CANTOPEN), which we surface as `.fullDiskAccessDenied`.

  /// Returns true if chat.db can actually be opened and read (i.e. FDA is granted).
  func hasFullDiskAccess() -> Bool {
    guard FileManager.default.fileExists(atPath: chatDatabaseURL.path) else {
      // No chat.db at all (Messages never used) — we can't prove access, treat as not granted.
      return false
    }
    do {
      let queue = try makeReadOnlyQueue()
      _ = try queue.read { db in try Int.fetchOne(db, sql: "SELECT 1") }
      return true
    } catch {
      return false
    }
  }

  /// Opens System Settings → Privacy & Security → Full Disk Access so the user can
  /// grant access. This is the closest thing to "requesting" FDA that macOS allows.
  nonisolated func openFullDiskAccessSettings() {
    if let url = URL(
      string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")
    {
      NSWorkspace.shared.open(url)
    }
  }

  // MARK: Queries

  /// Top correspondents ranked by total message count (descending).
  ///
  /// Restricted to 1:1 (direct) threads — a chat with exactly one participant handle.
  /// Group threads are excluded entirely, so a group's messages are never credited to
  /// its individual members. chat.db has no per-contact names, so `displayName` is the
  /// handle (phone/email); real names live in Contacts, not the Messages store.
  func topContacts(limit: Int) async throws -> [IMessageContact] {
    let queue = try makeReadOnlyQueue()
    do {
      return try await queue.read { db in
        let rows = try Row.fetchAll(
          db,
          sql: """
              WITH direct_chats AS (
                SELECT chat_id
                FROM chat_handle_join
                GROUP BY chat_id
                HAVING COUNT(*) = 1
              )
              SELECT
                h.id AS handle,
                COUNT(DISTINCT cmj.message_id) AS message_count
              FROM handle h
              JOIN chat_handle_join chj ON chj.handle_id = h.ROWID
              JOIN direct_chats dc ON dc.chat_id = chj.chat_id
              JOIN chat_message_join cmj ON cmj.chat_id = chj.chat_id
              WHERE h.id IS NOT NULL AND h.id <> ''
              GROUP BY h.id
              ORDER BY message_count DESC
              LIMIT ?
            """,
          arguments: [limit]
        )

        return rows.compactMap { row -> IMessageContact? in
          guard let handle = row["handle"] as? String, !handle.isEmpty else { return nil }

          let count =
            (row["message_count"] as? Int64).map(Int.init)
            ?? (row["message_count"] as? Int ?? 0)

          return IMessageContact(id: handle, displayName: handle, messageCount: count)
        }
      }
    } catch let error as IMessageReaderError {
      throw error
    } catch {
      log("IMessageReaderService: topContacts query failed: \(error)")
      throw IMessageReaderError.storeUnavailable
    }
  }

  /// Most-recent messages for a contact (newest first).
  ///
  /// Restricted to 1:1 (direct) threads only — group threads are excluded, matching
  /// `topContacts()`.
  func messages(for contact: IMessageContact, limit: Int = 500) async throws -> [IMessageMessage] {
    let queue = try makeReadOnlyQueue()
    let handle = contact.id
    do {
      return try await queue.read { db in
        let rows = try Row.fetchAll(
          db,
          sql: """
              WITH direct_chats AS (
                SELECT chat_id
                FROM chat_handle_join
                GROUP BY chat_id
                HAVING COUNT(*) = 1
              )
              SELECT
                m.ROWID AS row_id,
                m.is_from_me AS is_from_me,
                m.text AS text,
                m.attributedBody AS attributed_body,
                m.date AS date
              FROM message m
              JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
              JOIN direct_chats dc ON dc.chat_id = cmj.chat_id
              JOIN chat_handle_join chj ON chj.chat_id = cmj.chat_id
              JOIN handle h ON h.ROWID = chj.handle_id
              WHERE h.id = ?
              GROUP BY m.ROWID
              ORDER BY m.date DESC
              LIMIT ?
            """,
          arguments: [handle, limit]
        )

        return rows.compactMap { row -> IMessageMessage? in
          // Prefer the plain `text` column; when it's null/empty the body lives in the
          // binary `attributedBody` (an archived NSAttributedString written by the
          // rich-text editor), so decode that instead. Skip only if both are unusable.
          let messageText: String
          if let raw = row["text"] as? String,
            !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
          {
            messageText = raw
          } else if let blob: Data = row["attributed_body"],
            let decoded = Self.decodeAttributedBody(blob)
          {
            messageText = decoded
          } else {
            return nil
          }

          let isFromMe =
            ((row["is_from_me"] as? Int64) ?? Int64(row["is_from_me"] as? Int ?? 0)) == 1
          let rawDate = (row["date"] as? Int64) ?? Int64(row["date"] as? Int ?? 0)

          return IMessageMessage(
            isFromMe: isFromMe,
            text: messageText,
            date: Self.date(fromAppleTimestamp: rawDate)
          )
        }
      }
    } catch let error as IMessageReaderError {
      throw error
    } catch {
      log("IMessageReaderService: messages query failed: \(error)")
      throw IMessageReaderError.storeUnavailable
    }
  }

  // MARK: Helpers

  private func makeReadOnlyQueue() throws -> DatabaseQueue {
    guard FileManager.default.fileExists(atPath: chatDatabaseURL.path) else {
      throw IMessageReaderError.chatDatabaseNotFound
    }
    var configuration = Configuration()
    configuration.readonly = true
    do {
      return try DatabaseQueue(path: chatDatabaseURL.path, configuration: configuration)
    } catch {
      // The file exists but we can't open it — almost always missing Full Disk Access.
      log("IMessageReaderService: Failed to open chat.db read-only: \(error)")
      throw IMessageReaderError.fullDiskAccessDenied
    }
  }

  /// Extract the plain-string content from a message's `attributedBody` blob.
  ///
  /// iMessage stores rich-text bodies as an archived `NSAttributedString`. We try the
  /// modern secure keyed-archive path first, then a permissive (non-secure) keyed
  /// unarchive, then a direct parse of the legacy `streamtyped`/`NSArchiver` typedstream
  /// format (very common for iMessage `attributedBody`). Returns nil only when all paths
  /// fail, so the caller skips the message rather than dropping recoverable content.
  private static func decodeAttributedBody(_ data: Data) -> String? {
    guard !data.isEmpty else { return nil }

    func nonEmpty(_ attributed: NSAttributedString) -> String? {
      let string = attributed.string.trimmingCharacters(in: .whitespacesAndNewlines)
      return string.isEmpty ? nil : string
    }

    // Preferred: a modern, secure keyed archive of an NSAttributedString.
    if let attributed = try? NSKeyedUnarchiver.unarchivedObject(
      ofClass: NSAttributedString.self, from: data)
    {
      return nonEmpty(attributed)
    }

    // Fallback: permit non-secure keyed archives (older / wrapped encodings).
    if let unarchiver = try? NSKeyedUnarchiver(forReadingFrom: data) {
      unarchiver.requiresSecureCoding = false
      let root = unarchiver.decodeObject(forKey: NSKeyedArchiveRootObjectKey)
      unarchiver.finishDecoding()
      if let attributed = root as? NSAttributedString {
        return nonEmpty(attributed)
      }
    }

    // Final fallback: legacy typedstream (NSArchiver "streamtyped") blob. NSKeyedUnarchiver
    // cannot read these, so pull the string payload out of the raw bytes directly.
    return decodeTypedStreamString(data)
  }

  /// Extract the first string payload from a legacy `streamtyped` (NSArchiver) blob.
  ///
  /// This is not a general typedstream parser. The layout for an iMessage `attributedBody`
  /// places the message text as a length-prefixed byte string right after the `NSString`
  /// (or `NSMutableString`) class marker: the class name is followed by framing bytes, then
  /// a `+` (0x2b) "bytes" marker, then a variable-length count, then the UTF-8 payload.
  /// We locate that marker and read the count immediately preceding the string.
  private static func decodeTypedStreamString(_ data: Data) -> String? {
    let bytes = [UInt8](data)
    guard let classEnd = indexAfterStringClassMarker(bytes) else { return nil }

    // Scan forward for the first 0x2b ('+') bytes-value marker after the class name.
    var i = classEnd
    while i < bytes.count && bytes[i] != 0x2b { i += 1 }
    guard i < bytes.count else { return nil }
    i += 1  // step past '+'

    guard let (length, valueStart) = readTypedStreamLength(bytes, at: i),
      length > 0,
      valueStart + length <= bytes.count
    else { return nil }

    let payload = bytes[valueStart..<(valueStart + length)]
    let string = String(decoding: payload, as: UTF8.self)
      .trimmingCharacters(in: .whitespacesAndNewlines)
    return string.isEmpty ? nil : string
  }

  /// Find the byte index just past the earliest `NSString` / `NSMutableString` class-name
  /// marker in a typedstream blob.
  private static func indexAfterStringClassMarker(_ bytes: [UInt8]) -> Int? {
    let markers: [[UInt8]] = [Array("NSMutableString".utf8), Array("NSString".utf8)]
    var best: Int? = nil
    for marker in markers {
      if let start = firstIndex(of: marker, in: bytes) {
        let end = start + marker.count
        if best == nil || end < best! { best = end }
      }
    }
    return best
  }

  /// Read a typedstream variable-length integer. Values 0x00–0x80 are stored inline;
  /// 0x81 escapes to a following little-endian UInt16, 0x82 to a UInt32.
  private static func readTypedStreamLength(_ bytes: [UInt8], at index: Int) -> (
    length: Int, next: Int
  )? {
    guard index < bytes.count else { return nil }
    switch bytes[index] {
    case 0x81:
      guard index + 2 < bytes.count else { return nil }
      let value = Int(bytes[index + 1]) | (Int(bytes[index + 2]) << 8)
      return (value, index + 3)
    case 0x82:
      guard index + 4 < bytes.count else { return nil }
      let value =
        Int(bytes[index + 1]) | (Int(bytes[index + 2]) << 8)
        | (Int(bytes[index + 3]) << 16) | (Int(bytes[index + 4]) << 24)
      return (value, index + 5)
    default:
      return (Int(bytes[index]), index + 1)
    }
  }

  /// First index of a byte-sequence needle within a haystack (naive scan; needles are tiny).
  private static func firstIndex(of needle: [UInt8], in haystack: [UInt8]) -> Int? {
    guard !needle.isEmpty, haystack.count >= needle.count else { return nil }
    let last = haystack.count - needle.count
    var i = 0
    while i <= last {
      if haystack[i] == needle[0] {
        var matched = true
        var j = 1
        while j < needle.count {
          if haystack[i + j] != needle[j] {
            matched = false
            break
          }
          j += 1
        }
        if matched { return i }
      }
      i += 1
    }
    return nil
  }

  /// Convert a chat.db `date` value to a `Date`.
  ///
  /// The known quirk: iMessage timestamps are measured from the Mac absolute-time epoch
  /// (2001-01-01 00:00:00 UTC) — the same reference date Foundation uses — NOT the Unix
  /// epoch. macOS High Sierra and later store *nanoseconds*; older versions stored
  /// *seconds*. We detect the unit by magnitude and normalize to seconds before building
  /// the Date via `timeIntervalSinceReferenceDate`.
  private static func date(fromAppleTimestamp raw: Int64) -> Date {
    guard raw != 0 else { return Date(timeIntervalSinceReferenceDate: 0) }
    let seconds: Double
    if raw > 1_000_000_000_000 {
      // Nanoseconds since 2001-01-01 (High Sierra+).
      seconds = Double(raw) / 1_000_000_000.0
    } else {
      // Legacy: seconds since 2001-01-01.
      seconds = Double(raw)
    }
    return Date(timeIntervalSinceReferenceDate: seconds)
  }
}
