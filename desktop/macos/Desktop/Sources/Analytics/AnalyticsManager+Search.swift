import Foundation

extension AnalyticsManager {
  func searchQueryEntered(surface: SearchSurface, query: String, resultsCount: Int) {
    let properties = SearchAnalytics.queryEnteredProperties(
      surface: surface, query: query, resultsCount: resultsCount)
    trackSearch(SearchAnalytics.queryEnteredEvent, properties: properties)
  }

  func searchBarFocused(surface: SearchSurface) {
    trackSearch(
      SearchAnalytics.barFocusedEvent,
      properties: SearchAnalytics.barFocusedProperties(surface: surface))
  }

  func searchResultOpened(surface: SearchSurface, resultIndex: Int?) {
    let properties = SearchAnalytics.resultOpenedProperties(
      surface: surface, resultIndex: resultIndex)
    trackSearch(SearchAnalytics.resultOpenedEvent, properties: properties)
    if surface == .conversations {
      trackSearch(
        SearchAnalytics.conversationOpenedFromSearchEvent,
        properties: ["search_surface": SearchSurface.conversations.rawValue])
    }
  }

  private func trackSearch(_ event: String, properties: [String: Any]) {
    searchTelemetryCaptureForTests?(event, properties)
    switch event {
    case SearchAnalytics.queryEnteredEvent:
      PostHogManager.shared.searchQueryEntered(properties: properties)
    case SearchAnalytics.barFocusedEvent:
      PostHogManager.shared.searchBarFocused(properties: properties)
    case SearchAnalytics.resultOpenedEvent:
      PostHogManager.shared.searchResultOpened(properties: properties)
    case SearchAnalytics.conversationOpenedFromSearchEvent:
      PostHogManager.shared.conversationOpenedFromSearch(properties: properties)
    default:
      PostHogManager.shared.track(event, properties: properties)
    }
  }
}
