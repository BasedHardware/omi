import XCTest

@testable import Omi_Computer

#if DEBUG
  // omi-release-compile: this suite drives DEBUG-only test seams; the release-mode
  // notification regression step must compile the bundle without them.

  @MainActor
  final class AuthRefreshResilienceTests: XCTestCase {
    private var priorFirebaseApiKey: String?

    override func setUp() async throws {
      clearAuthDefaults()
      DesktopDiagnosticsManager.shared.resetForTests()
      priorFirebaseApiKey = getenv("FIREBASE_API_KEY").flatMap { String(validatingCString: $0) }
      setenv("FIREBASE_API_KEY", "test-firebase-api-key", 1)
    }

    override func tearDown() async throws {
      if let priorFirebaseApiKey {
        setenv("FIREBASE_API_KEY", priorFirebaseApiKey, 1)
      } else {
        unsetenv("FIREBASE_API_KEY")
      }
      clearAuthDefaults()
      DesktopDiagnosticsManager.shared.resetForTests()
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

    /// AUTH-04: a refresh that fails at the NETWORK layer (offline, dead port, DNS —
    /// the "point securetoken at a dead proxy port" class) must never sign the user
    /// out. The URLError is thrown by the transport before any HTTP status exists, so
    /// it can never be classified as a definitive auth failure; the session must
    /// survive for the 30s refresh timer to retry. Exercises the real
    /// `refreshIdToken()` path via `tokenRefreshHooks` — the same seam a live
    /// dead-port run would hit, without the local-profile storage-identity switch
    /// that blocked the runtime rig (Wave 9).
    func testRefreshNetworkErrorPreservesTokens() async {
      let auth = makeAuthWithUserDefaultsStorage()
      XCTAssertNoThrow(
        try auth.saveTokens(
          idToken: "id-token-net",
          refreshToken: "refresh-token-net",
          expiresIn: 3600,
          userId: "user-net"
        )
      )
      UserDefaults.standard.set("user-net", forKey: .authUserId)

      auth.tokenRefreshHooks = AuthService.TokenRefreshHooks(
        dataForRequest: { _ in
          throw URLError(.cannotConnectToHost)
        }
      )

      do {
        _ = try await auth.getIdToken(forceRefresh: true)
        XCTFail("expected the network error to propagate")
      } catch let error as URLError {
        XCTAssertEqual(error.code, .cannotConnectToHost)
      } catch let error as AuthError {
        // Whatever the wrapper, it must NOT be the signed-out terminal state.
        if case .notSignedIn = error {
          XCTFail("a transient network failure must not sign the user out")
        }
      } catch {
        // Other wrappers are acceptable as long as the session survives (below).
      }

      XCTAssertEqual(
        UserDefaults.standard.string(forKey: .authIdToken), "id-token-net",
        "id token must survive a network-layer refresh failure")
      XCTAssertEqual(
        UserDefaults.standard.string(forKey: .authRefreshToken), "refresh-token-net",
        "refresh token must survive a network-layer refresh failure")
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
#endif
