import XCTest

@testable import Omi_Computer

private struct CapturedCreateRequest {
  let url: URL
  let method: String
  let headers: [String: String]
}

private final class ActionItemCreateURLCapture: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var request: CapturedCreateRequest?

  static func reset() {
    lock.lock()
    request = nil
    lock.unlock()
  }

  static func captured() -> CapturedCreateRequest? {
    lock.lock()
    defer { lock.unlock() }
    return request
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    guard let url = request.url else {
      client?.urlProtocol(self, didFailWithError: URLError(.badURL))
      return
    }
    Self.lock.lock()
    Self.request = CapturedCreateRequest(
      url: url,
      method: request.httpMethod ?? "GET",
      headers: request.allHTTPHeaderFields ?? [:]
    )
    Self.lock.unlock()

    let body = Data(
      #"{"id":"task-1","description":"Buy milk","completed":false,"created_at":"2026-01-01T00:00:00.000Z","updated_at":"2026-01-01T00:00:00.000Z"}"#
        .utf8)
    guard
      let response = HTTPURLResponse(
        url: url, statusCode: 200, httpVersion: nil, headerFields: nil)
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
      return
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: body)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

final class ActionItemCreateIdempotencyTests: XCTestCase {
  override func setUp() {
    super.setUp()
    ActionItemCreateURLCapture.reset()
    setenv("OMI_PYTHON_API_URL", "http://python-test:9001", 1)
  }

  override func tearDown() {
    unsetenv("OMI_PYTHON_API_URL")
    ActionItemCreateURLCapture.reset()
    super.tearDown()
  }

  func testCreateActionItemAlwaysSendsIdempotencyKey() async throws {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [ActionItemCreateURLCapture.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")

    _ = try await client.createActionItem(description: "Buy milk")

    let request = try XCTUnwrap(ActionItemCreateURLCapture.captured())
    XCTAssertEqual(request.method, "POST")
    XCTAssertTrue(request.url.path.hasSuffix("/v1/action-items"))
    let key = try XCTUnwrap(request.headers["Idempotency-Key"])
    XCTAssertFalse(key.isEmpty)
  }

  func testCreateActionItemReusesCallerProvidedKey() async throws {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [ActionItemCreateURLCapture.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")

    _ = try await client.createActionItem(
      description: "Buy milk",
      idempotencyKey: "desktop-action-item:42"
    )

    let request = try XCTUnwrap(ActionItemCreateURLCapture.captured())
    XCTAssertEqual(request.headers["Idempotency-Key"], "desktop-action-item:42")
  }

  func testLocalRowIdempotencyKeyIsStableAcrossRetries() {
    let first = TasksStore.actionItemCreateIdempotencyKey(localRowID: 17)
    let second = TasksStore.actionItemCreateIdempotencyKey(localRowID: 17)
    XCTAssertEqual(first, second)
    XCTAssertEqual(first, "desktop-action-item:17")
    XCTAssertNotEqual(
      TasksStore.actionItemCreateIdempotencyKey(localRowID: 17),
      TasksStore.actionItemCreateIdempotencyKey(localRowID: 18))
  }
}
