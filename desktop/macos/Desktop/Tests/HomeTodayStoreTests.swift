import XCTest

@testable import Omi_Computer

@MainActor
final class HomeTodayStoreTests: XCTestCase {

  func testRefreshLoadsInsightsAndFilmstrip() async {
    let insight = HomeTodayStore.InsightItem(
      id: 7, text: "Deepgram spend is pacing 18% over last week", sourceApp: "Safari",
      createdAt: Date())
    let frame = Screenshot(timestamp: Date(), appName: "Xcode")
    var firstWinLoads = 0
    let store = HomeTodayStore(
      loader: HomeTodayStore.Loader(
        loadTodayInsights: { _ in [insight] },
        loadFilmstrip: { _ in [frame] },
        loadFirstWinMemories: {
          firstWinLoads += 1
          return (["Nik is building Omi, an AI wearable company."], 44)
        },
        dismissInsight: { _ in }
      ))

    await store.refresh(includeFirstWin: false)

    XCTAssertEqual(store.content.insights, [insight])
    XCTAssertEqual(store.content.filmstrip.count, 1)
    // First-win data only loads for the first-win surface.
    XCTAssertEqual(firstWinLoads, 0)
    XCTAssertTrue(store.content.firstWinMemories.isEmpty)

    await store.refresh(includeFirstWin: true)
    XCTAssertEqual(firstWinLoads, 1)
    XCTAssertEqual(store.content.firstWinMemoryCount, 44)
    XCTAssertEqual(store.content.firstWinMemories.count, 1)
  }

  func testDismissRemovesRowImmediatelyAndPersists() async {
    let insight = HomeTodayStore.InsightItem(
      id: 3, text: "You have pushed the design review twice this week", sourceApp: "Calendar",
      createdAt: Date())
    var dismissedIDs: [Int64] = []
    let store = HomeTodayStore(
      loader: HomeTodayStore.Loader(
        loadTodayInsights: { _ in [insight] },
        loadFilmstrip: { _ in [] },
        loadFirstWinMemories: { ([], 0) },
        dismissInsight: { dismissedIDs.append($0) }
      ))

    await store.refresh(includeFirstWin: false)
    XCTAssertEqual(store.content.insights.count, 1)

    await store.dismissInsight(insight)

    // Optimistic removal + storage dismissal both happen.
    XCTAssertTrue(store.content.insights.isEmpty)
    XCTAssertEqual(dismissedIDs, [3])
  }

  func testAppActivationSpamIsThrottled() async {
    var loads = 0
    var currentTime = Date(timeIntervalSince1970: 1_000_000)
    let store = HomeTodayStore(
      loader: HomeTodayStore.Loader(
        loadTodayInsights: { _ in
          loads += 1
          return []
        },
        loadFilmstrip: { _ in [] },
        loadFirstWinMemories: { ([], 0) },
        dismissInsight: { _ in }
      ),
      now: { currentTime }
    )

    await store.refresh(includeFirstWin: false)
    XCTAssertEqual(loads, 1)

    // A cmd-tab five seconds later must not resample the filmstrip.
    currentTime = currentTime.addingTimeInterval(5)
    await store.refresh(includeFirstWin: false)
    XCTAssertEqual(loads, 1)

    // Upgrading to the first-win pass always runs.
    await store.refresh(includeFirstWin: true)
    XCTAssertEqual(loads, 2)

    // And the cooldown expiring allows a fresh pass.
    currentTime = currentTime.addingTimeInterval(PollingConfig.activationCooldown)
    await store.refresh(includeFirstWin: true)
    XCTAssertEqual(loads, 3)
  }

  func testResetClearsContent() async {
    let store = HomeTodayStore(
      loader: HomeTodayStore.Loader(
        loadTodayInsights: { _ in
          [
            HomeTodayStore.InsightItem(
              id: 1, text: "An insight for the previous account", sourceApp: "Mail",
              createdAt: Date())
          ]
        },
        loadFilmstrip: { _ in [] },
        loadFirstWinMemories: { ([], 0) },
        dismissInsight: { _ in }
      ))

    await store.refresh(includeFirstWin: false)
    XCTAssertFalse(store.content.insights.isEmpty)

    store.resetSessionState()

    // Account switch: no stale content may leak to the next owner.
    XCTAssertEqual(store.content, HomeTodayStore.Content())
  }
}
