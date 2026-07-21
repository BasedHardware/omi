import XCTest

@testable import Omi_Computer

final class BetaEnhancedDiagnosticsConfigurationTests: XCTestCase {
  private var defaults: UserDefaults?
  private var suiteName = ""

  override func setUp() {
    super.setUp()
    suiteName = "BetaEnhancedDiagnosticsConfigurationTests.\(UUID().uuidString)"
    defaults = UserDefaults(suiteName: suiteName)
  }

  override func tearDown() {
    defaults?.removePersistentDomain(forName: suiteName)
    defaults = nil
    super.tearDown()
  }

  func testBetaDefaultsToEnhancedDiagnosticsEnabled() {
    guard let defaults else {
      XCTFail("Expected isolated UserDefaults suite")
      return
    }
    XCTAssertTrue(
      BetaEnhancedDiagnosticsConfiguration.isEnabled(
        bundleIdentifier: AppBuild.productionBundleIdentifier,
        updateChannel: "beta",
        defaults: defaults))
  }

  func testBetaRespectsAdvancedOptOut() {
    guard let defaults else {
      XCTFail("Expected isolated UserDefaults suite")
      return
    }
    defaults.set(false, forKey: BetaEnhancedDiagnosticsConfiguration.defaultsKey)

    XCTAssertFalse(
      BetaEnhancedDiagnosticsConfiguration.isEnabled(
        bundleIdentifier: AppBuild.productionBundleIdentifier,
        updateChannel: "beta",
        defaults: defaults))
  }

  func testStableNeverEnablesEnhancedDiagnostics() {
    guard let defaults else {
      XCTFail("Expected isolated UserDefaults suite")
      return
    }
    defaults.set(true, forKey: BetaEnhancedDiagnosticsConfiguration.defaultsKey)

    XCTAssertFalse(
      BetaEnhancedDiagnosticsConfiguration.isEnabled(
        bundleIdentifier: AppBuild.productionBundleIdentifier,
        updateChannel: "stable",
        defaults: defaults))
  }
}
