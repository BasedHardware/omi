import XCTest

@testable import Omi_Computer

/// Integration tests for the Auto-router Settings sidebar entry. Verifies
/// the navigation data (enum cases, sidebar visibility, search index, icon
/// mapping) so the Settings page can route to `AutoRouterSettingsView`.
///
/// We don't snapshot-test the actual navigation flow (SwiftUI navigation
/// isn't easily testable without UI testing). What we DO verify is that
/// the data the navigation system reads is consistent: every section in
/// `SettingsSection.allCases` has an icon, every visible section is in
/// `allCases`, and the search index includes the Auto-router entry.
@MainActor
final class AutoRouterSettingsViewIntegrationTests: XCTestCase {

    // MARK: - SettingsSection enum

    /// `SettingsSection` is `private` to `SettingsContentView`, but `@testable import`
    /// lets us reach it via the type name.
    private typealias Section = SettingsContentView.SettingsSection

    func testAutoRouterSection_existsInEnum() {
        // The case must exist; otherwise SettingsPage.swift wouldn't compile.
        // This test exists as documentation + a regression guard if the case
        // is ever renamed.
        let section = Section(rawValue: "Auto-router")
        XCTAssertNotNil(section, "SettingsSection must have an 'Auto-router' case")
        // `autoRouter` and `.rawValue` should round-trip.
        XCTAssertEqual(section?.rawValue, "Auto-router")
    }

    func testAllCases_includesAutoRouter() {
        XCTAssertTrue(
            Section.allCases.contains(where: { $0.rawValue == "Auto-router" }),
            "SettingsSection.allCases should include .autoRouter"
        )
    }

    // MARK: - Sidebar visibility

    func testSettingsSidebar_includesAutoRouterInVisibleSections() {
        // The SettingsSidebar's visibleSections is private, so we test the
        // public observable behavior instead: searching for "auto" should
        // return at least one search item pointing to .autoRouter.
        let results = SettingsSearchItem.allSearchableItems.filter { item in
            item.section.rawValue.lowercased().contains("auto")
        }
        XCTAssertFalse(results.isEmpty, "Search index should include Auto-router items")
        XCTAssertTrue(
            results.contains(where: { $0.section.rawValue == "Auto-router" }),
            "At least one search item should target the .autoRouter section"
        )
    }

    // MARK: - Search index

    func testSearchItem_indexedForAutoRouter() {
        // The sidebar search index must contain an item for Auto-router,
        // otherwise searching "auto router" returns no results.
        let names = SettingsSearchItem.allSearchableItems
            .filter { $0.section.rawValue == "Auto-router" }
            .map { $0.name }
        XCTAssertTrue(
            names.contains("Auto-router"),
            "Search index must have an 'Auto-router' item; found: \(names)"
        )
    }

    func testSearchItem_autoRouterHasKeywords() {
        // The search keywords let users find this setting with various terms.
        let items = SettingsSearchItem.allSearchableItems.filter {
            $0.section.rawValue == "Auto-router"
        }
        XCTAssertFalse(items.isEmpty)
        let allKeywords = items.flatMap { $0.keywords }.map { $0.lowercased() }
        for required in ["router", "model", "weights"] {
            XCTAssertTrue(
                allKeywords.contains(required),
                "Auto-router search items should include keyword '\(required)'"
            )
        }
    }

    // MARK: - Enum-icon consistency

    func testSettingsSection_enumAndSidebarIconsConsistent() {
        // We can't directly read the sidebar's `icon` mapping (it's in a
        // private computed property on SettingsSidebarItem). But we can at
        // least verify that for every section case in `allCases`, the icon
        // lookup is well-defined — by checking that allSections + the
        // SettingsSidebarItem constructor don't crash (compilation catches
        // missing cases in the `switch section` mapping).
        //
        // This is a smoke test — if a new section is added without updating
        // the icon switch, the build breaks. We rely on the build to enforce
        // that; this test exists only to document the contract.
        for section in Section.allCases {
            // Create a sidebar item for each section. If a case is missing
            // from the icon switch in SettingsSidebar.swift, this won't
            // compile.
            let _ = SettingsSidebarItem(
                section: section,
                isSelected: false,
                iconWidth: 20,
                onTap: {}
            )
            XCTAssertFalse(section.rawValue.isEmpty, "Section \(section) has empty rawValue")
        }
    }
}
