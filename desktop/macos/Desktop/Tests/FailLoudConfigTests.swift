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

  // MARK: BL-020 — checkSystemAudioPermission() must report the real state

  /// The check is no longer a no-op: it must derive `hasSystemAudioPermission`
  /// from the real screen-recording TCC preflight the rest of the app uses,
  /// mirroring `checkScreenRecordingPermission()`.
  func testCheckSystemAudioPermissionReadsRealTccState() throws {
    let src = try source(relativePath: "Sources/AppState/AppState+SystemActions.swift")

    guard let range = src.range(of: "func checkSystemAudioPermission() {") else {
      return XCTFail("checkSystemAudioPermission not found")
    }
    let body = String(src[range.lowerBound...].prefix(600))

    XCTAssertFalse(
      body.contains("No-op"),
      "checkSystemAudioPermission must no longer be a no-op")
    XCTAssertTrue(
      body.contains("hasSystemAudioPermission ="),
      "it must actually assign the reported permission state")
    XCTAssertTrue(
      body.contains("ScreenCaptureService.checkPermission()"),
      "it must query the real TCC preflight the rest of the app relies on")
  }

  func testProductionAuthTokensUseKeychainStorage() throws {
    let src = try source(relativePath: "Sources/AuthService.swift")

    XCTAssertTrue(src.contains("private var usesKeychainTokenStorage: Bool"))
    XCTAssertTrue(src.contains("!AppBuild.isNonProduction"))
    XCTAssertTrue(src.contains("DesktopKeychainStore.setString("))
    XCTAssertTrue(src.contains("migrated production auth tokens from UserDefaults to Keychain"))
    XCTAssertTrue(src.contains("clearUserDefaultsTokens()"))
    XCTAssertTrue(src.contains("allowsUserDefaultsTokenFallback"))
    XCTAssertTrue(src.contains("AuthService: Keychain token storage failed; falling back to UserDefaults for desktop auth continuity"))
    XCTAssertTrue(src.contains("\"update_channel\": AppBuild.currentUpdateChannel"))
    XCTAssertTrue(src.contains("failed to migrate production auth tokens from UserDefaults to Keychain"))
    XCTAssertTrue(src.contains("cachedStoredTokens"))
  }

  func testLocalAgentTokenUsesKeychainStorage() throws {
    let src = try source(relativePath: "Sources/LocalAgentAPIServer.swift")

    XCTAssertTrue(src.contains("tokenKeychainService"))
    XCTAssertTrue(src.contains("DesktopKeychainStore.string(service: tokenKeychainService"))
    XCTAssertTrue(src.contains("DesktopKeychainStore.setString(token, service: tokenKeychainService"))
    XCTAssertTrue(src.contains("enum LocalAgentAPIError"))
    XCTAssertTrue(src.contains("throw LocalAgentAPIError.tokenStorageUnavailable"))
    XCTAssertFalse(src.contains("UserDefaults.standard.set(token, forKey: tokenKey)"))
  }

  func testDesktopKeychainStoreUsesDataProtectionKeychain() throws {
    let src = try source(relativePath: "Sources/DesktopKeychainStore.swift")

    XCTAssertTrue(src.contains("kSecUseDataProtectionKeychain"))
    XCTAssertTrue(src.contains("useDataProtectionKeychain: true"))
  }

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
