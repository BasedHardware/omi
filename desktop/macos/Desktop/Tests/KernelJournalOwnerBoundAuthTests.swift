import Foundation
import XCTest

@testable import Omi_Computer

private final class InitialGreetingOwnerURLStub: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private static var requestCount = 0

  static func reset() {
    lock.lock()
    requestCount = 0
    lock.unlock()
  }

  static var requests: Int {
    lock.lock()
    defer { lock.unlock() }
    return requestCount
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    Self.lock.lock()
    Self.requestCount += 1
    Self.lock.unlock()
    let body = Data(#"{"message":"Hello","message_id":"greeting-1"}"#.utf8)
    let response = HTTPURLResponse(
      url: request.url!,
      statusCode: 200,
      httpVersion: nil,
      headerFields: ["Content-Type": "application/json"]
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: body)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

@MainActor
final class KernelJournalOwnerBoundAuthTests: XCTestCase {
  override func setUp() {
    super.setUp()
    InitialGreetingOwnerURLStub.reset()
  }

  override func tearDown() {
    let auth = AuthService.shared
    auth.invalidateSession(reason: .manual)
    auth.tokenStorageHooks = .live
    auth.tokenRefreshHooks = .live
    UserDefaults.standard.removeObject(forKey: .authUserId)
    super.tearDown()
  }

  func testTokenOwnerExtractionAcceptsFirebaseUserIDAndSubject() throws {
    XCTAssertEqual(
      AuthService.tokenOwnerId(from: token(payload: ["user_id": "owner-a", "sub": "fallback"])),
      "owner-a"
    )
    XCTAssertEqual(
      AuthService.tokenOwnerId(from: token(payload: ["sub": "owner-b"])),
      "owner-b"
    )
  }

  func testTokenOwnerExtractionFailsClosedForMalformedOrUnownedTokens() throws {
    XCTAssertNil(AuthService.tokenOwnerId(from: "not-a-jwt"))
    XCTAssertNil(AuthService.tokenOwnerId(from: token(payload: ["aud": "omi"])))
    XCTAssertNil(AuthService.tokenOwnerId(from: token(payload: ["sub": "  "])))
  }

  func testInitialGreetingRejectsAccountSwitchBeforeHTTP() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [InitialGreetingOwnerURLStub.self]
    let client = APIClient(session: URLSession(configuration: configuration))
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
      idToken: token(payload: ["user_id": "owner-b"]),
      refreshToken: "refresh-owner-b",
      expiresIn: 3_600,
      userId: "owner-b"
    )
    UserDefaults.standard.set("owner-b", forKey: .authUserId)

    do {
      _ = try await client.getInitialMessage(
        sessionId: "owner-a-session",
        expectedOwnerId: "owner-a"
      )
      XCTFail("an owner-A greeting must not use owner-B credentials")
    } catch AuthError.userChangedDuringRequest {
      // Expected: the owner fence rejects before URLSession sees the request.
    } catch {
      XCTFail("unexpected error: \(error)")
    }

    XCTAssertEqual(InitialGreetingOwnerURLStub.requests, 0)
  }

  private func token(payload: [String: Any]) -> String {
    let data = try! JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    let encoded = data.base64EncodedString()
      .replacingOccurrences(of: "+", with: "-")
      .replacingOccurrences(of: "/", with: "_")
      .replacingOccurrences(of: "=", with: "")
    return "e30.\(encoded).signature"
  }
}
