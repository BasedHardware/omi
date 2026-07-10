import XCTest

@testable import Omi_Computer

@MainActor
final class AuthRefreshResilienceTests: XCTestCase {
  private var priorFirebaseApiKey: String?

  override func setUp() {
    super.setUp()
    clearAuthDefaults()
    DesktopDiagnosticsManager.shared.resetForTests()
    priorFirebaseApiKey = getenv("FIREBASE_API_KEY").flatMap { String(validatingUTF8: $0) }
    setenv("FIREBASE_API_KEY", "test-firebase-api-key", 1)
  }

  override func tearDown() {
    if let priorFirebaseApiKey {
      setenv("FIREBASE_API_KEY", priorFirebaseApiKey, 1)
    } else {
      unsetenv("FIREBASE_API_KEY")
    }
    clearAuthDefaults()
    DesktopDiagnosticsManager.shared.resetForTests()
    super.tearDown()
  }

  func testRefresh400WithNonAuthBodyPreservesTokens() async {
    let auth = makeAuthWithUserDefaultsStorage()
    XCTAssertNoThrow(
      try auth.saveTokens(
        idToken: "id-token-stable",
        refreshToken: "refresh-token-stable",
        expiresIn: 3600,
        userId: "user-stable"
      )
    )
    UserDefaults.standard.set("user-stable", forKey: .authUserId)

    auth.tokenRefreshHooks = AuthService.TokenRefreshHooks(
      dataForRequest: { _ in
        let body = Data("{\"error\":\"backend unavailable\"}".utf8)
        let response = HTTPURLResponse(
          url: URL(string: "https://securetoken.googleapis.com/v1/token")!,
          statusCode: 400,
          httpVersion: nil,
          headerFields: nil
        )!
        return (body, response)
      }
    )

    do {
      _ = try await auth.getIdToken(forceRefresh: true)
      XCTFail("expected tokenExchangeFailed")
    } catch let error as AuthError {
      guard case .tokenExchangeFailed(400) = error else {
        return XCTFail("expected tokenExchangeFailed(400), got \(error)")
      }
    } catch {
      XCTFail("unexpected error \(error)")
    }

    XCTAssertEqual(UserDefaults.standard.string(forKey: .authIdToken), "id-token-stable")
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authRefreshToken), "refresh-token-stable")
  }

  func testRefresh400WithInvalidRefreshTokenClearsSessionAndRecordsHealth() async throws {
    let auth = makeAuthWithUserDefaultsStorage()
    XCTAssertNoThrow(
      try auth.saveTokens(
        idToken: "id-token-stable",
        refreshToken: "refresh-token-stable",
        expiresIn: 3600,
        userId: "user-stable"
      )
    )
    UserDefaults.standard.set("user-stable", forKey: .authUserId)

    auth.tokenRefreshHooks = AuthService.TokenRefreshHooks(
      dataForRequest: { _ in
        let body = Data("{\"error\":{\"message\":\"INVALID_REFRESH_TOKEN\"}}".utf8)
        let response = HTTPURLResponse(
          url: URL(string: "https://securetoken.googleapis.com/v1/token")!,
          statusCode: 400,
          httpVersion: nil,
          headerFields: nil
        )!
        return (body, response)
      }
    )

    do {
      _ = try await auth.getIdToken(forceRefresh: true)
      XCTFail("expected notSignedIn")
    } catch let error as AuthError {
      guard case .notSignedIn = error else {
        return XCTFail("expected notSignedIn, got \(error)")
      }
    } catch {
      XCTFail("unexpected error \(error)")
    }

    XCTAssertNil(UserDefaults.standard.string(forKey: .authIdToken))
    XCTAssertNil(UserDefaults.standard.string(forKey: .authRefreshToken))

    let snapshot = try latestHealthSnapshot()
    XCTAssertEqual(snapshot["event"] as? String, "auth_session_cleared")
    XCTAssertEqual(snapshot["reason"] as? String, "refresh_token_rejected")
    XCTAssertEqual(snapshot["failure_class"] as? String, "definitive_auth_failure")
    XCTAssertEqual(snapshot["http_status_code"] as? Int, 400)
  }

  func testTranscriptionReconnectUsesForceRefreshWhenRetrying() throws {
    let source = try sourceFile("TranscriptionService.swift")
    XCTAssertTrue(
      source.contains("getAuthHeader(forceRefresh: self.reconnectAttempts > 0)"),
      "WS reconnect must force-refresh auth after the first attempt")
  }

  private func makeAuthWithUserDefaultsStorage() -> AuthService {
    let auth = AuthService()
    auth.tokenStorageHooks = AuthService.TokenStorageHooks(
      usesKeychainTokenStorage: { true },
      allowsUserDefaultsFallback: { true },
      readKeychainString: { _, _ in nil },
      writeKeychainString: { _, _, _ in false },
      deleteKeychainString: { _, _ in },
      recordsFallbackTelemetry: false
    )
    return auth
  }

  private func latestHealthSnapshot() throws -> [String: Any] {
    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }
    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
    return try XCTUnwrap(snapshots.last)
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func clearAuthDefaults() {
    UserDefaults.standard.removeObject(forKey: .authIdToken)
    UserDefaults.standard.removeObject(forKey: .authRefreshToken)
    UserDefaults.standard.removeObject(forKey: .authTokenExpiry)
    UserDefaults.standard.removeObject(forKey: .authTokenUserId)
    UserDefaults.standard.removeObject(forKey: .authUserId)
  }
}
