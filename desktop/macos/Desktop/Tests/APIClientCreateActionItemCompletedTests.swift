import XCTest

@testable import Omi_Computer

/// `retryUnsyncedItems` used to create the backend row with `completed: nil`, then push
/// completion via a separate `try?` PATCH. If that PATCH failed (network blip), the local
/// row was still marked fully synced — since `markSynced` sets `backendSynced = true`, the
/// item is never revisited by the retry loop — permanently stranding the backend row as
/// incomplete and resurrecting an already-completed task on the next hydration. Passing
/// `completed` straight through the create call removes the extra fallible round trip.
private struct CapturedCreateActionItemRequest {
  let url: URL
  let method: String
  let body: Data?
}

private final class CreateActionItemURLProtocol: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var requests: [CapturedCreateActionItemRequest] = []

  static func reset() {
    lock.withLock { requests.removeAll() }
  }

  static var capturedRequests: [CapturedCreateActionItemRequest] {
    lock.withLock { requests }
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    guard let url = request.url else {
      client?.urlProtocol(self, didFailWithError: URLError(.badURL))
      return
    }
    let captured = CapturedCreateActionItemRequest(
      url: url,
      method: request.httpMethod ?? "GET",
      body: Self.bodyData(from: request)
    )
    Self.lock.withLock { Self.requests.append(captured) }

    guard
      let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil)
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.cannotParseResponse))
      return
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(
      self,
      didLoad: Data(
        #"{"id":"backend-created-1","description":"task","completed":true,"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"}"#
          .utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}

  private static func bodyData(from request: URLRequest) -> Data? {
    if let body = request.httpBody { return body }
    guard let stream = request.httpBodyStream else { return nil }

    stream.open()
    defer { stream.close() }
    var body = Data()
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: 4096)
    defer { buffer.deallocate() }
    while stream.hasBytesAvailable {
      let bytesRead = stream.read(buffer, maxLength: 4096)
      if bytesRead <= 0 { break }
      body.append(buffer, count: bytesRead)
    }
    return body.isEmpty ? nil : body
  }
}

final class APIClientCreateActionItemCompletedTests: XCTestCase {
  override func setUp() {
    super.setUp()
    CreateActionItemURLProtocol.reset()
    setenv("OMI_PYTHON_API_URL", "http://python-test:9001", 1)
  }

  override func tearDown() {
    unsetenv("OMI_PYTHON_API_URL")
    CreateActionItemURLProtocol.reset()
    super.tearDown()
  }

  private func makeClient() async -> APIClient {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [CreateActionItemURLProtocol.self]
    let session = URLSession(configuration: config)
    let client = APIClient(session: session)
    await client.setTestAuthHeader("Bearer test-token")
    return client
  }

  func testCreateActionItemSendsCompletedTrueInTheSameRequest() async throws {
    let client = await makeClient()

    _ = try await client.createActionItem(description: "task", completed: true)

    let requests = CreateActionItemURLProtocol.capturedRequests
    XCTAssertEqual(requests.count, 1, "completion must not require a follow-up request")
    let request = try XCTUnwrap(requests.first)
    XCTAssertEqual(request.url.path, "/v1/action-items")
    XCTAssertEqual(request.method, "POST")

    let body = try XCTUnwrap(request.body)
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
    XCTAssertEqual(json["completed"] as? Bool, true)
  }

  func testCreateActionItemOmitsCompletedWhenNotSpecified() async throws {
    let client = await makeClient()

    _ = try await client.createActionItem(description: "task")

    let request = try XCTUnwrap(CreateActionItemURLProtocol.capturedRequests.first)
    let body = try XCTUnwrap(request.body)
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
    XCTAssertNil(json["completed"], "existing callers must not start sending an explicit completed field")
  }
}
