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

  func testAllCatalogSearchAggregatesOnlyVisibleGroups() {
    XCTAssertEqual(
      AppsAllSearchPresentation.resolve(
        importsCount: 1,
        exportsCount: 2,
        appsCount: 4,
        marketplace: .results
      ),
      .results(total: 7))

    // Marketplace loading/failed states do not contribute cards to the All
    // presentation. Local matches still render while that group resolves.
    XCTAssertEqual(
      AppsAllSearchPresentation.resolve(
        importsCount: 1,
        exportsCount: 0,
        appsCount: 4,
        marketplace: .loading
      ),
      .results(total: 1))
    XCTAssertEqual(
      AppsAllSearchPresentation.resolve(
        importsCount: 0,
        exportsCount: 0,
        appsCount: 4,
        marketplace: .failure
      ),
      .failure)
  }

  func testAllCatalogSearchUsesOneGlobalEmptyStateWhenEveryGroupIsEmpty() {
    XCTAssertEqual(
      AppsAllSearchPresentation.resolve(
        importsCount: 0,
        exportsCount: 0,
        appsCount: 0,
        marketplace: .empty
      ),
      .empty)
    XCTAssertEqual(
      AppsAllSearchPresentation.resolve(
        importsCount: 0,
        exportsCount: 0,
        appsCount: 0,
        marketplace: .results
      ),
      .empty)
  }

  func testExportSearchTrimsWhitespaceAndRanksExactTitlesFirst() {
    let results = MemoryExportCatalog.matching("  notion  ")

    XCTAssertEqual(results.first?.destination, .notion)
    XCTAssertTrue(
      results.allSatisfy { entry in
        [entry.resolvedTitle, entry.resolvedSubtitle, entry.resolvedDescription]
          .contains { $0.localizedCaseInsensitiveContains("notion") }
      })
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

  func testClearingIndividualMarketplaceRefinementsPreservesSearchText() {
    let provider = AppProvider()
    provider.searchQuery = "notion"
    provider.selectedCategory = "productivity"
    provider.selectedCapability = "chat"
    provider.showInstalledOnly = true

    provider.clearCategoryFilter()
    provider.selectedCapability = nil
    provider.showInstalledOnly = false

    XCTAssertEqual(provider.searchQuery, "notion")
    XCTAssertTrue(provider.hasActiveFilters, "the preserved query remains an active search")
    XCTAssertNil(provider.selectedCategory)
    XCTAssertNil(provider.selectedCapability)
    XCTAssertFalse(provider.showInstalledOnly)
  }
}
