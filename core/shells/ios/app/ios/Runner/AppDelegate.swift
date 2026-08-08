import Flutter
import UIKit
import WebKit

// ============================================================================
// Ship-origin spike, candidate B: WKURLSchemeHandler serving the surface
// bundle from omi-ui://local/. This is the "thin in-house platform plugin"
// shape: ~150 lines of Swift, a method channel, zero new dependencies.
//
// Injection mechanism (spike-only): webview_flutter builds its
// WKWebViewConfiguration internally and exposes no hook, so we swizzle
// WKWebView's designated initializer and register the handler on every
// configuration that passes through. A production plugin would put the same
// handler class behind a real registration API (small fork of
// webview_flutter_wkwebview or a first-party platform view); the handler --
// the part under test -- is identical either way.
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

// -- Swizzle: register the handler on every WKWebViewConfiguration -----------
// Note: exchanging an init-family IMP with a plain method is the widely used
// spike pattern; ARC ownership mismatch is theoretical for an init that
// returns self. Production code uses a real registration API instead.
extension WKWebView {
  @objc dynamic func omi_initWithFrame(_ frame: CGRect, configuration: WKWebViewConfiguration) -> WKWebView {
    if configuration.urlSchemeHandler(forURLScheme: OmiSchemeHandler.scheme) == nil {
      configuration.setURLSchemeHandler(OmiSchemeHandler.shared, forURLScheme: OmiSchemeHandler.scheme)
      NSLog("[scheme] handler registered on configuration for %@://", OmiSchemeHandler.scheme)
    }
    // Implementations are exchanged: this call runs the original initializer.
    return omi_initWithFrame(frame, configuration: configuration)
  }

  static func omiInstallSchemeHandlerHook() {
    guard
      let orig = class_getInstanceMethod(WKWebView.self, NSSelectorFromString("initWithFrame:configuration:")),
      let repl = class_getInstanceMethod(WKWebView.self, #selector(WKWebView.omi_initWithFrame(_:configuration:)))
    else { return }
    method_exchangeImplementations(orig, repl)
    NSLog("[scheme] WKWebView init hook installed")
  }
}

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
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
  }
}
