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
    XCTAssertEqual(ChatDailySummaryCard.highlights(in: summary).count, 1)
    XCTAssertEqual(ChatDailySummaryCard.actionItems(in: summary).count, 1)

    let bare = record(highlights: nil, actionItems: [])
    XCTAssertTrue(ChatDailySummaryCard.highlights(in: bare).isEmpty)
    XCTAssertTrue(ChatDailySummaryCard.actionItems(in: bare).isEmpty)
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
    ChatDailySummaryCard.requestFollowUp(question)

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

  // MARK: - Transcript admission (INV-CHAT-2)

  /// The reported launch ergonomics: the card admitted above a transcript that
  /// was still loading printed the summary alone over a spinner, and the reader
  /// watched it yank above the fold when history landed at the live edge.
  func testAdmissionDefersToTheInitialHistoryLoad() {
    XCTAssertFalse(
      ChatDailySummaryAdmission.shouldAdmit(
        hasSummary: true, isClearedFromTranscript: false, alreadyAdmitted: false,
        isLoadingInitial: true, scrollMode: .followingBottom, hasMessages: false),
      "Launch must not print the summary above a transcript that is still loading"
    )
    XCTAssertTrue(
      ChatDailySummaryAdmission.shouldAdmit(
        hasSummary: true, isClearedFromTranscript: false, alreadyAdmitted: false,
        isLoadingInitial: false, scrollMode: .followingBottom, hasMessages: true),
      "The loading-complete observer admits once the snapshot is placed"
    )
    XCTAssertTrue(
      ChatDailySummaryAdmission.shouldAdmit(
        hasSummary: true, isClearedFromTranscript: false, alreadyAdmitted: false,
        isLoadingInitial: false, scrollMode: .followingBottom, hasMessages: false),
      "A genuinely empty thread shows the card once loading completes"
    )
  }

  func testAdmissionNeverMovesAReaderWhoScrolledAway() {
    XCTAssertFalse(
      ChatDailySummaryAdmission.shouldAdmit(
        hasSummary: true, isClearedFromTranscript: false, alreadyAdmitted: false,
        isLoadingInitial: false, scrollMode: .freeScrolling, hasMessages: true),
      "A reader away from the live edge meets the card on their next return to the bottom"
    )
    XCTAssertTrue(
      ChatDailySummaryAdmission.shouldAdmit(
        hasSummary: true, isClearedFromTranscript: false, alreadyAdmitted: false,
        isLoadingInitial: false, scrollMode: .freeScrolling, hasMessages: false),
      "An empty thread has nothing to move"
    )
    XCTAssertFalse(
      ChatDailySummaryAdmission.shouldAdmit(
        hasSummary: true, isClearedFromTranscript: false, alreadyAdmitted: true,
        isLoadingInitial: false, scrollMode: .followingBottom, hasMessages: true),
      "Once admitted the card stays"
    )
  }

  func testAdmissionWithdrawsWhenThereIsNothingToAdmit() {
    XCTAssertFalse(
      ChatDailySummaryAdmission.shouldAdmit(
        hasSummary: false, isClearedFromTranscript: false, alreadyAdmitted: true,
        isLoadingInitial: false, scrollMode: .followingBottom, hasMessages: true),
      "A summary that disappeared (owner change) withdraws the card"
    )
    XCTAssertFalse(
      ChatDailySummaryAdmission.shouldAdmit(
        hasSummary: true, isClearedFromTranscript: true, alreadyAdmitted: true,
        isLoadingInitial: false, scrollMode: .followingBottom, hasMessages: true),
      "A cleared summary keeps the card away"
    )
  }

}
