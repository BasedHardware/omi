import Flutter
import ObjectiveC.runtime
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
    // This is a capture-only, opt-in host return path.  It is intentionally
    // absent from normal launches and retains only typed lifecycle/style
    // values (never labels, field values, URLs, or credentials).
    OmiRuntimeProbeHandler.installIfRequested(on: configuration)
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

/// Redacted and allowlisted runtime result from the real WKWebView.  The
/// marker is surfaced through the native accessibility identifier only for the
/// fixture UI test; the production WebView never installs this handler.
final class OmiRuntimeProbeHandler: NSObject, WKScriptMessageHandler {
  private static var installedKey: UInt8 = 0

  static func installIfRequested(on configuration: WKWebViewConfiguration) {
    guard ProcessInfo.processInfo.environment["OMI_POLISH_RUNTIME_PROBE"] == "1",
          objc_getAssociatedObject(configuration, &installedKey) == nil else { return }
    let handler = OmiRuntimeProbeHandler()
    configuration.userContentController.add(handler, name: "omiRuntimeProbe")
    configuration.userContentController.addUserScript(
      WKUserScript(source: script, injectionTime: .atDocumentEnd, forMainFrameOnly: true)
    )
    objc_setAssociatedObject(
      configuration, &installedKey, handler, .OBJC_ASSOCIATION_RETAIN_NONATOMIC)
  }

  static let script = #"""
  (() => {
    let attempts = 0;
    const probe = () => {
      const url = new URL(location.href);
      const requestedQa = url.searchParams.get("qa") || "";
      const domain = requestedQa === "memories-platform" ? "memories" : requestedQa;
      const wantedState = url.searchParams.get("state") || "";
      const theme = url.searchParams.get("theme") || "";
      const accessibility = url.searchParams.get("accessibility") || "none";
      const root = document.querySelector("main[data-production-shell]");
      const polishState = document.documentElement.dataset.polishState || "";
      if (!root || root.dataset.route !== domain || polishState !== wantedState || document.documentElement.dataset.themeSelection !== theme) {
        attempts += 1;
        if (attempts < 80) setTimeout(probe, 100);
        return;
      }
      const target = root.querySelector("*") || root;
      const style = getComputedStyle(target);
      const events = [];
      if (accessibility === "none") {
        events.push({type: "lifecycle", name: "state", value: polishState, passed: true});
      } else if (accessibility === "reduced_motion") {
        events.push({type: "computed_style", name: "transition_duration", value: style.transitionDuration || "", passed: true});
        events.push({type: "computed_style", name: "animation_name", value: style.animationName || "", passed: true});
        events.push({type: "computed_style", name: "animation_duration", value: style.animationDuration || "", passed: true});
      } else if (accessibility === "reduced_transparency") {
        events.push({type: "computed_style", name: "backdrop_filter", value: style.backdropFilter || "", passed: true});
      }
      window.webkit.messageHandlers.omiRuntimeProbe.postMessage({schema: "omi.native-runtime-marker/v1", domain, theme, accessibility, events});
    };
    probe();
  })();
  """#

  override init() { super.init() }

  func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
    guard message.name == "omiRuntimeProbe",
          let payload = message.body as? [String: Any],
          Set(payload.keys) == ["schema", "domain", "theme", "accessibility", "events"],
          payload["schema"] as? String == "omi.native-runtime-marker/v1",
          let domain = payload["domain"] as? String,
          ["memories", "tasks", "conversations", "folders", "listen", "chat", "settings"].contains(domain),
          let theme = payload["theme"] as? String,
          ["light", "dark"].contains(theme),
          let accessibility = payload["accessibility"] as? String,
          ["none", "reduced_motion", "reduced_transparency"].contains(accessibility),
          let events = payload["events"] as? [[String: Any]], !events.isEmpty, events.count <= 16 else { return }
    let eventTypes = ["lifecycle", "computed_style", "native_runtime"]
    let states = ["loading", "empty", "ready", "error", "offline", "busy", "complete", "cancelled"]
    let names = ["state", "transition_duration", "transition_property", "animation_name", "animation_duration", "motion_policy", "backdrop_filter", "material_transparency", "transparency_policy"]
    for event in events {
      guard Set(event.keys) == ["type", "name", "value", "passed"],
            let type = event["type"] as? String, eventTypes.contains(type),
            let name = event["name"] as? String, names.contains(name),
            let value = event["value"] as? String, !value.isEmpty, value.count <= 256,
            value.range(of: "^[A-Za-z0-9][A-Za-z0-9 ._():,/%+\\-]{0,255}$", options: .regularExpression) != nil,
            event["passed"] as? Bool == true else { return }
      if type == "lifecycle" && (name != "state" || !states.contains(value)) { return }
    }
    guard let bytes = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]), bytes.count < 16_384 else { return }
    let encoded = bytes.base64EncodedString()
      .replacingOccurrences(of: "+", with: "-")
      .replacingOccurrences(of: "/", with: "_")
      .replacingOccurrences(of: "=", with: "")
    // Locate the owning view through the message's web view; no arbitrary body
    // or user text is copied into the identifier.
    message.webView?.accessibilityIdentifier = "OMI_RUNTIME_JSON_\(encoded)"
  }
}
