import Flutter
import Foundation
import PostHog

/// Install the native transport before the Flutter SDK bridge initializes.
enum OmiPostHogSetup {
  static func register(messenger: FlutterBinaryMessenger) {
    FlutterMethodChannel(name: "com.omi/posthog_setup", binaryMessenger: messenger).setMethodCallHandler { call, result in
      guard call.method == "setup", let args = call.arguments as? [String: Any],
        let token = args["projectToken"] as? String, let host = args["host"] as? String,
        let sdkVersion = args["sdkVersion"] as? String
      else { result(FlutterMethodNotImplemented); return }
      // setup snapshots SDK context before Flutter's later idempotent setup.
      postHogSdkName = "posthog-flutter"
      postHogVersion = sdkVersion
      let config = PostHogConfig(projectToken: token, host: host)
      config.captureApplicationLifecycleEvents = args["captureApplicationLifecycleEvents"] as? Bool ?? false
      config.captureScreenViews = false
      config.preloadFeatureFlags = false
      config.sendFeatureFlagEvent = false
      config.optOut = args["optOut"] as? Bool ?? false
      config.debug = args["debug"] as? Bool ?? false
      config.surveys = false
      config.sessionReplay = false
      config.sessionReplayConfig.captureNetworkTelemetry = false
      config.urlSessionConfiguration = PostHogFlagRequestBlocker.sessionConfiguration()
      PostHogSDK.shared.setup(config)
      result(nil)
    }
  }
}

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
      let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil,
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
