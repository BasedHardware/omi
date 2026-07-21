import XCTest

@testable import Omi_Computer

final class AppBuildProductionFamilyTests: XCTestCase {
  func testProductionFamilyContainsStableAndBetaIdentities() {
    // INV-DATA-1: installed Omi Beta apps are production-family customers and
    // must never leave the production data plane.
    XCTAssertEqual(
      AppBuild.productionFamilyBundleIdentifiers,
      [AppBuild.productionBundleIdentifier, AppBuild.betaProductionBundleIdentifier])
  }

  func testOnlyStableIdentityMayRunLegacyStableAppCleanup() {
    // The legacy "Omi Computer.app" cleanup force-terminates running stable
    // processes; Omi Beta running it would kill the side-by-side stable app.
    XCTAssertTrue(
      AppBuild.mayRunLegacyStableAppCleanup(bundleIdentifier: AppBuild.productionBundleIdentifier))
    XCTAssertFalse(
      AppBuild.mayRunLegacyStableAppCleanup(
        bundleIdentifier: AppBuild.betaProductionBundleIdentifier))
    XCTAssertFalse(
      AppBuild.mayRunLegacyStableAppCleanup(bundleIdentifier: AppBuild.desktopDevBundleIdentifier))
    XCTAssertFalse(
      AppBuild.mayRunLegacyStableAppCleanup(bundleIdentifier: "com.omi.omi-feature-test"))
  }
}
