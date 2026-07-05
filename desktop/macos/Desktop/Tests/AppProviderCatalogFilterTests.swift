import XCTest

@testable import Omi_Computer

@MainActor
final class AppProviderCatalogFilterTests: XCTestCase {
    func testClearFiltersResetsAllMarketplaceFilterState() {
        let provider = AppProvider()
        provider.searchQuery = "einstein"
        provider.selectedCategory = "personality-clone"
        provider.selectedCapability = "chat"
        provider.showInstalledOnly = true
        provider.filteredApps = []
        provider.hasMoreFilteredApps = true

        XCTAssertTrue(provider.hasActiveFilters)

        provider.clearFilters()

        XCTAssertFalse(provider.hasActiveFilters)
        XCTAssertEqual(provider.searchQuery, "")
        XCTAssertNil(provider.selectedCategory)
        XCTAssertNil(provider.selectedCapability)
        XCTAssertFalse(provider.showInstalledOnly)
        XCTAssertNil(provider.filteredApps)
        XCTAssertFalse(provider.hasMoreFilteredApps)
    }

    func testClearFiltersClearsEachFilterKindIndividually() {
        for configure in [
            { (p: AppProvider) in p.searchQuery = "  notes  " },
            { (p: AppProvider) in p.selectedCategory = "productivity" },
            { (p: AppProvider) in p.selectedCapability = "chat" },
            { (p: AppProvider) in p.showInstalledOnly = true },
        ] {
            let provider = AppProvider()
            configure(provider)
            XCTAssertTrue(provider.hasActiveFilters)

            provider.clearFilters()

            XCTAssertFalse(provider.hasActiveFilters)
        }
    }
}
