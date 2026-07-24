import XCTest

@testable import Omi_Computer

@MainActor
final class AppsPageCategoryFilterTests: XCTestCase {
  private func sampleCategories(count: Int) -> [OmiAppCategory] {
    (1...count).map { index in
      OmiAppCategory(id: "category-\(index)", title: "Category \(index)")
    }
  }

  func testCategoryDropdownOptionsPrependsAllCategories() {
    let options = AppsPageCategoryFilter.categoryDropdownOptions(
      categories: [
        OmiAppCategory(id: "productivity", title: "Productivity"),
        OmiAppCategory(id: "chat", title: "Chat"),
      ]
    )

    XCTAssertEqual(options.count, 3)
    XCTAssertEqual(options.first?.id, AppsPageCategoryFilter.allCategoriesOptionId)
    XCTAssertEqual(options.first?.title, AppsPageCategoryFilter.allCategoriesTitle)
    XCTAssertEqual(options.map(\.id), ["", "productivity", "chat"])
  }

  func testLongCategoryListUsesSearchablePopoverPath() {
    let options = AppsPageCategoryFilter.categoryDropdownOptions(categories: sampleCategories(count: 10))

    XCTAssertTrue(SearchableDropdownFiltering.usesSearchablePopover(optionCount: options.count))
  }

  func testShortCategoryListUsesCompactMenuPath() {
    let options = AppsPageCategoryFilter.categoryDropdownOptions(categories: sampleCategories(count: 5))

    XCTAssertFalse(SearchableDropdownFiltering.usesSearchablePopover(optionCount: options.count))
  }

  func testFilterCategoriesByTitle() {
    let options = AppsPageCategoryFilter.categoryDropdownOptions(
      categories: [
        OmiAppCategory(id: "productivity", title: "Productivity"),
        OmiAppCategory(id: "personality-clone", title: "Personality Clone"),
        OmiAppCategory(id: "chat", title: "Chat"),
      ]
    )

    let filtered = SearchableDropdownFiltering.filteredOptions(options, query: "clone")

    XCTAssertEqual(filtered.map(\.id), ["personality-clone"])
  }

  func testFilterCategoriesById() {
    let options = AppsPageCategoryFilter.categoryDropdownOptions(
      categories: [
        OmiAppCategory(id: "productivity", title: "Productivity"),
        OmiAppCategory(id: "personality-clone", title: "Personality Clone"),
      ]
    )

    let filtered = SearchableDropdownFiltering.filteredOptions(options, query: "productivity")

    XCTAssertEqual(filtered.map(\.id), ["productivity"])
  }

  func testSelectingSpecificCategoryUpdatesProviderState() {
    let provider = AppProvider()

    switch AppsPageCategoryFilter.categorySelection(forOptionId: "productivity") {
    case .allCategories:
      provider.clearCategoryFilter()
    case .category(let categoryId):
      provider.selectedCategory = categoryId
    }

    XCTAssertEqual(provider.selectedCategory, "productivity")
    XCTAssertEqual(
      AppsPageCategoryFilter.selectedCategoryDropdownId(provider.selectedCategory), "productivity")
  }

  func testResetToAllCategoriesClearsProviderState() {
    let provider = AppProvider()
    provider.selectedCategory = "productivity"
    provider.filteredApps = []
    provider.hasMoreFilteredApps = true

    switch AppsPageCategoryFilter.categorySelection(forOptionId: AppsPageCategoryFilter.allCategoriesOptionId) {
    case .allCategories:
      provider.clearCategoryFilter()
    case .category(let categoryId):
      provider.selectedCategory = categoryId
    }

    XCTAssertNil(provider.selectedCategory)
    XCTAssertNil(provider.filteredApps)
    XCTAssertFalse(provider.hasMoreFilteredApps)
    XCTAssertEqual(
      AppsPageCategoryFilter.selectedCategoryDropdownId(provider.selectedCategory),
      AppsPageCategoryFilter.allCategoriesOptionId)
  }
}
