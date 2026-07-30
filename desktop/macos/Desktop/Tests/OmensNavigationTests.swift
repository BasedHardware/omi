import XCTest

@testable import Omi_Computer

final class OmensNavigationTests: XCTestCase {
  func testStableAndBetaHideOmensWhileProductionRolloutIsDisabled() {
    for bundleIdentifier in [
      "com.omi.computer-macos",
      "com.omi.computer-macos.beta",
    ] {
      XCTAssertFalse(
        SidebarNavItem.mainItems(
          bundleIdentifier: bundleIdentifier,
          productionOmensRolloutEnabled: false
        ).contains(.projections))
      XCTAssertFalse(
        TopNavigationRoutes.primaryItems(
          bundleIdentifier: bundleIdentifier,
          productionOmensRolloutEnabled: false
        ).contains { $0.index == SidebarNavItem.projections.rawValue })
    }
  }

  func testNamedDevelopmentBundleShowsOmens() {
    XCTAssertTrue(
      SidebarNavItem.mainItems(
        bundleIdentifier: "com.omi.omi-omens",
        productionOmensRolloutEnabled: false
      ).contains(.projections))
    XCTAssertTrue(
      TopNavigationRoutes.primaryItems(
        bundleIdentifier: "com.omi.omi-omens",
        productionOmensRolloutEnabled: false
      ).contains { $0.index == SidebarNavItem.projections.rawValue })
  }

  func testExternalPreviewHidesOmens() {
    XCTAssertFalse(
      SidebarNavItem.mainItems(
        bundleIdentifier: "com.omi.preview.p8b1f42a9",
        productionOmensRolloutEnabled: false
      ).contains(.projections))
    XCTAssertFalse(
      TopNavigationRoutes.primaryItems(
        bundleIdentifier: "com.omi.preview.p8b1f42a9",
        productionOmensRolloutEnabled: false
      ).contains { $0.index == SidebarNavItem.projections.rawValue })
  }

  func testProductionRolloutSignalCanEnableOmensLater() {
    XCTAssertTrue(
      SidebarNavItem.mainItems(
        bundleIdentifier: "com.omi.computer-macos",
        productionOmensRolloutEnabled: true
      ).contains(.projections))
    XCTAssertTrue(
      TopNavigationRoutes.primaryItems(
        bundleIdentifier: "com.omi.computer-macos",
        productionOmensRolloutEnabled: true
      ).contains { $0.index == SidebarNavItem.projections.rawValue })
  }
}
