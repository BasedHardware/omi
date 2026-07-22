import XCTest

@testable import Omi_Computer

/// Regression coverage for the Second Brain onboarding launch-at-login override.
///
/// `SBOnboardingModel.complete(startListening:)` used to call
/// `LaunchAtLoginManager.shared.setEnabled(true)` unconditionally, forcing Omi to
/// reopen at login even for a user who had auto-start turned off — overriding the
/// selected `launchAtLogin` value instead of preserving it. Completion now routes
/// through `applyLaunchAtLoginSelection`, which forwards the user's actual
/// selection and reports the real value to analytics.
///
/// The test drives that seam directly with capturing closures so it stays
/// hermetic — no real login-item registration and no analytics side effects.
@MainActor
final class SBOnboardingLaunchAtLoginCompletionTests: XCTestCase {

  private func makeModel() -> SBOnboardingModel {
    SBOnboardingModel(appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
  }

  func testCompletionPreservesDeclinedLaunchAtLogin() {
    let model = makeModel()
    model.launchAtLogin = false

    var setEnabledArg: Bool?
    var reportedArg: Bool?
    model.applyLaunchAtLoginSelection(
      setEnabled: { value in
        setEnabledArg = value
        return true
      },
      report: { value in reportedArg = value })

    XCTAssertEqual(
      setEnabledArg, false,
      "A user who declined auto-start must NOT have launch-at-login force-enabled at completion")
    XCTAssertEqual(
      reportedArg, false,
      "Analytics must report the actual (declined) value, not a hardcoded true")
  }

  func testCompletionPreservesAcceptedLaunchAtLogin() {
    let model = makeModel()
    model.launchAtLogin = true

    var setEnabledArg: Bool?
    var reportedArg: Bool?
    model.applyLaunchAtLoginSelection(
      setEnabled: { value in
        setEnabledArg = value
        return true
      },
      report: { value in reportedArg = value })

    XCTAssertEqual(
      setEnabledArg, true,
      "A user who kept auto-start on must have launch-at-login enabled at completion")
    XCTAssertEqual(reportedArg, true, "Analytics must report the actual (accepted) value")
  }

  func testAnalyticsNotReportedWhenSetEnabledFails() {
    // Non-production bundles (dev / named test bundles) refuse to register and
    // return false; analytics should only fire on a successful state change.
    let model = makeModel()
    model.launchAtLogin = true

    var reported = false
    model.applyLaunchAtLoginSelection(
      setEnabled: { _ in false },
      report: { _ in reported = true })

    XCTAssertFalse(reported, "Analytics must not fire when the launch-at-login change did not take effect")
  }
}
