import XCTest

@testable import Omi_Computer

/// S-08 — Fail-loud config (BL-019, BL-020).
/// Behavioral tests where the type is constructible; source-scrape guards
/// (same pattern as `TranscriptionTransportTests`/`PTTAudioCaptureRaceTests`)
/// for the private auth internals and the AppState permission path that can't
/// be driven without a real signed-in session or a live TCC grant.
final class FailLoudConfigTests: XCTestCase {

  // MARK: BL-019 — empty firebaseApiKey must fail loud, not silently produce ""

  /// A dedicated, user-visible error exists for the missing-key case (so the
  /// failure surfaces as an actionable message instead of an opaque HTTP 400).
  func testMissingFirebaseApiKeyErrorIsUserVisible() {
    let message = AuthError.missingFirebaseApiKey.errorDescription
    XCTAssertNotNil(message)
    let lowered = (message ?? "").lowercased()
    XCTAssertTrue(
      lowered.contains("firebase") || lowered.contains("api key"),
      "the missing-key error must name the cause; got: \(message ?? "nil")")
  }

  /// Every Firebase REST URL builder resolves the key through the throwing
  /// `requireFirebaseApiKey()` helper — the raw `?key=\(firebaseApiKey)`
  /// interpolation (which silently emits `?key=` when unset) must be gone.
  func testFirebaseRequestsResolveKeyThroughThrowingHelper() throws {
    let src = try source(relativePath: "Sources/AuthService.swift")

    XCTAssertTrue(
      src.contains("func requireFirebaseApiKey() throws -> String"),
      "a throwing key accessor must exist")
    XCTAssertTrue(
      src.contains("throw AuthError.missingFirebaseApiKey"),
      "the helper must fail loud on an empty/missing key")

    // The silent path — interpolating the raw computed property straight into a
    // request URL — must no longer exist at any call site.
    XCTAssertFalse(
      src.contains("?key=\\(firebaseApiKey)"),
      "auth request URLs must use the guarded key (try requireFirebaseApiKey()), not the raw property")

    // Each of the three Firebase endpoints must go through the helper.
    XCTAssertTrue(src.contains("signInWithCustomToken?key=\\(apiKey)"))
    XCTAssertTrue(src.contains("securetoken.googleapis.com/v1/token?key=\\(apiKey)"))
    XCTAssertTrue(src.contains("signInWithIdp?key=\\(apiKey)"))
  }

  // MARK: BL-047 — system audio permission truth

  /// Core Audio process taps do not expose a preflight API. The app must not
  /// proxy this through Screen Recording; it retains the last real tap outcome.
  func testCheckSystemAudioPermissionUsesObservedTapOutcome() throws {
    let src = try source(relativePath: "Sources/AppState/AppState+SystemActions.swift")

    guard let range = src.range(of: "func checkSystemAudioPermission() {") else {
      return XCTFail("checkSystemAudioPermission not found")
    }
    let body = String(src[range.lowerBound...].prefix(900))

    XCTAssertFalse(
      body.contains("No-op"),
      "checkSystemAudioPermission must no longer be a no-op")
    XCTAssertFalse(
      body.contains("ScreenCaptureService.checkPermission()"),
      "system audio permission must not be proxied from Screen Recording TCC")
    XCTAssertTrue(
      src.contains("func recordSystemAudioCaptureOutcome(_ status: SystemAudioPermissionStatus)"),
      "tap outcomes should be recorded through a single AppState helper")
    XCTAssertTrue(
      body.contains("recordSystemAudioCaptureOutcome(.unsupported)"),
      "unsupported OS should be explicitly represented")
    XCTAssertTrue(
      body.contains("service.capturing"),
      "active system audio capture should preserve a granted state")
    XCTAssertFalse(
      body.contains("recordSystemAudioCaptureOutcome(.unknown)"),
      "an idle refresh has no new evidence and must not erase onboarding's successful tap")
  }

  func testSystemAudioCaptureOutcomesUpdatePermissionState() throws {
    let src = try source(relativePath: "Sources/AppState/AppState+Transcription.swift")

    XCTAssertTrue(
      src.contains("recordSystemAudioCaptureOutcome(.granted)"),
      "successful system-audio tap starts must mark the permission granted")
    XCTAssertTrue(
      src.contains("recordSystemAudioCaptureOutcome(SystemAudioPermissionStatus.classify(captureError: error))"),
      "failed system-audio tap starts must record the CLASSIFIED outcome (denial only for permission-class errors)")
  }

  func testAudioSourceManagerSystemAudioOutcomesUpdatePermissionState() throws {
    let src = try source(relativePath: "Sources/Audio/AudioSourceManager.swift")

    XCTAssertTrue(
      src.contains("AppState.current?.recordSystemAudioCaptureOutcome(.granted)"),
      "desktop audio-source system audio starts should mark the state granted")
    XCTAssertTrue(
      src.contains("SystemAudioPermissionStatus.classify(captureError: error)"),
      "desktop audio-source system audio failures should record the CLASSIFIED outcome")
    XCTAssertFalse(
      src.contains("throw error"),
      "a system-audio tap failure must not abort the already-running mic/mixer stream")
  }

  func testPermissionsPageSurfacesSystemAudioRow() throws {
    let src = try source(relativePath: "Sources/MainWindow/Pages/PermissionsPage.swift")

    XCTAssertTrue(src.contains("SystemAudioPermissionSection(appState: appState)"))
    XCTAssertTrue(src.contains("Text(\"System Audio\")"))
    XCTAssertTrue(src.contains("appState.systemAudioPermissionStatus"))
    XCTAssertTrue(src.contains("appState.triggerSystemAudioPermission()"))
  }

  @MainActor
  func testSystemAudioOutcomeMappingAndIdleReconciliation() {
    // Behavioral contract (BL-047): status follows OBSERVED tap outcomes and
    // an idle refresh cannot discard the last real observation.
    let state = AppState()
    state.recordSystemAudioCaptureOutcome(.granted)
    XCTAssertEqual(state.systemAudioPermissionStatus, .granted)
    XCTAssertTrue(state.hasSystemAudioPermission)

    state.recordSystemAudioCaptureOutcome(.denied)
    XCTAssertEqual(state.systemAudioPermissionStatus, .denied)
    XCTAssertFalse(state.hasSystemAudioPermission)

    // A successful onboarding prime remains authoritative across the transition
    // to the main app. There is no idle preflight that can contradict it.
    state.recordSystemAudioCaptureOutcome(.granted)
    state.checkSystemAudioPermission()
    XCTAssertEqual(state.systemAudioPermissionStatus, .granted)
    XCTAssertTrue(state.hasSystemAudioPermission)
    XCTAssertFalse(state.missingPermissions.contains("System Audio"))

    // A proven denial DOES count as missing, and persists through re-checks
    // (denial was observed; only stale grants decay).
    state.recordSystemAudioCaptureOutcome(.denied)
    XCTAssertTrue(state.missingPermissions.contains("System Audio"))
    state.checkSystemAudioPermission()
    XCTAssertEqual(state.systemAudioPermissionStatus, .denied)
    XCTAssertTrue(state.missingPermissions.contains("System Audio"))
  }

  @MainActor
  func testSystemAudioPrimeReconcilesSuccessAndFailureThroughSharedState() async {
    let state = AppState()

    let granted = await state.reconcileSystemAudioPermission { true }
    XCTAssertTrue(granted)
    XCTAssertEqual(state.systemAudioPermissionStatus, .granted)
    XCTAssertTrue(state.hasSystemAudioPermission)

    let denied = await state.reconcileSystemAudioPermission { false }
    XCTAssertFalse(denied)
    XCTAssertEqual(state.systemAudioPermissionStatus, .denied)
    XCTAssertFalse(state.hasSystemAudioPermission)
  }

  @available(macOS 14.4, *)
  func testSystemAudioCaptureErrorClassification() {
    // A TCC denial manifests as tap-creation/device-start failure; format and
    // converter errors are provably NOT permission problems and must not claim
    // a denial (they map to unknown so the row stays honest).
    XCTAssertEqual(
      SystemAudioPermissionStatus.classify(
        captureError: SystemAudioCaptureService.SystemAudioCaptureError.tapCreationFailed(-1)),
      .denied)
    XCTAssertEqual(
      SystemAudioPermissionStatus.classify(
        captureError: SystemAudioCaptureService.SystemAudioCaptureError.deviceStartFailed(-1)),
      .denied)
    XCTAssertEqual(
      SystemAudioPermissionStatus.classify(
        captureError: SystemAudioCaptureService.SystemAudioCaptureError.formatError),
      .unknown)
    XCTAssertEqual(
      SystemAudioPermissionStatus.classify(
        captureError: SystemAudioCaptureService.SystemAudioCaptureError.converterCreationFailed),
      .unknown)
    XCTAssertEqual(
      SystemAudioPermissionStatus.classify(
        captureError: SystemAudioCaptureService.SystemAudioCaptureError.unsupportedOS),
      .unsupported)
    struct OtherError: Error {}
    XCTAssertEqual(SystemAudioPermissionStatus.classify(captureError: OtherError()), .unknown)
  }

  func testAuthTokensUseKeychainStorageOnAllBuilds() throws {
    let src = try source(relativePath: "Sources/AuthService.swift")

    // Security invariant: new auth tokens use Keychain on every build. The only
    // UserDefaults continuity path updates an already-existing same-user legacy
    // migration source until signed-app Keychain persistence succeeds.
    XCTAssertTrue(src.contains("usesKeychainTokenStorage: { true }"))
    XCTAssertFalse(src.contains("!AppBuild.isNonProduction"))
    XCTAssertTrue(src.contains("allowsUserDefaultsFallback: { false }"))
    XCTAssertTrue(src.contains("DesktopKeychainStore.setString("))
    XCTAssertTrue(src.contains("persistKeychainTokensTransactionally"))
    XCTAssertTrue(src.contains("clearUserDefaultsTokens()"))
    XCTAssertTrue(src.contains("allowsUserDefaultsTokenFallback"))
    XCTAssertTrue(src.contains("Keychain token persistence deferred; preserving legacy migration source"))
    XCTAssertTrue(src.contains("\"update_channel\": AppBuild.currentUpdateChannel"))
    XCTAssertTrue(src.contains("Keychain migration deferred; retaining legacy auth tokens"))
    XCTAssertTrue(src.contains("DesktopDiagnosticsManager.shared.recordFallback"))
    XCTAssertTrue(src.contains("cachedStoredTokens"))
  }

  func testLocalAgentTokenUsesKeychainStorage() throws {
    let src = try source(relativePath: "Sources/LocalAgentAPIServer.swift")

    XCTAssertTrue(src.contains("tokenKeychainService"))
    XCTAssertTrue(src.contains("DesktopKeychainStore.scopedService(DesktopKeychainStore.legacyLocalAgentTokenService)"))
    XCTAssertTrue(src.contains("DesktopKeychainStore.string("))
    XCTAssertTrue(src.contains("DesktopKeychainStore.setString(token, service: tokenKeychainService"))
    XCTAssertTrue(src.contains("enum LocalAgentAPIError"))
    XCTAssertTrue(src.contains("throw LocalAgentAPIError.tokenStorageUnavailable"))
    XCTAssertFalse(src.contains("UserDefaults.standard.set(token, forKey: tokenKey)"))
    XCTAssertFalse(
      src.contains("private static let tokenKeychainService = \"com.omi.desktop.local-agent-api\""),
      "Local agent token service must be team-scoped, not a shared unscoped constant")
  }

  // The data-protection keychain assertion was inverted by the file-based-keychain fix:
  // a non-sandboxed Developer ID app has no keychain-access-groups entitlement, so the
  // data-protection keychain failed with errSecMissingEntitlement and blocked sign-in.
  // The correct invariant now lives in AuthTokenStorageTests.testKeychainStoreDoesNotUseDataProtectionKeychain.

  func testDesktopAutomationBridgeIsNonProductionAndAuthenticated() throws {
    let src = try source(relativePath: "Sources/DesktopAutomationBridge.swift")

    XCTAssertTrue(src.contains("guard AppBuild.isNonProduction else"))
    XCTAssertTrue(src.contains("OMI_AUTOMATION_TOKEN"))
    XCTAssertTrue(src.contains("writeTokenFileIfNeeded()"))
    XCTAssertTrue(src.contains("acceptsLoopbackHostAndOrigin"))
    XCTAssertTrue(src.contains("invalid_host_or_origin"))
    XCTAssertTrue(src.contains("authenticate(request.headers[\"authorization\"])"))
    XCTAssertTrue(src.contains("invalid_or_missing_automation_token"))
    XCTAssertTrue(src.contains("constantTimeEquals"))
    XCTAssertTrue(src.contains("authorization.lowercased().hasPrefix(\"bearer \")"))
    XCTAssertTrue(src.contains("DesktopAutomationHealth"))
    XCTAssertTrue(src.contains("requiresAuth: true"))
  }

  // MARK: Helper

  private func source(relativePath: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent(relativePath)
    return try String(contentsOf: url, encoding: .utf8)
  }
}
