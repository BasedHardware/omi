import XCTest

@testable import Omi_Computer

private final class AuthRetryURLStub: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private static var deleteAttempts = 0
  private static var alwaysUnauthorized = false
  private static var forcedStatus: Int?
  private static var forcedBody = Data()

  static func reset() {
    lock.lock()
    deleteAttempts = 0
    alwaysUnauthorized = false
    forcedStatus = nil
    forcedBody = Data()
    lock.unlock()
  }

  static func returnUnauthorizedForEveryAttempt(body: String = "") {
    lock.lock()
    alwaysUnauthorized = true
    forcedBody = Data(body.utf8)
    lock.unlock()
  }

  static func returnStatus(_ status: Int, body: String = "") {
    lock.lock()
    forcedStatus = status
    forcedBody = Data(body.utf8)
    lock.unlock()
  }

  static var attempts: Int {
    lock.lock()
    defer { lock.unlock() }
    return deleteAttempts
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    Self.lock.lock()
    Self.deleteAttempts += 1
    let attempt = Self.deleteAttempts
    let status = Self.forcedStatus ?? (Self.alwaysUnauthorized || attempt == 1 ? 401 : 204)
    let body = Self.forcedBody
    Self.lock.unlock()

    let response = HTTPURLResponse(
      url: request.url!,
      statusCode: status,
      httpVersion: nil,
      headerFields: nil
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: body)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

@MainActor
final class APIClientAuthRetryTests: XCTestCase {
  override func setUp() {
    super.setUp()
    AuthRetryURLStub.reset()
    DesktopDiagnosticsManager.shared.resetForTests()
  }

  override func tearDown() {
    DesktopDiagnosticsManager.shared.resetForTests()
    let auth = AuthService.shared
    auth.invalidateSession(reason: .manual)
    auth.tokenStorageHooks = .live
    auth.tokenRefreshHooks = .live
    UserDefaults.standard.removeObject(forKey: .authUserId)
    super.tearDown()
  }

  func testDeleteRetriesOnceAfter401() async throws {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [AuthRetryURLStub.self]
    let client = APIClient(session: URLSession(configuration: config))

    let auth = await MainActor.run { AuthService.shared }
    auth.tokenStorageHooks = AuthService.TokenStorageHooks(
      usesKeychainTokenStorage: { false },
      allowsUserDefaultsFallback: { true },
      readKeychainString: { _, _ in nil },
      writeKeychainString: { _, _, _ in true },
      deleteKeychainString: { _, _ in },
      recordsFallbackTelemetry: false
    )
    try auth.saveTokens(
      idToken: "id-token",
      refreshToken: "refresh-token",
      expiresIn: 3600,
      userId: "user-1"
    )
    UserDefaults.standard.set("user-1", forKey: .authUserId)

    auth.tokenRefreshHooks = AuthService.TokenRefreshHooks(
      dataForRequest: { _ in
        let body = Data("{\"id_token\":\"new-id\",\"refresh_token\":\"new-refresh\",\"expires_in\":\"3600\",\"user_id\":\"user-1\"}".utf8)
        let response = HTTPURLResponse(
          url: URL(string: "https://securetoken.googleapis.com/v1/token")!,
          statusCode: 200,
          httpVersion: nil,
          headerFields: nil
        )!
        return (body, response)
      }
    )

    setenv("FIREBASE_API_KEY", "test-key", 1)
    defer { unsetenv("FIREBASE_API_KEY") }

    try await client.delete("v1/test-delete")

    XCTAssertEqual(AuthRetryURLStub.attempts, 2)

    let snapshot = try latestHealthSnapshot()
    XCTAssertEqual(snapshot["event"] as? String, "fallback_triggered")
    XCTAssertEqual(snapshot["area"] as? String, "api_auth")
    XCTAssertEqual(snapshot["outcome"] as? String, "recovered")
    XCTAssertEqual(snapshot["retry_outcome"] as? String, "succeeded")
  }

  func testTTSProvider401RetriesWithoutInvalidatingFirebaseSession() async throws {
    AuthRetryURLStub.returnUnauthorizedForEveryAttempt(
      body: "{\"error\":\"OpenAI TTS request failed: Incorrect API key provided\"}"
    )
    setenv("OMI_DESKTOP_API_URL", "http://rust-test:9002", 1)
    setenv("FIREBASE_API_KEY", "test-key", 1)
    defer {
      unsetenv("OMI_DESKTOP_API_URL")
      unsetenv("FIREBASE_API_KEY")
    }

    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [AuthRetryURLStub.self]
    let client = APIClient(session: URLSession(configuration: config))

    let auth = AuthService.shared
    auth.tokenStorageHooks = AuthService.TokenStorageHooks(
      usesKeychainTokenStorage: { false },
      allowsUserDefaultsFallback: { true },
      readKeychainString: { _, _ in nil },
      writeKeychainString: { _, _, _ in true },
      deleteKeychainString: { _, _ in },
      recordsFallbackTelemetry: false
    )
    try auth.saveTokens(
      idToken: "id-token",
      refreshToken: "refresh-token",
      expiresIn: 3600,
      userId: "user-1"
    )
    UserDefaults.standard.set("user-1", forKey: .authUserId)
    auth.tokenRefreshHooks = AuthService.TokenRefreshHooks(
      dataForRequest: { _ in
        let body = Data(
          "{\"id_token\":\"new-id\",\"refresh_token\":\"new-refresh\",\"expires_in\":\"3600\",\"user_id\":\"user-1\"}".utf8)
        let response = HTTPURLResponse(
          url: URL(string: "https://securetoken.googleapis.com/v1/token")!,
          statusCode: 200,
          httpVersion: nil,
          headerFields: nil
        )!
        return (body, response)
      }
    )

    do {
      _ = try await client.synthesizeSpeech(
        request: APIClient.TtsSynthesizeRequest(
          text: "Hello",
          voiceId: "onyx",
          instructions: nil
        )
      )
      XCTFail("Expected provider authorization failure")
    } catch let error as CredentialHealthError {
      XCTAssertEqual(
        error.failureClass,
        .providerAuthFailed(provider: .openai, mode: .managed)
      )
    }

    XCTAssertEqual(AuthRetryURLStub.attempts, 2)
    XCTAssertEqual(UserDefaults.standard.string(forKey: .authUserId), "user-1")
    let retainedToken = try await auth.getIdToken()
    XCTAssertEqual(retainedToken, "new-id")
    XCTAssertFalse(try healthSnapshots().contains { $0["area"] as? String == "api_auth" })
  }

  func testTTSBare401DoesNotRemapToProviderAuth() async throws {
    AuthRetryURLStub.returnUnauthorizedForEveryAttempt(body: "{\"error\":\"Unauthorized\"}")
    setenv("OMI_DESKTOP_API_URL", "http://rust-test:9002", 1)
    setenv("FIREBASE_API_KEY", "test-key", 1)
    defer {
      unsetenv("OMI_DESKTOP_API_URL")
      unsetenv("FIREBASE_API_KEY")
    }

    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [AuthRetryURLStub.self]
    let client = APIClient(session: URLSession(configuration: config))

    let auth = AuthService.shared
    auth.tokenStorageHooks = AuthService.TokenStorageHooks(
      usesKeychainTokenStorage: { false },
      allowsUserDefaultsFallback: { true },
      readKeychainString: { _, _ in nil },
      writeKeychainString: { _, _, _ in true },
      deleteKeychainString: { _, _ in },
      recordsFallbackTelemetry: false
    )
    try auth.saveTokens(
      idToken: "id-token",
      refreshToken: "refresh-token",
      expiresIn: 3600,
      userId: "user-1"
    )
    UserDefaults.standard.set("user-1", forKey: .authUserId)
    auth.tokenRefreshHooks = AuthService.TokenRefreshHooks(
      dataForRequest: { _ in
        let body = Data(
          "{\"id_token\":\"new-id\",\"refresh_token\":\"new-refresh\",\"expires_in\":\"3600\",\"user_id\":\"user-1\"}".utf8)
        let response = HTTPURLResponse(
          url: URL(string: "https://securetoken.googleapis.com/v1/token")!,
          statusCode: 200,
          httpVersion: nil,
          headerFields: nil
        )!
        return (body, response)
      }
    )

    do {
      _ = try await client.synthesizeSpeech(
        request: APIClient.TtsSynthesizeRequest(
          text: "Hello",
          voiceId: "onyx",
          instructions: nil
        )
      )
      XCTFail("Expected unauthorized failure")
    } catch APIError.unauthorized {
      // Bare/Firebase-shaped 401 must not become providerAuth (BYOK poison).
    } catch {
      XCTFail("Unexpected error: \(error)")
    }

    XCTAssertEqual(AuthRetryURLStub.attempts, 2)
    XCTAssertNil(UserDefaults.standard.string(forKey: .authUserId))
  }

  func testTTSProvider429ReturnsTypedQuotaFailure() async throws {
    AuthRetryURLStub.returnStatus(
      429,
      body: "{\"error\":\"OpenAI TTS request failed: upstream quota exhausted\"}"
    )
    setenv("OMI_DESKTOP_API_URL", "http://rust-test:9002", 1)
    defer { unsetenv("OMI_DESKTOP_API_URL") }

    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [AuthRetryURLStub.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")

    do {
      _ = try await client.synthesizeSpeech(
        request: APIClient.TtsSynthesizeRequest(text: "Hello", voiceId: "onyx", instructions: nil)
      )
      XCTFail("Expected provider quota failure")
    } catch let error as CredentialHealthError {
      XCTAssertEqual(error.failureClass, .providerQuotaExceeded(provider: .openai))
    }

    XCTAssertEqual(AuthRetryURLStub.attempts, 1)
  }

  func testTTSLocal429RemainsBackendRateLimitFailure() async throws {
    AuthRetryURLStub.returnStatus(429, body: "{\"error\":\"TTS burst rate limit exceeded\"}")
    setenv("OMI_DESKTOP_API_URL", "http://rust-test:9002", 1)
    defer { unsetenv("OMI_DESKTOP_API_URL") }

    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [AuthRetryURLStub.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")

    do {
      _ = try await client.synthesizeSpeech(
        request: APIClient.TtsSynthesizeRequest(text: "Hello", voiceId: "onyx", instructions: nil)
      )
      XCTFail("Expected local rate-limit failure")
    } catch APIError.httpError(let statusCode, let detail) {
      XCTAssertEqual(statusCode, 429)
      XCTAssertEqual(detail, "TTS burst rate limit exceeded")
    }

    XCTAssertEqual(AuthRetryURLStub.attempts, 1)
  }

  private func latestHealthSnapshot() throws -> [String: Any] {
    try XCTUnwrap(healthSnapshots().last)
  }

  private func healthSnapshots() throws -> [[String: Any]] {
    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }
    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    return try XCTUnwrap(root["snapshots"] as? [[String: Any]])
  }
}
