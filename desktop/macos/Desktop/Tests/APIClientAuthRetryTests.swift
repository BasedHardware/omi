import XCTest

@testable import Omi_Computer

private final class AuthRetryURLStub: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private static var deleteAttempts = 0
  private static var responseStatus = 401

  static func reset() {
    lock.lock()
    deleteAttempts = 0
    responseStatus = 401
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
    let status = attempt == 1 ? 401 : 204
    Self.lock.unlock()

    let response = HTTPURLResponse(
      url: request.url!,
      statusCode: status,
      httpVersion: nil,
      headerFields: nil
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data())
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

  private func latestHealthSnapshot() throws -> [String: Any] {
    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }
    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
    return try XCTUnwrap(snapshots.last)
  }
}
