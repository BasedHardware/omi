import XCTest

@testable import Omi_Computer

/// Captures the outgoing request and answers `{"status":"ok"}` so we can assert
/// that the how-did-you-hear answer is PATCHed to the backend onboarding state.
private final class AcquisitionSourceURLCapture: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var _request: URLRequest?
  private nonisolated(unsafe) static var _body: Data?

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

  static func reset() {
    lock.lock()
    _request = nil
    _body = nil
    lock.unlock()
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let body = Self.bodyData(from: request)
    Self.lock.lock()
    Self._request = request
    Self._body = body
    Self.lock.unlock()

    guard let url = request.url,
      let response = HTTPURLResponse(
        url: url,
        statusCode: 200,
        httpVersion: nil,
        headerFields: ["Content-Type": "application/json"])
    else {
      client?.urlProtocolDidFinishLoading(self)
      return
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data("{\"status\":\"ok\"}".utf8))
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

final class OnboardingAcquisitionSourceTests: XCTestCase {
  override func setUp() {
    super.setUp()
    AcquisitionSourceURLCapture.reset()
    setenv("OMI_PYTHON_API_URL", "http://acquisition-contract-test:9001", 1)
  }

  override func tearDown() {
    unsetenv("OMI_PYTHON_API_URL")
    AcquisitionSourceURLCapture.reset()
    super.tearDown()
  }

  private func makeClient() async -> APIClient {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [AcquisitionSourceURLCapture.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer test-token")
    return client
  }

  func testUpdateAcquisitionSourcePatchesOnboardingStateWithSnakeCaseBody() async throws {
    let client = await makeClient()

    let status = try await client.updateOnboardingAcquisitionSource("YouTube")

    XCTAssertEqual(status, "ok")
    let request = try XCTUnwrap(AcquisitionSourceURLCapture.request)
    XCTAssertEqual(request.httpMethod, "PATCH")
    XCTAssertEqual(request.url?.path, "/v1/users/onboarding")
    let json = try XCTUnwrap(
      JSONSerialization.jsonObject(with: try XCTUnwrap(AcquisitionSourceURLCapture.body))
        as? [String: Any])
    // Must be the snake_case key the backend reads, not a camelCase Swift name.
    XCTAssertEqual(json["acquisition_source"] as? String, "YouTube")
  }
}
