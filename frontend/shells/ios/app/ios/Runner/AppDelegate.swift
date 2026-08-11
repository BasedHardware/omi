import Flutter
import UIKit
import WebKit
import AVFoundation

// ============================================================================
// Ship-origin host: WKURLSchemeHandler serving the surface bundle from
// omi-ui://local/ (ADR-009 — origin is frozen; IndexedDB is origin-keyed).
//
// The handler is registered on a WKWebViewConfiguration that WE own, inside
// OmiUiWebView (FlutterPlatformView). No process-wide WKWebView init swizzle.
// ============================================================================

final class OmiSchemeHandler: NSObject, WKURLSchemeHandler {
  static let shared = OmiSchemeHandler()
  static let scheme = "omi-ui"

  private let lock = NSLock()
  private var activeDir: String = ""
  // Guard for the documented stop-race (forums thread 712430): WebKit crashes
  // if didReceive/didFinish arrive after stopURLSchemeTask.
  private var stopped = Set<ObjectIdentifier>()
  private var requestLog: [String] = []

  func setActiveDir(_ path: String) {
    lock.lock(); activeDir = path; lock.unlock()
    record("setActiveDir \(path)")
  }

  func drainLog() -> [String] {
    lock.lock(); defer { lock.unlock() }
    let out = requestLog; requestLog = []
    return out
  }

  private func record(_ line: String) {
    let stamped = "\(Date().timeIntervalSince1970) \(line)"
    lock.lock()
    requestLog.append(stamped)
    if requestLog.count > 1000 { requestLog.removeFirst() }
    lock.unlock()
    NSLog("[scheme] %@", line)
  }

  private static let mime: [String: String] = [
    "html": "text/html; charset=utf-8", "js": "text/javascript",
    "mjs": "text/javascript", "css": "text/css", "json": "application/json",
    "svg": "image/svg+xml", "png": "image/png", "txt": "text/plain",
  ]

  func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
    let t0 = Date()
    let req = task.request
    guard let url = req.url else { return }
    let headers = req.allHTTPHeaderFields ?? [:]
    let headerDump = headers.map { "\($0)=\($1)" }.sorted().joined(separator: " ")
    let bodyBytes = req.httpBody?.count
    record("\(req.httpMethod ?? "?") \(url.absoluteString) headers[\(headerDump)] bodyBytes=\(bodyBytes.map(String.init) ?? "nil") bodyStream=\(req.httpBodyStream != nil)")

    if url.path == "/probe/echo" {
      // Echo what actually reached the handler -- the page logs this, which is
      // how we capture Origin/Cookie/body behavior on the custom scheme.
      var bodyText = "(nil)"
      if let b = req.httpBody { bodyText = String(data: b.prefix(200), encoding: .utf8) ?? "(binary)" }
      let payload: [String: Any] = [
        "method": req.httpMethod ?? "?", "url": url.absoluteString,
        "receivedHeaders": headers, "bodyBytes": bodyBytes ?? -1,
        "body": bodyText, "hasBodyStream": req.httpBodyStream != nil,
      ]
      let data = try! JSONSerialization.data(withJSONObject: payload)
      send(task, url: url, status: 200, mime: "application/json", data: data)
      return
    }

    lock.lock()
    let dir = activeDir
    lock.unlock()
    var rel = url.path.isEmpty || url.path == "/" ? "/index.html" : url.path
    rel = rel.removingPercentEncoding ?? rel
    let filePath = (dir as NSString).appendingPathComponent(rel)
    guard dir != "", let data = FileManager.default.contents(atPath: filePath) else {
      record("404 \(rel) (activeDir=\(dir))")
      send(task, url: url, status: 404, mime: "text/plain", data: Data("not found: \(rel)".utf8))
      return
    }
    let ext = (rel as NSString).pathExtension.lowercased()
    send(task, url: url, status: 200, mime: Self.mime[ext] ?? "application/octet-stream", data: data)
    record("200 \(rel) \(data.count)B +\(Int(Date().timeIntervalSince(t0) * 1000))ms")
  }

  func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {
    lock.lock(); stopped.insert(ObjectIdentifier(task)); lock.unlock()
    record("STOP \(task.request.url?.absoluteString ?? "?")")
  }

  private func isStopped(_ task: WKURLSchemeTask) -> Bool {
    lock.lock(); defer { lock.unlock() }
    return stopped.contains(ObjectIdentifier(task))
  }

  private func send(_ task: WKURLSchemeTask, url: URL, status: Int, mime: String, data: Data) {
    guard !isStopped(task) else { return }
    // Vite ship builds mark <script crossorigin> / <link crossorigin>, so
    // module fetches run in CORS mode against omi-ui://local. Mirror Capacitor
    // and advertise ACAO so those loads succeed (probe bundles had no
    // crossorigin attribute and never exercised this path).
    let resp = HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1",
      headerFields: [
        "Content-Type": mime,
        "Content-Length": "\(data.count)",
        "Cache-Control": "no-store",
        "Access-Control-Allow-Origin": "*",
      ])!
    task.didReceive(resp)
    guard !isStopped(task) else { return }
    task.didReceive(data)
    guard !isStopped(task) else { return }
    task.didFinish()
    lock.lock(); stopped.remove(ObjectIdentifier(task)); lock.unlock()
  }
}

// -- Registration hook: SPIKE-ONLY, and it is on borrowed time ---------------
//
// This exchanges WKWebView's designated initializer so every
// WKWebViewConfiguration created in the process — including the ones
// webview_flutter builds internally and never exposes — gets the omi-ui
// handler. It cannot ship: exchanging an init-family IMP is an ARC ownership
// violation, and it is process-global, so it silently affects webviews Omi does
// not own.
//
// It is still here for one measured reason. The replacement (OmiUiWebView, a
// platform view that owns its own configuration) is implemented and registered
// below, but nothing uses it yet: app/lib/main.dart drives a
// webview_flutter WebViewController for navigation, JS channels, the navigation
// delegate, and runJavaScript — including the LIVE bridge reply path. Adopting
// the platform view means reimplementing that controller surface, which is real
// work, not a rename.
//
// Removing the hook before that work lands does not make the shell more
// shippable, it makes it non-functional. Verified, not assumed — with the hook
// deleted the simulator reports:
//   WEB-RESOURCE-ERROR -1002 unsupported URL omi-ui://local/index.html
// i.e. no handler is registered for the scheme and the surface never loads.
//
// See decisions/FE-SHELLS-ios-nonswizzle-scheme.md for the remaining work.
extension WKWebView {
  @objc dynamic func omi_initWithFrame(_ frame: CGRect, configuration: WKWebViewConfiguration) -> WKWebView {
    if configuration.urlSchemeHandler(forURLScheme: OmiSchemeHandler.scheme) == nil {
      configuration.setURLSchemeHandler(OmiSchemeHandler.shared, forURLScheme: OmiSchemeHandler.scheme)
    }
    return omi_initWithFrame(frame, configuration: configuration)
  }

  static func omiInstallSchemeHandlerHook() {
    guard
      let orig = class_getInstanceMethod(WKWebView.self, NSSelectorFromString("initWithFrame:configuration:")),
      let repl = class_getInstanceMethod(WKWebView.self, #selector(WKWebView.omi_initWithFrame(_:configuration:)))
    else { return }
    method_exchangeImplementations(orig, repl)
    NSLog("[scheme] SPIKE-ONLY WKWebView init hook installed — see OmiUiWebView for the ship path")
  }
}

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  private func listenPreflightPayload() -> [String: Any] {
    let session = AVAudioSession.sharedInstance()
    let permission: String
    let recovery: String?
    switch session.recordPermission {
    case .undetermined:
      permission = "unknown"
      recovery = "request-permission"
    case .granted:
      permission = "granted"
      recovery = nil
    case .denied:
      permission = "denied"
      recovery = "open-settings"
    @unknown default:
      permission = "unavailable"
      recovery = nil
    }
    let hasInput = !session.currentRoute.inputs.isEmpty || !(session.availableInputs?.isEmpty ?? true)
    let deviceState: String
    if permission == "granted" {
      deviceState = hasInput ? "available" : "unavailable"
    } else if permission == "unknown" {
      deviceState = "unknown"
    } else {
      deviceState = "unavailable"
    }
    return [
      "permission": permission,
      "deviceState": deviceState,
      "deviceLabel": hasInput && permission == "granted" ? "Default microphone" : NSNull(),
      "recovery": recovery ?? NSNull(),
    ]
  }

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    WKWebView.omiInstallSchemeHandlerHook()
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    guard let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "OmiSchemeSpike") else { return }

    let channel = FlutterMethodChannel(name: "omi/scheme", binaryMessenger: registrar.messenger())
    channel.setMethodCallHandler { call, result in
      switch call.method {
      case "docsDir":
        result(NSSearchPathForDirectoriesInDomains(.documentDirectory, .userDomainMask, true).first!)
      case "setActiveBundle":
        OmiSchemeHandler.shared.setActiveDir(call.arguments as! String)
        result(true)
      case "drainSchemeLog":
        result(OmiSchemeHandler.shared.drainLog())
      default:
        result(FlutterMethodNotImplemented)
      }
    }

    // Capture-only builds obtain their per-coordinate values from the native
    // process arguments. Dart's Platform.executableArguments does not expose
    // UIKit launch arguments, so this narrow host channel returns only the two
    // allowlisted capture prefixes; it never exposes ambient arguments or
    // credentials to the surface JavaScript.
    let captureLaunch = FlutterMethodChannel(
      name: "omi/capture-launch", binaryMessenger: registrar.messenger())
    captureLaunch.setMethodCallHandler { call, result in
      if call.method == "arguments" {
        let prefixes = ["--omi-capture-query=", "--omi-capture-run-id="]
        result(ProcessInfo.processInfo.arguments.filter { argument in
          prefixes.contains { argument.hasPrefix($0) }
        })
        return
      }
      if call.method == "ready" {
        let noncePrefix = "--omi-capture-nonce="
        guard
          let payload = call.arguments as? [String: String],
          Set(payload.keys) == Set(["run_id", "route", "fixture", "state"]),
          let runId = payload["run_id"],
          let route = payload["route"],
          let fixture = payload["fixture"],
          let state = payload["state"],
          runId.range(of: "^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$", options: .regularExpression) != nil,
          route.range(of: "^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$", options: .regularExpression) != nil,
          fixture.range(of: "^polish:[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$", options: .regularExpression) != nil,
          state.range(of: "^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$", options: .regularExpression) != nil,
          ProcessInfo.processInfo.arguments.contains("--omi-capture-run-id=\(runId)"),
          let nonceArgument = ProcessInfo.processInfo.arguments.first(where: {
            $0.hasPrefix(noncePrefix)
          })
        else {
          result(FlutterError(code: "capture-ready-invalid", message: nil, details: nil))
          return
        }
        let nonce = String(nonceArgument.dropFirst(noncePrefix.count))
        guard nonce.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil else {
          result(FlutterError(code: "capture-ready-invalid", message: nil, details: nil))
          return
        }
        let marker: [String: String] = [
          "fixture": fixture,
          "nonce": nonce,
          "route": route,
          "run_id": runId,
          "state": state,
        ]
        do {
          guard let cache = FileManager.default.urls(
            for: .cachesDirectory, in: .userDomainMask
          ).first else {
            throw CocoaError(.fileNoSuchFile)
          }
          let data = try JSONSerialization.data(withJSONObject: marker, options: [.sortedKeys])
          try data.write(
            to: cache.appendingPathComponent("omi-native-capture-ready.json"),
            options: .atomic)
        } catch {
          result(FlutterError(code: "capture-ready-write-failed", message: nil, details: nil))
          return
        }
        NSLog(
          "NATIVE_CAPTURE_READY run_id=%@ route=%@ fixture=%@ state=%@",
          runId, route, fixture, state)
        result(true)
        return
      }
      result(FlutterMethodNotImplemented)
    }

    let listenPreflight = FlutterMethodChannel(
      name: "omi/listen-preflight", binaryMessenger: registrar.messenger())
    listenPreflight.setMethodCallHandler { [weak self] call, result in
      guard let self else {
        result(FlutterError(code: "host-gone", message: nil, details: nil))
        return
      }
      switch call.method {
      case "check":
        result(self.listenPreflightPayload())
      case "requestPermission":
        AVAudioSession.sharedInstance().requestRecordPermission { _ in
          DispatchQueue.main.async { result(self.listenPreflightPayload()) }
        }
      case "openSettings":
        guard let url = URL(string: UIApplication.openSettingsURLString) else {
          result(false)
          return
        }
        UIApplication.shared.open(url) { opened in result(opened) }
      default:
        result(FlutterMethodNotImplemented)
      }
    }

    registrar.register(
      OmiUiWebViewFactory(messenger: registrar.messenger()),
      withId: OmiUiWebViewFactory.viewType
    )
  }
}
