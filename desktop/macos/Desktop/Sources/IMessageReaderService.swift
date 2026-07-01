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

        guard let chatGUID = row["chat_guid"] as? String, !chatGUID.isEmpty else { continue }
        guard
          let text = AttributedBodyDecoder.bestText(
            text: row["text"] as? String, attributedBody: row["body"] as? Data), !text.isEmpty
        else { continue }

        let isFromMe = ((row["is_from_me"] as? Int64) ?? Int64(row["is_from_me"] as? Int ?? 0)) == 1
        let rawDate = (row["date"] as? Int64) ?? Int64(row["date"] as? Int ?? 0)
        let seconds = rawDate > 1_000_000_000_000 ? Double(rawDate) / 1_000_000_000.0 : Double(rawDate)
        let guid = (row["guid"] as? String) ?? "\(chatGUID)-\(rowid)"

        records.append(
          IMessageRecord(
            rowid: rowid,
            guid: guid,
            text: text,
            isFromMe: isFromMe,
            date: Date(timeIntervalSinceReferenceDate: seconds),
            handle: row["handle"] as? String,
            chatGUID: chatGUID,
            chatIdentifier: row["chat_identifier"] as? String,
            chatDisplayName: row["chat_display_name"] as? String
          ))
      }

      return (records, maxROWID)
    }
  }
}
