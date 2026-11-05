import Foundation
import PostHog
import XCTest
import zlib

@testable import Omi_Computer

final class PostHogFlagRequestBlockerTests: XCTestCase {
  func testOnlyFlagPathsAreHandledLocally() async throws {
    for path in ["/flags/?v=2", "/flags?v=2", "/decide/?v=3", "/decide?v=3"] {
      let url = try XCTUnwrap(URL(string: "https://posthog.invalid" + path))
      let session = URLSession(configuration: PostHogFlagRequestBlocker.sessionConfiguration())
      defer { session.invalidateAndCancel() }
      let (data, response) = try await session.data(from: url)
      XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
      let body = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      XCTAssertEqual((body["featureFlags"] as? [String: Bool])?.count, 0)
    }
    for path in ["/batch/", "/i/v0/e/", "/s/", "/array/token/config", "/v1/flags"] {
      let request = URLRequest(url: try XCTUnwrap(URL(string: "https://posthog.invalid" + path)))
      XCTAssertFalse(PostHogFlagRequestBlocker.canInit(with: request), path)
    }
  }

  func testSDKIdentifyResetAndReloadCannotReachFlagNetworkButCaptureDoes() async {
    let capture = expectation(description: "SDK sends the requested capture in an analytics batch")
    let recorder = FlagTrafficRecorder(capture: capture)
    SDKNetworkProbe.recorder = recorder
    defer { SDKNetworkProbe.recorder = nil }
    let config = PostHogConfig(projectToken: "flags-cut-hermetic", host: "https://posthog.invalid")
    config.preloadFeatureFlags = false
    config.captureApplicationLifecycleEvents = false
    config.captureScreenViews = false
    let transport = PostHogFlagRequestBlocker.sessionConfiguration()
    transport.protocolClasses?.insert(SDKNetworkProbe.self, at: 1)
    config.urlSessionConfiguration = transport
    PostHogSDK.shared.setup(config)
    defer { PostHogSDK.shared.close() }
    PostHogSDK.shared.identify("flags-cut-test")
    PostHogSDK.shared.reset()
    let flags = expectation(description: "SDK reload completes locally")
    PostHogSDK.shared.reloadFeatureFlags { flags.fulfill() }
    await fulfillment(of: [flags], timeout: 5)
    PostHogSDK.shared.capture("flags-cut-capture")
    PostHogSDK.shared.flush()
    await fulfillment(of: [capture], timeout: 5)
    XCTAssertFalse(
      recorder.paths.contains {
        let path = $0.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        return path == "flags" || path == "decide"
      })
    XCTAssertTrue(recorder.paths.contains { $0.trimmingCharacters(in: CharacterSet(charactersIn: "/")) == "batch" })
  }
}

private final class FlagTrafficRecorder: @unchecked Sendable {
  private let lock = NSLock()
  private var captured = false
  private var seen: [String] = []
  private let capture: XCTestExpectation
  init(capture: XCTestExpectation) { self.capture = capture }
  var paths: [String] { lock.withLock { seen } }
  func record(_ request: URLRequest) {
    let path = request.url?.path ?? ""
    let batch =
      decodedBody(request)
      .flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }?["batch"] as? [[String: Any]]
    let hasCapture = batch?.contains { $0["event"] as? String == "flags-cut-capture" } == true
    lock.withLock {
      seen.append(path)
      if hasCapture, !captured {
        captured = true
        capture.fulfill()
      }
    }
  }

  private func decodedBody(_ request: URLRequest) -> Data? {
    var body = request.httpBody
    if body == nil, let input = request.httpBodyStream {
      input.open()
      defer { input.close() }
      var data = Data()
      var buffer = [UInt8](repeating: 0, count: 4096)
      while input.hasBytesAvailable {
        let count = input.read(&buffer, maxLength: buffer.count)
        guard count > 0 else { break }
        data.append(buffer, count: count)
      }
      body = data
    }
    guard let body else { return nil }
    guard request.value(forHTTPHeaderField: "Content-Encoding") == "gzip" else { return body }
    var stream = z_stream()
    guard inflateInit2_(&stream, MAX_WBITS + 32, ZLIB_VERSION, Int32(MemoryLayout<z_stream>.size)) == Z_OK else {
      return nil
    }
    defer { inflateEnd(&stream) }
    // This hermetic batch has only a handful of events; refuse oversized output.
    var output = Data(count: 256 * 1024)
    return body.withUnsafeBytes { input in
      output.withUnsafeMutableBytes { destination in
        stream.next_in = UnsafeMutablePointer(mutating: input.bindMemory(to: Bytef.self).baseAddress)
        stream.avail_in = uInt(input.count)
        stream.next_out = destination.bindMemory(to: Bytef.self).baseAddress
        stream.avail_out = uInt(destination.count)
        guard inflate(&stream, Z_FINISH) == Z_STREAM_END else { return nil }
        return Data(destination.prefix(Int(stream.total_out)))
      }
    }
  }
}

private final class SDKNetworkProbe: URLProtocol {
  nonisolated(unsafe) static var recorder: FlagTrafficRecorder?
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
  override func startLoading() {
    guard let url = request.url,
      let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil)
    else { return }
    Self.recorder?.record(request)
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data("{}".utf8))
    client?.urlProtocolDidFinishLoading(self)
  }
  override func stopLoading() {}
}
