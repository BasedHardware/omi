// Exercises the real delete transport against synthetic HTTP replies.
// Injected time keeps retry budgets deterministic without wall-clock waits.

import XCTest

@testable import Omi_Computer

/// Returns a caller-chosen status for every request so a delete can be driven
/// against each backend answer it actually receives.
private final class ConversationDeleteStatusStub: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var _statuses = [204]
  private nonisolated(unsafe) static var _observed: [(method: String, path: String)] = []

  static var statuses: [Int] {
    get {
      lock.lock()
      defer { lock.unlock() }
      return _statuses
    }
    set {
      lock.lock()
      _statuses = newValue
      lock.unlock()
    }
  }

  static var observed: [(method: String, path: String)] {
    lock.lock()
    defer { lock.unlock() }
    return _observed
  }

  static func reset() {
    lock.lock()
    _statuses = [204]
    _observed = []
    lock.unlock()
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    Self.lock.lock()
    Self._observed.append((request.httpMethod ?? "GET", request.url?.path ?? ""))
    let status = Self._statuses.count > 1 ? Self._statuses.removeFirst() : Self._statuses[0]
    Self.lock.unlock()

    var headerFields = [
      "Content-Type": "application/json",
      "X-Omi-Delete-Outcome": request.url?.lastPathComponent == "gone" ? "already_deleted" : "tombstoned",
    ]
    var payload = Data("{\"status\":\"ok\"}".utf8)
    if status == 404 {
      payload = Data("{\"detail\":\"Conversation not found\"}".utf8)
    } else if status == 409 {
      // Mirrors `account_gate_busy_http_exception`: 409 account_gate_busy
      // plus a Retry-After header.
      headerFields["Retry-After"] = "2"
      payload = Data("{\"detail\":\"account_gate_busy\"}".utf8)
    }
    guard
      let url = request.url,
      let response = HTTPURLResponse(
        url: url,
        statusCode: status,
        httpVersion: nil,
        headerFields: headerFields
      )
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
      return
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: payload)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

final class APIClientConversationDeleteTests: XCTestCase {
  override func setUp() {
    super.setUp()
    ConversationDeleteStatusStub.reset()
    setenv("OMI_PYTHON_API_URL", "http://conversation-delete-test:9001", 1)
  }

  override func tearDown() {
    unsetenv("OMI_PYTHON_API_URL")
    ConversationDeleteStatusStub.reset()
    super.tearDown()
  }

  private func makeClient() async -> APIClient {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [ConversationDeleteStatusStub.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")
    return client
  }

  func testSuccessPreservesAlreadyDeletedHeader() async throws {
    let client = await makeClient()
    let outcome = try await client.deleteConversation(id: "gone")
    XCTAssertEqual(outcome, .alreadyDeleted)
    XCTAssertEqual(ConversationDeleteStatusStub.observed.first?.method, "DELETE")
    XCTAssertEqual(ConversationDeleteStatusStub.observed.first?.path, "/v1/conversations/gone")
  }

  func test204DeletesNormally() async throws {
    let client = await makeClient()
    let outcome = try await client.deleteConversation(id: "live")
    XCTAssertEqual(outcome, .deleted)
  }

  func test404IsAlreadyDeletedSuccess() async throws {
    let client = await makeClient()
    ConversationDeleteStatusStub.statuses = [404]
    let outcome = try await client.deleteConversation(id: "gone")
    XCTAssertEqual(outcome, .alreadyDeleted)
  }

  func testBusyThenSuccessRetriesUsingRetryAfter() async throws {
    let client = await makeClient()
    ConversationDeleteStatusStub.statuses = [409, 204]
    let clock = DeleteTestClock()
    let outcome = try await client.deleteConversation(id: "busy", now: { clock.now }, wait: { clock.advance($0) })
    XCTAssertTrue(outcome.succeeded)
    XCTAssertEqual(clock.delays, [2])
    XCTAssertEqual(ConversationDeleteStatusStub.observed.count, 2)
  }

  func test503ThenSuccessRetries() async throws {
    let client = await makeClient()
    ConversationDeleteStatusStub.statuses = [503, 204]
    let clock = DeleteTestClock()
    let outcome = try await client.deleteConversation(id: "busy", now: { clock.now }, wait: { clock.advance($0) })
    XCTAssertTrue(outcome.succeeded)
    XCTAssertEqual(clock.delays, [2])
  }

  func testBusyStopsAtBudgetAndRetainsRetryAfter() async throws {
    let client = await makeClient()
    ConversationDeleteStatusStub.statuses = [409]
    let clock = DeleteTestClock()
    let outcome = try await client.deleteConversation(id: "busy", now: { clock.now }, wait: { clock.advance($0) })
    XCTAssertEqual(outcome, .busy(retryAfter: 2))
    XCTAssertLessThan(clock.now.timeIntervalSince1970, 30)
    XCTAssertEqual(ConversationDeleteStatusStub.observed.count, 15)
  }

  func testHardFailureDoesNotRetryOrSucceed() async throws {
    let client = await makeClient()
    ConversationDeleteStatusStub.statuses = [500]
    do {
      _ = try await client.deleteConversation(id: "failed")
      XCTFail("Hard failure must reach the caller")
    } catch APIError.httpError(let status, _) {
      XCTAssertEqual(status, 500)
    }
    XCTAssertEqual(ConversationDeleteStatusStub.observed.count, 1)
  }

  func testRetryAfterDateAndClamping() throws {
    let now = Date(timeIntervalSince1970: 0)
    let cases: [(String, TimeInterval)] = [
      ("Thu, 01 Jan 1970 00:00:05 GMT", 5), ("0", 1), ("999", 10), ("bad", 2),
    ]
    for (raw, expected) in cases {
      let response = try XCTUnwrap(
        HTTPURLResponse(
          url: URL(string: "http://test/delete")!, statusCode: 409, httpVersion: nil,
          headerFields: ["Retry-After": raw]))
      XCTAssertEqual(APIClient.conversationDeleteRetryDelay(response, now: now), expected)
    }
  }
}

private final class DeleteTestClock: @unchecked Sendable {
  var now = Date(timeIntervalSince1970: 0)
  var delays: [TimeInterval] = []
  func advance(_ seconds: TimeInterval) {
    delays.append(seconds)
    now = now.addingTimeInterval(seconds)
  }
}
