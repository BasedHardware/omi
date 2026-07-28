import XCTest

@testable import Omi_Computer

/// Regression coverage for context-connector routing and failure projection.
///
/// Memory import and live MCP export are different product operations. The
/// context rows must use the same importer as Apps > Imports, while Google
/// functional-probe failures retain sanitized, actionable copy.
final class SBOnboardingCloudContextStateTests: XCTestCase {
  private let resumeStepKey = "sbOnboardingResumeStep"

  override func setUp() {
    super.setUp()
    DesktopDiagnosticsManager.shared.resetForTests()
    UserDefaults.standard.removeObject(forKey: resumeStepKey)
    UserDefaults.standard.removeObject(forKey: DefaultsKey.hasCompletedOnboarding.rawValue)
  }

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: resumeStepKey)
    UserDefaults.standard.removeObject(forKey: DefaultsKey.hasCompletedOnboarding.rawValue)
    super.tearDown()
  }

  @MainActor
  func testBeginSignalsCompletedFlagDisagreeingWithStageResumeAndSetupJournal() {
    let appState = AppState()
    appState.hasCompletedOnboarding = true
    UserDefaults.standard.set(
      SBOnboardingModel.Step.context.rawValue,
      forKey: SBOnboardingModel.resumeStepKey)
    let model = SBOnboardingModel(
      appState: appState,
      chatProvider: ChatProvider(),
      onComplete: nil)

    model.begin()

    let signals = DesktopDiagnosticsManager.shared.currentSnapshotsForSentry().filter {
      $0["seam"] as? String == DesktopStateAuthoritySeam.onboardingSetupState.rawValue
    }
    XCTAssertEqual(
      Set(signals.compactMap { $0["direction"] as? String }),
      [
        "completed_flag_with_active_stage",
        "completed_flag_with_resume_state",
        "completed_flag_with_active_journal",
      ])
    XCTAssertTrue(appState.hasCompletedOnboarding)
    XCTAssertTrue(model.chatProvider.isOnboarding)
  }

  func testMemoryContextRowsRouteToCanonicalImportConnectors() {
    XCTAssertEqual(SBOnboardingModel.contextConnectionRoute(for: "chatgpt"), .importConnector("chatgpt"))
    XCTAssertEqual(SBOnboardingModel.contextConnectionRoute(for: "claude"), .importConnector("claude"))
    XCTAssertEqual(SBOnboardingModel.contextConnectionRoute(for: "calendar"), .direct)
    XCTAssertEqual(SBOnboardingModel.contextConnectionRoute(for: "gmail"), .direct)

    for connectorID in ["chatgpt", "claude"] {
      let connector = ImportConnector.all.first(where: { $0.id == connectorID })
      XCTAssertEqual(connector?.subtitle, "Memory import")
      XCTAssertEqual(connector?.description, "Paste a memory export into Omi.")
    }
  }

  func testGoogleSignInFailurePreservesActionableMessage() {
    let resolution = SBOnboardingModel.googleContextResolution(
      connectorID: "gmail",
      connected: false,
      needsSignIn: true
    )

    XCTAssertEqual(resolution.state, "needsSignIn")
    XCTAssertEqual(
      resolution.detail,
      "Open Gmail in Chrome, Arc, Brave, or Edge, sign in, then retry."
    )
    XCTAssertTrue(resolution.shouldOpenSignIn)
  }

  func testGoogleOperationalFailureUsesBoundedCopyAndDoesNotOpenSignIn() {
    let resolution = SBOnboardingModel.googleContextResolution(
      connectorID: "calendar",
      connected: false,
      needsSignIn: false
    )

    XCTAssertEqual(resolution.state, "error")
    XCTAssertEqual(
      resolution.detail,
      "Couldn't verify Google Calendar. Check your browser session and connection, then retry."
    )
    XCTAssertFalse(resolution.shouldOpenSignIn)
  }

  func testGoogleSuccessClearsOldFailureDetail() {
    let resolution = SBOnboardingModel.googleContextResolution(
      connectorID: "gmail",
      connected: true,
      needsSignIn: false
    )

    XCTAssertEqual(resolution.state, "on")
    XCTAssertNil(resolution.detail)
    XCTAssertFalse(resolution.shouldOpenSignIn)
  }

  @MainActor
  func testPassiveGoogleRecoveryClearsThePreviouslyProjectedFailure() {
    let model = SBOnboardingModel(
      appState: AppState(),
      chatProvider: ChatProvider(),
      onComplete: nil)
    model.contextStates["calendar"] = "error"
    model.contextDetails["calendar"] = "Couldn't verify Google Calendar."

    model.markContextConnected("calendar")

    XCTAssertEqual(model.contextStates["calendar"], "on")
    XCTAssertNil(model.contextDetails["calendar"])
  }
}
