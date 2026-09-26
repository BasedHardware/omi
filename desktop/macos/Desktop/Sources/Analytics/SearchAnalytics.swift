import Foundation

/// Bounded search surfaces for desktop product analytics.
///
/// Raw query text, titles, paths, and prompts must never appear in PostHog
/// properties. These raw values are the only legal `search_surface` dimensions.
enum SearchSurface: String, CaseIterable, Sendable {
  case activity
  case home
  case conversations
  case memories
  case rewind
  case apps
  case tasks
  case brainMap = "brain_map"
}

/// Content-free search analytics. Call sites pass the committed query only so
/// this type can derive length/word-count; the query string itself never becomes
/// a PostHog property.
@MainActor
enum SearchAnalytics {
  static let queryEnteredEvent = "Search Query Entered"
  static let barFocusedEvent = "Search Bar Focused"
  static let resultOpenedEvent = "Search Result Opened"
  static let conversationOpenedFromSearchEvent = "Conversation Opened From Search"

  static let allowedQueryEnteredKeys: Set<String> = [
    "search_surface", "query_length", "query_word_count", "results_count", "had_results",
  ]
  static let forbiddenPropertyKeys: Set<String> = [
    "query", "search_query", "search_term", "q", "text", "prompt", "title",
  ]

  private static var debounceCoordinators: [SearchSurface: DebouncedSearchCoordinator] = [:]

  static func wordCount(of query: String) -> Int {
    let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return 0 }
    return trimmed.split { $0.isWhitespace || $0.isNewline }.count
  }

  static func queryEnteredProperties(
    surface: SearchSurface,
    query: String,
    resultsCount: Int
  ) -> [String: Any] {
    [
      "search_surface": surface.rawValue,
      "query_length": query.count,
      "query_word_count": wordCount(of: query),
      "results_count": resultsCount,
      "had_results": resultsCount > 0,
    ]
  }

  static func barFocusedProperties(surface: SearchSurface) -> [String: Any] {
    ["search_surface": surface.rawValue]
  }

  static func resultOpenedProperties(surface: SearchSurface, resultIndex: Int?) -> [String: Any] {
    var properties: [String: Any] = ["search_surface": surface.rawValue]
    if let resultIndex {
      properties["result_index"] = resultIndex
    }
    return properties
  }

  static func queryEntered(surface: SearchSurface, query: String, resultsCount: Int) {
    let normalized = DebouncedSearchCoordinator.normalized(query)
    guard !normalized.isEmpty else { return }
    AnalyticsManager.shared.searchQueryEntered(
      surface: surface, query: normalized, resultsCount: resultsCount)
  }

  /// Debounce live-filter surfaces so keystrokes do not flood PostHog.
  /// `resultsCount` is read at commit time so async filters can settle.
  static func scheduleQueryEntered(
    surface: SearchSurface,
    query: String,
    resultsCount: @escaping @MainActor () -> Int
  ) {
    let coordinator = debounceCoordinators[surface] ?? DebouncedSearchCoordinator()
    debounceCoordinators[surface] = coordinator
    coordinator.submit(query) { submitted in
      guard !submitted.isEmpty else { return }
      queryEntered(surface: surface, query: submitted, resultsCount: resultsCount())
    }
  }

  static func barFocused(surface: SearchSurface) {
    AnalyticsManager.shared.searchBarFocused(surface: surface)
  }

  static func resultOpened(surface: SearchSurface, resultIndex: Int? = nil, searchIsActive: Bool) {
    guard searchIsActive else { return }
    AnalyticsManager.shared.searchResultOpened(surface: surface, resultIndex: resultIndex)
  }

  static func resetDebounceCoordinatorsForTests() {
    debounceCoordinators.removeAll()
  }
}
