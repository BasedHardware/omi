import OmiSupport
import XCTest

@testable import Omi_Computer

/// Confirms `send_message` against `MessagesHistoryFixture`, a store shaped
/// like the Messages history. The fake send writes the rows Messages would
/// write; the injected clock and sleeper drive the poll, so nothing waits on
/// the wall clock.
final class MessageSendConfirmationTests: XCTestCase {
  static let sendStart = Date(timeIntervalSince1970: 1_800_000_000)
  static let recipient = "+14155550123"
  private static let fullWindowChecks = Int(MessageSendConfirmer.window / MessageSendConfirmer.pollInterval) + 1

  private let clock = ConfirmationTestClock(MessageSendConfirmationTests.sendStart)
  private let sends = LockedCounter()

  // MARK: - Outcomes

  func testDeliveredRowReportsDelivered() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("On my way", in: history) {
      try history.addOutgoing(chat: chat, text: "On my way", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .delivered)
    XCTAssertNil(confirmation.unconfirmedReason)
    XCTAssertFalse(confirmation.succeededAfterError)
    XCTAssertEqual(sends.count, 1)
  }

  func testACleanDeliveryStopsOnceItHasHeldForASecond() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("On my way", in: history) {
      try history.addOutgoing(chat: chat, text: "On my way", at: Self.sendStart, sent: true, delivered: true)
    }

    // Reads at 0, 0.5 and 1.0 s agree on one delivered row and no error row.
    XCTAssertEqual(confirmation.status, .delivered)
    XCTAssertEqual(confirmation.checks, 3)
    XCTAssertEqual(confirmation.waitedMilliseconds, 1000)
    XCTAssertEqual(confirmation.confirmedService, "iMessage")
  }

  func testADeliveryThatArrivesLateStillWaitsASettledSecond() async throws {
    let (history, chat) = try makeHistory()
    clock.onSleep = { sleeps in
      if sleeps == 3 { try history.markDelivered(text: "On my way") }
    }
    let confirmation = try await confirm("On my way", in: history) {
      try history.addOutgoing(chat: chat, text: "On my way", at: Self.sendStart, sent: true, delivered: false)
    }

    // Delivered from the read at 1.5 s; settled at 2.5 s.
    XCTAssertEqual(confirmation.status, .delivered)
    XCTAssertEqual(confirmation.waitedMilliseconds, 2500)
  }

  func testTheSettledSecondRestartsWhenTheDeliveredRowChanges() async throws {
    let (history, chat) = try makeHistory()
    clock.onSleep = { sleeps in
      if sleeps == 1 {
        // The first row is edited away and a second one takes its place.
        try history.edit(text: "ok", to: "edited")
        try history.addOutgoing(chat: chat, text: "ok", at: Self.sendStart, sent: true, delivered: true)
      }
    }
    let confirmation = try await confirm("ok", in: history) {
      try history.addOutgoing(chat: chat, text: "ok", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .delivered)
    XCTAssertEqual(confirmation.waitedMilliseconds, 1500, "the new row must hold for its own second")
  }

  func testAFailedReadRestartsTheSettledSecond() async throws {
    let (history, chat) = try makeHistory()
    let reads = LockedCounter()
    let store = MessageSendHistory.store(history.url, region: "US")
    let flaky = MessageSendHistory(
      latestRowID: store.latestRowID,
      outgoingStates: { handle, text, since, after, tracked in
        if reads.increment() == 2 { throw MessagesReaderError.storeReadFailed(path: "chat.db", reason: "locked") }
        return try await store.outgoingStates(handle, text, since, after, tracked)
      })
    let confirmation = try await confirm("ok", history: flaky) {
      try history.addOutgoing(chat: chat, text: "ok", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .delivered)
    XCTAssertEqual(confirmation.waitedMilliseconds, 2000, "reads at 1.0, 1.5 and 2.0 s must agree after the failure")
  }

  func testASecondIdenticalRowBeforeTheDeliverySettlesIsAmbiguous() async throws {
    let (history, chat) = try makeHistory()
    clock.onSleep = { sleeps in
      if sleeps == 1 {
        try history.addOutgoing(chat: chat, text: "ok", at: Self.sendStart, sent: true, delivered: true)
      }
    }
    let confirmation = try await confirm("ok", in: history) {
      try history.addOutgoing(chat: chat, text: "ok", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.unconfirmedReason, .ambiguous)
    XCTAssertEqual(confirmation.checks, Self.fullWindowChecks)
  }

  func testEverythingButACleanDeliveryReadsTheWholeWindow() async throws {
    let (history, chat) = try makeHistory()
    let sent = try await confirm("sent only", in: history) {
      try history.addOutgoing(chat: chat, text: "sent only", at: Self.sendStart, sent: true, delivered: false)
    }
    XCTAssertEqual(sent.checks, Self.fullWindowChecks)

    let none = try await confirm("nothing", in: history) {}
    XCTAssertEqual(none.checks, Self.fullWindowChecks)
  }

  func testARowThatMatchedStaysCountedIfItsDateChanges() async throws {
    let (history, chat) = try makeHistory()
    clock.onSleep = { sleeps in
      if sleeps == 1 { try history.redate(text: "On my way", to: Self.sendStart.addingTimeInterval(-60)) }
    }
    let confirmation = try await confirm("On my way", in: history) {
      try history.addOutgoing(chat: chat, text: "On my way", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .delivered)
  }

  func testARecipientMatchingTwoStoredNumbersIsAmbiguous() async throws {
    let history = try MessagesHistoryFixture()
    addTeardownBlock { history.remove() }
    let keepsZero = try history.directChat(with: "+390612345678")
    _ = try history.directChat(with: "+39612345678")
    let confirmation = try await confirm(
      "ciao", history: .store(history.url, region: "IT"), handle: "06 1234 5678"
    ) {
      try history.addOutgoing(chat: keepsZero, text: "ciao", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .unconfirmed)
    XCTAssertEqual(confirmation.unconfirmedReason, .ambiguousRecipient)
  }

  func testSentButNotDeliveredReportsSent() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("On my way", in: history) {
      try history.addOutgoing(chat: chat, text: "On my way", at: Self.sendStart, sent: true, delivered: false)
    }

    XCTAssertEqual(confirmation.status, .sent)
    XCTAssertNil(confirmation.unconfirmedReason)
    XCTAssertEqual(confirmation.checks, Self.fullWindowChecks)
  }

  func testDeliveryMarkedDuringThePollIsReported() async throws {
    let (history, chat) = try makeHistory()
    clock.onSleep = { sleeps in
      if sleeps == 2 { try history.markDelivered(text: "On my way") }
    }
    let confirmation = try await confirm("On my way", in: history) {
      try history.addOutgoing(chat: chat, text: "On my way", at: Self.sendStart, sent: true, delivered: false)
    }

    XCTAssertEqual(confirmation.status, .delivered)
  }

  func testErrorOnlyReportsNotDelivered() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("On my way", in: history) {
      try history.addOutgoing(
        chat: chat, text: "On my way", at: Self.sendStart, sent: false, delivered: false, error: 22)
    }

    XCTAssertEqual(confirmation.status, .notDelivered)
    XCTAssertEqual(confirmation.checks, Self.fullWindowChecks, "an error must not end the check early")
    XCTAssertEqual(sends.count, 1, "an error on the row must never trigger a second send")
  }

  func testErrorThenLaterTextMessageSuccessReportsDelivered() async throws {
    let (history, iMessageChat) = try makeHistory()
    let smsChat = try history.directChat(with: Self.recipient, service: "SMS")
    clock.onSleep = { sleeps in
      if sleeps == 2 {
        try history.addOutgoing(
          chat: smsChat, text: "On my way", at: Self.sendStart.addingTimeInterval(1), sent: true, delivered: true,
          service: "SMS")
      }
    }
    let confirmation = try await confirm("On my way", in: history) {
      try history.addOutgoing(
        chat: iMessageChat, text: "On my way", at: Self.sendStart, sent: false, delivered: false, error: 22)
    }

    XCTAssertEqual(confirmation.status, .delivered)
    XCTAssertTrue(confirmation.succeededAfterError)
    XCTAssertEqual(confirmation.confirmedService, "SMS")
    XCTAssertEqual(confirmation.checks, Self.fullWindowChecks, "a delivery after an error reads the whole window")
  }

  func testErrorBesideASentTextMessageReportsSent() async throws {
    let (history, iMessageChat) = try makeHistory()
    let smsChat = try history.directChat(with: Self.recipient, service: "SMS")
    let confirmation = try await confirm("On my way", in: history) {
      try history.addOutgoing(
        chat: iMessageChat, text: "On my way", at: Self.sendStart, sent: false, delivered: false, error: 22)
      try history.addOutgoing(
        chat: smsChat, text: "On my way", at: Self.sendStart, sent: true, delivered: false, service: "SMS")
    }

    XCTAssertEqual(confirmation.status, .sent)
    XCTAssertTrue(confirmation.succeededAfterError)
  }

  func testErrorBesideAnUnsentRowIsUnconfirmed() async throws {
    let (history, iMessageChat) = try makeHistory()
    let smsChat = try history.directChat(with: Self.recipient, service: "SMS")
    let confirmation = try await confirm("On my way", in: history) {
      try history.addOutgoing(
        chat: iMessageChat, text: "On my way", at: Self.sendStart, sent: false, delivered: false, error: 22)
      try history.addOutgoing(
        chat: smsChat, text: "On my way", at: Self.sendStart, sent: false, delivered: false, service: "SMS")
    }

    XCTAssertEqual(confirmation.status, .unconfirmed)
    XCTAssertEqual(confirmation.unconfirmedReason, .notYetSent)
  }

  func testRowNotYetMarkedSentIsUnconfirmedNotSent() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("On my way", in: history) {
      try history.addOutgoing(chat: chat, text: "On my way", at: Self.sendStart, sent: false, delivered: false)
    }

    XCTAssertEqual(confirmation.status, .unconfirmed)
    XCTAssertEqual(confirmation.unconfirmedReason, .notYetSent)
  }

  func testNoRowIsUnconfirmed() async throws {
    let (history, _) = try makeHistory()
    let confirmation = try await confirm("On my way", in: history) {}

    XCTAssertEqual(confirmation.status, .unconfirmed)
    XCTAssertEqual(confirmation.unconfirmedReason, .noMatchingRow)
    XCTAssertEqual(sends.count, 1)
  }

  // MARK: - More than one new row

  func testDeliveredBesideASentIdenticalRowIsAmbiguous() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("ok", in: history) {
      try history.addOutgoing(chat: chat, text: "ok", at: Self.sendStart, sent: true, delivered: true)
      try history.addOutgoing(chat: chat, text: "ok", at: Self.sendStart, sent: true, delivered: false)
    }

    XCTAssertEqual(confirmation.status, .unconfirmed)
    XCTAssertEqual(confirmation.unconfirmedReason, .ambiguous)
  }

  func testTwoDeliveredIdenticalRowsAreAmbiguous() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("ok", in: history) {
      try history.addOutgoing(chat: chat, text: "ok", at: Self.sendStart, sent: true, delivered: true)
      try history.addOutgoing(chat: chat, text: "ok", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.unconfirmedReason, .ambiguous)
  }

  func testIdenticalRowsInTheIMessageAndTextMessageChatsAreAmbiguous() async throws {
    let (history, iMessageChat) = try makeHistory()
    let smsChat = try history.directChat(with: Self.recipient, service: "SMS")
    let confirmation = try await confirm("ok", in: history) {
      try history.addOutgoing(chat: iMessageChat, text: "ok", at: Self.sendStart, sent: true, delivered: true)
      try history.addOutgoing(chat: smsChat, text: "ok", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.unconfirmedReason, .ambiguous)
  }

  // MARK: - Only this send's rows count

  func testOlderIdenticalRowDoesNotCount() async throws {
    let (history, chat) = try makeHistory()
    try history.addOutgoing(
      chat: chat, text: "On my way", at: Self.sendStart.addingTimeInterval(-3600), sent: true, delivered: true)

    let confirmation = try await confirm("On my way", in: history) {}

    XCTAssertEqual(confirmation.unconfirmedReason, .noMatchingRow)
  }

  func testIdenticalRowWrittenJustBeforeTheSendDoesNotCount() async throws {
    let (history, chat) = try makeHistory()
    try history.addOutgoing(
      chat: chat, text: "On my way", at: Self.sendStart.addingTimeInterval(-0.5), sent: true, delivered: true)

    let confirmation = try await confirm("On my way", in: history) {}

    XCTAssertEqual(confirmation.unconfirmedReason, .noMatchingRow)
  }

  func testSecondIdenticalSendIsJudgedOnlyByItsOwnRow() async throws {
    let (history, chat) = try makeHistory()
    let first = try await confirm("On my way", in: history) {
      try history.addOutgoing(chat: chat, text: "On my way", at: Self.sendStart, sent: true, delivered: true)
    }
    XCTAssertEqual(first.status, .delivered)

    let secondStart = clock.now()
    let second = try await confirm("On my way", in: history) {
      try history.addOutgoing(chat: chat, text: "On my way", at: secondStart, sent: true, delivered: false)
    }
    XCTAssertEqual(second.status, .sent, "the first send's delivered row must not make the second read delivered")

    let third = try await confirm("On my way", in: history) {}
    XCTAssertEqual(third.unconfirmedReason, .noMatchingRow, "earlier rows must not confirm a send that wrote nothing")
    XCTAssertEqual(sends.count, 3)
  }

  func testOldRowSyncedInDuringTheWindowDoesNotCount() async throws {
    let (history, chat) = try makeHistory()
    let synced = Self.sendStart.addingTimeInterval(-60)
    let confirmation = try await confirm("ok", in: history) {
      try history.addOutgoing(chat: chat, text: "ok", at: synced, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.unconfirmedReason, .noMatchingRow)
  }

  func testRowDatedWithinTheToleranceCounts() async throws {
    let (history, chat) = try makeHistory()
    // Half a second early: inside a 1-second tolerance, outside none at all.
    let skewed = Self.sendStart.addingTimeInterval(-0.5)
    let confirmation = try await confirm("ok", in: history) {
      try history.addOutgoing(chat: chat, text: "ok", at: skewed, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .delivered)
  }

  func testRowDatedBeyondTheToleranceDoesNotCount() async throws {
    let (history, chat) = try makeHistory()
    let tooEarly = Self.sendStart.addingTimeInterval(-(MessageSendConfirmer.clockTolerance + 0.5))
    let confirmation = try await confirm("ok", in: history) {
      try history.addOutgoing(chat: chat, text: "ok", at: tooEarly, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.unconfirmedReason, .noMatchingRow)
  }

  func testToleranceStaysSmall() {
    XCTAssertLessThanOrEqual(MessageSendConfirmer.clockTolerance, 1)
  }

  // MARK: - Which chats count

  func testTextMessageChatForTheSamePersonCounts() async throws {
    let (history, _) = try makeHistory()
    let smsChat = try history.directChat(with: Self.recipient, service: "SMS")
    let confirmation = try await confirm("ok", in: history) {
      try history.addOutgoing(
        chat: smsChat, text: "ok", at: Self.sendStart, sent: true, delivered: true, service: "SMS")
    }

    XCTAssertEqual(confirmation.status, .delivered)
  }

  func testAnotherPersonsChatWithIdenticalTextDoesNotCount() async throws {
    let (history, _) = try makeHistory()
    let india = try history.directChat(with: "+914155550123")
    let confirmation = try await confirm("ok", in: history) {
      try history.addOutgoing(chat: india, text: "ok", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.unconfirmedReason, .noMatchingRow)
  }

  func testTheSamePersonsEmailChatDoesNotCountForAPhoneSend() async throws {
    let (history, _) = try makeHistory()
    let email = try history.directChat(with: "sam@example.com")
    let confirmation = try await confirm("ok", in: history) {
      try history.addOutgoing(chat: email, text: "ok", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.unconfirmedReason, .noMatchingRow)
  }

  func testIdenticalTextInAGroupChatWithTheRecipientDoesNotCount() async throws {
    let (history, _) = try makeHistory()
    let group = try history.chat(
      handles: [history.handle(Self.recipient), history.handle("+14155550199")], service: "iMessage")
    let confirmation = try await confirm("ok", in: history) {
      try history.addOutgoing(chat: group, text: "ok", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.unconfirmedReason, .noMatchingRow)
  }

  func testIncomingIdenticalRowDoesNotCount() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("ok", in: history) {
      try history.addMessage(chat: chat, text: "ok", at: Self.sendStart, fromMe: false, sent: false, delivered: true)
    }

    XCTAssertEqual(confirmation.unconfirmedReason, .noMatchingRow)
  }

  func testHandleSpelledTheContactsWayFindsTheChat() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("ok", in: history, handle: "(415) 555-0123") {
      try history.addOutgoing(chat: chat, text: "ok", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .delivered)
  }

  // MARK: - National numbers resolved through the sending account

  func testANationalUSNumberSentFromAMacSetToIndiaConfirms() async throws {
    let history = try MessagesHistoryFixture()
    addTeardownBlock { history.remove() }
    let usChat = try history.directChat(with: "+12673618369")
    let confirmation = try await confirm(
      "omi send check 1", history: .store(history.url, region: "IN"), handle: "2673618369"
    ) {
      try history.addOutgoing(
        chat: usChat, text: "omi send check 1", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .delivered)
  }

  func testANationalNumberMatchingBothAUSAndAnIndianChatIsAmbiguous() async throws {
    let history = try MessagesHistoryFixture()
    addTeardownBlock { history.remove() }
    let usChat = try history.directChat(with: "+12673618369")
    _ = try history.directChat(with: "+912673618369")
    let confirmation = try await confirm(
      "omi send check 1", history: .store(history.url, region: "IN"), handle: "2673618369"
    ) {
      try history.addOutgoing(
        chat: usChat, text: "omi send check 1", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .unconfirmed)
    XCTAssertEqual(confirmation.unconfirmedReason, .ambiguousRecipient)
  }

  func testAPhoneSendingAccountDecidesBetweenTheSameDigitsInTwoCountries() async throws {
    let history = try MessagesHistoryFixture()
    addTeardownBlock { history.remove() }
    let account = "P:+12673618369"
    let usChat = try history.directChat(with: "+12673618369", accountLogin: account)
    _ = try history.directChat(with: "+912673618369", accountLogin: account)
    let confirmation = try await confirm(
      "omi send check 1", history: .store(history.url, region: "IN"), handle: "2673618369"
    ) {
      try history.addOutgoing(
        chat: usChat, text: "omi send check 1", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .delivered)
  }

  func testATextToYourselfIsDecidedByTheOutgoingRowNotTheIncomingCopy() async throws {
    let history = try MessagesHistoryFixture()
    addTeardownBlock { history.remove() }
    let ownChat = try history.directChat(with: "+12673618369", accountLogin: "P:+12673618369")
    let confirmation = try await confirm(
      "omi send check 1", history: .store(history.url, region: "IN"), handle: "2673618369"
    ) {
      try history.addOutgoing(
        chat: ownChat, text: "omi send check 1", at: Self.sendStart, sent: true, delivered: true)
      try history.addMessage(
        chat: ownChat, text: "omi send check 1", at: Self.sendStart, fromMe: false, sent: false, delivered: false)
    }

    XCTAssertEqual(confirmation.status, .delivered, "the incoming self-copy is ignored, not counted as a second row")
  }

  func testATextToYourselfWithoutADeliveredMarkWaitsTheWindow() async throws {
    let history = try MessagesHistoryFixture()
    addTeardownBlock { history.remove() }
    let ownChat = try history.directChat(with: "+12673618369")
    let confirmation = try await confirm(
      "omi send check 1", history: .store(history.url, region: "US"), handle: "+12673618369"
    ) {
      try history.addMessage(
        chat: ownChat, text: "omi send check 1", at: Self.sendStart, fromMe: false, sent: false, delivered: true)
    }

    XCTAssertEqual(confirmation.unconfirmedReason, .noMatchingRow, "an incoming copy alone never confirms a send")
  }

  // MARK: - Text matching

  func testLineEndingsAndWhitespaceAreNormalised() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("  Running late\r\nsee you   at\t5 \r\n", in: history) {
      try history.addOutgoing(
        chat: chat, text: "Running late\nsee you at 5", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .delivered)
  }

  func testDifferentTextDoesNotCount() async throws {
    let (history, chat) = try makeHistory()
    let confirmation = try await confirm("Running late", in: history) {
      try history.addOutgoing(chat: chat, text: "Running later", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.unconfirmedReason, .noMatchingRow)
  }

  func testBodiesStoredOnlyInTheAttributedBlobAreMatched() async throws {
    let bodies = [
      "On my way",
      String(repeating: "a", count: 127),
      String(repeating: "b", count: 128),
      String(repeating: "Running late, ", count: 12) + "😀 see you",
      String(repeating: "Long message ", count: 40),
    ]
    for body in bodies {
      let (history, chat) = try makeHistory()
      let blob = MessagesHistoryFixture.attributedBody(body)
      let start = clock.now()
      let confirmation = try await confirm(body, in: history) {
        try history.addOutgoing(chat: chat, text: nil, attributedBody: blob, at: start, sent: true, delivered: true)
      }
      XCTAssertEqual(confirmation.status, .delivered, "\(body.utf8.count)-byte body")
    }
  }

  // MARK: - Unreadable history

  func testUnreadableHistoryIsUnconfirmedAndStillSendsOnce() async throws {
    let missing = MessageSendHistory.store(URL(fileURLWithPath: "/nonexistent/omi-send-check-fixture.db"))
    let confirmation = try await confirm("ok", history: missing) {}

    XCTAssertEqual(confirmation.status, .unconfirmed)
    XCTAssertEqual(confirmation.unconfirmedReason, .historyUnreadable)
    XCTAssertEqual(confirmation.checks, 0)
    XCTAssertEqual(sends.count, 1)
  }

  func testAFailedReadMidPollIsRetriedOnTheNextTick() async throws {
    let (history, chat) = try makeHistory()
    let reads = LockedCounter()
    let store = MessageSendHistory.store(history.url, region: "US")
    let flaky = MessageSendHistory(
      latestRowID: store.latestRowID,
      outgoingStates: { handle, text, since, after, tracked in
        if reads.increment() == 1 { throw MessagesReaderError.storeReadFailed(path: "chat.db", reason: "locked") }
        return try await store.outgoingStates(handle, text, since, after, tracked)
      })
    let confirmation = try await confirm("ok", history: flaky) {
      try history.addOutgoing(chat: chat, text: "ok", at: Self.sendStart, sent: true, delivered: true)
    }

    XCTAssertEqual(confirmation.status, .delivered)
  }

  func testEveryReadAfterTheSendFailingIsUnreadable() async throws {
    let failing = MessageSendHistory(
      latestRowID: { 0 },
      outgoingStates: { _, _, _, _, _ in throw MessagesReaderError.authorizationDenied(path: "chat.db") })
    let confirmation = try await confirm("ok", history: failing) {}

    XCTAssertEqual(confirmation.unconfirmedReason, .historyUnreadable)
    XCTAssertEqual(sends.count, 1)
  }

  // MARK: - Never retried, and stopping

  func testFailedSendIsNotRetriedOrChecked() async throws {
    let reads = LockedCounter()
    let counting = MessageSendHistory(
      latestRowID: {
        reads.increment()
        return 0
      },
      outgoingStates: { _, _, _, _, _ in
        reads.increment()
        return OutgoingMessageRead(rows: [], recipientIsAmbiguous: false)
      })
    do {
      _ = try await confirm("ok", history: counting) { throw MessagesSenderError.allServicesFailed(detail: "refused") }
      XCTFail("Expected the send error to reach the caller")
    } catch MessagesSenderError.allServicesFailed {
      XCTAssertEqual(sends.count, 1)
      XCTAssertEqual(reads.count, 1, "only the baseline read runs when the send itself fails")
    }
  }

  func testStopDuringTheBaselineReadSendsNothing() async throws {
    let stopping = MessageSendHistory(
      latestRowID: {
        withUnsafeCurrentTask { $0?.cancel() }
        return 0
      },
      outgoingStates: { _, _, _, _, _ in OutgoingMessageRead(rows: [], recipientIsAmbiguous: false) })
    do {
      _ = try await confirm("ok", history: stopping) {}
      XCTFail("Expected the stop to reach the caller")
    } catch is CancellationError {
      XCTAssertEqual(sends.count, 0)
    }
  }

  func testStopBetweenPollsEndsTheCheck() async throws {
    clock.onSleep = { sleeps in
      if sleeps == 1 { withUnsafeCurrentTask { $0?.cancel() } }
    }
    // Reads that ignore cancellation, so only the loop's own check can stop it.
    let delivered = MessageSendHistory(
      latestRowID: { 0 },
      outgoingStates: { _, _, _, _, _ in
        OutgoingMessageRead(
          rows: [OutgoingMessageState(rowID: 1, service: "iMessage", isSent: true, isDelivered: true, errorCode: 0)],
          recipientIsAmbiguous: false)
      })
    let confirmation = try await confirm("ok", history: delivered) {}

    XCTAssertEqual(confirmation.unconfirmedReason, .checkStopped)
    XCTAssertEqual(confirmation.checks, 1)
  }

  func testStopDuringTheSleepEndsTheCheck() async throws {
    clock.onSleep = { _ in throw CancellationError() }
    let (history, _) = try makeHistory()
    let confirmation = try await confirm("ok", in: history) {}

    XCTAssertEqual(confirmation.unconfirmedReason, .checkStopped)
    XCTAssertEqual(sends.count, 1)
  }

  func testStopSurfacingFromAReadEndsTheCheck() async throws {
    let stopping = MessageSendHistory(
      latestRowID: { 0 }, outgoingStates: { _, _, _, _, _ in throw CancellationError() })
    let confirmation = try await confirm("ok", history: stopping) {}

    XCTAssertEqual(confirmation.unconfirmedReason, .checkStopped)
  }

  func testTimedOutSendIsStillChecked() async throws {
    let (history, chat) = try makeHistory()
    let result = try await MessageSendConfirmer.sendThenConfirm(
      handle: Self.recipient, text: "ok", history: .store(history.url, region: "US"),
      now: { [clock] in clock.now() }, sleep: { [clock] in try clock.sleep($0) },
      send: { [sends] in
        sends.increment()
        try history.addOutgoing(chat: chat, text: "ok", at: Self.sendStart, sent: true, delivered: true)
        return try await ChatToolExecutor.sendAttempt { throw MessagesSenderError.sendTimedOut(seconds: 30) }
      })

    XCTAssertEqual(result.sent, .timedOut)
    XCTAssertEqual(result.confirmation.status, .delivered)
    XCTAssertEqual(sends.count, 1)
  }

  func testOtherSendErrorsAreNotTreatedAsTimeouts() async {
    do {
      _ = try await ChatToolExecutor.sendAttempt { throw MessagesSenderError.allServicesFailed(detail: "refused") }
      XCTFail("Expected the send error to reach the caller")
    } catch {
      XCTAssertEqual((error as? MessagesSenderError)?.reasonCode, "send_failed")
    }
  }

  // MARK: - Probe

  func testDeviceToolsProbeReportsAnUnreadableHistoryAsUnconfirmed() async {
    let detail = await DeviceToolsProbe.sendCheckDetail()

    XCTAssertEqual(detail["sendCheckStatus"], "unconfirmed")
    XCTAssertEqual(detail["sendCheckReason"], "history_unreadable")
    XCTAssertEqual(detail["sendCheckSends"], "1")
  }

  // MARK: - Helpers

  /// A fresh store holding the recipient's direct iMessage chat.
  private func makeHistory() throws -> (MessagesHistoryFixture, Int64) {
    let history = try MessagesHistoryFixture()
    addTeardownBlock { history.remove() }
    return (history, try history.directChat(with: Self.recipient))
  }

  private func confirm(
    _ text: String,
    in fixture: MessagesHistoryFixture,
    handle: String = MessageSendConfirmationTests.recipient,
    send: @escaping @Sendable () async throws -> Void
  ) async throws -> MessageSendConfirmation {
    try await confirm(text, history: .store(fixture.url, region: "US"), handle: handle, send: send)
  }

  private func confirm(
    _ text: String,
    history: MessageSendHistory,
    handle: String = MessageSendConfirmationTests.recipient,
    send: @escaping @Sendable () async throws -> Void
  ) async throws -> MessageSendConfirmation {
    try await MessageSendConfirmer.sendThenConfirm(
      handle: handle,
      text: text,
      history: history,
      now: { [clock] in clock.now() },
      sleep: { [clock] in try clock.sleep($0) },
      send: { [sends] in
        sends.increment()
        try await send()
      }
    ).confirmation
  }
}
