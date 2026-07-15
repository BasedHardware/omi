import XCTest
@testable import Omi_Computer

private struct StagedScoreBatchRequest {
  let url: URL
  let method: String
  let body: Data?
}

private final class StagedScoreBatchURLProtocol: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private static var requests: [StagedScoreBatchRequest] = []

  static func reset() {
    lock.withLock { requests.removeAll() }
  }

  static var capturedRequests: [StagedScoreBatchRequest] {
    lock.withLock { requests }
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let captured = StagedScoreBatchRequest(
      url: request.url!,
      method: request.httpMethod ?? "GET",
      body: Self.bodyData(from: request)
    )
    Self.lock.withLock { Self.requests.append(captured) }

    let response = HTTPURLResponse(
      url: request.url!,
      statusCode: 200,
      httpVersion: nil,
      headerFields: nil
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(#"{"status":"ok"}"#.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}

  private static func bodyData(from request: URLRequest) -> Data? {
    if let body = request.httpBody {
      return body
    }
    guard let stream = request.httpBodyStream else {
      return nil
    }

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

final class APIClientStagedScoreBatchTests: XCTestCase {
  override func setUp() {
    super.setUp()
    StagedScoreBatchURLProtocol.reset()
    setenv("OMI_PYTHON_API_URL", "http://python-test:9001", 1)
  }

  override func tearDown() {
    unsetenv("OMI_PYTHON_API_URL")
    StagedScoreBatchURLProtocol.reset()
    super.tearDown()
  }

  func testBatchUpdateStagedScoresSplitsMoreThanFiveHundredScoresIntoOrderedRequests() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [StagedScoreBatchURLProtocol.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer test-token")
    let scores = (0...500).map { (id: "task-\($0)", score: $0) }

    try await client.batchUpdateStagedScores(scores)

    let requests = StagedScoreBatchURLProtocol.capturedRequests
    XCTAssertEqual(requests.count, 2)
    XCTAssertTrue(requests.allSatisfy {
      $0.url.path == "/v1/staged-tasks/batch-scores" && $0.method == "PATCH"
    })

    let batches = try requests.map { request -> [[String: Any]] in
      let body = try XCTUnwrap(request.body)
      let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
      return try XCTUnwrap(json["scores"] as? [[String: Any]])
    }
    XCTAssertEqual(batches.map(\.count), [500, 1])
    XCTAssertEqual(batches.flatMap { $0 }.map { $0["id"] as? String }, scores.map(\.id))
    XCTAssertEqual(batches.flatMap { $0 }.map { $0["relevance_score"] as? Int }, scores.map(\.score))
  }
}
