import Foundation
import PostHog
import XCTest

@testable import Omi_Computer

final class PostHogFlagRequestBlockerTests: XCTestCase {
  func testOnlyFlagPathsAreHandledLocally() async throws {
    for path in ["/flags/?v=2", "/decide/?v=3"] {
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
    let capture = expectation(description: "SDK sends analytics batch")
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
    XCTAssertFalse(recorder.paths.contains { $0 == "/flags/" || $0 == "/decide/" })
    XCTAssertTrue(recorder.paths.contains("/batch/"))
  }
}

private final class FlagTrafficRecorder: @unchecked Sendable {
  private let lock = NSLock()
  private var captured = false
  private var seen: [String] = []
  private let capture: XCTestExpectation
  init(capture: XCTestExpectation) { self.capture = capture }
  var paths: [String] { lock.withLock { seen } }
  func record(_ path: String) {
    lock.withLock {
      seen.append(path)
      if path == "/batch/", !captured {
        captured = true
        capture.fulfill()
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
    Self.recorder?.record(url.path)
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data("{}".utf8))
    client?.urlProtocolDidFinishLoading(self)
  }
  override func stopLoading() {}
}
