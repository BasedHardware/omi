import XCTest

@testable import Omi_Computer

/// Regression coverage for context-connector routing and failure projection.
///
/// Memory import and live MCP export are different product operations. The
/// context rows must use the same importer as Apps > Imports, while Google
/// functional-probe failures retain sanitized, actionable copy.
final class SBOnboardingCloudContextStateTests: XCTestCase {
  private let resumeStepKey = "sbOnboardingResumeStep"
  // Literals: setUp/tearDown are nonisolated, the model constants are not.
  private let resumeSchemaKey = "sbOnboardingResumeStepSchema"
  private let currentResumeSchemaVersion = 2

  override func setUp() {
    super.setUp()
    DesktopDiagnosticsManager.shared.resetForTests()
    UserDefaults.standard.removeObject(forKey: resumeStepKey)
    UserDefaults.standard.removeObject(forKey: DefaultsKey.hasCompletedOnboarding.rawValue)
    // Seeded resume values below are in the current `Step` numbering; stamp the
    // schema so `begin()` does not renumber them as version-1 state.
    UserDefaults.standard.set(currentResumeSchemaVersion, forKey: resumeSchemaKey)
  }

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: resumeStepKey)
    UserDefaults.standard.removeObject(forKey: resumeSchemaKey)
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
    XCTAssertEqual(SBOnboardingModel.importConnectorID(forGoogleContextID: "calendar"), "calendar")
    XCTAssertEqual(SBOnboardingModel.importConnectorID(forGoogleContextID: "gmail"), "email")

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
  func testSuccessfulGoogleImportPersistsTheSameConnectedStateReadAfterOnboarding() throws {
    let testDefaults = try makeDefaults()
    defer { testDefaults.defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let statusStore = ImportConnectorStatusStore(defaults: testDefaults.defaults, sessionUserID: "test-user")
    let model = SBOnboardingModel(
      appState: AppState(),
      chatProvider: ChatProvider(),
      importConnectorStatusStore: statusStore,
      onComplete: nil)

    let terminal = model.completeGoogleContextImport(
      contextID: "calendar",
      connectorID: "calendar",
      outcome: .success(
        ConnectorImportOperations.SyncResult(sourceCount: 0, memoryCount: 0, newItems: 0),
        message: "Imported 0 events and saved 0 memories."
      ),
      statusStore: statusStore,
      wasFirstSync: true
    )

    XCTAssertEqual(model.contextStates["calendar"], "on")
    XCTAssertNil(model.contextDetails["calendar"])
    guard case .success(_, let metrics) = terminal else {
      return XCTFail("expected a successful import terminal")
    }
    XCTAssertEqual(metrics.sourceCount, 0)
    guard let calendarConnector = ImportConnector.all.first(where: { $0.id == "calendar" }) else {
      return XCTFail("calendar connector must remain registered")
    }
    XCTAssertTrue(
      ImportConnectorStatusStore(defaults: testDefaults.defaults, sessionUserID: "test-user")
        .snapshot(for: calendarConnector)
        .isConnected
    )
  }

  @MainActor
  func testFailedGoogleImportNeverPersistsOrProjectsConnected() throws {
    let testDefaults = try makeDefaults()
    defer { testDefaults.defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let statusStore = ImportConnectorStatusStore(defaults: testDefaults.defaults, sessionUserID: "test-user")
    let model = SBOnboardingModel(
      appState: AppState(),
      chatProvider: ChatProvider(),
      importConnectorStatusStore: statusStore,
      onComplete: nil)

    let terminal = model.completeGoogleContextImport(
      contextID: "gmail",
      connectorID: "email",
      outcome: .failure(message: "Sign in", failureClass: .sessionExpired),
      statusStore: statusStore,
      wasFirstSync: true
    )

    XCTAssertEqual(model.contextStates["gmail"], "needsSignIn")
    XCTAssertEqual(
      model.contextDetails["gmail"],
      "Open Gmail in Chrome, Arc, Brave, or Edge, sign in, then retry."
    )
    guard case .failure(_, let metrics) = terminal else {
      return XCTFail("expected a failed import terminal")
    }
    XCTAssertEqual(metrics.failureClass, .sessionExpired)
    guard let emailConnector = ImportConnector.all.first(where: { $0.id == "email" }) else {
      return XCTFail("email connector must remain registered")
    }
    XCTAssertFalse(
      ImportConnectorStatusStore(defaults: testDefaults.defaults, sessionUserID: "test-user")
        .snapshot(for: emailConnector)
        .isConnected
    )
  }

  @MainActor
  func testPersistedEmailConnectorIDUpdatesGmailContextRow() {
    let model = SBOnboardingModel(
      appState: AppState(),
      chatProvider: ChatProvider(),
      onComplete: nil)

    model.markPersistedContextConnectorConnected("email")

    XCTAssertEqual(model.contextStates["gmail"], "on")
    XCTAssertNil(model.contextDetails["gmail"])
  }

  private func makeDefaults() throws -> (defaults: UserDefaults, suiteName: String) {
    let suiteName = "SBOnboardingCloudContextStateTests.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      throw NSError(
        domain: "SBOnboardingCloudContextStateTests",
        code: 1,
        userInfo: [NSLocalizedDescriptionKey: "unable to create isolated UserDefaults suite"]
      )
    }
    return (defaults, suiteName)
  }
}
