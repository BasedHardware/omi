import XCTest

@testable import Omi_Computer

private final class Box<T>: @unchecked Sendable {
  var value: T
  init(_ value: T) { self.value = value }
}

/// Bounded-payload contract for desktop search analytics. The helper must never
/// accept a raw query string as a PostHog property, and every listed surface's
/// committed search must call it.
@MainActor
final class SearchAnalyticsTests: XCTestCase {
  private let capturedBox = Box<[(String, [String: Any])]>([])

  override func tearDown() async throws {
    SearchAnalytics.resetDebounceCoordinatorsForTests()
  }

  private func startCapturing() {
    let box = capturedBox
    box.value = []
    AnalyticsManager.shared.setSearchTelemetryCaptureForTests { event, properties in
      box.value.append((event, properties))
    }
    addTeardownBlock {
      await MainActor.run {
        AnalyticsManager.shared.setSearchTelemetryCaptureForTests(nil)
      }
    }
  }

  func testQueryEnteredPayloadIsBoundedAndCountsWords() {
    let properties = SearchAnalytics.queryEnteredProperties(
      surface: .conversations, query: "  two   words  ", resultsCount: 3)

    XCTAssertEqual(properties["search_surface"] as? String, "conversations")
    XCTAssertEqual(properties["query_length"] as? Int, "  two   words  ".count)
    XCTAssertEqual(properties["query_word_count"] as? Int, 2)
    XCTAssertEqual(properties["results_count"] as? Int, 3)
    XCTAssertEqual(properties["had_results"] as? Bool, true)
    XCTAssertEqual(Set(properties.keys), SearchAnalytics.allowedQueryEnteredKeys)
    XCTAssertTrue(Set(properties.keys).isDisjoint(with: SearchAnalytics.forbiddenPropertyKeys))
  }

  func testEmptyResultsAreValidAndZeroWordCountIsEmptyQuery() {
    XCTAssertEqual(SearchAnalytics.wordCount(of: " \n\t "), 0)
    let properties = SearchAnalytics.queryEnteredProperties(
      surface: .apps, query: "solo", resultsCount: 0)
    XCTAssertEqual(properties["had_results"] as? Bool, false)
    XCTAssertEqual(properties["results_count"] as? Int, 0)
  }

  func testSurfaceRawValuesMatchTheGovernedMetric() {
    XCTAssertEqual(SearchSurface.activity.rawValue, "activity")
    XCTAssertEqual(SearchSurface.home.rawValue, "home")
    XCTAssertEqual(SearchSurface.conversations.rawValue, "conversations")
    XCTAssertEqual(SearchSurface.memories.rawValue, "memories")
    XCTAssertEqual(SearchSurface.rewind.rawValue, "rewind")
    XCTAssertEqual(SearchSurface.apps.rawValue, "apps")
    XCTAssertEqual(SearchSurface.tasks.rawValue, "tasks")
    XCTAssertEqual(SearchSurface.brainMap.rawValue, "brain_map")
  }

  func testQueryEnteredEmitterOmitsTheRawQuery() {
    startCapturing()

    SearchAnalytics.queryEntered(surface: .rewind, query: "secret phrase", resultsCount: 4)

    XCTAssertEqual(capturedBox.value.count, 1)
    XCTAssertEqual(capturedBox.value[0].0, SearchAnalytics.queryEnteredEvent)
    XCTAssertEqual(capturedBox.value[0].1["search_surface"] as? String, "rewind")
    XCTAssertEqual(capturedBox.value[0].1["results_count"] as? Int, 4)
    XCTAssertNil(capturedBox.value[0].1["query"])
    XCTAssertNil(capturedBox.value[0].1["search_query"])
  }

  func testEmptyOrWhitespaceQueryDoesNotEmit() {
    startCapturing()
    SearchAnalytics.queryEntered(surface: .home, query: "   ", resultsCount: 1)
    XCTAssertTrue(capturedBox.value.isEmpty)
  }

  func testBarFocusedEmitsSurfaceOnly() {
    startCapturing()
    SearchAnalytics.barFocused(surface: .activity)
    XCTAssertEqual(capturedBox.value.count, 1)
    XCTAssertEqual(capturedBox.value[0].0, SearchAnalytics.barFocusedEvent)
    XCTAssertEqual(capturedBox.value[0].1["search_surface"] as? String, "activity")
    XCTAssertEqual(Set(capturedBox.value[0].1.keys), ["search_surface"])
  }

  func testResultOpenedDualEmitsConversationOpenedFromSearchOnlyForConversations() {
    startCapturing()

    SearchAnalytics.resultOpened(surface: .memories, resultIndex: 2, searchIsActive: true)
    SearchAnalytics.resultOpened(surface: .conversations, resultIndex: 0, searchIsActive: true)
    SearchAnalytics.resultOpened(surface: .home, resultIndex: 1, searchIsActive: false)

    XCTAssertEqual(
      capturedBox.value.map(\.0),
      [
        SearchAnalytics.resultOpenedEvent,
        SearchAnalytics.resultOpenedEvent,
        SearchAnalytics.conversationOpenedFromSearchEvent,
      ])
    XCTAssertEqual(capturedBox.value[0].1["search_surface"] as? String, "memories")
    XCTAssertEqual(capturedBox.value[0].1["result_index"] as? Int, 2)
    XCTAssertEqual(capturedBox.value[1].1["search_surface"] as? String, "conversations")
    XCTAssertEqual(capturedBox.value[2].1["search_surface"] as? String, "conversations")
    XCTAssertNil(capturedBox.value[2].1["query"])
  }

  func testCommittedSearchCallSitesCoverEverySurface() throws {
    let sourcesRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")

    let required: [(String, String)] = [
      ("MainWindow/Pages/ConversationsPage.swift", "SearchAnalytics.queryEntered(surface: .conversations"),
      ("MainWindow/Pages/MemoriesPage.swift", "SearchAnalytics.queryEntered(surface: .memories"),
      ("Rewind/UI/RewindViewModel.swift", "SearchAnalytics.queryEntered(surface: .rewind"),
      ("Rewind/UI/RewindViewModel.swift", "rewindSearchPerformed(queryLength:"),
      ("MainWindow/Pages/AppsPage.swift", "SearchAnalytics.queryEntered(surface: .apps"),
      ("MainWindow/Pages/TasksPage.swift", "SearchAnalytics.queryEntered(surface: .tasks"),
      ("MainWindow/Spine/SpineStream.swift", "SearchAnalytics.scheduleQueryEntered(surface: searchSurface"),
      ("MainWindow/QueryShell/QueryShellHome.swift", "searchSurface: .home"),
      ("MainWindow/QueryShell/ActivityHubTab.swift", "searchSurface: .activity"),
      ("MainWindow/Pages/MemoryGraph/MemoryGraphPage.swift", "SearchAnalytics.scheduleQueryEntered(surface: .brainMap"),
      (
        "MainWindow/Pages/MemoryGraph/CanonicalMemoryAtlasView.swift",
        "SearchAnalytics.scheduleQueryEntered(surface: .brainMap"
      ),
    ]

    for (relativePath, needle) in required {
      // omi-test-quality: source-inspection -- static contract: each search surface must call SearchAnalytics
      let source = try String(contentsOf: sourcesRoot.appendingPathComponent(relativePath), encoding: .utf8)
      XCTAssertTrue(
        source.contains(needle),
        "\(relativePath) must commit search analytics with \(needle)")
    }
  }

  func testPayloadBuildersNeverAdvertiseAQueryStringKey() throws {
    let sourcesRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
    let files = [
      "Analytics/SearchAnalytics.swift",
      "Analytics/AnalyticsManager+Search.swift",
    ]
    for relativePath in files {
      // omi-test-quality: source-inspection -- static contract: PostHog search payloads cannot grow a query string key
      let source = try String(contentsOf: sourcesRoot.appendingPathComponent(relativePath), encoding: .utf8)
      for forbidden in ["\"query\"", "\"search_query\"", "\"search_term\""] {
        XCTAssertFalse(
          source.contains("\(forbidden):"),
          "\(relativePath) must not send \(forbidden) to PostHog")
      }
    }
  }
}
