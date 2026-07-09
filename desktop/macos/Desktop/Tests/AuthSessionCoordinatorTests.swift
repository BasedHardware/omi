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

  func testRefreshSingleFlightAPIExistsOnCoordinator() {
    // Behavioral single-flight concurrency test lands in commit 2 when refreshIdToken
    // is wired through the coordinator. Here we only assert the API surface exists.
    XCTAssertNotNil(AuthSessionCoordinator.shared)
    _ = AuthSessionCoordinator.shared.refreshSingleFlight
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let testFile = URL(fileURLWithPath: #filePath)
    let sourcesRoot = testFile.deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("Sources")
    let fileURL = sourcesRoot.appendingPathComponent(relativePath)
    return try String(contentsOf: fileURL, encoding: .utf8)
  }
}
