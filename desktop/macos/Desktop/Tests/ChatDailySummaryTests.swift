import Foundation
import XCTest

@testable import Omi_Computer

/// The daily summary as Chat renders it: the date rules, the follow-up, the notch-card
/// announcement, and the owner scoping that keeps one account's day off another's screen.
final class ChatDailySummaryTests: XCTestCase {
  /// Test-only mutable state the injected `@Sendable` closures can capture.
  private final class Box: @unchecked Sendable {
    var calls = 0
    var clock = Date(timeIntervalSince1970: 1_000)
    var records: [DailySummaryRecord] = []
    var cards: [(title: String, body: String)] = []
    var owner: String? = "owner-a"
  }

  private var calendar: Calendar {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(identifier: "America/New_York") ?? .current
    return calendar
  }

  private func date(_ year: Int, _ month: Int, _ day: Int, hour: Int = 9) -> Date {
    calendar.date(from: DateComponents(year: year, month: month, day: day, hour: hour))
      ?? Date(timeIntervalSince1970: 0)
  }

  private func record(
    id: String = "ds_1", date: String? = "2026-09-01", headline: String? = "A focused day",
    overview: String? = "You shipped the summary card.",
    highlights: [DailySummaryRecord.Highlight]? = nil,
    actionItems: [DailySummaryRecord.ActionItem]? = nil
  ) -> DailySummaryRecord {
    DailySummaryRecord(
      id: id, date: date, headline: headline, overview: overview, dayEmoji: "🚀",
      highlights: highlights, actionItems: actionItems)
  }

  // MARK: - Date label

  func testDateLabelSaysTodayYesterdayThenTheWeekdayAndDate() {
    let now = date(2026, 9, 2)
    XCTAssertEqual(
      ChatDailySummaryPresentation.dateLabel(
        for: "2026-09-02", now: now, calendar: calendar, locale: Locale(identifier: "en_US")),
      "Today")
    XCTAssertEqual(
      ChatDailySummaryPresentation.dateLabel(
        for: "2026-09-01", now: now, calendar: calendar, locale: Locale(identifier: "en_US")),
      "Yesterday")
    XCTAssertEqual(
      ChatDailySummaryPresentation.dateLabel(
        for: "2026-08-30", now: now, calendar: calendar, locale: Locale(identifier: "en_US")),
      "Sun, Aug 30")
  }

  /// The day before the 1st is in the previous month, and a subtract-86400 implementation gets
  /// this right only by accident. Counting calendar days is what makes it a rule.
  func testDateLabelCrossesAMonthBoundary() {
    let now = date(2026, 9, 1)
    XCTAssertEqual(
      ChatDailySummaryPresentation.dateLabel(
        for: "2026-08-31", now: now, calendar: calendar, locale: Locale(identifier: "en_US")),
      "Yesterday")
    XCTAssertEqual(
      ChatDailySummaryPresentation.dateLabel(
        for: "2026-08-30", now: now, calendar: calendar, locale: Locale(identifier: "en_US")),
      "Sun, Aug 30")
  }

  func testDateLabelIsNilWhenTheDateIsMissingOrMalformed() {
    let now = date(2026, 9, 2)
    XCTAssertNil(ChatDailySummaryPresentation.dateLabel(for: nil, now: now, calendar: calendar))
    XCTAssertNil(
      ChatDailySummaryPresentation.dateLabel(for: "not-a-date", now: now, calendar: calendar))
    XCTAssertNil(
      ChatDailySummaryPresentation.dateLabel(for: "2026-13-40", now: now, calendar: calendar))
  }

  func testIsStaleIsFalseThroughTwoWholeDaysAndTrueOnTheThird() {
    let now = date(2026, 9, 2)
    XCTAssertFalse(ChatDailySummaryPresentation.isStale("2026-09-02", now: now, calendar: calendar))
    XCTAssertFalse(ChatDailySummaryPresentation.isStale("2026-09-01", now: now, calendar: calendar))
    XCTAssertFalse(ChatDailySummaryPresentation.isStale("2026-08-31", now: now, calendar: calendar))
    XCTAssertTrue(ChatDailySummaryPresentation.isStale("2026-08-30", now: now, calendar: calendar))
    XCTAssertFalse(ChatDailySummaryPresentation.isStale(nil, now: now, calendar: calendar))
  }

  /// Spring-forward 2026-03-08 in America/New_York is not 24 hours. Counting calendar days
  /// still treats March 8 as two days before March 10, not a stale recap.
  func testIsStaleUsesCalendarDaysAcrossASpringForward() {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(identifier: "America/New_York") ?? .current
    let now =
      calendar.date(from: DateComponents(year: 2026, month: 3, day: 10, hour: 9))
      ?? Date(timeIntervalSince1970: 0)
    XCTAssertFalse(ChatDailySummaryPresentation.isStale("2026-03-10", now: now, calendar: calendar))
    XCTAssertFalse(ChatDailySummaryPresentation.isStale("2026-03-09", now: now, calendar: calendar))
    XCTAssertFalse(ChatDailySummaryPresentation.isStale("2026-03-08", now: now, calendar: calendar))
    XCTAssertTrue(ChatDailySummaryPresentation.isStale("2026-03-07", now: now, calendar: calendar))
  }

  func testFollowUpNamesTheDayTheSummaryIsAbout() {
    let now = date(2026, 9, 2)
    XCTAssertEqual(
      ChatDailySummaryPresentation.followUpQuestion(for: "2026-09-02", now: now, calendar: calendar),
      "What did I do today?")
    XCTAssertEqual(
      ChatDailySummaryPresentation.followUpQuestion(for: "2026-09-01", now: now, calendar: calendar),
      "What did I do yesterday?")
    XCTAssertEqual(
      ChatDailySummaryPresentation.followUpQuestion(for: nil, now: now, calendar: calendar),
      "What did I do yesterday?")
  }

  // MARK: - Notch card text

  func testCardBodyTruncatesAtAWordBoundaryAndDropsAnEmptyOverview() throws {
    XCTAssertNil(ChatDailySummaryPresentation.cardBody(for: nil))
    XCTAssertNil(ChatDailySummaryPresentation.cardBody(for: "   "))
    XCTAssertEqual(ChatDailySummaryPresentation.cardBody(for: "Short day."), "Short day.")

    let long = String(repeating: "alpha beta ", count: 40)
    let body = try XCTUnwrap(ChatDailySummaryPresentation.cardBody(for: long))
    XCTAssertTrue(body.hasSuffix("…"))
    XCTAssertLessThanOrEqual(body.count, ChatDailySummaryPresentation.cardBodyLimit + 1)
    XCTAssertFalse(body.dropLast().hasSuffix(" "))
  }

  func testCardTitleFallsBackWhenTheBackendSentNoHeadline() {
    XCTAssertEqual(
      ChatDailySummaryPresentation.cardTitle(for: record()), "🚀 A focused day")
    XCTAssertEqual(
      ChatDailySummaryPresentation.cardTitle(
        for: DailySummaryRecord(id: "x", date: nil, headline: nil, overview: nil)),
      "Your day in review")
  }

  // MARK: - Generation failures say what the server said

  /// The three statuses the backend uses as *answers* each get their own line; the reader on
  /// a quiet day was told "couldn't generate" and read it as a broken button.
  func testServerDeclinesAreNotReportedAsFailures() {
    let fallback = "Couldn't generate this recap."
    func message(_ status: Int) -> String {
      ChatDailySummaryPresentation.generationFailureMessage(
        for: APIError.httpError(statusCode: status, detail: "Nothing to summarize for 2026-09-04"),
        fallback: fallback)
    }
    XCTAssertTrue(message(400).contains("Nothing to summarize"))
    XCTAssertTrue(message(409).contains("Already being generated"))
    XCTAssertTrue(message(429).contains("wait a moment"))
    for status in [400, 409, 429] {
      XCTAssertNotEqual(message(status), fallback, "status \(status) is an answer, not a failure")
    }
  }

  func testGenuineFailuresKeepTheCallersFallback() {
    let fallback = "Couldn't regenerate this recap."
    XCTAssertEqual(
      ChatDailySummaryPresentation.generationFailureMessage(
        for: APIError.httpError(statusCode: 500, detail: nil), fallback: fallback),
      fallback)
    XCTAssertEqual(
      ChatDailySummaryPresentation.generationFailureMessage(
        for: APIError.httpError(statusCode: 404, detail: "Daily summary not found"), fallback: fallback),
      fallback)
    XCTAssertEqual(
      ChatDailySummaryPresentation.generationFailureMessage(
        for: URLError(.notConnectedToInternet), fallback: fallback),
      fallback)
  }

  // MARK: - Sections render only what is there

  func testEmptySectionsAreDroppedRatherThanDrawnEmpty() {
    let summary = record(
      highlights: [
        DailySummaryRecord.Highlight(topic: "Launch", emoji: "📈", summary: "Pricing pending."),
        DailySummaryRecord.Highlight(topic: "Noise", emoji: nil, summary: ""),
      ],
      actionItems: [
        DailySummaryRecord.ActionItem(description: "Ping Priya", priority: "high", completed: false),
        DailySummaryRecord.ActionItem(description: "", priority: nil, completed: nil),
      ])
    XCTAssertEqual(ChatDailySummaryPresentation.highlights(in: summary).count, 1)
    XCTAssertEqual(ChatDailySummaryPresentation.actionItems(in: summary).count, 1)

    let bare = record(highlights: nil, actionItems: [])
    XCTAssertTrue(ChatDailySummaryPresentation.highlights(in: bare).isEmpty)
    XCTAssertTrue(ChatDailySummaryPresentation.actionItems(in: bare).isEmpty)
  }

  // MARK: - Coordinator

  @MainActor
  private func makeCoordinator(_ box: Box, defaults: UserDefaults) -> ChatDailySummaryCoordinator {
    let store = HomeDailySummaryStore(
      ownerFence: { { true } },
      fetch: { _ in
        box.calls += 1
        return box.records
      },
      now: { box.clock })
    return ChatDailySummaryCoordinator(
      store: store, defaults: defaults, ownerID: { box.owner },
      cardSink: { _, title, body in box.cards.append((title, body)) })
  }

  @MainActor
  private func makeDefaults(_ name: String = #function) throws -> UserDefaults {
    let suite = "ChatDailySummaryTests.\(name).\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    addTeardownBlock { UserDefaults.standard.removePersistentDomain(forName: suite) }
    return defaults
  }

  /// Clearing Chat has to take the card with it.
  ///
  /// The card is chrome above the thread, not a turn (INV-CHAT-1 keeps
  /// transcript authorship in the kernel), so the journal clear cannot reach
  /// it — and the day's summary was left sitting alone in a chat the reader had
  /// just emptied, which reads as a clear that did not work.
  @MainActor
  func testClearingChatWithdrawsTheCard() async throws {
    let box = Box()
    box.records = [record(id: "ds_1")]
    let coordinator = makeCoordinator(box, defaults: try makeDefaults())
    await coordinator.refresh()
    XCTAssertFalse(coordinator.isClearedFromTranscript)

    coordinator.noteChatCleared()
    XCTAssertTrue(coordinator.isClearedFromTranscript, "the card must leave with the thread")

    // Still cleared after the next read: the same summary does not come back on
    // a refresh, or the card would reappear over an empty chat minutes later.
    box.clock = box.clock.addingTimeInterval(3_600)
    await coordinator.refresh()
    XCTAssertTrue(coordinator.isClearedFromTranscript)
  }

  /// Clearing suppresses one summary, not the feature. Tomorrow's comes back.
  @MainActor
  func testANewerSummaryReturnsAfterAClear() async throws {
    let box = Box()
    box.records = [record(id: "ds_1")]
    let coordinator = makeCoordinator(box, defaults: try makeDefaults())
    await coordinator.refresh()
    coordinator.noteChatCleared()
    XCTAssertTrue(coordinator.isClearedFromTranscript)

    box.records = [record(id: "ds_2", date: "2026-09-02")]
    box.clock = box.clock.addingTimeInterval(3_600)
    await coordinator.refresh()
    XCTAssertFalse(
      coordinator.isClearedFromTranscript,
      "a clear withdraws the summary that was on screen, not every summary after it")
  }

  /// The watermark is per account, like the announcement's. Clearing on one
  /// account must not blank the next reader's day on a shared Mac.
  @MainActor
  func testAClearOnOneAccountDoesNotWithdrawAnothersSummary() async throws {
    let box = Box()
    box.records = [record(id: "ds_1")]
    let coordinator = makeCoordinator(box, defaults: try makeDefaults())
    await coordinator.refresh()
    coordinator.noteChatCleared()

    box.owner = "owner-b"
    box.clock = box.clock.addingTimeInterval(3_600)
    await coordinator.refresh()
    XCTAssertFalse(coordinator.isClearedFromTranscript)
  }

  @MainActor
  func testNoSummaryLeavesNothingToRenderAndAnnouncesNothing() async throws {
    let box = Box()
    let coordinator = makeCoordinator(box, defaults: try makeDefaults())
    await coordinator.refresh()
    XCTAssertNil(coordinator.store.latest)
    XCTAssertTrue(box.cards.isEmpty)
  }

  @MainActor
  func testFirstSummaryAnnouncesExactlyOnceAndANewIDAnnouncesAgain() async throws {
    let box = Box()
    box.records = [record(id: "ds_1")]
    let coordinator = makeCoordinator(box, defaults: try makeDefaults())

    await coordinator.refresh()
    XCTAssertEqual(coordinator.store.latest?.id, "ds_1")
    XCTAssertEqual(box.cards.count, 1)
    XCTAssertEqual(box.cards.first?.title, "🚀 A focused day")
    XCTAssertEqual(box.cards.first?.body, "You shipped the summary card.")

    // Same summary, another refresh (wake, day-change, remount): no second interruption.
    await coordinator.refresh()
    XCTAssertEqual(box.cards.count, 1)

    box.records = [record(id: "ds_2", date: "2026-09-02", headline: "A newer day")]
    await coordinator.refresh()
    XCTAssertEqual(box.cards.count, 2)
    XCTAssertEqual(box.cards.last?.title, "🚀 A newer day")
  }

  @MainActor
  func testRefreshIfNeededHonoursTheStoreThrottle() async throws {
    let box = Box()
    box.records = [record()]
    let coordinator = makeCoordinator(box, defaults: try makeDefaults())

    await coordinator.refreshIfNeeded()
    await coordinator.refreshIfNeeded()
    XCTAssertEqual(box.calls, 1)

    box.clock = box.clock.addingTimeInterval(HomeDailySummaryStore.refreshInterval + 1)
    await coordinator.refreshIfNeeded()
    XCTAssertEqual(box.calls, 2)
  }

  @MainActor
  func testSignedOutProcessNeverFetches() async throws {
    let box = Box()
    box.owner = nil
    box.records = [record()]
    let coordinator = makeCoordinator(box, defaults: try makeDefaults())
    await coordinator.refresh()
    XCTAssertEqual(box.calls, 0)
    XCTAssertNil(coordinator.store.latest)
    XCTAssertTrue(box.cards.isEmpty)
  }

  /// The last-seen id is per account: switching owners must not silence the new owner's summary
  /// just because the previous one had already seen a record with the same id.
  @MainActor
  func testLastSeenSummaryIsScopedToTheOwner() async throws {
    let box = Box()
    box.records = [record(id: "ds_1")]
    let defaults = try makeDefaults()
    let coordinator = makeCoordinator(box, defaults: defaults)

    await coordinator.refresh()
    XCTAssertEqual(box.cards.count, 1)

    box.owner = "owner-b"
    await coordinator.refresh()
    XCTAssertEqual(box.cards.count, 2)
  }

  /// The store drops the previous owner's record on an account switch, so nothing of one person's
  /// day survives into another's Chat.
  @MainActor
  func testOwnerChangeClearsTheRenderedSummary() async throws {
    let box = Box()
    box.records = [record()]
    let coordinator = makeCoordinator(box, defaults: try makeDefaults())
    await coordinator.refresh()
    XCTAssertNotNil(coordinator.store.latest)

    NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)
    // The store's reset hops back through the main actor; yielding drains it without a clock.
    for _ in 0..<50 where coordinator.store.latest != nil {
      await Task.yield()
    }
    XCTAssertNil(coordinator.store.latest)
  }

  // MARK: - Follow-up chip

  @MainActor
  func testFollowUpChipPrefillsTheComposerAndSendsNothing() {
    _ = MainChatNavigationRequestStore.shared.consume()
    _ = MainChatNavigationRequestStore.shared.consumeDraft()

    let question = ChatDailySummaryPresentation.followUpQuestion(
      for: "2026-09-01", now: date(2026, 9, 2), calendar: calendar)
    ChatDailySummaryPresentation.requestFollowUp(question)

    XCTAssertEqual(MainChatNavigationRequestStore.shared.consumeDraft(), "What did I do yesterday?")
    // Consumed exactly once — a second composer must not re-insert it, and nothing was sent.
    XCTAssertNil(MainChatNavigationRequestStore.shared.consumeDraft())
    XCTAssertTrue(MainChatNavigationRequestStore.shared.consume())
  }

  func testFollowUpNamesTheDayForOlderSummaries() {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(identifier: "America/Los_Angeles") ?? .current
    let now = calendar.date(from: DateComponents(year: 2026, month: 9, day: 2, hour: 9)) ?? Date()
    let question = ChatDailySummaryPresentation.followUpQuestion(
      for: "2026-08-23", now: now, calendar: calendar, locale: Locale(identifier: "en_US"))
    XCTAssertEqual(question, "What did I do on Sun, Aug 23?")
  }

  // MARK: - The recap as a day boundary in the transcript

  /// The recap lives in history now: a day-boundary row anchored above the
  /// first message on or after the recap's day. `ChatDailyRecapRowPlacement`
  /// decides, without a view, where that boundary is, when it waits for older
  /// history to load, and when it takes the live edge — a marker the transcript
  /// cannot back up would be a lie about where the day began.
  func testRecapRowPlacement() throws {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "UTC"))
    func message(_ month: Int, _ day: Int, hour: Int, sender: ChatSender = .user) throws -> ChatMessage {
      let date = try XCTUnwrap(
        calendar.date(from: DateComponents(year: 2_026, month: month, day: day, hour: hour)))
      return ChatMessage(text: "\(month)/\(day)", createdAt: date, sender: sender)
    }

    // Aug 31 afternoon, Sep 1 morning, Sep 2 evening.
    let thread = [
      try message(8, 31, hour: 15),
      try message(9, 1, hour: 9),
      try message(9, 2, hour: 21),
    ]

    // The Sep 1 boundary sits above the first Sep 1 message.
    XCTAssertEqual(
      ChatDailyRecapRowPlacement.anchorMessageID(
        in: thread, recapDate: "2026-09-01", hasOlderMessagesAbove: false, calendar: calendar),
      thread[1].id)
    // The window's own first day anchors at its first row when nothing is hidden above.
    XCTAssertEqual(
      ChatDailyRecapRowPlacement.anchorMessageID(
        in: thread, recapDate: "2026-08-31", hasOlderMessagesAbove: false, calendar: calendar),
      thread[0].id)
    // …but not when older messages exist above the window — the day may begin
    // further up, and a marker above same-day history would be wrong once it loads.
    XCTAssertNil(
      ChatDailyRecapRowPlacement.anchorMessageID(
        in: thread, recapDate: "2026-08-31", hasOlderMessagesAbove: true, calendar: calendar))
    // A recap newer than everything loaded is the newest thing in the thread:
    // it takes the live edge, below the last row.
    XCTAssertEqual(
      ChatDailyRecapRowPlacement.anchorMessageID(
        in: thread, recapDate: "2026-09-03", hasOlderMessagesAbove: false, calendar: calendar),
      thread[2].id)
    XCTAssertEqual(
      ChatDailyRecapRowPlacement.anchorMessageID(
        in: thread, recapDate: "2026-09-03", hasOlderMessagesAbove: true, calendar: calendar),
      thread[2].id,
      "the live edge does not depend on how much older history is still hidden")
    // An empty thread renders nothing rather than inventing a row.
    XCTAssertNil(
      ChatDailyRecapRowPlacement.anchorMessageID(
        in: [], recapDate: "2026-09-03", hasOlderMessagesAbove: false, calendar: calendar))
    // A missing or malformed date renders nothing rather than anchoring somewhere.
    XCTAssertNil(
      ChatDailyRecapRowPlacement.anchorMessageID(
        in: thread, recapDate: nil, hasOlderMessagesAbove: false, calendar: calendar))
    XCTAssertNil(
      ChatDailyRecapRowPlacement.anchorMessageID(
        in: thread, recapDate: "not-a-date", hasOlderMessagesAbove: false, calendar: calendar))
  }

}

extension ChatDailySummaryTests {
  /// Staleness copy must not cost the reader the date. Naming the day is the whole reason the
  /// eyebrow exists; "several days old" on its own is less informative than what it replaced.
  func testStaleLabelKeepsTheDayItIsAbout() throws {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
    let now = try XCTUnwrap(calendar.date(from: DateComponents(year: 2026, month: 9, day: 2)))

    let label = ChatDailySummaryPresentation.staleLabel(
      for: "2026-08-23", now: now, calendar: calendar, locale: Locale(identifier: "en_US"))

    XCTAssertTrue(label.contains("Aug"), "stale label must still name the day: \(label)")
    XCTAssertTrue(label.contains("23"), "stale label must still name the day: \(label)")
    XCTAssertTrue(label.lowercased().contains("old"), "stale label must say it is old: \(label)")
  }

  func testStaleLabelFallsBackWhenTheDateIsUnusable() {
    let label = ChatDailySummaryPresentation.staleLabel(for: nil, now: Date())
    XCTAssertEqual(label, "Several days old")
  }
}
