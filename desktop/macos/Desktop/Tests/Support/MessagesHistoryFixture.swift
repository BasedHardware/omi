import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

/// A small store shaped like the Messages history (`chat.db`), built in a test
/// rather than read from a real Mac.
///
/// Like the real store it runs in WAL mode, keeps one `handle` row per
/// address and service (`UNIQUE(id, service)`), and gives one person a
/// separate direct chat per service.
final class MessagesHistoryFixture: @unchecked Sendable {
  let directory: URL
  let url: URL
  private let queue: DatabaseQueue

  init(wal: Bool = true) throws {
    directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-messages-fixture-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    url = directory.appendingPathComponent("chat.db")
    queue = try DatabaseQueue(path: url.path)
    try queue.writeWithoutTransaction { db in
      if wal { try db.execute(sql: "PRAGMA journal_mode = WAL") }
      try db.execute(
        sql: """
          CREATE TABLE handle (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL, service TEXT NOT NULL, UNIQUE (id, service));
          CREATE TABLE chat (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT, chat_identifier TEXT, service_name TEXT, display_name TEXT,
            account_login TEXT);
          CREATE TABLE chat_handle_join (chat_id INTEGER, handle_id INTEGER, UNIQUE (chat_id, handle_id));
          CREATE TABLE message (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT,
            attributedBody BLOB,
            handle_id INTEGER DEFAULT 0,
            service TEXT,
            date INTEGER,
            is_from_me INTEGER DEFAULT 0,
            is_sent INTEGER DEFAULT 0,
            is_delivered INTEGER DEFAULT 0,
            error INTEGER DEFAULT 0);
          CREATE TABLE chat_message_join (
            chat_id INTEGER, message_id INTEGER, message_date INTEGER, PRIMARY KEY (chat_id, message_id));
          CREATE TABLE message_attachment_join (message_id INTEGER, attachment_id INTEGER);
          """)
    }
  }

  func remove() {
    try? FileManager.default.removeItem(at: directory)
  }

  /// The handle row for an address on one service, created on first use.
  func handle(_ id: String, service: String = "iMessage") throws -> Int64 {
    try queue.write { db in
      try db.execute(
        sql: "INSERT OR IGNORE INTO handle (id, service) VALUES (?, ?)", arguments: [id, service])
      return try Int64.fetchOne(
        db, sql: "SELECT ROWID FROM handle WHERE id = ? AND service = ?", arguments: [id, service]) ?? 0
    }
  }

  /// A direct chat with one address on one service.
  /// A direct chat with one address on one service. `accountLogin` is the
  /// sending account Messages records, such as "P:+12673618369" or "E:sam@icloud.com".
  func directChat(with id: String, service: String = "iMessage", accountLogin: String? = nil) throws -> Int64 {
    try chat(handles: [handle(id, service: service)], service: service, identifier: id, accountLogin: accountLogin)
  }

  func chat(handles: [Int64], service: String, identifier: String? = nil, accountLogin: String? = nil) throws -> Int64 {
    try queue.write { db in
      try db.execute(
        sql: "INSERT INTO chat (chat_identifier, service_name, account_login) VALUES (?, ?, ?)",
        arguments: [identifier, service, accountLogin])
      let chat = db.lastInsertedRowID
      for handle in handles {
        try db.execute(
          sql: "INSERT INTO chat_handle_join (chat_id, handle_id) VALUES (?, ?)", arguments: [chat, handle])
      }
      return chat
    }
  }

  @discardableResult
  func addOutgoing(
    chat: Int64, text: String?, attributedBody: Data? = nil, at date: Date, sent: Bool, delivered: Bool,
    error: Int64 = 0, service: String = "iMessage"
  ) throws -> Int64 {
    try addMessage(
      chat: chat, text: text, attributedBody: attributedBody, at: date, fromMe: true, sent: sent,
      delivered: delivered, error: error, service: service)
  }

  @discardableResult
  func addMessage(
    chat: Int64, text: String?, attributedBody: Data? = nil, at date: Date, fromMe: Bool, sent: Bool,
    delivered: Bool, error: Int64 = 0, service: String = "iMessage"
  ) throws -> Int64 {
    try queue.write { db in
      let stamp = MessagesReaderService.appleTimestamp(from: date)
      try db.execute(
        sql: """
          INSERT INTO message (text, attributedBody, service, date, is_from_me, is_sent, is_delivered, error)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?)
          """,
        arguments: [
          text, attributedBody, service, stamp, fromMe ? 1 : 0, sent ? 1 : 0, delivered ? 1 : 0, error,
        ])
      let message = db.lastInsertedRowID
      try db.execute(
        sql: "INSERT INTO chat_message_join (chat_id, message_id, message_date) VALUES (?, ?, ?)",
        arguments: [chat, message, stamp])
      return message
    }
  }

  func edit(text: String, to newText: String) throws {
    try queue.write { db in
      try db.execute(sql: "UPDATE message SET text = ? WHERE text = ?", arguments: [newText, text])
    }
  }

  func redate(text: String, to date: Date) throws {
    try queue.write { db in
      try db.execute(
        sql: "UPDATE message SET date = ? WHERE text = ?",
        arguments: [MessagesReaderService.appleTimestamp(from: date), text])
    }
  }

  func markDelivered(text: String) throws {
    try queue.write { db in
      try db.execute(sql: "UPDATE message SET is_sent = 1, is_delivered = 1 WHERE text = ?", arguments: [text])
    }
  }

  /// Holds an exclusive lock on a rollback-journal store while `body` runs.
  func whileLocked<T>(_ body: () throws -> T) throws -> T {
    try queue.writeWithoutTransaction { db in
      try db.execute(sql: "BEGIN EXCLUSIVE")
      defer { try? db.execute(sql: "ROLLBACK") }
      return try body()
    }
  }

  /// The typedstream layout `MessagesReaderService.decodeAttributedBody` reads:
  /// the class name, a five-byte header, then a length-prefixed UTF-8 run.
  /// Lengths of 128 and over use an `0x81` marker and a 16-bit little-endian count.
  static func attributedBody(_ text: String) -> Data {
    let utf8 = Data(text.utf8)
    precondition(utf8.count <= 0xFFFF, "the fixture encodes at most a 16-bit length")
    var data = Data("streamtyped NSAttributedString NSObject NSString".utf8)
    data.append(contentsOf: [0x01, 0x94, 0x84, 0x01, 0x2B])
    if utf8.count < 0x80 {
      data.append(UInt8(utf8.count))
    } else {
      data.append(contentsOf: [0x81, UInt8(utf8.count & 0xFF), UInt8(utf8.count >> 8)])
    }
    data.append(utf8)
    return data
  }
}

/// A clock that only moves when the code under test sleeps or a test advances it.
final class ConfirmationTestClock: @unchecked Sendable {
  private let lock = NSLock()
  private var current: Date
  private var sleeps = 0
  /// Runs on each sleep with the sleep's ordinal, before time moves.
  var onSleep: (@Sendable (Int) throws -> Void)?

  init(_ start: Date) { current = start }

  func now() -> Date {
    lock.withLock { current }
  }

  func advance(_ seconds: TimeInterval) {
    lock.withLock { current = current.addingTimeInterval(seconds) }
  }

  func sleep(_ seconds: TimeInterval) throws {
    let ordinal = lock.withLock {
      sleeps += 1
      return sleeps
    }
    try onSleep?(ordinal)
    advance(seconds)
  }
}
