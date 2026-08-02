import XCTest

@testable import Omi_Computer

/// Exercises the per-person message-history model's controllable seams: person↔thread identity
/// matching (including the nil-contactName fallback), the two-channel merge into one chronological
/// log, the SQL-row offset arithmetic that makes `loadMore` page backwards, and the consent gate.
///
/// No live database: the reads themselves are `nonisolated static` functions over a `DatabaseQueue`,
/// and the model reads through a `PersonMessageHistorySource` seam a stub can stand in for — so
/// "consent off performs zero reads" is asserted behaviorally rather than by inspection.
final class PersonMessageHistoryTests: XCTestCase {

  // MARK: - Identity + thread matching

  func testIdentityRejectsNamesThatCarryNoIdentity() {
    XCTAssertEqual(PersonMessageMatching.identity(for: "Maya Iyer"), "maya-iyer")
    XCTAssertEqual(
      PersonMessageMatching.identity(for: "  Maya Iyer  "), "maya-iyer",
      "surrounding whitespace is not part of a person's identity")
    XCTAssertNil(PersonMessageMatching.identity(for: nil))
    XCTAssertNil(PersonMessageMatching.identity(for: ""))
    XCTAssertNil(
      PersonMessageMatching.identity(for: "   "),
      "slug() maps an empty name to the literal \"person\"; treating that as an identity would fuse "
        + "every unnamed thread onto one person")
    XCTAssertNil(
      PersonMessageMatching.identity(for: "—?—"),
      "a symbol-only name also slugs to \"person\" and must not become a match key")
  }

  func testMatchKeysUsePersonIDDisplayNameAndOptionalContactName() {
    let withContact = PersonMessageMatching.matchKeys(
      personID: "maya-iyer", contactName: "Maya R Iyer", displayName: "Maya")
    XCTAssertTrue(withContact.contains("maya-iyer"), "the person id is itself a match key")
    XCTAssertTrue(withContact.contains("maya-r-iyer"), "the contact name's slug is a match key")
    XCTAssertTrue(withContact.contains("maya"), "the display name's slug is a match key")

    // The people file does not carry a contact name for every person; matching must still work.
    let withoutContact = PersonMessageMatching.matchKeys(
      personID: "maya-iyer", contactName: nil, displayName: "Maya Iyer")
    XCTAssertEqual(
      withoutContact, ["maya-iyer"],
      "with no contact name the person id and the display-name slug are the only keys (identical here)")

    let renamed = PersonMessageMatching.matchKeys(
      personID: "person-42", contactName: nil, displayName: "Maya Iyer")
    XCTAssertEqual(
      renamed, ["person-42", "maya-iyer"],
      "a person id that is not the display name's slug still matches threads by display name")
  }

  func testThreadMatchesOnContactNameSlugAndNeverOnAnUnnamedThread() {
    let keys = PersonMessageMatching.matchKeys(
      personID: "maya-iyer", contactName: nil, displayName: "Maya Iyer")

    let imessage = PersonThreadRef(
      chatID: 7, channel: PersonMessage.imessageChannel, contactName: "Maya Iyer")
    let whatsApp = PersonThreadRef(
      chatID: 12, channel: PersonMessage.whatsAppChannel, contactName: "maya  iyer")
    let someoneElse = PersonThreadRef(
      chatID: 9, channel: PersonMessage.imessageChannel, contactName: "Maya Sharma")
    let unnamed = PersonThreadRef(
      chatID: 3, channel: PersonMessage.imessageChannel, contactName: nil)

    XCTAssertTrue(PersonMessageMatching.matches(imessage, keys: keys))
    XCTAssertTrue(
      PersonMessageMatching.matches(whatsApp, keys: keys),
      "WhatsApp's own partner name slugs to the same identity as the iMessage contact name")
    XCTAssertFalse(
      PersonMessageMatching.matches(someoneElse, keys: keys),
      "a shared first name is never a match — that is how people get fused")
    XCTAssertFalse(
      PersonMessageMatching.matches(unnamed, keys: keys),
      "a thread whose counterpart could not be named is not evidence of anyone")
  }

  // MARK: - Two-channel merge

  private func message(
    _ id: String, _ channel: String, _ secondsSinceReference: Double, fromMe: Bool = false
  ) -> PersonMessage {
    PersonMessage(
      id: id, text: "m-\(id)", isFromMe: fromMe,
      date: Date(timeIntervalSinceReferenceDate: secondsSinceReference), channel: channel)
  }

  func testMergeInterleavesChannelsOldestFirstAndDeduplicates() {
    let imessage = [
      message("imessage:1", PersonMessage.imessageChannel, 100),
      message("imessage:2", PersonMessage.imessageChannel, 300),
    ]
    let whatsApp = [
      message("whatsapp:1", PersonMessage.whatsAppChannel, 200),
      message("whatsapp:2", PersonMessage.whatsAppChannel, 400),
    ]

    let merged = PersonMessageMatching.merge([imessage, whatsApp])
    XCTAssertEqual(
      merged.map(\.id), ["imessage:1", "whatsapp:1", "imessage:2", "whatsapp:2"],
      "both channels render as one chat log, oldest first")

    // Overlapping pages (a `loadMore` that re-reads a boundary row) must not duplicate a message.
    let overlapping = PersonMessageMatching.merge([merged, imessage, whatsApp])
    XCTAssertEqual(overlapping.map(\.id), merged.map(\.id), "merge de-duplicates by message id")
  }

  func testMergeOrdersEqualTimestampsDeterministically() {
    let tie = [
      message("whatsapp:9", PersonMessage.whatsAppChannel, 500),
      message("imessage:9", PersonMessage.imessageChannel, 500),
    ]
    XCTAssertEqual(
      PersonMessageMatching.merge([tie]).map(\.id), ["imessage:9", "whatsapp:9"],
      "messages sharing a timestamp order by id so the log never reshuffles between reads")
    XCTAssertEqual(
      PersonMessageMatching.merge([tie.reversed()]).map(\.id), ["imessage:9", "whatsapp:9"],
      "the tiebreak does not depend on the order the channels were read in")
  }

  // MARK: - Pagination offset arithmetic

  /// The cursor counts SQL rows, not kept messages. An iMessage row whose `attributedBody` decodes
  /// to nothing is dropped in Swift after the query; advancing by kept-message count would re-read
  /// those rows on every page and the log would stop paging backwards.
  func testCursorAdvancesBySQLRowsScannedNotByMessagesKept() {
    var cursor = PersonMessageCursor()
    XCTAssertEqual(cursor.offset, 0)
    XCTAssertFalse(cursor.exhausted)

    // A full page of 50 rows where only 37 decoded to text still advances the offset by 50.
    cursor.advance(rowsScanned: 50, rowsRequested: 50)
    XCTAssertEqual(cursor.offset, 50, "offset advances by rows consumed, not messages rendered")
    XCTAssertFalse(cursor.exhausted, "a full page means there may be older history")

    cursor.advance(rowsScanned: 50, rowsRequested: 50)
    XCTAssertEqual(cursor.offset, 100)
    XCTAssertFalse(cursor.exhausted)

    // A short page is the end of the thread.
    cursor.advance(rowsScanned: 12, rowsRequested: 50)
    XCTAssertEqual(cursor.offset, 112)
    XCTAssertTrue(cursor.exhausted, "fewer rows than requested means there is no older history")
  }

  func testCursorsReportMoreUntilBothChannelsAreExhausted() {
    var cursors = PersonMessageCursors()
    XCTAssertTrue(cursors.hasMore, "a fresh pair of cursors has not read anything yet")

    cursors.imessage.advance(rowsScanned: 3, rowsRequested: 50)
    XCTAssertTrue(
      cursors.hasMore, "iMessage ran dry but WhatsApp may still have years of older history")

    cursors.whatsApp.finish()
    XCTAssertFalse(cursors.hasMore, "only when both channels are exhausted does paging stop")
  }

  func testChannelWithNoMatchingThreadIsFinishedSoItIsNeverRePaged() {
    var cursor = PersonMessageCursor()
    cursor.finish()
    XCTAssertTrue(cursor.exhausted)
    XCTAssertEqual(cursor.offset, 0, "finishing an unmatched channel does not fabricate an offset")
  }

  // MARK: - Consent gate + model state machine

  /// Counts reads so the consent gate is proved by behavior: an off flag must reach zero reads.
  private actor StubSource: PersonMessageHistorySource {
    private(set) var pageCalls = 0
    private(set) var closeCalls = 0
    private var outcomes: [PersonMessagePageOutcome]

    init(outcomes: [PersonMessagePageOutcome] = []) {
      self.outcomes = outcomes
    }

    func page(_ request: PersonMessagePageRequest) async -> PersonMessagePageOutcome {
      pageCalls += 1
      guard !outcomes.isEmpty else { return .page(messages: [], cursors: PersonMessageCursors()) }
      return outcomes.removeFirst()
    }

    func close() async {
      closeCalls += 1
    }
  }

  @MainActor
  func testConsentOffPublishesNeedsConsentAndReadsNothing() async {
    let source = StubSource()
    let model = PersonMessageHistoryModel(source: source, consentGranted: { false })

    await model.load(personID: "maya-iyer", contactName: nil, displayName: "Maya Iyer")

    XCTAssertEqual(model.state, .needsConsent)
    XCTAssertTrue(model.messages.isEmpty)
    XCTAssertFalse(model.canLoadMore)
    let reads = await source.pageCalls
    XCTAssertEqual(reads, 0, "consent off must not open or read any on-device message store")

    // Paging must stay gated too — a scroll cannot back-door the flag.
    await model.loadMore()
    let readsAfterLoadMore = await source.pageCalls
    XCTAssertEqual(readsAfterLoadMore, 0, "loadMore is gated by the same consent flag")
  }

  @MainActor
  func testLoadPublishesLoadedPageAndLoadMorePrependsOlderHistory() async {
    var first = PersonMessageCursors()
    first.imessage.advance(rowsScanned: 50, rowsRequested: 50)
    first.whatsApp.finish()
    var second = first
    second.imessage.advance(rowsScanned: 2, rowsRequested: 50)

    let recent = [
      message("imessage:10", PersonMessage.imessageChannel, 1000),
      message("imessage:11", PersonMessage.imessageChannel, 1100),
    ]
    let older = [
      message("imessage:1", PersonMessage.imessageChannel, 100),
      message("imessage:2", PersonMessage.imessageChannel, 200),
    ]
    let source = StubSource(outcomes: [
      .page(messages: recent, cursors: first),
      .page(messages: older, cursors: second),
    ])
    let model = PersonMessageHistoryModel(source: source, consentGranted: { true })

    await model.load(personID: "maya-iyer", contactName: nil, displayName: "Maya Iyer")
    XCTAssertEqual(model.state, .loaded)
    XCTAssertEqual(model.messages.map(\.id), ["imessage:10", "imessage:11"])
    XCTAssertTrue(model.canLoadMore, "iMessage returned a full page, so older history may exist")

    await model.loadMore()
    XCTAssertEqual(
      model.messages.map(\.id), ["imessage:1", "imessage:2", "imessage:10", "imessage:11"],
      "older messages merge in ahead of the page already on screen")
    XCTAssertFalse(model.canLoadMore, "a short page exhausted the last channel")

    await model.loadMore()
    let reads = await source.pageCalls
    XCTAssertEqual(reads, 2, "loadMore is a no-op once both channels are exhausted")
  }

  @MainActor
  func testMissingFullDiskAccessAndAbsentStoresPublishDistinctStates() async {
    let blocked = StubSource(outcomes: [.needsFullDiskAccess])
    let blockedModel = PersonMessageHistoryModel(source: blocked, consentGranted: { true })
    await blockedModel.load(personID: "maya-iyer", contactName: nil, displayName: "Maya Iyer")
    XCTAssertEqual(blockedModel.state, .needsFullDiskAccess)
    XCTAssertFalse(blockedModel.canLoadMore)

    let absent = StubSource(outcomes: [.unavailable])
    let absentModel = PersonMessageHistoryModel(source: absent, consentGranted: { true })
    await absentModel.load(personID: "maya-iyer", contactName: nil, displayName: "Maya Iyer")
    XCTAssertEqual(
      absentModel.state, .unavailable,
      "no messaging database at all is a different answer than a missing grant")
  }

  @MainActor
  func testResetClearsStateAndReleasesTheCachedSnapshot() async {
    var cursors = PersonMessageCursors()
    cursors.imessage.advance(rowsScanned: 50, rowsRequested: 50)
    let source = StubSource(outcomes: [
      .page(messages: [message("imessage:1", PersonMessage.imessageChannel, 100)], cursors: cursors)
    ])
    let model = PersonMessageHistoryModel(source: source, consentGranted: { true })

    await model.load(personID: "maya-iyer", contactName: nil, displayName: "Maya Iyer")
    XCTAssertFalse(model.messages.isEmpty)

    model.reset()
    XCTAssertEqual(model.state, .idle)
    XCTAssertTrue(model.messages.isEmpty)
    XCTAssertFalse(model.canLoadMore)

    // `reset` releases the database copies on a detached task; poll rather than sleep so the test
    // stays hermetic and does not depend on a fixed delay.
    var closes = await source.closeCalls
    for _ in 0..<200 where closes == 0 {
      await Task.yield()
      closes = await source.closeCalls
    }
    XCTAssertEqual(closes, 1, "reset must delete the disposable copy of the user's message database")

    // After a reset there is nothing to page.
    await model.loadMore()
    let reads = await source.pageCalls
    XCTAssertEqual(reads, 1, "loadMore after reset has no person to page")
  }
}
