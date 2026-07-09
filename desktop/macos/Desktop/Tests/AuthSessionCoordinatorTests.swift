import XCTest

@testable import Omi_Computer

final class AuthDefinitiveDeathClassifierTests: XCTestCase {
  func testDefinitiveRefreshCodes() {
    XCTAssertTrue(
      AuthDefinitiveDeathClassifier.isDefinitiveRefreshFailure(
        httpStatus: 400,
        errorBody: #"{"error":{"message":"INVALID_REFRESH_TOKEN"}}"#
      )
    )
    XCTAssertTrue(
      AuthDefinitiveDeathClassifier.isDefinitiveRefreshFailure(
        httpStatus: 400,
        errorBody: #"{"error":{"message":"USER_DISABLED"}}"#
      )
    )
    XCTAssertTrue(
      AuthDefinitiveDeathClassifier.isDefinitiveRefreshFailure(
        httpStatus: 400,
        errorBody: #"{"error":{"message":"USER_NOT_FOUND"}}"#
      )
    )
    XCTAssertTrue(
      AuthDefinitiveDeathClassifier.isDefinitiveRefreshFailure(
        httpStatus: 400,
        errorBody: #"{"error":{"message":"TOKEN_EXPIRED"}}"#
      )
    )
  }

  func testBlanketHTTP400IsNotDefinitive() {
    XCTAssertFalse(
      AuthDefinitiveDeathClassifier.isDefinitiveRefreshFailure(
        httpStatus: 400,
        errorBody: #"{"error":{"message":"API key not valid. Please pass a valid API key."}}"#
      )
    )
    XCTAssertFalse(
      AuthDefinitiveDeathClassifier.isDefinitiveRefreshFailure(
        httpStatus: 400,
        errorBody: "malformed"
      )
    )
  }

  func testTransient5xxIsNotDefinitive() {
    XCTAssertFalse(
      AuthDefinitiveDeathClassifier.isDefinitiveRefreshFailure(
        httpStatus: 503,
        errorBody: "Service Unavailable"
      )
    )
  }

  func testPostRefreshHTTP401() {
    XCTAssertTrue(AuthDefinitiveDeathClassifier.isPostRefreshHTTPUnauthorized(401))
    XCTAssertFalse(AuthDefinitiveDeathClassifier.isPostRefreshHTTPUnauthorized(403))
  }
}

@MainActor
final class AuthSessionCoordinatorTests: XCTestCase {
  func testInvalidateSessionIsLightVersusNuclearSignOut() throws {
    let coordinatorSource = try sourceFile("AuthSessionCoordinator.swift")
    let authSource = try sourceFile("AuthService.swift")

    XCTAssertTrue(coordinatorSource.contains("performLightSessionInvalidation"))
    XCTAssertTrue(coordinatorSource.contains("sessionDidInvalidate"))
    XCTAssertFalse(coordinatorSource.contains("stopTranscription"))
    XCTAssertFalse(coordinatorSource.contains("hasCompletedOnboarding"))

    XCTAssertTrue(authSource.contains("func invalidateSession(reason:"))
    XCTAssertTrue(authSource.contains("func performLightSessionInvalidation()"))
    XCTAssertTrue(authSource.contains("clearTokens()"))
    XCTAssertTrue(authSource.contains("saveAuthState(isSignedIn: false"))

    // Nuclear signOut still wipes onboarding — invalidate must not.
    let signOutRange = authSource.range(of: "func signOut() throws")
    XCTAssertNotNil(signOutRange)
    let signOutSnippet = String(authSource[signOutRange!.lowerBound...]).prefix(4000)
    XCTAssertTrue(signOutSnippet.contains("onboardingStep"))
    XCTAssertTrue(signOutSnippet.contains("userDidSignOut"))

    let invalidateRange = authSource.range(of: "func performLightSessionInvalidation()")
    XCTAssertNotNil(invalidateRange)
    let invalidateSnippet = String(authSource[invalidateRange!.lowerBound...]).prefix(500)
    XCTAssertFalse(invalidateSnippet.contains("onboardingStep"))
    XCTAssertFalse(invalidateSnippet.contains("userDidSignOut"))
    XCTAssertFalse(invalidateSnippet.contains("stopTranscription"))
  }

  func testChatProviderStopsBridgeOnSessionInvalidateWithoutFullReset() throws {
    let source = try sourceFile("Providers/ChatProvider.swift")
    XCTAssertTrue(source.contains("sessionDidInvalidate"))
    XCTAssertTrue(source.contains("sessionInvalidateObserver"))
    let invalidateBlock = source.range(of: "sessionDidInvalidate — stopping agent bridge")
    XCTAssertNotNil(invalidateBlock)
    let snippet = String(source[invalidateBlock!.lowerBound...]).prefix(400)
    XCTAssertFalse(snippet.contains("resetSessionStateForAuthChange"))
  }

  func testRefreshIdTokenUsesClassifierNotBlanket400() throws {
    let source = try sourceFile("AuthService.swift")
    XCTAssertTrue(source.contains("AuthDefinitiveDeathClassifier.isDefinitiveRefreshFailure"))
    let refreshRange = source.range(of: "private func refreshIdToken()")
    XCTAssertNotNil(refreshRange)
    let snippet = String(source[refreshRange!.lowerBound...]).prefix(2500)
    XCTAssertFalse(snippet.contains("httpResponse.statusCode == 400"))
    XCTAssertTrue(snippet.contains("invalidateSession(reason: .definitiveRefreshFailure)"))
  }

  func testRestoreValidationUsesRefreshSingleFlight() throws {
    let source = try sourceFile("AuthService.swift")
    let validationRange = source.range(of: "private func validateRestoredUserDefaultsSession()")
    XCTAssertNotNil(validationRange)
    let snippet = String(source[validationRange!.lowerBound...]).prefix(800)
    XCTAssertTrue(snippet.contains("refreshSingleFlight(auth: self)"))
    XCTAssertTrue(snippet.contains("defer { AuthState.shared.isRestoringAuth = false }"))
  }

  func testProactiveEnsureValidSessionOnBecomeActive() throws {
    let coordinator = try sourceFile("AuthSessionCoordinator.swift")
    XCTAssertTrue(coordinator.contains("ensureValidSessionDebounced"))
    XCTAssertTrue(coordinator.contains("minInterval: TimeInterval = 30"))
    let app = try sourceFile("OmiApp.swift")
    XCTAssertTrue(app.contains("ensureValidSessionDebounced"))
  }

  func testInvAuthInvariantDocExists() throws {
    let path = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("docs/product/invariants/auth-session.md")
    XCTAssertTrue(FileManager.default.fileExists(atPath: path.path))
    let text = try String(contentsOf: path, encoding: .utf8)
    XCTAssertTrue(text.contains("INV-AUTH-1"))
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let testFile = URL(fileURLWithPath: #filePath)
    let sourcesRoot = testFile.deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("Sources")
    let fileURL = sourcesRoot.appendingPathComponent(relativePath)
    return try String(contentsOf: fileURL, encoding: .utf8)
  }
}
