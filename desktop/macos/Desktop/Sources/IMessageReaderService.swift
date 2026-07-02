import Foundation
import GRDB

enum IMessageReaderError: LocalizedError {
  case accessDenied

  var errorDescription: String? {
    switch self {
    case .accessDenied:
      return "Couldn't open Messages. Grant Full Disk Access and reopen Omi."
    }
  }
}

/// Reads new messages from the local Messages database (`~/Library/Messages/chat.db`).
///
/// Opens the live database read-only (so the `-wal` sidecar with the newest
/// messages is included) and reads incrementally past a stored ROWID high-water
/// mark. On first run it backfills a bounded window rather than all history.
actor IMessageReaderService {
  static let shared = IMessageReaderService()

  private let cursorKey = "imessageLastProcessedROWID"

  var lastProcessedROWID: Int64 {
    Int64(UserDefaults.standard.integer(forKey: cursorKey))
  }

  func setLastProcessedROWID(_ value: Int64) {
    UserDefaults.standard.set(Int(value), forKey: cursorKey)
  }

  func readNewMessages(backfillDays: Int = 90, limit: Int = 2000) throws -> (
    records: [IMessageRecord], maxROWID: Int64
  ) {
    var config = Configuration()
    config.readonly = true

    let dbQueue: DatabaseQueue
    do {
      dbQueue = try DatabaseQueue(
        path: IMessagePermissionPolicy.chatDatabaseURL.path, configuration: config)
    } catch {
      throw IMessageReaderError.accessDenied
    }

    let cursor = lastProcessedROWID
    // message.date is nanoseconds since the 2001 reference date on modern macOS.
    let cutoffDate =
      Calendar.current.date(byAdding: .day, value: -backfillDays, to: Date())
      ?? Date(timeIntervalSince1970: 0)
    let cutoffNanos = Int64(cutoffDate.timeIntervalSinceReferenceDate * 1_000_000_000)

    return try dbQueue.read { db -> (records: [IMessageRecord], maxROWID: Int64) in
      var sql = """
          SELECT m.ROWID AS rowid, m.guid AS guid, m.text AS text, m.attributedBody AS body,
                 m.date AS date, m.is_from_me AS is_from_me, h.id AS handle,
                 c.guid AS chat_guid, c.chat_identifier AS chat_identifier,
                 c.display_name AS chat_display_name
          FROM message m
          LEFT JOIN handle h ON m.handle_id = h.ROWID
          LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
          LEFT JOIN chat c ON c.ROWID = cmj.chat_id
          WHERE m.ROWID > ?
            AND (m.associated_message_type = 0 OR m.associated_message_type IS NULL)
        """
      var args: [DatabaseValueConvertible] = [cursor]
      if cursor == 0 {
        sql += " AND m.date >= ?"
        args.append(cutoffNanos)
      }
      sql += " ORDER BY m.ROWID ASC LIMIT ?"
      args.append(limit)

      let rows = try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args))
      var records: [IMessageRecord] = []
      var maxROWID = cursor

      for row in rows {
        let rowid = (row["rowid"] as? Int64) ?? Int64(row["rowid"] as? Int ?? 0)
        maxROWID = max(maxROWID, rowid)
        if let record = Self.record(from: row) {
          records.append(record)
        }
      }

      return (records, maxROWID)
    }
  }

  /// Recent inbound threads awaiting a reply, for the Replies inbox. Does NOT
  /// advance the ingest cursor — this is a read-only view over recent history.
  func readInboxThreads(days: Int = 7, limit: Int = 800, perThreadContext: Int = 15) async throws
    -> [IMessageInboxThread]
  {
    var config = Configuration()
    config.readonly = true
    let dbQueue: DatabaseQueue
    do {
      dbQueue = try DatabaseQueue(
        path: IMessagePermissionPolicy.chatDatabaseURL.path, configuration: config)
    } catch {
      throw IMessageReaderError.accessDenied
    }

    let cutoffDate =
      Calendar.current.date(byAdding: .day, value: -days, to: Date()) ?? Date(timeIntervalSince1970: 0)
    let cutoffNanos = Int64(cutoffDate.timeIntervalSinceReferenceDate * 1_000_000_000)

    let records: [IMessageRecord] = try await dbQueue.read { db in
      let rows = try Row.fetchAll(
        db,
        sql: """
            SELECT m.ROWID AS rowid, m.guid AS guid, m.text AS text, m.attributedBody AS body,
                   m.date AS date, m.is_from_me AS is_from_me, h.id AS handle,
                   c.guid AS chat_guid, c.chat_identifier AS chat_identifier,
                   c.display_name AS chat_display_name
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            LEFT JOIN chat c ON c.ROWID = cmj.chat_id
            WHERE m.date >= ?
              AND (m.associated_message_type = 0 OR m.associated_message_type IS NULL)
            ORDER BY m.ROWID DESC LIMIT ?
          """,
        arguments: [cutoffNanos, limit]
      )
      return rows.compactMap { Self.record(from: $0) }
    }

    var byChat: [String: [IMessageRecord]] = [:]
    for record in records {
      byChat[record.chatGUID, default: []].append(record)
    }

    var items: [IMessageInboxThread] = []
    for (chatGUID, recs) in byChat {
      let sorted = recs.sorted { $0.date < $1.date }
      guard let last = sorted.last, !last.isFromMe else { continue }  // only threads awaiting a reply

      let isGroup =
        chatGUID.contains(";+;") || (sorted.first?.chatIdentifier?.hasPrefix("chat") ?? false)
      let groupName = Self.nonEmpty(last.chatDisplayName)
      var name = groupName ?? last.handle.map(Self.prettyHandle) ?? "Unknown"
      var personRef = last.handle ?? name
      if !isGroup, let handle = last.handle {
        name = await IMessageContactResolver.shared.displayName(for: handle) ?? groupName ?? Self.prettyHandle(handle)
        personRef = handle
      }

      let context = sorted.suffix(perThreadContext).map {
        IMessageDraftMessagePayload(text: $0.text, isFromMe: $0.isFromMe)
      }
      items.append(
        IMessageInboxThread(
          chatGUID: chatGUID,
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

  private struct RawMessage {
    let rowid: Int64
    let guid: String
    let text: String?
    let date: Date
    let isFromMe: Bool
    let handle: String?
    let chatGUID: String
    let chatIdentifier: String?
    let chatDisplayName: String?
    let hasAttachment: Bool
    let attachmentFilename: String?
    let attachmentMime: String?
  }

  /// Trimmed non-empty string, or nil. Messages stores 1:1 chat display names as
  /// "" (not NULL), which would otherwise shadow a real handle fallback.
  private static func nonEmpty(_ s: String?) -> String? {
    guard let t = s?.trimmingCharacters(in: .whitespacesAndNewlines), !t.isEmpty else { return nil }
    return t
  }

  /// A human-friendly fallback when a handle isn't in Contacts: format a US phone
  /// number as (415) 555-1234, otherwise return the raw handle (email/short code).
  static func prettyHandle(_ handle: String) -> String {
    let h = handle.trimmingCharacters(in: .whitespacesAndNewlines)
    if h.contains("@") { return h }
    let digits = h.filter { $0.isNumber }
    let local = digits.count == 11 && digits.hasPrefix("1") ? String(digits.dropFirst()) : digits
    if local.count == 10 {
      let a = local.prefix(3)
      let b = local.dropFirst(3).prefix(3)
      let c = local.suffix(4)
      return "(\(a)) \(b)-\(c)"
    }
    return h
  }

  /// Compose an unnamed group's title from member names, like Messages.app:
  /// "Josh & Eli", "Josh, Eli & 2 others".
  private static func composeGroupTitle(_ names: [String]) -> String {
    let cleaned = names.filter { !$0.isEmpty }
    switch cleaned.count {
    case 0: return "Group Message"
    case 1: return cleaned[0]
    case 2: return "\(cleaned[0]) & \(cleaned[1])"
    case 3: return "\(cleaned[0]), \(cleaned[1]) & \(cleaned[2])"
    default: return "\(cleaned[0]), \(cleaned[1]) & \(cleaned.count - 2) others"
    }
  }

  private static func attachmentPlaceholder(mime: String?) -> String {
    guard let mime = mime?.lowercased() else { return "📎 Attachment" }
    if mime.hasPrefix("image/") { return "📷 Photo" }
    if mime.hasPrefix("video/") { return "🎥 Video" }
    if mime.hasPrefix("audio/") { return "🎤 Audio" }
    return "📎 Attachment"
  }

  /// Loads recent chats with their full-ish message history (text + attachments +
  /// contact photos), for the native-style Messages tab. Read-only.
  func readChats(days: Int = 365, maxChats: Int = 60, perChatMessages: Int = 1000) async throws -> [IMessageChat] {
    var config = Configuration()
    config.readonly = true
    let dbQueue: DatabaseQueue
    do {
      dbQueue = try DatabaseQueue(
        path: IMessagePermissionPolicy.chatDatabaseURL.path, configuration: config)
    } catch {
      throw IMessageReaderError.accessDenied
    }

    let cutoffDate =
      Calendar.current.date(byAdding: .day, value: -days, to: Date()) ?? Date(timeIntervalSince1970: 0)
    let cutoffNanos = Int64(cutoffDate.timeIntervalSinceReferenceDate * 1_000_000_000)

    let raws: [RawMessage] = try await dbQueue.read { db in
      let rows = try Row.fetchAll(
        db,
        sql: """
            SELECT m.ROWID AS rowid, m.guid AS guid, m.text AS text, m.attributedBody AS body,
                   m.date AS date, m.is_from_me AS is_from_me, h.id AS handle,
                   c.guid AS chat_guid, c.chat_identifier AS chat_identifier, c.display_name AS chat_display_name,
                   m.cache_has_attachments AS has_att, att.filename AS att_filename, att.mime_type AS att_mime
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            LEFT JOIN chat c ON c.ROWID = cmj.chat_id
            LEFT JOIN message_attachment_join maj ON maj.message_id = m.ROWID
            LEFT JOIN attachment att ON att.ROWID = maj.attachment_id
            WHERE m.date >= ?
              AND (m.associated_message_type = 0 OR m.associated_message_type IS NULL)
            ORDER BY m.ROWID DESC LIMIT ?
          """,
        arguments: [cutoffNanos, 40000]
      )
      var seen = Set<Int64>()
      var out: [RawMessage] = []
      for row in rows {
        let rowid = (row["rowid"] as? Int64) ?? Int64(row["rowid"] as? Int ?? 0)
        if seen.contains(rowid) { continue }  // dedup multi-attachment rows (keep first)
        seen.insert(rowid)
        guard let chatGUID = row["chat_guid"] as? String, !chatGUID.isEmpty else { continue }
        let rawDate = (row["date"] as? Int64) ?? Int64(row["date"] as? Int ?? 0)
        let seconds = rawDate > 1_000_000_000_000 ? Double(rawDate) / 1_000_000_000.0 : Double(rawDate)
        let hasAtt = ((row["has_att"] as? Int64) ?? Int64(row["has_att"] as? Int ?? 0)) == 1
        out.append(
          RawMessage(
            rowid: rowid,
            guid: (row["guid"] as? String) ?? "\(chatGUID)-\(rowid)",
            text: AttributedBodyDecoder.bestText(text: row["text"] as? String, attributedBody: row["body"] as? Data),
            date: Date(timeIntervalSinceReferenceDate: seconds),
            isFromMe: ((row["is_from_me"] as? Int64) ?? Int64(row["is_from_me"] as? Int ?? 0)) == 1,
            handle: row["handle"] as? String,
            chatGUID: chatGUID,
            chatIdentifier: row["chat_identifier"] as? String,
            chatDisplayName: row["chat_display_name"] as? String,
            hasAttachment: hasAtt,
            attachmentFilename: row["att_filename"] as? String,
            attachmentMime: row["att_mime"] as? String))
      }
      return out
    }

    // Participants per chat (the reliable source of who's in a thread — the
    // per-message `handle` is nil on outbound messages, so resolving a 1:1 chat
    // from the latest message fails whenever you sent last).
    let participantsByChat: [String: [String]] = try await dbQueue.read { db in
      let rows = try Row.fetchAll(
        db,
        sql: """
            SELECT c.guid AS chat_guid, h.id AS handle
            FROM chat_handle_join chj
            JOIN chat c ON c.ROWID = chj.chat_id
            JOIN handle h ON h.ROWID = chj.handle_id
          """)
      var map: [String: [String]] = [:]
      for row in rows {
        guard let g = row["chat_guid"] as? String, let h = (row["handle"] as? String)?.trimmingCharacters(in: .whitespaces),
          !h.isEmpty
        else { continue }
        if !(map[g]?.contains(h) ?? false) { map[g, default: []].append(h) }
      }
      return map
    }

    var byChat: [String: [RawMessage]] = [:]
    for r in raws {
      byChat[r.chatGUID, default: []].append(r)
    }

    var chats: [IMessageChat] = []
    for (chatGUID, recs) in byChat {
      let sorted = recs.sorted { $0.date < $1.date }
      guard let latest = sorted.last else { continue }
      let recent = Array(sorted.suffix(perChatMessages))

      let groupName = Self.nonEmpty(latest.chatDisplayName)
      let isGroup = chatGUID.contains(";+;") || (latest.chatIdentifier?.hasPrefix("chat") ?? false)
      let participants = participantsByChat[chatGUID] ?? []

      var title: String
      var personRef: String
      var avatar: Data? = nil
      let resolver = IMessageContactResolver.shared

      if !isGroup {
        // The counterparty is the single participant (or the chat identifier),
        // never the outbound message's nil handle.
        let counterparty = participants.first ?? Self.nonEmpty(latest.chatIdentifier) ?? latest.handle
        if let handle = counterparty {
          title = await resolver.displayName(for: handle) ?? groupName ?? Self.prettyHandle(handle)
          personRef = handle
          avatar = await resolver.imageData(for: handle)
        } else {
          title = groupName ?? "Unknown"
          personRef = title
        }
      } else if let name = groupName {
        title = name
        personRef = Self.nonEmpty(latest.chatIdentifier) ?? chatGUID
      } else {
        // Unnamed group: compose from participant names, like Messages.app.
        var names: [String] = []
        for h in participants {
          names.append(await resolver.displayName(for: h) ?? Self.prettyHandle(h))
        }
        title = Self.composeGroupTitle(names)
        personRef = Self.nonEmpty(latest.chatIdentifier) ?? chatGUID
      }

      var bubbles: [IMessageChatBubble] = []
      for r in recent {
        let text = r.text ?? ""
        if text.isEmpty && !r.hasAttachment { continue }  // skip empty non-attachment messages

        var sender: String? = nil
        var senderImg: Data? = nil
        if isGroup && !r.isFromMe, let h = r.handle {
          sender = await resolver.displayName(for: h) ?? Self.prettyHandle(h)
          senderImg = await resolver.imageData(for: h)
        }

        var attPath: String? = nil
        if let fn = r.attachmentFilename, !fn.isEmpty {
          attPath = (fn as NSString).expandingTildeInPath
        }

        let displayText = text.isEmpty ? Self.attachmentPlaceholder(mime: r.attachmentMime) : text
        bubbles.append(
          IMessageChatBubble(
            id: r.guid, text: displayText, isFromMe: r.isFromMe, date: r.date, senderName: sender,
            senderImage: senderImg, attachmentPath: attPath, attachmentMime: r.attachmentMime))
      }

      if bubbles.isEmpty { continue }
      chats.append(
        IMessageChat(
          chatGUID: chatGUID, displayName: title, isGroup: isGroup, personRef: personRef,
          bubbles: bubbles, avatarImageData: avatar))
    }

    chats.sort { $0.lastDate > $1.lastDate }
    return Array(chats.prefix(maxChats))
  }

  private static func record(from row: Row) -> IMessageRecord? {
    let rowid = (row["rowid"] as? Int64) ?? Int64(row["rowid"] as? Int ?? 0)
    guard let chatGUID = row["chat_guid"] as? String, !chatGUID.isEmpty else { return nil }
    guard
      let text = AttributedBodyDecoder.bestText(
        text: row["text"] as? String, attributedBody: row["body"] as? Data), !text.isEmpty
    else { return nil }

    let isFromMe = ((row["is_from_me"] as? Int64) ?? Int64(row["is_from_me"] as? Int ?? 0)) == 1
    let rawDate = (row["date"] as? Int64) ?? Int64(row["date"] as? Int ?? 0)
    let seconds = rawDate > 1_000_000_000_000 ? Double(rawDate) / 1_000_000_000.0 : Double(rawDate)
    let guid = (row["guid"] as? String) ?? "\(chatGUID)-\(rowid)"

    return IMessageRecord(
      rowid: rowid,
      guid: guid,
      text: text,
      isFromMe: isFromMe,
      date: Date(timeIntervalSinceReferenceDate: seconds),
      handle: row["handle"] as? String,
      chatGUID: chatGUID,
      chatIdentifier: row["chat_identifier"] as? String,
      chatDisplayName: row["chat_display_name"] as? String
    )
  }
}
