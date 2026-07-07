import XCTest
@testable import Omi_Computer

final class APIClientUploadLocalFilesV2Tests: XCTestCase {

  override func setUp() {
    SyncUploadURLProtocol.reset()
  }

  func testUploadLocalFilesV2202ReturnsQueuedJobId() async throws {
    SyncUploadURLProtocol.setResponse(
      statusCode: 202,
      body: """
      {"job_id":"job-123","status":"queued","total_files":1,"total_segments":0,"poll_after_ms":1000}
      """.data(using: .utf8)!
    )

    let client = APIClient(session: makeSession())
    await client.setTestAuthHeader("Bearer test-token")
    let fileURL = try writeTempFile()
    let result = try await client.uploadLocalFilesV2(fileURLs: [fileURL])

    XCTAssertEqual(result.jobId, "job-123")
    XCTAssertTrue(SyncUploadURLProtocol.lastRequestURL?.path.contains("/v2/sync-local-files") == true)
    XCTAssertEqual(SyncUploadURLProtocol.lastRequestMethod, "POST")
  }

  func testUploadLocalFilesV2200ReturnsCompleted() async throws {
    SyncUploadURLProtocol.setResponse(
      statusCode: 200,
      body: """
      {"new_memories":["c1"],"updated_memories":[],"failed_segments":0,"total_segments":1,"errors":[]}
      """.data(using: .utf8)!
    )

    let client = APIClient(session: makeSession())
    await client.setTestAuthHeader("Bearer test-token")
    let fileURL = try writeTempFile()
    let result = try await client.uploadLocalFilesV2(fileURLs: [fileURL])

    guard case .done(let completed) = result else {
      return XCTFail("expected done result")
    }
    XCTAssertEqual(completed.newMemories, ["c1"])
  }

  func testUploadLocalFilesV2429ThrowsRateLimited() async throws {
    SyncUploadURLProtocol.setResponse(
      statusCode: 429,
      body: Data("{\"detail\":\"limited\"}".utf8),
      headers: ["Retry-After": "120"]
    )

    let client = APIClient(session: makeSession())
    await client.setTestAuthHeader("Bearer test-token")
    let fileURL = try writeTempFile()

    do {
      _ = try await client.uploadLocalFilesV2(fileURLs: [fileURL])
      XCTFail("expected rate limit error")
    } catch APIError.syncRateLimited(let retryAfter) {
      XCTAssertEqual(retryAfter, 120)
    } catch {
      XCTFail("unexpected error: \(error)")
    }
  }

  private func makeSession() -> URLSession {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [SyncUploadURLProtocol.self]
    return URLSession(configuration: config)
  }

  private func writeTempFile() throws -> URL {
    let url = FileManager.default.temporaryDirectory.appendingPathComponent("wal-\(UUID().uuidString).bin")
    try Data([0xAA, 0xBB]).write(to: url)
    return url
  }
}

private final class SyncUploadURLProtocol: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private static var statusCode = 403
  private static var body = Data()
  private static var responseHeaders: [String: String] = [:]
  static var lastRequestURL: URL?
  static var lastRequestMethod: String?

  static func reset() {
    lock.lock()
    statusCode = 403
    body = Data()
    responseHeaders = [:]
    lastRequestURL = nil
    lastRequestMethod = nil
    lock.unlock()
  }

  static func setResponse(statusCode: Int, body: Data, headers: [String: String] = [:]) {
    lock.lock()
    self.statusCode = statusCode
    self.body = body
    self.responseHeaders = headers
    lock.unlock()
  }

  private static func snapshot() -> (Int, Data, [String: String]) {
    lock.lock()
    defer { lock.unlock() }
    return (statusCode, body, responseHeaders)
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    if let url = request.url {
      Self.lock.lock()
      Self.lastRequestURL = url
      Self.lastRequestMethod = request.httpMethod
      Self.lock.unlock()
    }
    let (statusCode, body, headers) = Self.snapshot()
    let response = HTTPURLResponse(
      url: request.url!, statusCode: statusCode, httpVersion: nil, headerFields: headers)!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: body)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}
