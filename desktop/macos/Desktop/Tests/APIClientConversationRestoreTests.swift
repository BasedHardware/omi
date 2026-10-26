import XCTest

@testable import Omi_Computer

private final class RestoreConversationURLStub: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var captured: [URLRequest] = []

  static var requests: [URLRequest] {
    lock.lock()
    defer { lock.unlock() }
    return captured
  }

  static func reset() {
    lock.lock()
    captured = []
    lock.unlock()
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    Self.lock.lock()
    Self.captured.append(request)
    Self.lock.unlock()
    let payload =
      request.url?.path.hasSuffix("/count") == true
      ? #"{"count":1}"#
      : #"{"id":"restore-fixture","created_at":"2026-10-26T05:00:00Z","structured":{"title":"Restored conversation","overview":"Restored notes","emoji":"","category":"other","action_items":[],"events":[]},"status":"completed","source":"desktop","discarded":false,"deleted":false}"#
    guard
      let url = request.url,
      let response = HTTPURLResponse(
        url: url, statusCode: 200, httpVersion: nil,
        headerFields: ["Content-Type": "application/json"])
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.badURL))
      return
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(payload.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

final class APIClientConversationRestoreTests: XCTestCase {
  override func setUp() {
    super.setUp()
    RestoreConversationURLStub.reset()
    setenv("OMI_PYTHON_API_URL", "http://restore-test.invalid:9001", 1)
  }

  override func tearDown() {
    unsetenv("OMI_PYTHON_API_URL")
    RestoreConversationURLStub.reset()
    super.tearDown()
  }

  func testRestoreUsesPhoneReprocessEndpointAndInvalidatesCounts() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [RestoreConversationURLStub.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer synthetic-token")
    _ = try await client.getConversationsCount()
    _ = try await client.getConversationsCount()
    let restored = try await client.restoreConversation(conversationId: "restore-fixture")
    XCTAssertFalse(restored.discarded)
    XCTAssertEqual(restored.title, "Restored conversation")
    _ = try await client.getConversationsCount()
    let requests = RestoreConversationURLStub.requests
    XCTAssertEqual(requests.map { $0.httpMethod }, ["GET", "POST", "GET"])
    XCTAssertEqual(requests[1].url?.path, "/v1/conversations/restore-fixture/reprocess")
    XCTAssertNil(requests[1].url?.query)
    XCTAssertEqual(requests[1].timeoutInterval, 180)
    // user_kept is derived by the endpoint from the stored discard/keep state,
    // exactly as on phone; there is no new client-selected classification.
    XCTAssertEqual(requests[1].value(forHTTPHeaderField: "Authorization"), "Bearer synthetic-token")
  }

  func testDetailExplicitlyRequestsRetainedDiscardedConversation() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [RestoreConversationURLStub.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer synthetic-token")
    _ = try await client.getConversation(id: "restore-fixture", includeDiscarded: true)
    let requestURL = RestoreConversationURLStub.requests.first?.url
    XCTAssertEqual(requestURL?.path, "/v1/conversations/restore-fixture")
    XCTAssertEqual(requestURL?.query, "include_discarded=true")
  }
}
