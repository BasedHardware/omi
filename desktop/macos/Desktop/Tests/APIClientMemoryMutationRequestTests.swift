import XCTest

@testable import Omi_Computer

private final class MemoryMutationURLCapture: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private static var _request: URLRequest?
  private static var _body: Data?
  private static var _requests: [(method: String, path: String)] = []

  static var request: URLRequest? {
    lock.lock()
    defer { lock.unlock() }
    return _request
  }

  static var body: Data? {
    lock.lock()
    defer { lock.unlock() }
    return _body
  }

  static var requests: [(method: String, path: String)] {
    lock.lock()
    defer { lock.unlock() }
    return _requests
  }

  static func reset() {
    lock.lock()
    _request = nil
    _body = nil
    _requests = []
    lock.unlock()
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let body = Self.bodyData(from: request)
    Self.lock.lock()
    Self._request = request
    Self._body = body
    Self._requests.append((request.httpMethod ?? "GET", request.url?.path ?? ""))
    Self.lock.unlock()

    let response = HTTPURLResponse(
      url: request.url!,
      statusCode: 200,
      httpVersion: nil,
      headerFields: ["Content-Type": "application/json"]
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    let payload: Data
    if request.httpMethod == "GET", request.url?.path == "/v1/users/transcription-preferences" {
      payload = Data(
        "{\"single_language_mode\":false,\"vocabulary\":[\"Omi\",\"Codex\"],\"language\":\"en\"}".utf8)
    } else {
      payload = Data("{\"status\":\"ok\"}".utf8)
    }
    client?.urlProtocol(self, didLoad: payload)
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
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: 4_096)
    defer { buffer.deallocate() }
    while stream.hasBytesAvailable {
      let readCount = stream.read(buffer, maxLength: 4_096)
      if readCount > 0 {
        body.append(buffer, count: readCount)
      } else {
        break
      }
    }
    return body
  }
}

final class APIClientMemoryMutationRequestTests: XCTestCase {
  override func setUp() {
    super.setUp()
    MemoryMutationURLCapture.reset()
    setenv("OMI_PYTHON_API_URL", "http://memory-contract-test:9001", 1)
  }

  override func tearDown() {
    unsetenv("OMI_PYTHON_API_URL")
    MemoryMutationURLCapture.reset()
    super.tearDown()
  }

  private func makeClient() async -> APIClient {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [MemoryMutationURLCapture.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer test-token")
    return client
  }

  func testEditMemorySendsValueInJSONBody() async throws {
    let client = await makeClient()

    try await client.editMemory(id: "memory-1", content: "Updated content")

    let request = try XCTUnwrap(MemoryMutationURLCapture.request)
    XCTAssertEqual(request.httpMethod, "PATCH")
    XCTAssertEqual(request.url?.path, "/v3/memories/memory-1")
    XCTAssertNil(request.url?.query)
    XCTAssertEqual(try requestJSON()["value"] as? String, "Updated content")
  }

  func testUpdateMemoryVisibilitySendsValueInJSONBody() async throws {
    let client = await makeClient()

    try await client.updateMemoryVisibility(id: "memory-1", visibility: "private")

    let request = try XCTUnwrap(MemoryMutationURLCapture.request)
    XCTAssertEqual(request.httpMethod, "PATCH")
    XCTAssertEqual(request.url?.path, "/v3/memories/memory-1/visibility")
    XCTAssertNil(request.url?.query)
    XCTAssertEqual(try requestJSON()["value"] as? String, "private")
  }

  func testUpdateTranscriptionPreferencesReadsCanonicalStateAfterStatusResponse() async throws {
    let client = await makeClient()

    let saved = try await client.updateTranscriptionPreferences(vocabulary: ["Omi", "Codex"])

    XCTAssertEqual(saved.vocabulary, ["Omi", "Codex"])
    XCTAssertEqual(
      MemoryMutationURLCapture.requests.map { "\($0.method) \($0.path)" },
      [
        "PATCH /v1/users/transcription-preferences",
        "GET /v1/users/transcription-preferences",
      ]
    )
  }

  private func requestJSON() throws -> [String: Any] {
    let body = try XCTUnwrap(MemoryMutationURLCapture.body)
    return try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
  }
}
