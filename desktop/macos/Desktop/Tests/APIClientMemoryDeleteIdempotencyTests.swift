import XCTest

@testable import Omi_Computer

/// Returns a caller-chosen status for every request so a delete can be driven
/// against each backend answer it actually receives.
private final class MemoryDeleteStatusStub: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var _status = 200
  private nonisolated(unsafe) static var _observed: [(method: String, path: String)] = []

  static var status: Int {
    get {
      lock.lock()
      defer { lock.unlock() }
      return _status
    }
    set {
      lock.lock()
      _status = newValue
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
    _status = 200
    _observed = []
    lock.unlock()
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    Self.lock.lock()
    Self._observed.append((request.httpMethod ?? "GET", request.url?.path ?? ""))
    let status = Self._status
    Self.lock.unlock()

    var headerFields = ["Content-Type": "application/json"]
    var payload = Data("{\"status\":\"ok\"}".utf8)
    if status == 404 {
      payload = Data("{\"detail\":\"Memory not found\"}".utf8)
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

/// A memory the backend no longer has must not be resurrected on this device.
///
/// The desktop cache outlives backend rows: nothing prunes a local row whose
/// memory was deleted on another device, because the cache reconcile fails
/// closed while the list endpoint cannot prove scope completeness. Deleting one
/// of those orphans answers `404 Memory not found`, and while that read as an
/// error the caller restored the row it had just removed — the memory could not
/// be cleared from the machine at all, which is what "I can't delete them on the
/// desktop app" was.
final class APIClientMemoryDeleteIdempotencyTests: XCTestCase {
  override func setUp() {
    super.setUp()
    MemoryDeleteStatusStub.reset()
    setenv("OMI_PYTHON_API_URL", "http://memory-delete-test:9001", 1)
  }

  override func tearDown() {
    unsetenv("OMI_PYTHON_API_URL")
    MemoryDeleteStatusStub.reset()
    super.tearDown()
  }

  private func makeClient() async -> APIClient {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [MemoryDeleteStatusStub.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer test-token")
    return client
  }

  func testDeleteTreatsAlreadyAbsentMemoryAsSuccess() async throws {
    let client = await makeClient()
    MemoryDeleteStatusStub.status = 404

    try await client.deleteMemory(id: "orphaned-memory")

    let observed = try XCTUnwrap(MemoryDeleteStatusStub.observed.first)
    XCTAssertEqual(observed.method, "DELETE")
    XCTAssertEqual(observed.path, "/v3/memories/orphaned-memory")
  }

  func testDeleteSucceedsNormally() async throws {
    let client = await makeClient()
    MemoryDeleteStatusStub.status = 200

    try await client.deleteMemory(id: "live-memory")

    XCTAssertEqual(MemoryDeleteStatusStub.observed.first?.path, "/v3/memories/live-memory")
  }

  /// The other direction: swallowing 404 must not swallow real failures, or a
  /// delete that never happened would read as done and the row would vanish
  /// locally while the backend still holds it.
  func testDeleteStillFailsOnServerError() async throws {
    let client = await makeClient()
    MemoryDeleteStatusStub.status = 500

    do {
      try await client.deleteMemory(id: "memory-1")
      XCTFail("A 500 must surface as an error rather than reading as a completed delete")
    } catch APIError.httpError(let statusCode, _) {
      XCTAssertEqual(statusCode, 500)
    }
  }

  func testDeleteStillFailsOnForbidden() async throws {
    let client = await makeClient()
    MemoryDeleteStatusStub.status = 403

    do {
      try await client.deleteMemory(id: "locked-memory")
      XCTFail("A 403 must surface as an error rather than reading as a completed delete")
    } catch APIError.httpError(let statusCode, _) {
      XCTAssertEqual(statusCode, 403)
    }
  }

  /// The account-gate-busy 409 must arrive as a typed, retryable error that
  /// carries the server's Retry-After, so the Memories page can back off and
  /// retry instead of resurrecting the row it just removed.
  func testDeleteSurfacesGateBusy409WithRetryAfter() async throws {
    let client = await makeClient()
    MemoryDeleteStatusStub.status = 409

    do {
      try await client.deleteMemory(id: "gated-memory")
      XCTFail("A gate-busy 409 must surface as a retryable error, not a completed delete")
    } catch APIError.memoryDeleteGateBusy(let retryAfterSeconds) {
      XCTAssertEqual(retryAfterSeconds, 2, "the Retry-After header must survive the transport")
    }
  }
}
