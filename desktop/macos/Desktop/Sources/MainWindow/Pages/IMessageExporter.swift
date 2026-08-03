import Foundation
import GRDB

/// Minimal, opt-in exporter that reads the local Messages database
/// (`~/Library/Messages/chat.db`, which needs Full Disk Access) and writes
/// per-contact aggregates to
/// `~/Library/Application Support/Omi/users/<uid>/imessage_export.json`.
///
/// Gated entirely behind the `peopleIMessageExport` UserDefaults flag (default
/// false) — it never runs unless a developer explicitly opts in. To avoid WAL/lock
/// issues it copies the live database plus its `-wal`/`-shm` sidecars into a
/// throwaway temp dir and opens the copy read-only, so it never touches, locks, or
/// mutates the user's real database.
enum IMessageExporter {
  /// Entry point. Cheap flag + throttle check on the caller's thread, then all blocking work
  /// (copy + SQLite reads + JSON write) runs off the main thread, awaited so a caller can sequence
  /// the graph rebuild after the export completes. Self-throttles so re-running from frequent
  /// data-arrival triggers stays cheap; new messages are picked up on the next run past the window.
  /// Pass `force: true` to bypass the throttle (e.g. right after opt-in).
  static func exportIfRequested(force: Bool = false) async {
    guard UserDefaults.standard.bool(forKey: .peopleIMessageExport) else { return }
    guard PeopleGraphBuilder.claimRun(.peopleIMessageExportLastRun, force: force) else { return }
    await Task.detached(priority: .utility) {
      runExport()
    }.value
  }

  // MARK: - Orchestration

  private static func runExport() {
    let iso = ISO8601DateFormatter()
    iso.formatOptions = [.withInternetDateTime]
    let generatedAt = iso.string(from: Date())

    guard let outputURL = resolveOutputURL() else {
      log("IMessageExporter: no signed-in user directory resolved; skipping export")
      return
    }

    let chatDB = FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent("Library/Messages/chat.db")

    let tempDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-imsg-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: tempDir) }

    let dbQueue: DatabaseQueue
    do {
      dbQueue = try openReadOnlyCopy(of: chatDB, into: tempDir)
    } catch {
      writeError(
        "Couldn't open Messages database: \(error.localizedDescription)",
        generatedAt: generatedAt, to: outputURL)
      log("IMessageExporter: open failed: \(error)")
      return
    }

    do {
      let (total, handles, groups) = try aggregate(from: dbQueue, iso: iso)
      try write(generatedAt: generatedAt, totalMessages: total, handles: handles, groups: groups, to: outputURL)
      log(
        "IMessageExporter: wrote \(handles.count) handles, \(groups.count) groups (\(total) messages) to \(outputURL.path)"
      )
    } catch {
      writeError(
        "Couldn't read Messages database: \(error.localizedDescription)",
        generatedAt: generatedAt, to: outputURL)
      log("IMessageExporter: read failed: \(error)")
    }
  }

  /// Copies `chat.db` (+ `-wal`/`-shm` sidecars) into `tempDir` and opens the copy
  /// read-only. Copying the sidecars ensures the newest messages (still in the WAL)
  /// are included without opening the live database. Shared with `PeopleThreadIngest`
  /// so both read the Messages DB through the same never-touch-the-original path.
  static func openReadOnlyCopy(of dbURL: URL, into tempDir: URL) throws -> DatabaseQueue {
    let fm = FileManager.default
    try fm.createDirectory(at: tempDir, withIntermediateDirectories: true)
    let dest = tempDir.appendingPathComponent("chat.db")
    try fm.copyItem(at: dbURL, to: dest)
    for suffix in ["-wal", "-shm"] {
      let side = URL(fileURLWithPath: dbURL.path + suffix)
      if fm.fileExists(atPath: side.path) {
        try? fm.copyItem(at: side, to: URL(fileURLWithPath: dest.path + suffix))
      }
    }
    var config = Configuration()
    config.readonly = true
    return try DatabaseQueue(path: dest.path, configuration: config)
  }

  // MARK: - Aggregation

  private struct Agg {
    var messageCount = 0
    var sent = 0
    var received = 0
    var firstDate: Int64 = .max
    var lastDate: Int64 = .min
    var isGroup = false
  }

  private static func aggregate(from dbQueue: DatabaseQueue, iso: ISO8601DateFormatter) throws
    -> (total: Int, handles: [ExportHandle], groups: [ExportGroup])
  {
    try dbQueue.read { db -> (Int, [ExportHandle], [ExportGroup]) in
      // Which chats are groups (style 43, `;+;` guid, `chat…` identifier, or >1 member).
      // Also keep each chat's guid + display name so we can emit group membership.
      var groupChat: [Int64: Bool] = [:]
      var chatGuid: [Int64: String] = [:]
      var chatDisplayName: [Int64: String] = [:]
      let chatCursor = try Row.fetchCursor(
        db, sql: "SELECT ROWID AS cid, guid, chat_identifier AS ident, display_name AS dname, style FROM chat")
      while let row = try chatCursor.next() {
        let cid = int64(row, "cid")
        let guid = row["guid"] as? String ?? ""
        let ident = row["ident"] as? String ?? ""
        chatGuid[cid] = guid
        chatDisplayName[cid] = (row["dname"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        groupChat[cid] = int64(row, "style") == 43 || guid.contains(";+;") || ident.hasPrefix("chat")
      }

      // Participants per chat. For a 1:1 chat this is the single counterparty we
      // attribute outbound messages to (their `message.handle_id` is 0).
      var participants: [Int64: [String]] = [:]
      let partCursor = try Row.fetchCursor(
        db,
        sql: """
            SELECT chj.chat_id AS cid, h.id AS handle
            FROM chat_handle_join chj JOIN handle h ON h.ROWID = chj.handle_id
          """)
      while let row = try partCursor.next() {
        guard let h = (row["handle"] as? String)?.trimmingCharacters(in: .whitespaces), !h.isEmpty else { continue }
        let cid = int64(row, "cid")
        if !(participants[cid]?.contains(h) ?? false) { participants[cid, default: []].append(h) }
      }
      for (cid, list) in participants where list.count > 1 { groupChat[cid] = true }

      // Group membership: every group chat with >=2 participant handles becomes an
      // entry for the people-to-people social graph. Members carry their handle plus
      // a `phone_last10` key (nil for emails/short codes).
      let groups: [ExportGroup] =
        participants
        .compactMap { cid, list -> ExportGroup? in
          guard groupChat[cid] == true, list.count >= 2 else { return nil }
          let members = list.map { ExportGroupMember(handle: $0, phoneLast10: phoneLast10($0)) }
          return ExportGroup(
            chatGuid: chatGuid[cid] ?? "",
            displayName: chatDisplayName[cid] ?? "",
            memberCount: members.count,
            members: members)
        }
        .sorted { $0.memberCount > $1.memberCount }

      // Pass 1 — counts + date range, streamed (no text) to bound memory.
      var aggs: [String: Agg] = [:]
      var total = 0
      var seen = Set<Int64>()
      let countCursor = try Row.fetchCursor(
        db,
        sql: """
            SELECT m.ROWID AS rowid, m.is_from_me AS from_me, m.date AS date,
                   h.id AS handle, cmj.chat_id AS cid
            FROM message m
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            WHERE (m.associated_message_type = 0 OR m.associated_message_type IS NULL)
          """)
      while let row = try countCursor.next() {
        let rowid = int64(row, "rowid")
        if seen.contains(rowid) { continue }  // a message could appear once per chat join
        seen.insert(rowid)
        total += 1
        let fromMe = int64(row, "from_me") == 1
        let cid = int64(row, "cid")
        guard
          let cp = counterparty(
            messageHandle: row["handle"] as? String, chatID: cid, participants: participants)
        else { continue }
        var a = aggs[cp] ?? Agg()
        a.messageCount += 1
        if fromMe { a.sent += 1 } else { a.received += 1 }
        let date = int64(row, "date")
        if date < a.firstDate { a.firstDate = date }
        if date > a.lastDate { a.lastDate = date }
        if cid != 0, groupChat[cid] == true { a.isGroup = true }
        aggs[cp] = a
      }

      let handles =
        aggs
        .map { key, a -> ExportHandle in
          ExportHandle(
            handle: key,
            phoneLast10: phoneLast10(key),
            messageCount: a.messageCount,
            sent: a.sent,
            received: a.received,
            firstDate: a.firstDate == .max ? nil : isoString(appleTime: a.firstDate, iso: iso),
            lastDate: a.lastDate == .min ? nil : isoString(appleTime: a.lastDate, iso: iso),
            isGroup: a.isGroup)
        }
        .sorted { $0.messageCount > $1.messageCount }
      return (total, handles, groups)
    }
  }

  /// The counterparty handle a message is attributed to. Inbound messages (and
  /// group senders) carry their handle directly; outbound 1:1 messages have
  /// `handle_id == 0`, so we attribute them to the chat's single participant.
  /// Outbound group messages have no single recipient and are skipped.
  private static func counterparty(messageHandle: String?, chatID: Int64, participants: [Int64: [String]])
    -> String?
  {
    if let h = messageHandle?.trimmingCharacters(in: .whitespaces), !h.isEmpty { return h }
    guard chatID != 0, let list = participants[chatID], list.count == 1 else { return nil }
    return list[0]
  }

  // MARK: - Helpers

  private static func int64(_ row: Row, _ column: String) -> Int64 {
    (row[column] as? Int64) ?? Int64(row[column] as? Int ?? 0)
  }

  /// `message.date` is nanoseconds since the 2001 reference date on modern macOS;
  /// legacy databases store seconds. Convert either to an ISO 8601 string.
  private static func isoString(appleTime raw: Int64, iso: ISO8601DateFormatter) -> String {
    let seconds = raw > 1_000_000_000_000 ? Double(raw) / 1_000_000_000.0 : Double(raw)
    return iso.string(from: Date(timeIntervalSinceReferenceDate: seconds))
  }

  /// Last 10 digits of a phone handle (a stable cross-format key), or nil for
  /// emails and short codes with fewer than 10 digits.
  private static func phoneLast10(_ handle: String) -> String? {
    if handle.contains("@") { return nil }
    let digits = handle.filter { $0.isNumber }
    guard digits.count >= 10 else { return nil }
    return String(digits.suffix(10))
  }

  // MARK: - Output

  /// `~/Library/Application Support/Omi/users/<uid>/imessage_export.json`. Prefers
  /// the signed-in uid; otherwise reuses the directory that already holds
  /// `people_intelligence.json` (mirrors PeopleViewModel's file resolution).
  private static func resolveOutputURL() -> URL? {
    let fm = FileManager.default
    guard let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else { return nil }
    let usersDir = support.appendingPathComponent("Omi/users", isDirectory: true)

    if let uid = UserDefaults.standard.string(forKey: .authUserId), !uid.isEmpty {
      let dir = usersDir.appendingPathComponent(uid, isDirectory: true)
      try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
      return dir.appendingPathComponent("imessage_export.json")
    }
    if let entries = try? fm.contentsOfDirectory(
      at: usersDir, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles])
    {
      for entry in entries
      where fm.fileExists(atPath: entry.appendingPathComponent("people_intelligence.json").path) {
        return entry.appendingPathComponent("imessage_export.json")
      }
    }
    return nil
  }

  private static func write(
    generatedAt: String, totalMessages: Int, handles: [ExportHandle], groups: [ExportGroup], to url: URL
  ) throws {
    try encode(
      ExportFile(
        generatedAt: generatedAt, totalMessages: totalMessages, error: nil, handles: handles, groups: groups),
      to: url)
  }

  private static func writeError(_ message: String, generatedAt: String, to url: URL) {
    try? encode(
      ExportFile(generatedAt: generatedAt, totalMessages: 0, error: message, handles: [], groups: []), to: url)
  }

  private static func encode(_ file: ExportFile, to url: URL) throws {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    let data = try encoder.encode(file)
    try FileManager.default.createDirectory(
      at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    try data.write(to: url, options: .atomic)
  }

  private struct ExportFile: Encodable {
    let generatedAt: String
    let totalMessages: Int
    let error: String?
    let handles: [ExportHandle]
    let groups: [ExportGroup]

    enum CodingKeys: String, CodingKey {
      case generatedAt = "generated_at"
      case totalMessages = "total_messages"
      case error
      case handles
      case groups
    }

    func encode(to encoder: Encoder) throws {
      var c = encoder.container(keyedBy: CodingKeys.self)
      try c.encode(generatedAt, forKey: .generatedAt)
      try c.encode(totalMessages, forKey: .totalMessages)
      try c.encodeIfPresent(error, forKey: .error)
      try c.encode(handles, forKey: .handles)
      try c.encode(groups, forKey: .groups)
    }
  }

  private struct ExportHandle: Encodable {
    let handle: String
    let phoneLast10: String?
    let messageCount: Int
    let sent: Int
    let received: Int
    let firstDate: String?
    let lastDate: String?
    let isGroup: Bool

    enum CodingKeys: String, CodingKey {
      case handle
      case phoneLast10 = "phone_last10"
      case messageCount = "message_count"
      case sent
      case received
      case firstDate = "first_date"
      case lastDate = "last_date"
      case isGroup = "is_group"
    }
  }

  /// A group chat and its participant handles, for the people-to-people social graph.
  private struct ExportGroup: Encodable {
    let chatGuid: String
    let displayName: String
    let memberCount: Int
    let members: [ExportGroupMember]

    enum CodingKeys: String, CodingKey {
      case chatGuid = "chat_guid"
      case displayName = "display_name"
      case memberCount = "member_count"
      case members
    }
  }

  private struct ExportGroupMember: Encodable {
    let handle: String
    let phoneLast10: String?

    enum CodingKeys: String, CodingKey {
      case handle
      case phoneLast10 = "phone_last10"
    }
  }
}
