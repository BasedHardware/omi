import XCTest

@testable import Omi_Computer

private struct CapturedTaskSortOrderBatchRequest {
  let url: URL
  let method: String
  let body: Data?
}

private final class TaskSortOrderBatchURLProtocol: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var requests: [CapturedTaskSortOrderBatchRequest] = []
  private nonisolated(unsafe) static var failingRequestNumbers = Set<Int>()

  static func reset() {
    lock.withLock {
      requests.removeAll()
      failingRequestNumbers.removeAll()
    }
  }

  static func failRequest(number: Int) {
    failRequests(numbers: [number])
  }

  static func failRequests(numbers: [Int]) {
    lock.withLock { failingRequestNumbers.formUnion(numbers) }
  }

  static var capturedRequests: [CapturedTaskSortOrderBatchRequest] {
    lock.withLock { requests }
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    guard let url = request.url else {
      client?.urlProtocol(self, didFailWithError: URLError(.badURL))
      return
    }
    let captured = CapturedTaskSortOrderBatchRequest(
      url: url,
      method: request.httpMethod ?? "GET",
      body: Self.bodyData(from: request)
    )
    let requestNumber = Self.lock.withLock {
      Self.requests.append(captured)
      return Self.requests.count
    }
    let statusCode = Self.lock.withLock {
      Self.failingRequestNumbers.contains(requestNumber) ? 500 : 200
    }

    guard
      let response = HTTPURLResponse(
        url: url,
        statusCode: statusCode,
        httpVersion: nil,
        headerFields: nil
      )
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.cannotParseResponse))
      return
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    if statusCode == 200 {
      client?.urlProtocol(self, didLoad: Data(#"{"status":"ok"}"#.utf8))
    } else {
      client?.urlProtocol(self, didLoad: Data(#"{"detail":"batch failed"}"#.utf8))
    }
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

private final class LegacyRecoveryCursorURLProtocol: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var capturedURL: URL?

  static func reset() {
    lock.withLock { capturedURL = nil }
  }

  static var requestURL: URL? {
    lock.withLock { capturedURL }
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    guard let url = request.url else {
      client?.urlProtocol(self, didFailWithError: URLError(.badURL))
      return
    }
    Self.lock.withLock { Self.capturedURL = url }
    guard
      let response = HTTPURLResponse(
        url: url,
        statusCode: 200,
        httpVersion: nil,
        headerFields: nil
      )
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
      return
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(
      self,
      didLoad: Data(#"{"restored":0,"skipped_existing":0,"has_more":false,"next_cursor":null}"#.utf8)
    )
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

final class APIClientTaskSortOrderBatchTests: XCTestCase {
  override func setUp() {
    super.setUp()
    TaskSortOrderBatchURLProtocol.reset()
    setenv("OMI_PYTHON_API_URL", "http://python-test:9001", 1)
  }

  override func tearDown() {
    unsetenv("OMI_PYTHON_API_URL")
    TaskSortOrderBatchURLProtocol.reset()
    LegacyRecoveryCursorURLProtocol.reset()
    super.tearDown()
  }

  func testRestoreLegacyConversationItemsStrictlyEncodesOpaqueCursor() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [LegacyRecoveryCursorURLProtocol.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer test-token")
    let cursor = "opaque&part=1+2/base:tail?x=y#fragment%done"

    _ = try await client.restoreLegacyConversationItems(cursor: cursor)

    let url = try XCTUnwrap(LegacyRecoveryCursorURLProtocol.requestURL)
    let queryItems = try XCTUnwrap(URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems)
    XCTAssertEqual(queryItems.map(\.name), ["limit", "cursor"])
    XCTAssertEqual(queryItems.last?.value, cursor)
    XCTAssertTrue(
      URLComponents(url: url, resolvingAgainstBaseURL: false)?.percentEncodedQuery?.contains("%26") == true,
      "reserved ampersand must not become a second query item"
    )
  }

  func testBatchUpdateSortOrdersSplitsLargeTaskSetsIntoOrderedRequests() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [TaskSortOrderBatchURLProtocol.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer test-token")
    let updates = (0..<1061).map { (id: "task-\($0)", sortOrder: $0, indentLevel: $0 % 4) }

    try await client.batchUpdateSortOrders(updates)

    let requests = TaskSortOrderBatchURLProtocol.capturedRequests
    XCTAssertEqual(requests.count, 3)
    XCTAssertTrue(
      requests.allSatisfy {
        $0.url.path == "/v1/action-items/batch" && $0.method == "PATCH"
      })

    let batches = try requests.map { request -> [[String: Any]] in
      let body = try XCTUnwrap(request.body)
      let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
      return try XCTUnwrap(json["items"] as? [[String: Any]])
    }
    XCTAssertEqual(batches.map(\.count), [500, 500, 61])
    XCTAssertEqual(
      batches.flatMap { $0 }.map { $0["id"] as? String },
      updates.map(\.id)
    )
    XCTAssertEqual(
      batches.flatMap { $0 }.map { $0["sort_order"] as? Int },
      updates.map(\.sortOrder)
    )
  }

  func testBatchUpdateSortOrdersStopsAfterAChunkFails() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [TaskSortOrderBatchURLProtocol.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer test-token")
    TaskSortOrderBatchURLProtocol.failRequests(numbers: [2, 4])
    let updates = (0..<1061).map { (id: "task-\($0)", sortOrder: $0, indentLevel: 0) }

    do {
      try await client.batchUpdateSortOrders(updates)
      XCTFail("Expected the second batch failure to be thrown")
    } catch {
      // Requests are intentionally non-atomic: the first chunk may already be applied.
    }

    let requests = TaskSortOrderBatchURLProtocol.capturedRequests
    XCTAssertEqual(requests.count, 4, "A failed retry must stop after replaying the failing chunk")
    let batchSizes = try requests.map { request -> Int in
      let body = try XCTUnwrap(request.body)
      let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
      return try XCTUnwrap(json["items"] as? [[String: Any]]).count
    }
    XCTAssertEqual(batchSizes, [500, 500, 500, 500])
  }

  func testBatchUpdateSortOrdersRetriesTheCompleteSetAfterTransientLaterChunkFailure() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [TaskSortOrderBatchURLProtocol.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer test-token")
    TaskSortOrderBatchURLProtocol.failRequest(number: 2)
    let updates = (0..<1061).map { (id: "task-\($0)", sortOrder: $0, indentLevel: 0) }

    try await client.batchUpdateSortOrders(updates)

    let requests = TaskSortOrderBatchURLProtocol.capturedRequests
    XCTAssertEqual(requests.count, 5, "the retry must replay all three ordered chunks")
    let batchSizes = try requests.map { request -> Int in
      let body = try XCTUnwrap(request.body)
      let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
      return try XCTUnwrap(json["items"] as? [[String: Any]]).count
    }
    XCTAssertEqual(batchSizes, [500, 500, 500, 500, 61])
  }
}
