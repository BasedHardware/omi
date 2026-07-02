import Foundation
import GRDB

enum WhatsAppReaderError: LocalizedError {
  case accessDenied

  var errorDescription: String? {
    switch self {
    case .accessDenied:
      return "Couldn't open WhatsApp. Grant Full Disk Access and reopen Omi."
    }
  }
}

/// Reads new text messages from the local WhatsApp database
/// (`~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite`).
///
/// Opens the live database read-only (so the `-wal` sidecar with the newest
/// messages is included) and reads incrementally past a stored `Z_PK` high-water
/// mark. On first run it backfills a bounded window rather than all history. The
/// cursor is kept entirely client-side (UserDefaults) — the backend has no
/// `last_rowid` concept for WhatsApp.
actor WhatsAppReaderService {
  static let shared = WhatsAppReaderService()

  private let cursorKey = "whatsappLastProcessedZPK"

  // MARK: - Schema constants (verified live 2026-07-02)
  //
  // Core Data-backed schema: ZWAMESSAGE rows join to ZWACHATSESSION (the chat) and,
  // for group messages, ZWAGROUPMEMBER (the sender). `ZMESSAGETYPE = 0` filters to
  // real text rows (other types are media/system). `ZTEXT` is plain text (no
  // attributedBody). `ZMESSAGEDATE` is seconds since the 2001 reference date.
  private enum SQL {
    static let message = "ZWAMESSAGE"
    static let session = "ZWACHATSESSION"
    static let groupMember = "ZWAGROUPMEMBER"

    // Only text rows in 1:1 (`@s.whatsapp.net`) or group (`@g.us`) sessions —
    // skips broadcast/status sessions and non-text message types.
    static let baseWhere = """
        m.ZMESSAGETYPE = 0
        AND m.ZTEXT IS NOT NULL AND m.ZTEXT <> ''
        AND (s.ZCONTACTJID LIKE '%@s.whatsapp.net' OR s.ZCONTACTJID LIKE '%@g.us')
      """

    /// Column projection shared by every read, aliased to stable names.
    static let projection = """
        m.Z_PK AS rowid, m.ZSTANZAID AS message_id, m.ZTEXT AS text,
        m.ZISFROMME AS is_from_me, m.ZMESSAGEDATE AS date, m.ZPUSHNAME AS push_name,
        s.ZCONTACTJID AS chat_jid, s.ZPARTNERNAME AS partner_name,
        gm.ZMEMBERJID AS member_jid, gm.ZCONTACTNAME AS member_contact_name,
        gm.ZFIRSTNAME AS member_first_name
      """

    static let from = """
        FROM \(message) m
        JOIN \(session) s ON s.Z_PK = m.ZCHATSESSION
        LEFT JOIN \(groupMember) gm ON gm.Z_PK = m.ZGROUPMEMBER
      """
  }

  var lastProcessedZPK: Int64 {
    Int64(UserDefaults.standard.integer(forKey: cursorKey))
  }

  func setLastProcessedZPK(_ value: Int64) {
    UserDefaults.standard.set(Int(value), forKey: cursorKey)
  }

  func readNewMessages(backfillDays: Int = 90, limit: Int = 2000) throws -> (
    records: [WhatsAppRecord], maxZPK: Int64
  ) {
    let dbQueue = try openDatabase()

    let cursor = lastProcessedZPK
    // ZMESSAGEDATE is seconds since the 2001 reference date (no ns scaling).
    let cutoffDate =
      Calendar.current.date(byAdding: .day, value: -backfillDays, to: Date())
      ?? Date(timeIntervalSince1970: 0)
    let cutoffSeconds = cutoffDate.timeIntervalSinceReferenceDate

    return try dbQueue.read { db -> (records: [WhatsAppRecord], maxZPK: Int64) in
      var sql = """
          SELECT \(SQL.projection)
          \(SQL.from)
          WHERE m.Z_PK > ?
            AND \(SQL.baseWhere)
        """
      var args: [DatabaseValueConvertible] = [cursor]
      if cursor == 0 {
        sql += " AND m.ZMESSAGEDATE >= ?"
        args.append(cutoffSeconds)
      }
      sql += " ORDER BY m.Z_PK ASC LIMIT ?"
      args.append(limit)

      let rows = try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args))
      var records: [WhatsAppRecord] = []
      var maxZPK = cursor
      for row in rows {
        let rowid = Self.int64(row, "rowid")
        maxZPK = max(maxZPK, rowid)
        if let record = Self.record(from: row) { records.append(record) }
      }
      return (records, maxZPK)
    }
  }

  /// Incremental fetch for the inbox watcher: messages with `Z_PK` greater than
  /// `afterZPK` (ascending), plus the current high-water `Z_PK` in the database.
  /// Takes an explicit cursor and never touches the shared ingest cursor, so
  /// gating the real-time watcher can't disturb ingest. `maxZPK` is the DB-wide
  /// MAX (not just the max among returned rows), so it's a reliable "anything
  /// new?" high-water mark even when priming with `afterZPK == 0` and a small
  /// `limit`.
  func newMessages(afterZPK: Int64, limit: Int = 1000) throws -> (
    records: [WhatsAppRecord], maxZPK: Int64
  ) {
    let dbQueue = try openDatabase()

    return try dbQueue.read { db -> (records: [WhatsAppRecord], maxZPK: Int64) in
      let dbMax = (try Int64.fetchOne(db, sql: "SELECT MAX(Z_PK) FROM \(SQL.message)")) ?? afterZPK
      let rows = try Row.fetchAll(
        db,
        sql: """
            SELECT \(SQL.projection)
            \(SQL.from)
            WHERE m.Z_PK > ?
              AND \(SQL.baseWhere)
            ORDER BY m.Z_PK ASC LIMIT ?
          """,
        arguments: [afterZPK, limit])
      let records = rows.compactMap { Self.record(from: $0) }
      return (records, dbMax)
    }
  }

  /// Recent inbound threads awaiting a reply, for the inbox. Does NOT advance the
  /// ingest cursor — this is a read-only view over recent history.
  ///
  /// Selects the most recently active chats first (bounded by `maxThreads`), then
  /// fetches per-chat context. A flat message budget would let one high-volume
  /// chat consume it and starve other recent threads in the window.
  func readInboxThreads(days: Int = 7, maxThreads: Int = 50, perThreadContext: Int = 15) async throws
    -> [WhatsAppInboxThread]
  {
    let dbQueue = try openDatabase()

    let cutoffDate =
      Calendar.current.date(byAdding: .day, value: -days, to: Date()) ?? Date(timeIntervalSince1970: 0)
    let cutoffSeconds = cutoffDate.timeIntervalSinceReferenceDate

    let byChat: [String: [WhatsAppRecord]] = try await dbQueue.read { db in
      // Phase 1: the most recently active chats within the window (one row per
      // chat), so a single noisy thread can't starve other recent threads.
      let chatRows = try Row.fetchAll(
        db,
        sql: """
            SELECT s.ZCONTACTJID AS chat_jid, MAX(m.ZMESSAGEDATE) AS max_date
            \(SQL.from)
            WHERE m.ZMESSAGEDATE >= ?
              AND \(SQL.baseWhere)
            GROUP BY s.ZCONTACTJID
            ORDER BY max_date DESC LIMIT ?
          """,
        arguments: [cutoffSeconds, maxThreads]
      )

      // Phase 2: fetch recent per-chat context (bounded per chat).
      var map: [String: [WhatsAppRecord]] = [:]
      for chatRow in chatRows {
        guard let chatJID = chatRow["chat_jid"] as? String, !chatJID.isEmpty else { continue }
        let rows = try Row.fetchAll(
          db,
          sql: """
              SELECT \(SQL.projection)
              \(SQL.from)
              WHERE s.ZCONTACTJID = ?
                AND m.ZMESSAGEDATE >= ?
                AND \(SQL.baseWhere)
              ORDER BY m.Z_PK DESC LIMIT ?
            """,
          arguments: [chatJID, cutoffSeconds, perThreadContext]
        )
        let recs = rows.compactMap { Self.record(from: $0) }
        if !recs.isEmpty { map[chatJID] = recs }
      }
      return map
    }

    var items: [WhatsAppInboxThread] = []
    for (chatID, recs) in byChat {
      let sorted = recs.sorted { $0.date < $1.date }
      guard let last = sorted.last, !last.isFromMe else { continue }  // only threads awaiting a reply

      let groupName = Self.nonEmpty(last.chatDisplayName)
      var name = groupName ?? last.handle.map(Self.prettyHandle) ?? "Unknown"
      var personRef = last.handle ?? name
      if !last.isGroup, let handle = last.handle {
        name =
          await IMessageContactResolver.shared.displayName(for: handle) ?? groupName
          ?? Self.prettyHandle(handle)
        personRef = handle
      }

      let context = sorted.suffix(perThreadContext).map {
        WhatsAppDraftMessagePayload(text: $0.text, isFromMe: $0.isFromMe, timestamp: $0.date)
      }
      items.append(
        WhatsAppInboxThread(
          chatID: chatID,
          displayName: name,
          lastMessage: last.text,
          lastDate: last.date,
          personRef: personRef,
          context: context
        ))
    }

    items.sort { $0.lastDate > $1.lastDate }
    return items
  }

  /// Loads recent chats with their message history (text only — WhatsApp media
  /// isn't ingested), for the native-style WhatsApp tab. Read-only.
  func readChats(days: Int = 365, maxChats: Int = 60, perChatMessages: Int = 1000) async throws
    -> [WhatsAppChat]
  {
    let dbQueue = try openDatabase()

    let cutoffDate =
      Calendar.current.date(byAdding: .day, value: -days, to: Date()) ?? Date(timeIntervalSince1970: 0)
    let cutoffSeconds = cutoffDate.timeIntervalSinceReferenceDate

    // The visual chats tab (unlike ingest/draft) also surfaces inline IMAGES
    // (ZMESSAGETYPE=1): LEFT JOIN the media item and accept either a real text row
    // or an image row that has a local media path. Ingest stays text-only.
    let raws: [WhatsAppRecord] = try await dbQueue.read { db in
      let rows = try Row.fetchAll(
        db,
        sql: """
            SELECT \(SQL.projection), mi.ZMEDIALOCALPATH AS media_path, m.ZMESSAGETYPE AS msg_type
            \(SQL.from)
            LEFT JOIN ZWAMEDIAITEM mi ON mi.ZMESSAGE = m.Z_PK
            WHERE m.ZMESSAGEDATE >= ?
              AND (s.ZCONTACTJID LIKE '%@s.whatsapp.net' OR s.ZCONTACTJID LIKE '%@g.us')
              AND (
                (m.ZMESSAGETYPE = 0 AND m.ZTEXT IS NOT NULL AND m.ZTEXT <> '')
                OR (m.ZMESSAGETYPE = 1 AND mi.ZMEDIALOCALPATH IS NOT NULL AND mi.ZMEDIALOCALPATH <> '')
              )
            ORDER BY m.Z_PK DESC LIMIT ?
          """,
        arguments: [cutoffSeconds, 40000]
      )
      return rows.compactMap { Self.chatRecord(from: $0) }
    }

    // Per-group member directory (chat JID → member-id-digits → display name), used
    // to turn `@<id>` mentions in group text into readable `@Name`.
    let membersByChat: [String: [String: String]] = try await dbQueue.read { db in
      let rows = try Row.fetchAll(
        db,
        sql: """
            SELECT s.ZCONTACTJID AS chat_jid, gm.ZMEMBERJID AS member_jid,
                   gm.ZCONTACTNAME AS cname, gm.ZFIRSTNAME AS fname
            FROM ZWAGROUPMEMBER gm
            JOIN ZWACHATSESSION s ON s.Z_PK = gm.ZCHATSESSION
            WHERE s.ZCONTACTJID LIKE '%@g.us'
          """)
      var map: [String: [String: String]] = [:]
      for row in rows {
        guard let chatJID = row["chat_jid"] as? String,
          let memberJID = (row["member_jid"] as? String)?.trimmingCharacters(in: .whitespaces),
          let digits = memberJID.split(separator: "@").first.map(String.init), !digits.isEmpty
        else { continue }
        let name =
          Self.sanitizedName(row["cname"] as? String)
          ?? Self.sanitizedName(row["fname"] as? String)
          ?? Self.prettyHandle(digits)
        map[chatJID, default: [:]][digits] = name
      }
      return map
    }

    var byChat: [String: [WhatsAppRecord]] = [:]
    for r in raws {
      byChat[r.chatID, default: []].append(r)
    }

    var chats: [WhatsAppChat] = []
    let resolver = IMessageContactResolver.shared
    let thumbMap = Self.profileThumbMap()
    for (chatID, recs) in byChat {
      let sorted = recs.sorted { $0.date < $1.date }
      guard let latest = sorted.last else { continue }
      let recent = Array(sorted.suffix(perChatMessages))

      let isGroup = latest.isGroup
      let groupName = Self.nonEmpty(latest.chatDisplayName)

      var title: String
      var personRef: String
      var avatar: Data? = nil

      if !isGroup {
        // 1:1: resolve the counterparty phone (the session JID) to a Contacts name.
        if let handle = latest.handle ?? Self.handle(fromJID: chatID) {
          title = await resolver.displayName(for: handle) ?? groupName ?? Self.prettyHandle(handle)
          personRef = handle
          // Prefer the saved Contacts photo; fall back to WhatsApp's own profile thumb.
          avatar =
            await resolver.imageData(for: handle) ?? Self.profileThumb(for: chatID, in: thumbMap)
        } else {
          title = groupName ?? "Unknown"
          personRef = title
        }
      } else {
        title = groupName ?? "Group Chat"
        personRef = chatID
        // Groups have no Contacts entry — use WhatsApp's cached group photo.
        avatar = Self.profileThumb(for: chatID, in: thumbMap)
      }

      let members = isGroup ? (membersByChat[chatID] ?? [:]) : [:]
      var bubbles: [WhatsAppChatBubble] = []
      for r in recent {
        guard !r.text.isEmpty || r.imagePath != nil else { continue }
        var senderImg: Data? = nil
        if isGroup, !r.isFromMe, let h = r.handle {
          senderImg = await resolver.imageData(for: h) ?? Self.profileThumb(for: h, in: thumbMap)
        }
        let bubbleText = r.text.isEmpty ? "" : Self.resolveMentions(in: r.text, members: members)
        bubbles.append(
          WhatsAppChatBubble(
            id: r.messageId.isEmpty ? "\(chatID)-\(r.rowid)" : r.messageId,
            text: bubbleText, isFromMe: r.isFromMe, date: r.date,
            senderName: (isGroup && !r.isFromMe) ? r.senderName : nil, senderImage: senderImg,
            imagePath: r.imagePath))
      }

      if bubbles.isEmpty { continue }
      chats.append(
        WhatsAppChat(
          chatID: chatID, displayName: title, isGroup: isGroup, personRef: personRef,
          bubbles: bubbles, avatarImageData: avatar))
    }

    chats.sort { $0.lastDate > $1.lastDate }
    return Array(chats.prefix(maxChats))
  }

  // MARK: - Profile photos

  /// WhatsApp caches contact/group profile thumbnails under `Media/Profile/` as
  /// `<jid-local-part>-<id>.thumb` (96×96 JPEG). Build a one-shot map of
  /// local-part → file path so per-chat avatar lookup is O(1) (no per-chat
  /// directory scan). Only ~dozens of files exist, so this is cheap.
  private static func profileThumbMap() -> [String: String] {
    let dir = WhatsAppPermissionPolicy.messageMediaDirectoryURL
      .deletingLastPathComponent()  // .../shared/Message -> .../shared
      .appendingPathComponent("Media/Profile", isDirectory: true)
    guard
      let files = try? FileManager.default.contentsOfDirectory(
        at: dir, includingPropertiesForKeys: nil)
    else { return [:] }
    var map: [String: String] = [:]
    for f in files where f.pathExtension == "thumb" {
      // "<localPart>-<id>.thumb" — key on the part before the first dash.
      let base = f.deletingPathExtension().lastPathComponent
      guard let dash = base.firstIndex(of: "-") else { continue }
      let localPart = String(base[..<dash])
      if !localPart.isEmpty { map[localPart] = f.path }
    }
    return map
  }

  /// The WhatsApp profile-thumb image data for a chat JID, if cached.
  private static func profileThumb(for jid: String, in map: [String: String]) -> Data? {
    let localPart = jid.split(separator: "@").first.map(String.init) ?? jid
    guard let path = map[localPart] else { return nil }
    return try? Data(contentsOf: URL(fileURLWithPath: path))
  }

  // MARK: - Row → record

  private func openDatabase() throws -> DatabaseQueue {
    var config = Configuration()
    config.readonly = true
    do {
      return try DatabaseQueue(
        path: WhatsAppPermissionPolicy.chatDatabaseURL.path, configuration: config)
    } catch {
      throw WhatsAppReaderError.accessDenied
    }
  }

  private static func int64(_ row: Row, _ column: String) -> Int64 {
    (row[column] as? Int64) ?? Int64(row[column] as? Int ?? 0)
  }

  private static func record(from row: Row) -> WhatsAppRecord? {
    guard let chatJID = row["chat_jid"] as? String, !chatJID.isEmpty else { return nil }
    let text = (row["text"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    guard !text.isEmpty else { return nil }

    let rowid = int64(row, "rowid")
    let isFromMe = int64(row, "is_from_me") == 1
    let seconds = (row["date"] as? Double) ?? Double(int64(row, "date"))
    let messageId = (row["message_id"] as? String) ?? "\(chatJID)-\(rowid)"
    let isGroup = chatJID.hasSuffix("@g.us")

    // Sender handle + display name:
    //  - Outbound: no handle/sender (the user).
    //  - 1:1 inbound: the counterparty is the session JID; name is ZPARTNERNAME.
    //  - Group inbound: the sender comes from the group-member JID; name from the
    //    member's contact/first/push name (ZFROMJID is unreliable for groups).
    var handle: String? = nil
    var senderName: String? = nil
    if !isFromMe {
      if isGroup {
        handle = (row["member_jid"] as? String).flatMap(Self.handle(fromJID:))
        // Prefer a real saved/first name; ZPUSHNAME (and sometimes ZFIRSTNAME) can
        // hold a base64 protocol blob for @lid senders, so sanitize each candidate
        // and fall back to a readable phone rather than showing the blob.
        senderName =
          sanitizedName(row["member_contact_name"] as? String)
          ?? sanitizedName(row["member_first_name"] as? String)
          ?? sanitizedName(row["push_name"] as? String)
          ?? handle.map(Self.prettyHandle)
      } else {
        handle = Self.handle(fromJID: chatJID)
      }
    }

    return WhatsAppRecord(
      rowid: rowid,
      messageId: messageId,
      text: text,
      isFromMe: isFromMe,
      date: Date(timeIntervalSinceReferenceDate: seconds),
      handle: handle,
      chatID: chatJID,
      chatDisplayName: nonEmpty(row["partner_name"] as? String),
      isGroup: isGroup,
      senderName: senderName
    )
  }

  /// Like `record(from:)`, but for the visual chats tab: accepts image rows
  /// (`ZMESSAGETYPE=1`) whose text may be empty, resolving `ZMEDIALOCALPATH` to an
  /// absolute file path. Returns nil only when there's neither text nor an image.
  private static func chatRecord(from row: Row) -> WhatsAppRecord? {
    guard let chatJID = row["chat_jid"] as? String, !chatJID.isEmpty else { return nil }
    let text = (row["text"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    let imagePath: String? = {
      guard let rel = row["media_path"] as? String,
        let url = WhatsAppPermissionPolicy.mediaFileURL(forLocalPath: rel),
        FileManager.default.fileExists(atPath: url.path)
      else { return nil }
      return url.path
    }()
    guard !text.isEmpty || imagePath != nil else { return nil }

    let rowid = int64(row, "rowid")
    let isFromMe = int64(row, "is_from_me") == 1
    let seconds = (row["date"] as? Double) ?? Double(int64(row, "date"))
    let messageId = (row["message_id"] as? String) ?? "\(chatJID)-\(rowid)"
    let isGroup = chatJID.hasSuffix("@g.us")

    var handle: String? = nil
    var senderName: String? = nil
    if !isFromMe {
      if isGroup {
        handle = (row["member_jid"] as? String).flatMap(Self.handle(fromJID:))
        senderName =
          sanitizedName(row["member_contact_name"] as? String)
          ?? sanitizedName(row["member_first_name"] as? String)
          ?? sanitizedName(row["push_name"] as? String)
          ?? handle.map(Self.prettyHandle)
      } else {
        handle = Self.handle(fromJID: chatJID)
      }
    }

    return WhatsAppRecord(
      rowid: rowid,
      messageId: messageId,
      text: text,
      isFromMe: isFromMe,
      date: Date(timeIntervalSinceReferenceDate: seconds),
      handle: handle,
      chatID: chatJID,
      chatDisplayName: nonEmpty(row["partner_name"] as? String),
      isGroup: isGroup,
      senderName: senderName,
      imagePath: imagePath
    )
  }

  /// Canonical handle for a WhatsApp JID.
  ///  - `<digits>@s.whatsapp.net` → the bare phone digits (matches Contacts lookup).
  ///  - `<id>@lid` and anything else → the FULL JID kept verbatim (opaque handle;
  ///    the backend preserves the `@` for these).
  static func handle(fromJID jid: String?) -> String? {
    guard let jid = jid?.trimmingCharacters(in: .whitespacesAndNewlines), !jid.isEmpty else {
      return nil
    }
    if jid.hasSuffix("@s.whatsapp.net") {
      let digits = jid.split(separator: "@").first.map(String.init) ?? jid
      return digits.isEmpty ? jid : digits
    }
    return jid  // opaque (@lid, @g.us, …) — keep verbatim
  }

  /// Trimmed non-empty string, or nil.
  private static func nonEmpty(_ s: String?) -> String? {
    guard let t = s?.trimmingCharacters(in: .whitespacesAndNewlines), !t.isEmpty else { return nil }
    return t
  }

  /// WhatsApp stores a base64 protocol/identity blob in `ZPUSHNAME` (and sometimes
  /// `ZFIRSTNAME`) for many `@lid`-era senders instead of a readable name — e.g.
  /// `CKLi2ssGGhMxNTg1MzIwNDEy` or values ending in `=`. Those must never be shown
  /// as a person's name. A real display name either has whitespace, or lacks the
  /// base64 punctuation and isn't a long random case+digit token.
  static func isLikelyEncodedName(_ s: String) -> Bool {
    let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
    if t.isEmpty || t.contains(" ") { return false }  // names with spaces are always fine
    if t.count >= 6, t.contains("=") || t.contains("+") || t.contains("/") { return true }
    if t.count >= 12 {
      let wordChars = t.allSatisfy { $0.isLetter || $0.isNumber }
      let hasDigit = t.contains { $0.isNumber }
      let hasUpper = t.contains { $0.isUppercase }
      let hasLower = t.contains { $0.isLowercase }
      if wordChars && hasDigit && hasUpper && hasLower { return true }  // random id-looking token
    }
    return false
  }

  /// A trimmed, human-readable name, or nil when the candidate is empty or an
  /// encoded protocol blob (see `isLikelyEncodedName`).
  static func sanitizedName(_ s: String?) -> String? {
    guard let t = nonEmpty(s), !isLikelyEncodedName(t) else { return nil }
    return t
  }

  /// Replace WhatsApp `@<id>` mentions in group text with the mentioned member's
  /// display name (from `members`, keyed by the digits of their JID). Unknown ids
  /// are left as-is. No-op when there are no members or no `@` in the text.
  static func resolveMentions(in text: String, members: [String: String]) -> String {
    guard !members.isEmpty, text.contains("@") else { return text }
    let chars = Array(text)
    var result = ""
    result.reserveCapacity(chars.count)
    var i = 0
    while i < chars.count {
      if chars[i] == "@" {
        var j = i + 1
        while j < chars.count, chars[j].isNumber { j += 1 }
        let digits = String(chars[(i + 1)..<j])
        if digits.count >= 5, let name = members[digits] {
          result += "@" + name
          i = j
          continue
        }
      }
      result.append(chars[i])
      i += 1
    }
    return result
  }

  /// A human-friendly fallback when a handle isn't in Contacts: format a US phone
  /// number as (415) 555-1234. A JID domain (`@lid` / `@s.whatsapp.net`) is stripped
  /// so it's never shown, and an opaque non-phone id (e.g. a long `@lid` number,
  /// which carries no phone) collapses to a short stable tag like `~009509` rather
  /// than a 15-digit string.
  static func prettyHandle(_ handle: String) -> String {
    var h = handle.trimmingCharacters(in: .whitespacesAndNewlines)
    if let at = h.firstIndex(of: "@") { h = String(h[..<at]) }  // drop JID domain
    let digits = h.filter { $0.isNumber }
    let local = digits.count == 11 && digits.hasPrefix("1") ? String(digits.dropFirst()) : digits
    if local.count == 10 {
      let a = local.prefix(3)
      let b = local.dropFirst(3).prefix(3)
      let c = local.suffix(4)
      return "(\(a)) \(b)-\(c)"
    }
    if local.count > 10 { return "~" + String(local.suffix(6)) }  // opaque @lid id → short tag
    return h.isEmpty ? handle : h
  }
}
