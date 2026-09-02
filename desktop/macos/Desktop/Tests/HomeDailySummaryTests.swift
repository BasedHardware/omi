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

  func testEyebrowFormatsDateAndFallsBackCleanly() throws {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "UTC"))
    let eyebrow = HomeDailySummarySection.eyebrow(
      for: "2026-09-01", calendar: calendar, locale: Locale(identifier: "en_US"))
    XCTAssertEqual(eyebrow, "DAILY SUMMARY · TUE, SEP 1")
    XCTAssertEqual(HomeDailySummarySection.eyebrow(for: nil), "DAILY SUMMARY")
    XCTAssertEqual(HomeDailySummarySection.eyebrow(for: "not-a-date"), "DAILY SUMMARY")
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
  /// Two records for one date is the #4608 duplicate-write bug, and the endpoint serves
  /// **newest-first**. So the lookup must resolve to the newer of the two, and — the reason this
  /// test exists at all — must not trap the way `Dictionary(uniqueKeysWithValues:)` would.
  func testByDateLookupResolvesDuplicateDatesToTheNewestAndDoesNotTrap() async {
    let store = HomeDailySummaryStore(
      ownerFence: { { true } },
      fetch: { _ in
        [
          DailySummaryRecord(id: "newer", date: "2026-09-01", headline: "new", overview: "o"),
          DailySummaryRecord(id: "older", date: "2026-09-01", headline: "old", overview: "o"),
        ]
      },
      now: Date.init)
    await store.refresh()
    XCTAssertEqual(store.latest?.id, "newer")
    XCTAssertEqual(store.byDate["2026-09-01"]?.id, "newer")
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
