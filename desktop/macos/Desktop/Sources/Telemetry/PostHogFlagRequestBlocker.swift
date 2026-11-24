import Foundation

/// Scoped to the PostHog SDK session. It has no flag authority: Omi serves flags.
/// Capture, replay and remote configuration continue through their usual paths.
final class PostHogFlagRequestBlocker: URLProtocol {
  override class func canInit(with request: URLRequest) -> Bool {
    let path = request.url?.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    return path == "flags" || path == "decide"
  }

  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    guard let url = request.url,
      let response = HTTPURLResponse(
        url: url, statusCode: 200, httpVersion: nil,
        headerFields: ["Content-Type": "application/json"])
    else { return }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(#"{"featureFlags":{},"featureFlagPayloads":{},"flags":{}}"#.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}

  static func sessionConfiguration() -> URLSessionConfiguration {
    let config = URLSessionConfiguration.default
    config.protocolClasses = [PostHogFlagRequestBlocker.self] + (config.protocolClasses ?? [])
    return config
  }
}
