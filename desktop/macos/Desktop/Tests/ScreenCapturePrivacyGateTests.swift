import XCTest

@testable import Omi_Computer

@MainActor
final class ScreenCapturePrivacyGateTests: XCTestCase {
  private nonisolated static let monitoringKey = "screenAnalysisEnabled"
  private nonisolated(unsafe) static var previousMonitoring = false

  override nonisolated func setUp() {
    super.setUp()
    Self.previousMonitoring = UserDefaults.standard.bool(forKey: Self.monitoringKey)
    UserDefaults.standard.set(true, forKey: Self.monitoringKey)
  }

  override nonisolated func tearDown() {
    UserDefaults.standard.set(Self.previousMonitoring, forKey: Self.monitoringKey)
    super.tearDown()
  }

  func testMonitoringKillSwitchBlocksCapture() {
    UserDefaults.standard.set(false, forKey: Self.monitoringKey)
    XCTAssertEqual(
      ScreenCapturePrivacyGate.decide(appName: "Safari", bundleID: "com.apple.Safari"),
      .monitoringDisabled)
  }

  func testExcludedAppNameBlocksCapture() {
    RewindSettings.shared.excludeApp("1Password")
    XCTAssertEqual(
      ScreenCapturePrivacyGate.decide(appName: "1Password", bundleID: nil),
      .appExcluded("1Password"))
  }

  func testPasswordManagerBundleIDsBlockCaptureEvenWhenNotNamedInTheList() {
    // These ship under localized or renamed display names that
    // `RewindSettings.isAppExcluded` cannot match.
    for bundleID in [
      "me.proton.pass",
      "com.nordpass.macos",
      "com.markmcguill.strongbox.mac",
      "com.1password.1password",
      "com.apple.keychainaccess",
    ] {
      XCTAssertTrue(
        ScreenCapturePrivacyGate.isExcludedBundleID(bundleID),
        "expected \(bundleID) to be excluded")
      XCTAssertEqual(
        ScreenCapturePrivacyGate.decide(appName: "Gestor de contraseñas", bundleID: bundleID),
        .appExcluded(bundleID))
    }
  }

  func testOrdinaryAppIsAllowed() {
    XCTAssertEqual(
      ScreenCapturePrivacyGate.decide(appName: "Xcode", bundleID: "com.apple.dt.Xcode"),
      .allowed)
  }
}
