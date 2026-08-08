import Flutter
import UIKit
import WebKit

// Owns the WKWebView + WKWebViewConfiguration so the omi-ui scheme handler is
// registered with setURLSchemeHandler at construction time — no swizzle.
//
// Dart contract (hand to the Dart worker):
//   viewType:            "omi/ui_webview"
//   per-view channel:    "omi/ui_webview_<viewId>"  (viewId from onPlatformViewCreated)
//   method loadUrl:      argument is a String absolute URL
//                        e.g. "omi-ui://local/index.html"
//   creationParams:      optional Map { "url": String } — loads that URL once
//                        the view is created (same string shape as loadUrl)

final class OmiUiWebViewFactory: NSObject, FlutterPlatformViewFactory {
  static let viewType = "omi/ui_webview"

  private let messenger: FlutterBinaryMessenger

  init(messenger: FlutterBinaryMessenger) {
    self.messenger = messenger
    super.init()
  }

  func createArgsCodec() -> (FlutterMessageCodec & NSObjectProtocol) {
    FlutterStandardMessageCodec.sharedInstance()
  }

  func create(
    withFrame frame: CGRect,
    viewIdentifier viewId: Int64,
    arguments args: Any?
  ) -> FlutterPlatformView {
    OmiUiWebView(frame: frame, viewId: viewId, arguments: args, messenger: messenger)
  }
}

final class OmiUiWebView: NSObject, FlutterPlatformView {
  private let webView: WKWebView
  private let channel: FlutterMethodChannel

  init(
    frame: CGRect,
    viewId: Int64,
    arguments args: Any?,
    messenger: FlutterBinaryMessenger
  ) {
    let configuration = WKWebViewConfiguration()
    // Handler must be attached before the WKWebView is constructed.
    configuration.setURLSchemeHandler(
      OmiSchemeHandler.shared,
      forURLScheme: OmiSchemeHandler.scheme
    )
    NSLog(
      "[scheme] handler registered on owned configuration for %@:// (viewId=%lld)",
      OmiSchemeHandler.scheme,
      viewId
    )

    webView = WKWebView(frame: frame, configuration: configuration)
    webView.scrollView.contentInsetAdjustmentBehavior = .never

    channel = FlutterMethodChannel(
      name: "\(OmiUiWebViewFactory.viewType)_\(viewId)",
      binaryMessenger: messenger
    )
    super.init()

    channel.setMethodCallHandler { [weak self] call, result in
      self?.handle(call, result: result)
    }

    if let params = args as? [String: Any],
       let urlString = params["url"] as? String
    {
      navigate(to: urlString, result: nil)
    }
  }

  func view() -> UIView { webView }

  private func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "loadUrl":
      guard let urlString = call.arguments as? String else {
        result(
          FlutterError(
            code: "bad_args",
            message: "loadUrl expects a String absolute URL",
            details: nil
          )
        )
        return
      }
      navigate(to: urlString, result: result)
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  private func navigate(to urlString: String, result: FlutterResult?) {
    guard let url = URL(string: urlString) else {
      result?(
        FlutterError(
          code: "bad_url",
          message: "could not parse URL: \(urlString)",
          details: nil
        )
      )
      return
    }
    webView.load(URLRequest(url: url))
    result?(nil)
  }
}
