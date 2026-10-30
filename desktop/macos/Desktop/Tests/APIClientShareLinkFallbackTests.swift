import XCTest

@testable import Omi_Computer

private final class ShareLinkFallbackURLStub: URLProtocol, @unchecked Sendable {
  static let conversationID = "conv-share-1"
  private static let lock = NSLock()
  private nonisolated(unsafe) static var _requests: [(method: String, url: String)] = []
  private nonisolated(unsafe) static var patchStatus = 204
  private nonisolated(unsafe) static var getStatus = 200
  private nonisolated(unsafe) static var visibility = "private"

  static var requests: [(method: String, url: String)] {
    lock.lock()
    defer { lock.unlock() }
    return _requests
  }

  static func reset(patchStatus: Int, getStatus: Int = 200, visibility: String = "private") {
    lock.lock()
    _requests = []
    self.patchStatus = patchStatus
    self.getStatus = getStatus
    self.visibility = visibility
    lock.unlock()
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let method = request.httpMethod ?? "GET"
    let url = request.url?.absoluteString ?? ""
    let path = request.url?.path ?? ""
    Self.lock.lock()
    Self._requests.append((method: method, url: url))
    let patchStatus = Self.patchStatus
    let getStatus = Self.getStatus
    let visibility = Self.visibility
    Self.lock.unlock()

    let (status, body): (Int, Data)
    if method == "PATCH", path.hasSuffix("/visibility") {
      status = patchStatus
      body = Data()
    } else if method == "GET", path.contains("/v1/conversations/") {
      status = getStatus
      body =
        getStatus == 200
        ? Data(Self.conversationJSON(visibility: visibility).utf8)
        : Data(#"{"detail":"unavailable"}"#.utf8)
    } else {
      status = 500
      body = Data()
    }

    guard
      let requestURL = request.url,
      let response = HTTPURLResponse(url: requestURL, statusCode: status, httpVersion: nil, headerFields: nil)
    else { return }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: body)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}

  private static func conversationJSON(visibility: String) -> String {
    """
    {
      "id": "\(conversationID)",
      "created_at": "2026-06-25T10:00:00Z",
      "structured": {
        "title": "Already shared",
        "overview": "Overview",
        "emoji": "🔗",
        "category": "other",
        "action_items": [],
        "events": []
      },
      "status": "completed",
      "visibility": "\(visibility)"
    }
    """
  }
}

final class APIClientShareLinkFallbackTests: XCTestCase {
  private static var conversationID: String { ShareLinkFallbackURLStub.conversationID }

  override func tearDown() {
    unsetenv("OMI_PYTHON_API_URL")
    ShareLinkFallbackURLStub.reset(patchStatus: 204)
    super.tearDown()
  }

  func testPatchFailureWithSharedVisibilityReturnsExistingLink() async throws {
    let url = try await shareLink(patchStatus: 429, visibility: "shared")

    assertShareURL(url)
    XCTAssertEqual(requestMethods(), ["PATCH", "GET"])
  }

  func testPatchFailureWithPublicVisibilityReturnsExistingLink() async throws {
    let url = try await shareLink(patchStatus: 429, visibility: "public")

    assertShareURL(url)
    XCTAssertEqual(requestMethods(), ["PATCH", "GET"])
  }

  func testPatchFailureWithPrivateVisibilityRethrowsOriginalError() async {
    do {
      _ = try await shareLink(patchStatus: 429, visibility: "private")
      XCTFail("Expected the original visibility error")
    } catch let error as APIError {
      guard case .httpError(let statusCode, _) = error else {
        return XCTFail("Expected the original HTTP error, got \(error)")
      }
      XCTAssertEqual(statusCode, 429)
    } catch {
      XCTFail("Expected APIError, got \(error)")
    }

    XCTAssertEqual(requestMethods(), ["PATCH", "GET"])
  }

  func testPatchFailureWhenReadFailsRethrowsOriginalError() async {
    do {
      _ = try await shareLink(patchStatus: 429, getStatus: 503, visibility: "shared")
      XCTFail("Expected the original visibility error")
    } catch let error as APIError {
      guard case .httpError(let statusCode, _) = error else {
        return XCTFail("Expected the original HTTP error, got \(error)")
      }
      XCTAssertEqual(statusCode, 429)
    } catch {
      XCTFail("Expected APIError, got \(error)")
    }

    XCTAssertEqual(requestMethods(), ["PATCH", "GET"])
  }

  func testSuccessfulPatchReturnsShareURLWithoutReadingConversation() async throws {
    let url = try await shareLink(patchStatus: 204, visibility: "private")

    assertShareURL(url)
    XCTAssertEqual(requestMethods(), ["PATCH"])
    let patch = try XCTUnwrap(ShareLinkFallbackURLStub.requests.first?.url)
    XCTAssertTrue(patch.contains("/v1/conversations/\(Self.conversationID)/visibility?"))
    XCTAssertTrue(patch.contains("value=shared"))
    XCTAssertTrue(patch.contains("visibility=shared"))
  }

  private func shareLink(patchStatus: Int, getStatus: Int = 200, visibility: String) async throws -> String {
    ShareLinkFallbackURLStub.reset(patchStatus: patchStatus, getStatus: getStatus, visibility: visibility)
    setenv("OMI_PYTHON_API_URL", "http://share-link-fallback-test:9001", 1)
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ShareLinkFallbackURLStub.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer test-token")
    return try await client.getConversationShareLink(id: Self.conversationID)
  }

  private func requestMethods() -> [String] {
    ShareLinkFallbackURLStub.requests.map(\.method)
  }

  private func assertShareURL(_ url: String, file: StaticString = #filePath, line: UInt = #line) {
    let prefix = DesktopBackendEnvironment.shareBaseURL() + "/conversations/\(Self.conversationID)"
    XCTAssertTrue(url.hasPrefix(prefix), url, file: file, line: line)
    let items = URLComponents(string: url)?.queryItems ?? []
    XCTAssertEqual(items.first { $0.name == "s" }?.value, "mac", file: file, line: line)
    XCTAssertEqual(items.first { $0.name == "sid" }?.value?.count, 32, file: file, line: line)
  }
}
