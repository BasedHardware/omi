import Foundation
import XCTest

@testable import Omi_Computer

final class HomeDailySummaryTests: XCTestCase {
  /// Test-only mutable state the injected closures can touch without capturing `var`s.
  private final class Box: @unchecked Sendable {
    var calls = 0
    var clock = Date(timeIntervalSince1970: 1_000)
    var shouldFail = false
  }

  // MARK: decoding

  func testDecodesWireRecordIncludingDesktopStats() throws {
    let json = """
      {"summaries": [{
        "id": "ds_1", "date": "2026-09-01", "created_at": "2026-09-02T09:00:00Z",
        "headline": "A focused day", "overview": "You set up Omi.", "day_emoji": "🚀",
        "stats": {"total_conversations": 1, "total_duration_minutes": 12, "action_items_count": 2,
                  "memories_created": 9, "action_items_created": 2, "watching_minutes": 130,
                  "proactive_moments": 3},
        "highlights": [{"topic": "Q4 launch plan", "emoji": "📈", "summary": "Pricing table pending."}],
        "action_items": [{"description": "Ping Priya", "priority": "high", "completed": false}]
      }]}
      """
    let decoded = try JSONDecoder().decode(DailySummariesListResponse.self, from: Data(json.utf8))
    let record = try XCTUnwrap(decoded.summaries.first)
    XCTAssertEqual(record.id, "ds_1")
    XCTAssertEqual(record.stats?.watchingMinutes, 130)
    XCTAssertEqual(record.stats?.proactiveMoments, 3)
    XCTAssertEqual(record.stats?.memoriesCreated, 9)
    XCTAssertEqual(record.highlights?.first?.topic, "Q4 launch plan")
    XCTAssertEqual(record.actionItems?.first?.completed, false)
  }

  func testRecordWithoutIDGetsDateDerivedIdentity() throws {
    let json = #"{"summaries": [{"date": "2026-09-01", "headline": "x"}]}"#
    let decoded = try JSONDecoder().decode(DailySummariesListResponse.self, from: Data(json.utf8))
    XCTAssertEqual(decoded.summaries.first?.id, "date:2026-09-01")
    XCTAssertNil(decoded.summaries.first?.stats)
  }

  /// The sections only the dedicated recap page renders, with the conversation links the page
  /// deep-links through. Keys are the backend's snake_case wire names
  /// (`backend/routers/users.py` `DailySummaryResponse`), which mobile's
  /// `daily_summary.dart` mirrors.
  func testDecodesRecapPageSectionsAndTheirConversationLinks() throws {
    let json = """
      {"summaries": [{
        "id": "ds_2", "date": "2026-09-02", "headline": "h", "overview": "o",
        "highlights": [{"topic": "t", "emoji": "📈", "summary": "s",
                        "conversation_ids": ["c1", "c2"]}],
        "action_items": [{"description": "d", "priority": "high",
                          "source_conversation_id": "c3", "completed": true}],
        "unresolved_questions": [{"question": "q?", "conversation_id": "c4"}],
        "decisions_made": [{"decision": "ship it", "conversation_id": "c5"}],
        "knowledge_nuggets": [{"insight": "learned i", "conversation_id": "c6"}]
      }]}
      """
    let decoded = try JSONDecoder().decode(DailySummariesListResponse.self, from: Data(json.utf8))
    let record = try XCTUnwrap(decoded.summaries.first)
    XCTAssertEqual(record.highlights?.first?.conversationIds, ["c1", "c2"])
    XCTAssertEqual(record.actionItems?.first?.sourceConversationId, "c3")
    XCTAssertEqual(record.actionItems?.first?.completed, true)
    XCTAssertEqual(record.unresolvedQuestions?.first?.question, "q?")
    XCTAssertEqual(record.unresolvedQuestions?.first?.conversationId, "c4")
    XCTAssertEqual(record.decisionsMade?.first?.decision, "ship it")
    XCTAssertEqual(record.decisionsMade?.first?.conversationId, "c5")
    XCTAssertEqual(record.knowledgeNuggets?.first?.insight, "learned i")
    XCTAssertEqual(record.knowledgeNuggets?.first?.conversationId, "c6")
  }

  /// Every new section must stay optional: a record from before the backend grew them (or from a
  /// backend that never grows them) decodes to nil sections, not a dropped summary.
  func testRecapPageSectionsStayAbsentForOlderBackends() throws {
    let json = #"{"summaries": [{"id": "ds_1", "date": "2026-09-01", "headline": "x"}]}"#
    let decoded = try JSONDecoder().decode(DailySummariesListResponse.self, from: Data(json.utf8))
    let record = try XCTUnwrap(decoded.summaries.first)
    XCTAssertNil(record.unresolvedQuestions)
    XCTAssertNil(record.decisionsMade)
    XCTAssertNil(record.knowledgeNuggets)
    XCTAssertNil(record.highlights?.first?.conversationIds)
    XCTAssertNil(record.actionItems?.first?.sourceConversationId)
  }

  // MARK: stats row

  func testChipsSkipMissingAndZeroStatsAndKeepFixedOrder() {
    let stats = DailySummaryRecord.Stats(
      totalConversations: 0, totalDurationMinutes: nil, actionItemsCount: 4, memoriesCreated: 9,
      actionItemsCreated: nil, watchingMinutes: 130, proactiveMoments: 1)
    let chips = HomeDailySummaryStatsRow.chips(for: stats)
    XCTAssertEqual(chips.map(\.id), ["watching", "moments", "memories", "tasks"])
    XCTAssertEqual(chips[0].value, "2h 10m")
    XCTAssertEqual(chips[1].label, "moment")
    // `action_items_created` wins over the legacy count when both exist; here only the legacy
    // count is present, so it is used.
    XCTAssertEqual(chips[3].value, "4")
  }

  func testDurationFormatting() {
    XCTAssertEqual(HomeDailySummaryStatsRow.duration(45), "45m")
    XCTAssertEqual(HomeDailySummaryStatsRow.duration(60), "1h")
    XCTAssertEqual(HomeDailySummaryStatsRow.duration(130), "2h 10m")
  }

  /// The hub's `HomeDailySummarySection` eyebrow was the other renderer of this
  /// date; it went with `DashboardPage`. The surviving surface is the Chat
  /// card's pill, whose own rules are covered in `ChatDailySummaryTests`.
  func testChatCardDatePillIsTheSurvivingDateRenderer() throws {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "UTC"))
    let now = try XCTUnwrap(
      calendar.date(from: DateComponents(year: 2_026, month: 9, day: 2)))
    XCTAssertEqual(
      ChatDailySummaryPresentation.dateLabel(
        for: "2026-09-01", now: now, calendar: calendar, locale: Locale(identifier: "en_US")),
      "Yesterday")
    XCTAssertNil(
      ChatDailySummaryPresentation.dateLabel(for: "not-a-date", now: now, calendar: calendar))
  }

  // MARK: store

  @MainActor
  func testStoreRefreshIfNeededFetchesOnceWithinTheInterval() async {
    let box = Box()
    let store = HomeDailySummaryStore(
      ownerFence: { { true } },
      fetch: { _ in
        box.calls += 1
        return [DailySummaryRecord(id: "a", date: "2026-09-01", headline: "h", overview: "o")]
      },
      now: { box.clock })
    await store.refreshIfNeeded()
    await store.refreshIfNeeded()
    XCTAssertEqual(box.calls, 1)
    XCTAssertEqual(store.latest?.id, "a")
    XCTAssertEqual(store.byDate["2026-09-01"]?.id, "a")

    box.clock = box.clock.addingTimeInterval(HomeDailySummaryStore.refreshInterval + 1)
    await store.refreshIfNeeded()
    XCTAssertEqual(box.calls, 2)
  }

  @MainActor
  func testStoreKeepsLastGoodRecordWhenFetchFails() async {
    struct Boom: Error {}
    let box = Box()
    let store = HomeDailySummaryStore(
      ownerFence: { { true } },
      fetch: { _ in
        if box.shouldFail { throw Boom() }
        return [DailySummaryRecord(id: "a", date: "2026-09-01", headline: "h", overview: "o")]
      },
      now: Date.init)
    await store.refresh()
    XCTAssertEqual(store.latest?.id, "a")
    box.shouldFail = true
    await store.refresh()
    XCTAssertEqual(store.latest?.id, "a")
    XCTAssertNotNil(store.lastError)
  }

  @MainActor
  func testStoreFetchesAFourteenDayWindow() async {
    let box = Box()
    let store = HomeDailySummaryStore(
      ownerFence: { { true } },
      fetch: { limit in
        box.calls = limit
        return []
      },
      now: Date.init)
    await store.refresh()
    XCTAssertEqual(box.calls, HomeDailySummaryStore.fetchLimit)
  }

  @MainActor
  /// Two records for one date is the #4608 duplicate-write bug. The endpoint orders by `date`
  /// alone, so the *served order* between two records sharing a date is unspecified — only
  /// `created_at` can say which write is newer. The lookup must resolve to that one, and — the
  /// reason this test exists at all — must not trap the way `Dictionary(uniqueKeysWithValues:)`
  /// would. Served here worst-last, so an implementation trusting array order fails.
  func testByDateLookupResolvesDuplicateDatesByCreatedAtAndDoesNotTrap() async {
    let store = HomeDailySummaryStore(
      ownerFence: { { true } },
      fetch: { _ in
        [
          DailySummaryRecord(
            id: "newer", date: "2026-09-01", createdAt: "2026-09-02T09:00:00Z", headline: "new",
            overview: "o"),
          DailySummaryRecord(
            id: "older", date: "2026-09-01", createdAt: "2026-09-01T23:00:00Z", headline: "old",
            overview: "o"),
        ]
      },
      now: Date.init)
    await store.refresh()
    XCTAssertEqual(store.byDate["2026-09-01"]?.id, "newer")
  }

  @MainActor
  /// INV-AUTH-1. Generation is a network round trip that can outlive an account switch, and
  /// `.runtimeOwnerDidChange` only clears what is already stored. Without a fence captured before
  /// the request, a late result repopulates this shared store — and Chat and Activity then render
  /// one account's recap to another.
  func testUpsertDropsARecordWhoseOwnerIsNoLongerCurrent() async {
    let store = HomeDailySummaryStore(
      ownerFence: { { true } }, fetch: { _ in [] }, settingsHour: { 22 }, now: Date.init)
    await store.refresh()
    store.upsert(
      DailySummaryRecord(id: "other-owner", date: "2026-09-01", headline: "h", overview: "o"),
      isOwnerStillCurrent: { false })
    XCTAssertNil(store.byDate["2026-09-01"])
    XCTAssertNil(store.latest)
  }

  @MainActor
  /// Generating today's recap from the timeline is the one action whose entire point is to
  /// replace the stale card. Matching only the *same* date left `latest` on yesterday, so Chat
  /// kept showing the old recap until the next 15-minute refresh.
  func testUpsertPromotesANewerDayToLatestButKeepsOlderDaysAddressable() async {
    let store = HomeDailySummaryStore(
      ownerFence: { { true } },
      fetch: { _ in
        [DailySummaryRecord(id: "yesterday", date: "2026-09-01", headline: "h", overview: "o")]
      },
      now: Date.init)
    await store.refresh()
    XCTAssertEqual(store.latest?.id, "yesterday")

    store.upsert(
      DailySummaryRecord(id: "today", date: "2026-09-02", headline: "h", overview: "o"),
      isOwnerStillCurrent: { true })
    XCTAssertEqual(store.latest?.id, "today")

    // An older day generated from the timeline is addressable by date but must not become `latest`.
    store.upsert(
      DailySummaryRecord(id: "backfilled", date: "2026-08-30", headline: "h", overview: "o"),
      isOwnerStillCurrent: { true })
    XCTAssertEqual(store.latest?.id, "today")
    XCTAssertEqual(store.byDate["2026-08-30"]?.id, "backfilled")
  }

  @MainActor
  /// The production `settingsHour` default reads the user's chosen hour; the store must publish
  /// whatever it resolves rather than a constant, or the timeline's empty-state gate lies for
  /// everyone who is not on the 22:00 default.
  func testSummaryHourComesFromSettingsNotAConstant() async {
    let store = HomeDailySummaryStore(
      ownerFence: { { true } },
      fetch: { _ in [DailySummaryRecord(id: "a", date: "2026-09-01", headline: "h", overview: "o")] },
      settingsHour: { 8 },
      now: Date.init)
    await store.refresh()
    XCTAssertEqual(store.summaryHour, 8)
  }

  @MainActor
  func testMalformedAndNilDatesAreDroppedFromLookupButStillCountForLatest() async {
    let store = HomeDailySummaryStore(
      ownerFence: { { true } },
      fetch: { _ in
        [
          DailySummaryRecord(id: "nil-date", date: nil, headline: "h", overview: "o"),
          DailySummaryRecord(id: "bad-date", date: "not-a-date", headline: "h", overview: "o"),
          DailySummaryRecord(id: "ok", date: "2026-09-01", headline: "h", overview: "o"),
        ]
      },
      now: Date.init)
    await store.refresh()
    XCTAssertEqual(store.latest?.id, "nil-date")
    XCTAssertNil(store.byDate["not-a-date"])
    XCTAssertEqual(store.byDate.count, 1)
    XCTAssertEqual(store.byDate["2026-09-01"]?.id, "ok")
  }

  @MainActor
  func testOwnerChangeClearsTheByDateLookup() async {
    let store = HomeDailySummaryStore(
      ownerFence: { { true } },
      fetch: { _ in
        [DailySummaryRecord(id: "a", date: "2026-09-01", headline: "h", overview: "o")]
      },
      now: Date.init)
    await store.refresh()
    XCTAssertEqual(store.byDate["2026-09-01"]?.id, "a")

    NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)
    for _ in 0..<50 where !store.byDate.isEmpty {
      await Task.yield()
    }
    XCTAssertTrue(store.byDate.isEmpty)
    XCTAssertNil(store.latest)
  }
}
