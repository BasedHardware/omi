import XCTest

@testable import Omi_Computer

/// The Omi Beta identity (`com.omi.computer-macos.beta`) must behave as a shipped
/// production artifact — never as a dev/test bundle — while keeping its own update
/// channel, storage root, and log path so it can run beside stable.
final class AppBuildBetaIdentityTests: XCTestCase {
  func testBetaIdentityIsProductionGrade() {
    let config = AppBuild.configuration(
      bundleIdentifier: AppBuild.betaProductionBundleIdentifier,
      infoDictionary: [:])

    XCTAssertFalse(config.isNonProduction)
    XCTAssertFalse(config.allowsLocalAutomation)
    XCTAssertTrue(config.allowsSparkleUpdates)
    XCTAssertFalse(config.isExternalPreview)
  }

  func testStableIdentityGatingIsUnchanged() {
    let config = AppBuild.configuration(
      bundleIdentifier: AppBuild.productionBundleIdentifier,
      infoDictionary: [:])

    XCTAssertFalse(config.isNonProduction)
    XCTAssertFalse(config.allowsLocalAutomation)
    XCTAssertTrue(config.allowsSparkleUpdates)
  }

  func testNamedDevBundleStaysNonProduction() {
    let config = AppBuild.configuration(
      bundleIdentifier: "com.omi.omi-feature-test",
      infoDictionary: [:])

    XCTAssertTrue(config.isNonProduction)
    XCTAssertTrue(config.allowsLocalAutomation)
  }

  func testProductionFamilyMembership() {
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
      AppBuild.mayRunLegacyStableAppCleanup(bundleIdentifier: AppBuild.betaProductionBundleIdentifier))
    XCTAssertFalse(
      AppBuild.mayRunLegacyStableAppCleanup(bundleIdentifier: AppBuild.desktopDevBundleIdentifier))
    XCTAssertFalse(
      AppBuild.mayRunLegacyStableAppCleanup(bundleIdentifier: "com.omi.omi-feature-test"))
  }

  func testManualDownloadURLCarriesBetaIdentity() {
    XCTAssertEqual(
      AppBuild.manualDownloadURL(channel: "beta", isBetaIdentity: true).absoluteString,
      "https://api.omi.me/v2/desktop/download/latest?channel=beta&identity=beta")
    XCTAssertEqual(
      AppBuild.manualDownloadURL(channel: "beta", isBetaIdentity: false).absoluteString,
      "https://api.omi.me/v2/desktop/download/latest?channel=beta")
    XCTAssertEqual(
      AppBuild.manualDownloadURL(channel: "stable", isBetaIdentity: false).absoluteString,
      "https://api.omi.me/v2/desktop/download/latest?channel=stable")
  }

  func testProductionLogPathsAreSeparatePerIdentity() {
    XCTAssertEqual(
      OmiLogPathResolver.logPath(
        isNonProduction: false,
        bundleIdentifier: AppBuild.productionBundleIdentifier,
        processID: 1),
      "/tmp/omi.log")
    XCTAssertEqual(
      OmiLogPathResolver.logPath(
        isNonProduction: false,
        bundleIdentifier: AppBuild.betaProductionBundleIdentifier,
        processID: 1),
      "/tmp/omi-beta.log")
  }
}
