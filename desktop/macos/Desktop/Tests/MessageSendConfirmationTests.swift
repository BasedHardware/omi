import GRDB
import XCTest

@testable import Omi_Computer

/// Confirms `send_message` against a small store shaped like the Messages
/// history (`chat.db`), built here rather than read from a real Mac. The fake
/// send writes the row Messages would write; the injected clock and sleeper
/// stand in for the poll so nothing waits on the wall clock.
final class MessageSendConfirmationTests: XCTestCase {
  private static let sendStart = Date(timeIntervalSince1970: 1_800_000_000)
  private static let recipient = "+15555550123"

  private let clock = ConfirmationTestClock(MessageSendConfirmationTests.sendStart)
  private let sends = CallCounter()
  private let lookups = CallCounter()

  // MARK: - Outcomes

  func testDeliveredRowReportsDeliveredOnTheFirstCheck() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("On my way", store: history.url) { [history, chat] in
      try history.addOutgoing(chat: chat, text: "On my way", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .delivered)
    XCTAssertNil(confirmation.unconfirmedReason)
    XCTAssertEqual(confirmation.checks, 1)
    XCTAssertEqual(sends.count, 1)
  }

  func testSentButNotDeliveredReportsSentWhenTheWindowEnds() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("On my way", store: history.url) { [history, chat] in
      try history.addOutgoing(chat: chat, text: "On my way", at: Self.sendStart, sent: true, delivered: false)
    }

    XCTAssertEqual(confirmation.status, .sent)
    XCTAssertNil(confirmation.unconfirmedReason)
    XCTAssertEqual(confirmation.waitedMilliseconds, Int(MessageSendConfirmer.window * 1000))
    XCTAssertGreaterThan(confirmation.checks, 1)
    XCTAssertEqual(sends.count, 1)
  }

  func testDeliveryMarkedDuringThePollIsReported() async throws {
    let (history, chat) = try makeHistory()
    let rowID = LockedValue<Int64>(0)
    clock.onSleep = { [history] sleeps in
      if sleeps == 2 { try history.markDelivered(rowID.value) }
    }
    let confirmation = try await confirm("On my way", store: history.url) { [history, chat] in
      rowID.value = try history.addOutgoing(
        chat: chat, text: "On my way", at: Self.sendStart, sent: true, delivered: false)
    }

    XCTAssertEqual(confirmation.status, .delivered)
    XCTAssertEqual(confirmation.checks, 3)
    XCTAssertEqual(confirmation.waitedMilliseconds, 1000)
  }

  func testRowWithAnErrorReportsNotDelivered() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("On my way", store: history.url) { [history, chat] in
      try history.addOutgoing(
        chat: chat, text: "On my way", at: Self.sendStart, sent: false, delivered: false, error: 22)
    }

    XCTAssertEqual(confirmation.status, .notDelivered)
    XCTAssertEqual(confirmation.checks, 1)
    XCTAssertEqual(sends.count, 1, "an error on the row must never trigger a second send")
  }

  func testRowNotYetMarkedSentIsUnconfirmedNotSent() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("On my way", store: history.url) { [history, chat] in
      try history.addOutgoing(chat: chat, text: "On my way", at: Self.sendStart, sent: false, delivered: false)
    }

    XCTAssertEqual(confirmation.status, .unconfirmed)
    XCTAssertEqual(confirmation.unconfirmedReason, .notYetSent)
  }

  func testNoRowIsUnconfirmedAndNotRetried() async throws {
    let (history, _) = try makeHistory()
    let confirmation = try await confirm("On my way", store: history.url) { _ = 0 }

    XCTAssertEqual(confirmation.status, .unconfirmed)
    XCTAssertEqual(confirmation.unconfirmedReason, .noMatchingRow)
    XCTAssertEqual(confirmation.waitedMilliseconds, Int(MessageSendConfirmer.window * 1000))
    XCTAssertEqual(sends.count, 1)
  }

  // MARK: - Only this send's row counts

  func testOlderIdenticalRowDoesNotCount() async throws {
    let (history, chat) = try makeHistory()
    try history.addOutgoing(
      chat: chat, text: "On my way", at: Self.sendStart.addingTimeInterval(-3600), sent: true, delivered: true)

    let confirmation = try await confirm("On my way", store: history.url) { _ = 0 }

    XCTAssertEqual(confirmation.status, .unconfirmed)
    XCTAssertEqual(confirmation.unconfirmedReason, .noMatchingRow)
  }

  func testIdenticalRowInsideTheToleranceThatExistedBeforeTheSendDoesNotCount() async throws {
    let (history, chat) = try makeHistory()
    try history.addOutgoing(
      chat: chat, text: "On my way", at: Self.sendStart.addingTimeInterval(-1), sent: true, delivered: true)

    let confirmation = try await confirm("On my way", store: history.url) { _ = 0 }

    XCTAssertEqual(confirmation.status, .unconfirmed)
    XCTAssertEqual(confirmation.unconfirmedReason, .noMatchingRow)
  }

  func testSecondIdenticalSendIsJudgedOnlyByItsOwnRow() async throws {
    let (history, chat) = try makeHistory()
    let first = try await confirm("On my way", store: history.url) { [history, chat] in
      try history.addOutgoing(chat: chat, text: "On my way", at: Self.sendStart, sent: true, delivered: true)
    }
    XCTAssertEqual(first.status, .delivered)

    clock.advance(1)
    let secondStart = clock.now()
    let second = try await confirm("On my way", store: history.url) { [history, chat] in
      try history.addOutgoing(chat: chat, text: "On my way", at: secondStart, sent: true, delivered: false)
    }
    XCTAssertEqual(second.status, .sent, "the first send's delivered row must not make the second read delivered")
    XCTAssertEqual(sends.count, 2)
  }

  func testSecondIdenticalSendThatWroteNothingIsUnconfirmed() async throws {
    let (history, chat) = try makeHistory()
    let first = try await confirm("On my way", store: history.url) { [history, chat] in
      try history.addOutgoing(chat: chat, text: "On my way", at: Self.sendStart, sent: true, delivered: true)
    }
    XCTAssertEqual(first.status, .delivered)

    clock.advance(1)
    let second = try await confirm("On my way", store: history.url) { _ = 0 }
    XCTAssertEqual(second.status, .unconfirmed, "the first send's row must not confirm a send that wrote nothing")
    XCTAssertEqual(sends.count, 2)
  }

  func testDisagreeingNewIdenticalRowsAreUnconfirmed() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("On my way", store: history.url) { [history, chat] in
      try history.addOutgoing(chat: chat, text: "On my way", at: Self.sendStart, sent: true, delivered: true)
      try history.addOutgoing(
        chat: chat, text: "On my way", at: Self.sendStart, sent: false, delivered: false, error: 22)
    }

    XCTAssertEqual(confirmation.status, .unconfirmed)
    XCTAssertEqual(confirmation.unconfirmedReason, .ambiguous)
  }

  func testIdenticalTextInAGroupChatWithTheRecipientDoesNotCount() async throws {
    let (history, _) = try makeHistory()
    let recipient = try history.handleID(Self.recipient)
    let other = try history.addHandle("+15555550199")
    let group = try history.addChat(handles: [recipient, other], service: "iMessage")

    let confirmation = try await confirm("On my way", store: history.url) { [history] in
      try history.addOutgoing(chat: group, text: "On my way", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .unconfirmed)
    XCTAssertEqual(confirmation.unconfirmedReason, .noMatchingRow)
  }

  func testIncomingIdenticalRowDoesNotCount() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("On my way", store: history.url) { [history, chat] in
      try history.addMessage(
        chat: chat, text: "On my way", at: Self.sendStart, fromMe: false, sent: false, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .unconfirmed)
  }

  // MARK: - Clock tolerance

  func testRowDatedSlightlyBeforeTheSendStartCounts() async throws {
    let (history, chat) = try makeHistory()
    let skewed = Self.sendStart.addingTimeInterval(-2)
    let confirmation = try await confirm("On my way", store: history.url) { [history, chat] in
      try history.addOutgoing(chat: chat, text: "On my way", at: skewed, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .delivered)
  }

  func testRowDatedBeyondTheToleranceDoesNotCount() async throws {
    let (history, chat) = try makeHistory()
    let tooEarly = Self.sendStart.addingTimeInterval(-(MessageSendConfirmer.clockTolerance + 1))
    let confirmation = try await confirm("On my way", store: history.url) { [history, chat] in
      try history.addOutgoing(chat: chat, text: "On my way", at: tooEarly, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .unconfirmed)
  }

  // MARK: - Text and handle matching

  func testLineEndingsAndWhitespaceAreNormalised() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("  Running late\r\nsee you   at\t5 \r\n", store: history.url) {
      [history, chat] in
      try history.addOutgoing(
        chat: chat, text: "Running late\nsee you at 5", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .delivered)
  }

  func testDifferentTextDoesNotCount() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("Running late", store: history.url) { [history, chat] in
      try history.addOutgoing(chat: chat, text: "Running later", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .unconfirmed)
  }

  func testBodyStoredOnlyInTheAttributedBlobIsMatched() async throws {
    let (history, chat) = try makeHistory()
    let blob = MessagesHistoryFixture.attributedBody("On my way")
    let confirmation = try await confirm("On my way", store: history.url) { [history, chat] in
      try history.addOutgoing(
        chat: chat, text: nil, attributedBody: blob, at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .delivered)
  }

  func testHandleSpelledTheContactsWayFindsTheChat() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("On my way", handle: "(555) 555-0123", store: history.url) { [history, chat] in
      try history.addOutgoing(chat: chat, text: "On my way", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .delivered)
  }

  func testHandleMatching() {
    XCTAssertTrue(MessagesReaderService.isSameMessagingHandle("+15555550123", "(555) 555-0123"))
    XCTAssertTrue(MessagesReaderService.isSameMessagingHandle("+15555550123", "+1 555-555-0123"))
    XCTAssertTrue(MessagesReaderService.isSameMessagingHandle("+447700900123", "07700 900123"))
    XCTAssertTrue(MessagesReaderService.isSameMessagingHandle("Sam@Example.com", "sam@example.com"))
    XCTAssertTrue(MessagesReaderService.isSameMessagingHandle("12345", "12345"))
    XCTAssertFalse(MessagesReaderService.isSameMessagingHandle("+15555550123", "+15555550124"))
    XCTAssertFalse(MessagesReaderService.isSameMessagingHandle("+15555550123", "0123"))
    XCTAssertFalse(MessagesReaderService.isSameMessagingHandle("512345", "12345"))
    XCTAssertFalse(MessagesReaderService.isSameMessagingHandle("sam@example.com", "sam@example.org"))
    XCTAssertFalse(MessagesReaderService.isSameMessagingHandle("", ""))
  }

  // MARK: - Unreadable history

  func testUnreadableHistoryIsUnconfirmedAndStillSendsOnce() async throws {
    let missing = URL(fileURLWithPath: "/nonexistent/omi-send-check-fixture.db")
    let confirmation = try await confirm("On my way", store: missing) { _ = 0 }

    XCTAssertEqual(confirmation.status, .unconfirmed)
    XCTAssertEqual(confirmation.unconfirmedReason, .historyUnreadable)
    XCTAssertEqual(confirmation.checks, 0)
    XCTAssertEqual(sends.count, 1)
  }

  func testHistoryBecomingUnreadableAfterTheSendIsUnconfirmed() async throws {
    let lookups = CallCounter()
    let result = try await MessageSendConfirmer.sendThenConfirm(
      handle: Self.recipient,
      text: "On my way",
      lookup: { _, _, _ in
        if lookups.increment() > 1 { throw MessagesReaderError.authorizationDenied(path: "chat.db") }
        return []
      },
      now: { [clock] in clock.now() },
      sleep: { [clock] in try clock.sleep($0) },
      send: { [sends] in sends.increment() })

    XCTAssertEqual(result.confirmation.status, .unconfirmed)
    XCTAssertEqual(result.confirmation.unconfirmedReason, .historyUnreadable)
    XCTAssertEqual(sends.count, 1)
  }

  func testDeviceToolsProbeReportsAnUnreadableHistoryAsUnconfirmed() async {
    let detail = await DeviceToolsProbe.run(messagesDbPath: nil)

    XCTAssertEqual(detail["sendCheckStatus"], "unconfirmed")
    XCTAssertEqual(detail["sendCheckReason"], "history_unreadable")
    XCTAssertEqual(detail["sendCheckSends"], "1")
  }

  // MARK: - Never retried

  func testFailedSendIsNotRetriedOrChecked() async throws {
    let (history, _) = try makeHistory()
    do {
      _ = try await confirm("On my way", store: history.url) {
        throw MessagesSenderError.allServicesFailed(detail: "refused")
      }
      XCTFail("Expected the send error to reach the caller")
    } catch MessagesSenderError.allServicesFailed {
      XCTAssertEqual(sends.count, 1)
      XCTAssertEqual(lookups.count, 1, "only the baseline read runs when the send itself fails")
    }
  }

  func testStoppedCheckIsUnconfirmed() async throws {
    let (history, _) = try makeHistory()
    clock.onSleep = { _ in throw CancellationError() }
    let confirmation = try await confirm("On my way", store: history.url) { _ = 0 }

    XCTAssertEqual(confirmation.status, .unconfirmed)
    XCTAssertEqual(confirmation.unconfirmedReason, .checkStopped)
    XCTAssertEqual(sends.count, 1)
  }

  // MARK: - Result wording

  @MainActor
  func testResultTellsTheModelWhatHappened() throws {
    let outcome = MessageSendOutcome(handle: Self.recipient, service: "iMessage", attachedFile: nil)
    func result(_ status: MessageSendOutcomeStatus, _ reason: MessageSendConfirmation.UnconfirmedReason? = nil)
      throws -> [String: Any]
    {
      let json = ChatToolExecutor.sendMessageResult(
        outcome,
        confirmation: MessageSendConfirmation(
          status: status, unconfirmedReason: reason, checks: 1, waitedMilliseconds: 0),
        charactersSent: 9)
      return try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
    }

    let delivered = try result(.delivered)
    XCTAssertEqual(delivered["ok"] as? Bool, true)
    XCTAssertEqual(delivered["status"] as? String, "delivered")

    let sent = try result(.sent)
    XCTAssertEqual(sent["status"] as? String, "sent")
    XCTAssertTrue((sent["summary"] as? String ?? "").contains("not yet delivered"))

    let unconfirmed = try result(.unconfirmed, .historyUnreadable)
    XCTAssertEqual(unconfirmed["ok"] as? Bool, true, "an unknown outcome is not a failure")
    XCTAssertNil(unconfirmed["error"], "an error key would record the call as failed")
    XCTAssertEqual(unconfirmed["unconfirmed_reason"] as? String, "history_unreadable")
    let unconfirmedSummary = unconfirmed["summary"] as? String ?? ""
    XCTAssertTrue(unconfirmedSummary.contains("check Messages"))
    XCTAssertTrue(unconfirmedSummary.contains("Do not send it again"))

    let notDelivered = try result(.notDelivered)
    XCTAssertEqual(notDelivered["ok"] as? Bool, false)
    XCTAssertEqual(notDelivered["status"] as? String, "not_delivered")
    XCTAssertEqual(notDelivered["reason"] as? String, "not_delivered")
  }

  // MARK: - Helpers

  /// A fresh store holding the recipient's direct iMessage chat.
  private func makeHistory() throws -> (MessagesHistoryFixture, Int64) {
    let history = try MessagesHistoryFixture()
    addTeardownBlock { history.remove() }
    let handle = try history.addHandle(Self.recipient)
    return (history, try history.addChat(handles: [handle], service: "iMessage"))
  }

  private func confirm(
    _ text: String,
    handle: String = MessageSendConfirmationTests.recipient,
    store storeURL: URL,
    send: @escaping @Sendable () async throws -> Void
  ) async throws -> MessageSendConfirmation {
    let result = try await MessageSendConfirmer.sendThenConfirm(
      handle: handle,
      text: text,
      lookup: { [lookups] handle, text, since in
        lookups.increment()
        return try await MessagesReaderService.shared.outgoingMessageStates(
          sentTo: handle, text: text, createdSince: since, storeOverride: storeURL)
      },
      now: { [clock] in clock.now() },
      sleep: { [clock] in try clock.sleep($0) },
      send: { [sends] in
        sends.increment()
        try await send()
      })
    return result.confirmation
  }
}

// MARK: - Fixture

/// The tables and columns of `chat.db` that the reader touches.
private final class MessagesHistoryFixture: @unchecked Sendable {
  let directory: URL
  let url: URL
  private let queue: DatabaseQueue

  init() throws {
    directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-send-check-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    url = directory.appendingPathComponent("chat.db")
    queue = try DatabaseQueue(path: url.path)
    try queue.write { db in
      try db.execute(
        sql: """
          CREATE TABLE handle (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL, service TEXT);
          CREATE TABLE chat (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT, chat_identifier TEXT, service_name TEXT, display_name TEXT);
          CREATE TABLE chat_handle_join (chat_id INTEGER, handle_id INTEGER);
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
          CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER, message_date INTEGER);
          CREATE TABLE message_attachment_join (message_id INTEGER, attachment_id INTEGER);
          """)
    }
  }

  func remove() {
    try? FileManager.default.removeItem(at: directory)
  }

  func addHandle(_ id: String) throws -> Int64 {
    try queue.write { db in
      try db.execute(sql: "INSERT INTO handle (id, service) VALUES (?, 'iMessage')", arguments: [id])
      return db.lastInsertedRowID
    }
  }

  func handleID(_ id: String) throws -> Int64 {
    try queue.read { db in
      try XCTUnwrap(try Int64.fetchOne(db, sql: "SELECT ROWID FROM handle WHERE id = ?", arguments: [id]))
    }
  }

  func addChat(handles: [Int64], service: String) throws -> Int64 {
    try queue.write { db in
      try db.execute(sql: "INSERT INTO chat (service_name) VALUES (?)", arguments: [service])
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
    error: Int64 = 0
  ) throws -> Int64 {
    try addMessage(
      chat: chat, text: text, attributedBody: attributedBody, at: date, fromMe: true, sent: sent,
      delivered: delivered, error: error)
  }

  @discardableResult
  func addMessage(
    chat: Int64, text: String?, attributedBody: Data? = nil, at date: Date, fromMe: Bool, sent: Bool,
    delivered: Bool, error: Int64 = 0
  ) throws -> Int64 {
    try queue.write { db in
      let stamp = MessagesReaderService.appleTimestamp(from: date)
      try db.execute(
        sql: """
          INSERT INTO message (text, attributedBody, service, date, is_from_me, is_sent, is_delivered, error)
          VALUES (?, ?, 'iMessage', ?, ?, ?, ?, ?)
          """,
        arguments: [text, attributedBody, stamp, fromMe ? 1 : 0, sent ? 1 : 0, delivered ? 1 : 0, error])
      let message = db.lastInsertedRowID
      try db.execute(
        sql: "INSERT INTO chat_message_join (chat_id, message_id, message_date) VALUES (?, ?, ?)",
        arguments: [chat, message, stamp])
      return message
    }
  }

  func markDelivered(_ rowID: Int64) throws {
    try queue.write { db in
      try db.execute(sql: "UPDATE message SET is_sent = 1, is_delivered = 1 WHERE ROWID = ?", arguments: [rowID])
    }
  }

  /// The typedstream layout `MessagesReaderService.decodeAttributedBody` reads:
  /// the class name, a five-byte header, a length byte, then UTF-8.
  static func attributedBody(_ text: String) -> Data {
    let utf8 = Data(text.utf8)
    var data = Data("streamtyped NSAttributedString NSObject NSString".utf8)
    data.append(contentsOf: [0x01, 0x94, 0x84, 0x01, 0x2B, UInt8(utf8.count)])
    data.append(utf8)
    return data
  }
}

/// A clock that only moves when the confirmer sleeps or a test advances it.
private final class ConfirmationTestClock: @unchecked Sendable {
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

private final class CallCounter: @unchecked Sendable {
  private let lock = NSLock()
  private var calls = 0

  var count: Int { lock.withLock { calls } }

  @discardableResult
  func increment() -> Int {
    lock.withLock {
      calls += 1
      return calls
    }
  }
}

private final class LockedValue<Value: Sendable>: @unchecked Sendable {
  private let lock = NSLock()
  private var stored: Value

  init(_ value: Value) { stored = value }

  var value: Value {
    get { lock.withLock { stored } }
    set { lock.withLock { stored = newValue } }
  }
}
