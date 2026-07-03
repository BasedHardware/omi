import Foundation
import GRDB

// MARK: - Errors

enum IMessageSendError: LocalizedError {
  case sendScriptFailed(String)
  case automationDenied
  case emptyText

  var errorDescription: String? {
    switch self {
    case .sendScriptFailed(let detail):
      return "Couldn't send the iMessage: \(detail)"
    case .automationDenied:
      return "Omi needs permission to control Messages (System Settings → Privacy → Automation)."
    case .emptyText:
      return "Nothing to send — the message is empty."
    }
  }
}

// MARK: - Service

/// Native iMessage send + live-receive service, the iMessage counterpart to
/// `TelegramSendService`. Sending goes through Messages.app via AppleScript (there is no
/// public send API); receiving is a lightweight poll of the local `chat.db` for rows that
/// appear after we start listening.
///
/// Deliberately mirrors `TelegramSendService`'s surface so the AI Clone send-mode layer
/// can treat both platforms uniformly:
///   * `send(toHandle:text:)`
///   * `startListening(onNewMessage:)` / `stopListening()`
///
/// The listener callback carries the same `(peerKey, fromMe, text, date)` shape; here the
/// peer key is the iMessage handle (phone/email), which is exactly the AI Clone contact id
/// for iMessage contacts (they are stored unprefixed).
actor IMessageSendService {
  static let shared = IMessageSendService()

  /// Poll cadence for new-message detection. iMessage has no push API we can tap locally,
  /// so we tail the WAL-backed store. 3s keeps replies feeling live without hammering I/O.
  private static let pollInterval: TimeInterval = 3.0

  private var listenerTask: Task<Void, Never>?
  private var onNewMessage: (@Sendable (String, Bool, String, Date) -> Void)?
  /// Highest `message.ROWID` seen so far. Seeded to the current max on first poll so we
  /// never replay history — only messages that arrive after listening starts fire.
  private var lastRowID: Int64 = 0

  // MARK: - Sending

  /// Send a plain-text iMessage to `handle` (a phone number or email) via Messages.app.
  /// Throws `IMessageSendError` on failure; the caller decides how (or whether) to surface it.
  func send(toHandle handle: String, text: String) async throws {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { throw IMessageSendError.emptyText }

    // Handle + text are passed as argv (never interpolated into the script source) so a
    // message body can't break out into AppleScript.
    let script = """
      on run argv
        set targetHandle to item 1 of argv
        set messageText to item 2 of argv
        tell application "Messages"
          set targetService to 1st service whose service type = iMessage
          set targetBuddy to buddy targetHandle of targetService
          send messageText to targetBuddy
        end tell
      end run
      """

    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
    process.arguments = ["-", handle, trimmed]

    let stdin = Pipe()
    let stderr = Pipe()
    process.standardInput = stdin
    process.standardOutput = Pipe()
    process.standardError = stderr

    do {
      try process.run()
    } catch {
      throw IMessageSendError.sendScriptFailed(error.localizedDescription)
    }
    stdin.fileHandleForWriting.write(Data(script.utf8))
    try? stdin.fileHandleForWriting.close()
    process.waitUntilExit()

    guard process.terminationStatus == 0 else {
      let errText = String(
        data: stderr.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      // osascript surfaces the Automation-permission refusal as error -1743.
      if errText.contains("-1743") || errText.localizedCaseInsensitiveContains("not allowed") {
        throw IMessageSendError.automationDenied
      }
      throw IMessageSendError.sendScriptFailed(errText.isEmpty ? "osascript failed" : errText)
    }
  }

  // MARK: - Listening

  /// Begin polling `chat.db` for new direct-thread messages. The callback fires for both
  /// directions (`fromMe` distinguishes them), mirroring `TelegramSendService`. Idempotent —
  /// a second call just replaces the callback; the single poll loop keeps running.
  func startListening(
    onNewMessage: @escaping @Sendable (
      _ handle: String, _ fromMe: Bool, _ text: String, _ date: Date) -> Void
  ) {
    self.onNewMessage = onNewMessage
    guard listenerTask == nil else { return }

    // Seed the baseline synchronously-ish on the first loop tick, then emit only newer rows.
    lastRowID = 0
    listenerTask = Task { [weak self] in
      while !Task.isCancelled {
        await self?.poll()
        try? await Task.sleep(nanoseconds: UInt64(Self.pollInterval * 1_000_000_000))
      }
    }
  }

  func stopListening() {
    listenerTask?.cancel()
    listenerTask = nil
    onNewMessage = nil
    lastRowID = 0
  }

  /// One poll pass: read direct-thread messages with `ROWID > lastRowID`, emit them, and
  /// advance the cursor. The very first pass only establishes the cursor (no emit) so we
  /// don't replay the whole history the moment listening starts.
  private func poll() async {
    guard onNewMessage != nil else { return }
    let path = IMessageReaderService.chatDatabaseURL.path
    guard FileManager.default.fileExists(atPath: path) else { return }

    var configuration = Configuration()
    configuration.readonly = true

    // First pass: cheaply anchor the cursor to the newest row so we never replay history.
    if lastRowID == 0 {
      do {
        let queue = try DatabaseQueue(path: path, configuration: configuration)
        let maxRow = try await queue.read { db in
          try Int64.fetchOne(db, sql: "SELECT MAX(ROWID) FROM message") ?? 0
        }
        lastRowID = max(1, maxRow)
      } catch {
        // Couldn't open (WAL busy / FDA) — retry next tick without advancing.
      }
      return
    }

    let rows: [Row]
    do {
      let queue = try DatabaseQueue(path: path, configuration: configuration)
      let cursor = lastRowID
      rows = try await queue.read { db in
        try Row.fetchAll(
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
                m.date AS date,
                h.id AS handle
              FROM message m
              JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
              JOIN direct_chats dc ON dc.chat_id = cmj.chat_id
              JOIN chat_handle_join chj ON chj.chat_id = cmj.chat_id
              JOIN handle h ON h.ROWID = chj.handle_id
              WHERE m.ROWID > ?
              GROUP BY m.ROWID
              ORDER BY m.ROWID ASC
            """,
          arguments: [cursor]
        )
      }
    } catch {
      // Transient (WAL busy, FDA revoked mid-session) — try again next tick, no banner.
      return
    }

    guard !rows.isEmpty else { return }

    var maxRow = lastRowID
    var events: [(handle: String, fromMe: Bool, text: String, date: Date)] = []
    for row in rows {
      let rowID = (row["row_id"] as? Int64) ?? Int64(row["row_id"] as? Int ?? 0)
      maxRow = max(maxRow, rowID)
      guard let handle = row["handle"] as? String, !handle.isEmpty else { continue }
      let attributed: Data? = row["attributed_body"]
      guard
        let text = IMessageReaderService.decodeMessageText(
          text: row["text"] as? String, attributedBody: attributed)
      else { continue }
      let fromMe =
        ((row["is_from_me"] as? Int64) ?? Int64(row["is_from_me"] as? Int ?? 0)) == 1
      let rawDate = (row["date"] as? Int64) ?? Int64(row["date"] as? Int ?? 0)
      events.append((handle, fromMe, text, Self.date(fromAppleTimestamp: rawDate)))
    }

    lastRowID = maxRow
    guard let onNewMessage else { return }
    for event in events {
      onNewMessage(event.handle, event.fromMe, event.text, event.date)
    }
  }

  /// Same Apple-absolute-time conversion the reader uses (nanoseconds since 2001 on
  /// High Sierra+, seconds on older stores).
  private static func date(fromAppleTimestamp raw: Int64) -> Date {
    guard raw != 0 else { return Date(timeIntervalSinceReferenceDate: 0) }
    let seconds = raw > 1_000_000_000_000 ? Double(raw) / 1_000_000_000.0 : Double(raw)
    return Date(timeIntervalSinceReferenceDate: seconds)
  }
}
