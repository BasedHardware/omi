import XCTest

@testable import Omi_Computer

@MainActor
final class AppsPageSearchResultsPresentationTests: XCTestCase {
  func testEmptyResultsAppearOnlyAfterACompletedQuery() {
    for state in [AppFilterResultsQueryState.unknown, .loading, .failed] {
      XCTAssertNotEqual(
        AppsFilteredResultsPresentation.resolve(queryState: state, resultsCount: 0),
        .empty,
        "\(state) must not be rendered as an empty search result"
      )
    }

    XCTAssertEqual(
      AppsFilteredResultsPresentation.resolve(queryState: .completed, resultsCount: 0),
      .empty
    )
  }

  func testPendingSearchUsesLoadingPresentationBeforeResultsArrive() {
    XCTAssertEqual(
      AppsFilteredResultsPresentation.resolve(queryState: .unknown, resultsCount: 0),
      .loading
    )
    XCTAssertEqual(
      AppsFilteredResultsPresentation.resolve(queryState: .loading, resultsCount: 0),
      .loading
    )
    XCTAssertEqual(
      AppsFilteredResultsPresentation.resolve(queryState: .completed, resultsCount: 1),
      .results
    )
  }

  func testChangingAFilterInvalidatesPreviouslyDisplayedResults() {
    let provider = AppProvider()
    provider.filteredApps = []
    provider.hasMoreFilteredApps = true

    provider.searchQuery = "calendar"

    XCTAssertNil(provider.filteredApps)
    XCTAssertFalse(provider.hasMoreFilteredApps)
    XCTAssertEqual(provider.filteredAppsQueryState, .unknown)
  }
}
