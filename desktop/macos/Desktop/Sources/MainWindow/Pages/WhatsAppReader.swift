import Foundation
import GRDB

/// Minimal, opt-in reader that reads WhatsApp's local Core Data database
/// (`~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite`,
/// readable with the same Full Disk Access grant iMessage uses) and writes per-contact
/// and per-group aggregates to
/// `~/Library/Application Support/Omi/users/<uid>/whatsapp_export.json`.
///
/// The output uses the **same shape** as `imessage_export.json` so `PeopleGraphBuilder`
/// can merge it into the identical canonical-people + edge + community computation — a
/// person who appears on both channels resolves to one node, and WhatsApp group
/// co-membership contributes real "who-knows-whom" edges.
///
/// Gated behind the same `peopleIMessageExport` consent flag as the iMessage exporter
/// (Full Disk Access is a single grant, so opting in to on-device message mapping enables
/// both connectors) plus its own throttle key. To avoid WAL/lock issues it copies the live
/// database (and WhatsApp's `LID.sqlite` privacy-ID bridge) into a throwaway temp dir and
/// opens the copies read-only via `IMessageExporter.openReadOnlyCopy`, so it never touches,
/// locks, or mutates WhatsApp's real databases.
///
/// This export carries **metadata only** — contact/group names, phone tails, message counts
/// and dates. No message text ever leaves ChatStorage, mirroring the iMessage export.
enum WhatsAppReader {
  /// Entry point. Cheap flag + throttle check on the caller's thread, then all blocking work
  /// (copy + SQLite reads + JSON write) runs off the main thread, awaited so a caller can sequence
  /// the graph rebuild after the export completes. Self-throttles so re-running from frequent
  /// data-arrival triggers stays cheap. Pass `force: true` to bypass the throttle (e.g. right
  /// after opt-in).
  static func exportIfRequested(force: Bool = false) async {
    // Same consent gate as iMessage: Full Disk Access is one grant, so enabling on-device
    // message mapping authorizes reading WhatsApp's container too.
    guard UserDefaults.standard.bool(forKey: .peopleIMessageExport) else { return }
    guard PeopleGraphBuilder.claimRun(.peopleWhatsAppExportLastRun, force: force) else { return }
    await Task.detached(priority: .utility) {
      runExport()
    }.value
  }

  // MARK: - Paths

  private static var groupContainer: URL {
    FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent("Library/Group Containers/group.net.whatsapp.WhatsApp.shared", isDirectory: true)
  }

  // MARK: - Orchestration

  private static func runExport() {
    let iso = ISO8601DateFormatter()
    iso.formatOptions = [.withInternetDateTime]
    let generatedAt = iso.string(from: Date())

    guard let outputURL = resolveOutputURL() else {
      log("WhatsAppReader: no signed-in user directory resolved; skipping export")
      return
    }

    let chatDB = groupContainer.appendingPathComponent("ChatStorage.sqlite")
    // WhatsApp not installed (or container never created) is normal, not an error — leave any
    // previous export untouched so the graph keeps using it, and produce no misleading error file.
    guard FileManager.default.fileExists(atPath: chatDB.path) else {
      log("WhatsAppReader: ChatStorage.sqlite not present; skipping (WhatsApp not installed)")
      return
    }
    let lidDB = groupContainer.appendingPathComponent("LID.sqlite")

    let tempDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-wa-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: tempDir) }

    let chatQueue: DatabaseQueue
    do {
      chatQueue = try IMessageExporter.openReadOnlyCopy(of: chatDB, into: tempDir)
    } catch {
      writeError(
        "Couldn't open WhatsApp database: \(error.localizedDescription)",
        generatedAt: generatedAt, to: outputURL)
      log("WhatsAppReader: open failed: \(error)")
      return
    }

    // The LID → phone bridge is best-effort: newer WhatsApp identifies members by `@lid` privacy
    // IDs, and this table maps them back to phone numbers. A missing/unreadable bridge just means
    // those members stay keyed by their opaque LID (still a stable identity) rather than by phone.
    let lidBridge = loadLIDBridge(from: lidDB, into: tempDir)

    do {
      let (total, handles, groups) = try aggregate(from: chatQueue, lidBridge: lidBridge, iso: iso)
      try write(generatedAt: generatedAt, totalMessages: total, handles: handles, groups: groups, to: outputURL)
      log(
        "WhatsAppReader: wrote \(handles.count) handles, \(groups.count) groups (\(total) messages, "
          + "\(lidBridge.count / 2) LID bridges) to \(outputURL.path)")
    } catch {
      writeError(
        "Couldn't read WhatsApp database: \(error.localizedDescription)",
        generatedAt: generatedAt, to: outputURL)
      log("WhatsAppReader: read failed: \(error)")
    }
  }

  // MARK: - LID → phone bridge

  /// Loads WhatsApp's `LID.sqlite` `ZWAZACCOUNT` table (privacy-ID → phone). Keyed by both the full
  /// `<id>@lid` identifier and its numeric local part so a member JID resolves either way. Returns an
  /// empty map (never throws) when the bridge is absent/unreadable — WhatsApp is usable without it.
  static func loadLIDBridge(from lidDB: URL, into parentTemp: URL) -> [String: String] {
    guard FileManager.default.fileExists(atPath: lidDB.path) else { return [:] }
    let tempDir = parentTemp.appendingPathComponent("lid-\(UUID().uuidString)", isDirectory: true)
    let queue: DatabaseQueue
    do {
      queue = try IMessageExporter.openReadOnlyCopy(of: lidDB, into: tempDir)
    } catch {
      log("WhatsAppReader: LID bridge open failed: \(error)")
      return [:]
    }
    var map: [String: String] = [:]
    do {
      try queue.read { db in
        let cursor = try Row.fetchCursor(
          db, sql: "SELECT ZIDENTIFIER AS ident, ZPHONENUMBER AS phone FROM ZWAZACCOUNT WHERE ZPHONENUMBER IS NOT NULL")
        while let row = try cursor.next() {
          guard let ident = (row["ident"] as? String)?.lowercased(), !ident.isEmpty,
            let phone = (row["phone"] as? String)?.trimmingCharacters(in: .whitespaces), !phone.isEmpty
          else { continue }
          map[ident] = phone
          let local = String(ident.prefix { $0 != "@" })
          if !local.isEmpty { map[local] = phone }
        }
      }
    } catch {
      log("WhatsAppReader: LID bridge read failed: \(error)")
    }
    return map
  }

  // MARK: - Aggregation

  private struct Member {
    let handle: String
    let phoneLast10: String?
  }

  private static func aggregate(from chatDB: DatabaseQueue, lidBridge: [String: String], iso: ISO8601DateFormatter)
    throws -> (total: Int, handles: [ExportHandle], groups: [ExportGroup])
  {
    try chatDB.read { db -> (Int, [ExportHandle], [ExportGroup]) in
      // ---- sessions: one row per chat (1:1 partner or group) ----
      var sessionJID: [Int64: String] = [:]
      var sessionName: [Int64: String] = [:]
      var sessionCount: [Int64: Int] = [:]
      var sessionLast: [Int64: Double] = [:]  // Apple reference-date seconds
      var isGroup: [Int64: Bool] = [:]
      let sessionCursor = try Row.fetchCursor(
        db,
        sql: """
            SELECT Z_PK AS pk, ZCONTACTJID AS jid, ZPARTNERNAME AS name,
                   ZMESSAGECOUNTER AS cnt, ZLASTMESSAGEDATE AS last
            FROM ZWACHATSESSION
          """)
      while let row = try sessionCursor.next() {
        let jid = (row["jid"] as? String)?.trimmingCharacters(in: .whitespaces) ?? ""
        guard isRealContactJID(jid) else { continue }  // skip @status / @broadcast / @newsletter
        let pk = int64(row, "pk")
        sessionJID[pk] = jid
        sessionName[pk] = (row["name"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        sessionCount[pk] = max(Int(int64(row, "cnt")), 0)
        if let last = appleSeconds(row["last"]) { sessionLast[pk] = last }
        isGroup[pk] = jid.lowercased().hasSuffix("@g.us")
      }

      // ---- group membership: resolve each member JID to a phone tail via the LID bridge ----
      var membersByGroup: [Int64: [Member]] = [:]
      let memberCursor = try Row.fetchCursor(
        db, sql: "SELECT ZCHATSESSION AS gs, ZMEMBERJID AS mjid FROM ZWAGROUPMEMBER")
      while let row = try memberCursor.next() {
        let gs = int64(row, "gs")
        guard isGroup[gs] == true else { continue }
        guard let mjid = (row["mjid"] as? String)?.trimmingCharacters(in: .whitespaces), !mjid.isEmpty else {
          continue
        }
        let digits = phoneDigits(forJID: mjid, lidBridge: lidBridge)
        let handle = digits.map { "+\($0)" } ?? mjid
        membersByGroup[gs, default: []].append(Member(handle: handle, phoneLast10: digits.flatMap(last10)))
      }

      // ---- groups: every group with >=2 distinct resolved members feeds the social graph ----
      let groups: [ExportGroup] =
        sessionJID
        .compactMap { pk, jid -> ExportGroup? in
          guard isGroup[pk] == true else { return nil }
          var seen = Set<String>()
          var members: [ExportGroupMember] = []
          for m in membersByGroup[pk] ?? [] {
            let key = m.phoneLast10 ?? m.handle.lowercased()
            if seen.contains(key) { continue }
            seen.insert(key)
            members.append(ExportGroupMember(handle: m.handle, phoneLast10: m.phoneLast10))
          }
          guard members.count >= 2 else { return nil }
          return ExportGroup(
            chatGuid: jid, displayName: sessionName[pk] ?? "", memberCount: members.count, members: members)
        }
        .sorted { $0.memberCount > $1.memberCount }

      // ---- handles: one per 1:1 partner (groups are represented above, not as handles) ----
      var handles: [ExportHandle] = []
      var total = 0
      for (pk, jid) in sessionJID where isGroup[pk] != true {
        let name = sessionName[pk] ?? ""
        let digits = phoneDigits(forJID: jid, lidBridge: lidBridge)
        let p10 = digits.flatMap(last10)
        // Need at least one durable identity key — a phone tail or a human name. A bare, unbridged
        // LID with no partner name is unattributable, so skip it rather than mint a junk node.
        guard p10 != nil || !name.isEmpty else { continue }
        let handleString: String
        if let d = digits {
          handleString = "+\(d)"
        } else if !name.isEmpty {
          handleString = name
        } else {
          handleString = jid
        }
        let count = sessionCount[pk] ?? 0
        total += count
        let last = sessionLast[pk].map { iso.string(from: Date(timeIntervalSinceReferenceDate: $0)) }
        handles.append(
          ExportHandle(
            handle: handleString,
            phoneLast10: p10,
            contactName: name.isEmpty ? nil : name,
            messageCount: count,
            lastDate: last,
            isGroup: false))
      }
      handles.sort { $0.messageCount > $1.messageCount }

      return (total, handles, groups)
    }
  }

  // MARK: - JID helpers

  /// True for JIDs that identify a real person or group we want in the graph. Filters WhatsApp's
  /// non-contact JIDs (status updates, broadcast lists, newsletters, official/system accounts).
  static func isRealContactJID(_ jid: String) -> Bool {
    let lower = jid.lowercased()
    guard lower.contains("@") else { return false }
    return lower.hasSuffix("@g.us") || lower.hasSuffix("@s.whatsapp.net") || lower.hasSuffix("@lid")
  }

  /// The E.164-style digit string a JID maps to, or nil. `@s.whatsapp.net` JIDs carry the phone in
  /// their local part; `@lid` privacy JIDs are resolved through the `LID.sqlite` bridge. Requires at
  /// least 10 digits so short codes / system JIDs don't masquerade as phone numbers.
  static func phoneDigits(forJID jid: String, lidBridge: [String: String]) -> String? {
    let lower = jid.lowercased()
    let local = String(lower.prefix { $0 != "@" })
    if lower.hasSuffix("@s.whatsapp.net") {
      let digits = local.filter { $0.isNumber }
      return digits.count >= 10 ? digits : nil
    }
    if lower.hasSuffix("@lid") {
      guard let phone = lidBridge[local] ?? lidBridge[lower] else { return nil }
      let digits = phone.filter { $0.isNumber }
      return digits.count >= 10 ? digits : nil
    }
    return nil
  }

  /// Last 10 digits of a digit string (a stable cross-format key), or nil below 10 digits — same
  /// rule the iMessage exporter uses for `phone_last10`.
  static func last10(_ digits: String) -> String? {
    let d = digits.filter { $0.isNumber }
    return d.count >= 10 ? String(d.suffix(10)) : nil
  }

  private static func int64(_ row: Row, _ column: String) -> Int64 {
    (row[column] as? Int64) ?? Int64(row[column] as? Int ?? 0)
  }

  // MARK: - Deep-ingest reads (1:1 message TEXT, on-device only)
  //
  // The metadata export above never carries message text. `PeopleThreadIngest` needs the actual
  // words to route a relationship through Omi's conversation→memory extraction, so these helpers
  // read a bounded window of a 1:1 chat's text off a throwaway read-only copy — same isolation as
  // `runExport`. Nothing is written to disk here; the transcript is handed to the ingester in memory
  // and redacted before it leaves the machine.

  /// A named 1:1 WhatsApp chat, ready for deep ingest. `contactName` is WhatsApp's own
  /// `ZPARTNERNAME`, so we get a human label without Contacts access.
  struct OneToOneThread: Equatable {
    let sessionPK: Int64
    let contactName: String
    let phoneLast10: String?
    let messageCount: Int
    let lastDate: String
  }

  /// One decoded WhatsApp message: `fromMe` distinguishes the user; `date` is ISO-8601.
  struct WAMessage: Equatable {
    let fromMe: Bool
    let text: String
    let date: String
  }

  /// Open a throwaway read-only copy of WhatsApp's `ChatStorage.sqlite`. Returns nil when WhatsApp
  /// isn't installed or the copy can't be opened (no Full Disk Access). Caller owns nothing to clean
  /// up beyond process temp.
  private static func openChatDBReadOnly() -> DatabaseQueue? {
    let chatDB = groupContainer.appendingPathComponent("ChatStorage.sqlite")
    guard FileManager.default.fileExists(atPath: chatDB.path) else { return nil }
    let tempDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-wa-ingest-\(UUID().uuidString)", isDirectory: true)
    return try? IMessageExporter.openReadOnlyCopy(of: chatDB, into: tempDir)
  }

  /// Enumerate substantial **1:1** WhatsApp chats that carry a partner name — the deep-ingest
  /// candidates. Groups are excluded (they feed the graph, not per-person memories). Guarded: no DB /
  /// no access returns empty.
  static func readOneToOneThreads() -> [OneToOneThread] {
    guard let dbQueue = openChatDBReadOnly() else { return [] }
    let iso = ISO8601DateFormatter()
    iso.formatOptions = [.withInternetDateTime]
    return
      (try? dbQueue.read { db -> [OneToOneThread] in
        var out: [OneToOneThread] = []
        let cursor = try Row.fetchCursor(
          db,
          sql: """
              SELECT Z_PK AS pk, ZCONTACTJID AS jid, ZPARTNERNAME AS name,
                     ZMESSAGECOUNTER AS cnt, ZLASTMESSAGEDATE AS last
              FROM ZWACHATSESSION
            """)
        while let row = try cursor.next() {
          let jid = (row["jid"] as? String)?.trimmingCharacters(in: .whitespaces) ?? ""
          guard isRealContactJID(jid), !jid.lowercased().hasSuffix("@g.us") else { continue }  // 1:1 only
          let name = (row["name"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
          guard !name.isEmpty else { continue }  // need a human label
          let pk = int64(row, "pk")
          let count = max(Int(int64(row, "cnt")), 0)
          // `@s.whatsapp.net` JIDs carry the phone directly; `@lid` needs the bridge we don't load
          // here (a name is enough to label + ingest).
          let digits =
            jid.lowercased().hasSuffix("@s.whatsapp.net")
            ? String(jid.prefix { $0 != "@" }).filter { $0.isNumber } : ""
          let p10 = last10(digits)
          let last = appleSeconds(row["last"]).map { iso.string(from: Date(timeIntervalSinceReferenceDate: $0)) } ?? ""
          out.append(
            OneToOneThread(sessionPK: pk, contactName: name, phoneLast10: p10, messageCount: count, lastDate: last))
        }
        return out
      }) ?? []
  }

  /// Read the most-recent `limit` text messages of a 1:1 chat, chronological. Media-only rows (no
  /// `ZTEXT`) are skipped. Guarded like the rest of the reader.
  static func readThreadMessages(sessionPK: Int64, limit: Int) -> [WAMessage] {
    guard let dbQueue = openChatDBReadOnly() else { return [] }
    let iso = ISO8601DateFormatter()
    iso.formatOptions = [.withInternetDateTime]
    let recentDesc: [WAMessage] =
      (try? dbQueue.read { db -> [WAMessage] in
        var out: [WAMessage] = []
        let cursor = try Row.fetchCursor(
          db,
          sql: """
              SELECT ZTEXT AS text, ZISFROMME AS from_me, ZMESSAGEDATE AS date
              FROM ZWAMESSAGE
              WHERE ZCHATSESSION = ? AND ZTEXT IS NOT NULL AND length(trim(ZTEXT)) > 0
              ORDER BY ZMESSAGEDATE DESC
              LIMIT ?
            """,
          arguments: [sessionPK, limit])
        while let row = try cursor.next() {
          guard let text = (row["text"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty
          else { continue }
          let date = appleSeconds(row["date"]).map { iso.string(from: Date(timeIntervalSinceReferenceDate: $0)) } ?? ""
          out.append(WAMessage(fromMe: int64(row, "from_me") == 1, text: text, date: date))
        }
        return out
      }) ?? []
    return recentDesc.reversed()
  }

  /// WhatsApp `TIMESTAMP` columns are Core Data reference-date seconds (Double); guard against them
  /// arriving as Int as well. Returns nil for a missing/zero date.
  private static func appleSeconds(_ value: DatabaseValueConvertible?) -> Double? {
    let seconds: Double
    if let d = value as? Double {
      seconds = d
    } else if let i = value as? Int64 {
      seconds = Double(i)
    } else if let i = value as? Int {
      seconds = Double(i)
    } else {
      return nil
    }
    return seconds > 0 ? seconds : nil
  }

  // MARK: - Output

  /// `~/Library/Application Support/Omi/users/<uid>/whatsapp_export.json`. Prefers the signed-in
  /// uid; otherwise reuses the directory that already holds `people_intelligence.json` — mirrors
  /// `IMessageExporter.resolveOutputURL`.
  private static func resolveOutputURL() -> URL? {
    let fm = FileManager.default
    guard let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else { return nil }
    let usersDir = support.appendingPathComponent("Omi/users", isDirectory: true)

    if let uid = UserDefaults.standard.string(forKey: .authUserId), !uid.isEmpty {
      let dir = usersDir.appendingPathComponent(uid, isDirectory: true)
      try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
      return dir.appendingPathComponent("whatsapp_export.json")
    }
    if let entries = try? fm.contentsOfDirectory(
      at: usersDir, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles])
    {
      for entry in entries
      where fm.fileExists(atPath: entry.appendingPathComponent("people_intelligence.json").path) {
        return entry.appendingPathComponent("whatsapp_export.json")
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

  // MARK: - Export shape (mirrors imessage_export.json)

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

  /// A 1:1 partner. Carries `contact_name` (WhatsApp's own `ZPARTNERNAME`) so the graph gets a human
  /// name even without Contacts access — the iMessage exporter leaves naming to the Contacts store.
  private struct ExportHandle: Encodable {
    let handle: String
    let phoneLast10: String?
    let contactName: String?
    let messageCount: Int
    let lastDate: String?
    let isGroup: Bool

    enum CodingKeys: String, CodingKey {
      case handle
      case phoneLast10 = "phone_last10"
      case contactName = "contact_name"
      case messageCount = "message_count"
      case lastDate = "last_date"
      case isGroup = "is_group"
    }

    func encode(to encoder: Encoder) throws {
      var c = encoder.container(keyedBy: CodingKeys.self)
      try c.encode(handle, forKey: .handle)
      try c.encodeIfPresent(phoneLast10, forKey: .phoneLast10)
      try c.encodeIfPresent(contactName, forKey: .contactName)
      try c.encode(messageCount, forKey: .messageCount)
      try c.encodeIfPresent(lastDate, forKey: .lastDate)
      try c.encode(isGroup, forKey: .isGroup)
    }
  }

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

    func encode(to encoder: Encoder) throws {
      var c = encoder.container(keyedBy: CodingKeys.self)
      try c.encode(handle, forKey: .handle)
      try c.encodeIfPresent(phoneLast10, forKey: .phoneLast10)
    }
  }
}
