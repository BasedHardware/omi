import XCTest

@testable import Omi_Computer

private final class PublicWebSearchURLCapture: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var capturedRequest: URLRequest?
  private nonisolated(unsafe) static var capturedBody: Data?

  static func reset() {
    lock.lock()
    capturedRequest = nil
    capturedBody = nil
    lock.unlock()
  }

  static func snapshot() -> (URLRequest?, Data?) {
    lock.lock()
    defer { lock.unlock() }
    return (capturedRequest, capturedBody)
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    Self.lock.lock()
    Self.capturedRequest = request
    Self.capturedBody = Self.bodyData(from: request)
    Self.lock.unlock()

    guard
      let url = request.url,
      let response = HTTPURLResponse(
        url: url, statusCode: 200, httpVersion: nil,
        headerFields: ["Content-Type": "application/json"])
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
      return
    }
    let body =
      #"{"choices":[{"message":{"content":"It is sunny and 80 degrees, according to the National Weather Service."}}],"search_results":[{"title":"Founder launch account","url":"https://example.test/founder","snippet":"We launched the first desktop version six weeks after ending the hardware effort."}]}"#
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(body.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}

  private static func bodyData(from request: URLRequest) -> Data? {
    if let body = request.httpBody { return body }
    guard let stream = request.httpBodyStream else { return nil }
    stream.open()
    defer { stream.close() }
    var data = Data()
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: 4_096)
    defer { buffer.deallocate() }
    while stream.hasBytesAvailable {
      let count = stream.read(buffer, maxLength: 4_096)
      if count <= 0 { break }
      data.append(buffer, count: count)
    }
    return data
  }
}

@MainActor
final class APIClientPublicWebSearchTests: XCTestCase {
  override func tearDown() {
    PublicWebSearchURLCapture.reset()
    super.tearDown()
  }

  func testVoiceWebSearchUsesOnePublicOnlyManagedRequest() async throws {
    let ownerFixture = RuntimeOwnerAuthorityTestFixture()
    await ownerFixture.establish(authOwnerID: "public-web-owner")
    do {
      let configuration = URLSessionConfiguration.ephemeral
      configuration.protocolClasses = [PublicWebSearchURLCapture.self]
      let client = APIClient(session: URLSession(configuration: configuration))
      await client.setTestAuthHeader("Bearer public-web-token")

      let answer = try await client.searchPublicWebForVoice(
        query: "Search current New York weather and name the source.",
        expectedOwnerID: "public-web-owner",
        customBaseURL: "https://desktop.example.test")
      XCTAssertEqual(
        answer,
        "It is sunny and 80 degrees, according to the National Weather Service.")

      let (capturedRequest, bodyData) = PublicWebSearchURLCapture.snapshot()
      let request = try XCTUnwrap(capturedRequest)
      XCTAssertEqual(request.url?.absoluteString, "https://desktop.example.test/v2/chat/completions")
      XCTAssertEqual(request.httpMethod, "POST")
      XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer public-web-token")
      XCTAssertNil(request.value(forHTTPHeaderField: "X-BYOK-Anthropic"))

      let body = try XCTUnwrap(
        try JSONSerialization.jsonObject(with: XCTUnwrap(bodyData)) as? [String: Any])
      XCTAssertEqual(body["model"] as? String, "omi-sonnet")
      XCTAssertEqual(body["omi_web_search"] as? Bool, true)
      XCTAssertEqual(body["stream"] as? Bool, false)
      XCTAssertEqual(body["max_tokens"] as? Int, 512)
      let messages = try XCTUnwrap(body["messages"] as? [[String: Any]])
      XCTAssertEqual(messages.count, 1)
      XCTAssertEqual(messages[0]["role"] as? String, "user")
      XCTAssertEqual(
        messages[0]["content"] as? String,
        "Search current New York weather and name the source.")
    } catch {
      await ownerFixture.restore()
      throw error
    }
    await ownerFixture.restore()
  }

  func testHistoricalVoiceWebSearchCarriesStructuredSourceEvidence() async throws {
    let ownerFixture = RuntimeOwnerAuthorityTestFixture()
    await ownerFixture.establish(authOwnerID: "historical-web-owner")
    do {
      let configuration = URLSessionConfiguration.ephemeral
      configuration.protocolClasses = [PublicWebSearchURLCapture.self]
      let client = APIClient(session: URLSession(configuration: configuration))
      await client.setTestAuthHeader("Bearer public-web-token")

      let evidence = try await client.searchPublicWebForVoice(
        query: "How long did the first desktop version take?",
        expectedOwnerID: "historical-web-owner",
        customBaseURL: "https://desktop.example.test",
        includeSourceEvidence: true)

      XCTAssertTrue(evidence.contains("Search-result evidence:"))
      XCTAssertTrue(evidence.contains("Founder launch account"))
      XCTAssertTrue(evidence.contains("six weeks after ending the hardware effort"))
    } catch {
      await ownerFixture.restore()
      throw error
    }
    await ownerFixture.restore()
  }
}
