import XCTest

@testable import Omi_Computer

private struct ChannelCapturedRequest {
  let url: URL
  let headers: [String: String]
}

private final class ChannelURLCapture: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var _requests: [ChannelCapturedRequest] = []

  static var capturedRequests: [ChannelCapturedRequest] {
    lock.lock()
    defer { lock.unlock() }
    return _requests
  }

  static func reset() {
    lock.lock()
    _requests.removeAll()
    lock.unlock()
  }

  private static func record(_ request: ChannelCapturedRequest) {
    lock.lock()
    _requests.append(request)
    lock.unlock()
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    if let url = request.url {
      Self.record(ChannelCapturedRequest(url: url, headers: request.allHTTPHeaderFields ?? [:]))
    }
    let response = HTTPURLResponse(
      url: request.url!, statusCode: 500, httpVersion: nil, headerFields: nil)!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data("{}".utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

/// Channel management is unrelated to model inference: `/v1/channels` and
/// `/v1/channels/{channel}/link` never read a provider key, so sending the user's
/// active BYOK credentials on that traffic exposes them for nothing.
final class APIClientChannelBYOKTests: XCTestCase {
  override func setUp() {
    super.setUp()
    ChannelURLCapture.reset()
    setenv("OMI_PYTHON_API_URL", "http://python-test:9001", 1)
    for provider in BYOKProvider.allCases {
      UserDefaults.standard.set("sk-test-\(provider.rawValue)", forKey: provider.storageKey)
    }
  }

  override func tearDown() {
    unsetenv("OMI_PYTHON_API_URL")
    ChannelURLCapture.reset()
    for provider in BYOKProvider.allCases {
      UserDefaults.standard.removeObject(forKey: provider.storageKey)
    }
    super.tearDown()
  }

  private func makeClient() async -> APIClient {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [ChannelURLCapture.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")
    return client
  }

  private func assertNoBYOKHeaders(file: StaticString = #filePath, line: UInt = #line) {
    let requests = ChannelURLCapture.capturedRequests
    XCTAssertFalse(requests.isEmpty, "expected a captured request", file: file, line: line)
    for request in requests {
      for provider in BYOKProvider.allCases {
        XCTAssertNil(
          request.headers[provider.headerName],
          "\(request.url.path) leaked \(provider.headerName)",
          file: file, line: line)
      }
    }
  }

  func testChannelStatusDoesNotSendBYOKKeys() async {
    let client = await makeClient()
    _ = try? await client.getChannelStatus()
    assertNoBYOKHeaders()
  }

  func testChannelLinkDoesNotSendBYOKKeys() async {
    let client = await makeClient()
    _ = try? await client.createChannelLink(channel: "telegram")
    assertNoBYOKHeaders()
  }
}
