// Minimal macOS shell: one window, one WKWebView, one generated typed bridge,
// plus an in-process loopback that serves the shared @omi-core/surfaces dist/.
// Hand-written surface area is deliberately small; everything protocol-shaped
// comes from Bridge.generated.swift.
import AppKit
import Darwin
import WebKit

let env = ProcessInfo.processInfo.environment

/// Fixed loopback port. Storage (IndexedDB) is origin-keyed including the port —
/// changing this wipes the offline task queue across relaunches.
let loopbackPort: UInt16 = {
  UInt16(env["OMI_SURFACE_PORT"] ?? "") ?? LoopbackServer.defaultPort
}()

/// Resolve the static surface root: env override, then bundled Resources/surface.
func resolveSurfaceRoot() -> URL? {
  if let dir = env["OMI_SURFACE_DIR"], !dir.isEmpty {
    return URL(fileURLWithPath: dir, isDirectory: true)
  }
  if let res = Bundle.main.resourceURL?
    .appendingPathComponent("surface", isDirectory: true)
  {
    let index = res.appendingPathComponent("index.html")
    if FileManager.default.fileExists(atPath: index.path) { return res }
  }
  return nil
}

func redactedURL(_ url: URL) -> String {
  guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
    return "(invalid-url)"
  }
  components.query = nil
  components.fragment = nil
  components.user = nil
  components.password = nil
  return components.url?.absoluteString ?? "(invalid-url)"
}

/// Apply an optional path/query to every load strategy, including a bundled
/// loopback server. `OMI_SURFACE_PATH=/?selftest=1` remains accepted for the
/// existing probe scripts; `OMI_SURFACE_QUERY` is the explicit query-only form.
func configuredSurfaceURL(_ base: URL) -> URL {
  guard var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else { return base }
  var path = env["OMI_SURFACE_PATH"]
  var query = env["OMI_SURFACE_QUERY"]
  if let rawPath = path, let marker = rawPath.firstIndex(of: "?") {
    path = String(rawPath[..<marker])
    if query == nil { query = String(rawPath[rawPath.index(after: marker)...]) }
  }
  if let path, !path.isEmpty {
    components.path = path.hasPrefix("/") ? path : "/\(path)"
  }
  if let query {
    components.query = query.hasPrefix("?") ? String(query.dropFirst()) : query
  }
  if let profile = env["OMI_SURFACE_PROFILE"], !profile.isEmpty {
    var items = components.queryItems ?? []
    items.removeAll { $0.name == "profile" }
    items.append(URLQueryItem(name: "profile", value: profile))
    components.queryItems = items
  }
  var items = components.queryItems ?? []
  items.removeAll { $0.name == "nativeGlass" }
  items.append(URLQueryItem(name: "nativeGlass", value: "1"))
  components.queryItems = items
  return components.url ?? base
}

/// Production-shaped path: shell owns the loopback origin and serves dist/.
/// `OMI_SURFACE_URL` still overrides for alternate-load probes (file://, external).
let surfaceLoad: (server: LoopbackServer?, url: URL) = {
  if let raw = env["OMI_SURFACE_URL"], let u = URL(string: raw) {
    return (nil, configuredSurfaceURL(u))
  }
  guard let root = resolveSurfaceRoot() else {
    let port = String(loopbackPort)
    return (nil, configuredSurfaceURL(URL(string: "http://127.0.0.1:\(port)/")!))
  }
  let server = LoopbackServer(root: root, port: loopbackPort)
  return (server, configuredSurfaceURL(server.originURL))
}()

// MARK: - Native side of the bridge (the only hand-written bridge code)

final class NativeHandlers: BridgeHandling, @unchecked Sendable {
  weak var emitter: WebViewController?
  private var sessionId: String?
  private var startedAt: Date?
  private var settings = [
    "capture.autoStart": "false",
    "capture.sampleRateHz": "16000",
    "ui.theme": "system",
  ]

  func startCapture(_ params: StartCaptureParams) async throws -> StartCaptureResult {
    let id = "sess-\(Int(Date().timeIntervalSince1970))"
    sessionId = id
    startedAt = Date()
    await emitter?.startTicking(handler: self)
    return StartCaptureResult(sessionId: id, state: .starting)
  }

  func readSetting(_ params: ReadSettingParams) async throws -> ReadSettingResult {
    ReadSettingResult(key: params.key, value: settings[params.key])
  }

  func openExternal(_ params: OpenExternalParams) async throws -> OpenExternalResult {
    guard let url = URL(string: params.url), url.scheme == "https" else {
      return OpenExternalResult(opened: false)
    }
    let ok = NSWorkspace.shared.open(url)
    return OpenExternalResult(opened: ok)
  }

  /// Fake capture telemetry so the native -> surface direction is exercised.
  func currentStatus() -> CaptureStatusEvent {
    let elapsed = startedAt.map { Int(Date().timeIntervalSince($0) * 1000) } ?? 0
    return CaptureStatusEvent(
      sessionId: sessionId,
      state: sessionId == nil ? .idle : (elapsed < 1200 ? .starting : .recording),
      elapsedMs: elapsed,
      levelDb: -60 + Double.random(in: 0...42)
    )
  }
}

// MARK: - Window + webview

/// A page can be transparent while WKWebView's AppKit host still advertises an
/// opaque backing store. Keep the public view and layer contracts clear so the
/// compositor never substitutes a white rectangle around the glass islands.
final class TransparentWKWebView: WKWebView {
  override var isOpaque: Bool { false }

  override func viewDidMoveToWindow() {
    super.viewDidMoveToWindow()
    wantsLayer = true
    layer?.isOpaque = false
    layer?.backgroundColor = NSColor.clear.cgColor
  }
}

@MainActor
final class WebViewController: NSObject, WKScriptMessageHandler, WKNavigationDelegate {
  let webView: WKWebView
  private let dispatcher: BridgeDispatcher
  private var ticker: Timer?
  private let loadURL: URL
  private let http: BridgeHttpHandler?
  var onCommittedURL: ((URL) -> Void)?

  init(handlers: NativeHandlers, frame: NSRect, loadURL: URL, http: BridgeHttpHandler?) {
    self.loadURL = loadURL
    self.http = http
    let config = WKWebViewConfiguration()
    config.defaultWebpagePreferences.allowsContentJavaScript = true
    let webView = TransparentWKWebView(frame: frame, configuration: config)
    webView.wantsLayer = true
    webView.layer?.isOpaque = false
    webView.layer?.backgroundColor = NSColor.clear.cgColor
    if #available(macOS 11.0, *) { webView.underPageBackgroundColor = .clear }
    self.webView = webView
    self.dispatcher = BridgeDispatcher(handler: handlers)
    super.init()
    handlers.emitter = self
    config.userContentController.add(self, name: BridgeDispatcher.messageHandlerName)
    // Privileged HTTP: reply-capable, so postMessage() returns a promise in JS.
    // Registered only when the shell actually holds a base URL, so the surface's
    // feature detection is truthful — no handler means no bridge mode.
    if let http {
      config.userContentController.addScriptMessageHandler(
        http, contentWorld: .page, name: BridgeHttpHandler.channel)
    }
    webView.navigationDelegate = self
    if #available(macOS 13.3, *) { webView.isInspectable = true }
  }

  /// Load only after the view is in a visible window. Loading a webview that is
  /// not yet on screen leaves `document.visibilityState === "hidden"`, which
  /// suspends requestAnimationFrame and timers in the page.
  func start() {
    if loadURL.isFileURL {
      webView.loadFileURL(loadURL, allowingReadAccessTo: loadURL.deletingLastPathComponent())
    } else {
      webView.load(URLRequest(url: loadURL))
    }
  }

  func userContentController(
    _ controller: WKUserContentController, didReceive message: WKScriptMessage
  ) {
    guard let dict = message.body as? [String: Any],
      let raw = try? JSONSerialization.data(withJSONObject: dict)
    else { return }
    let dispatcher = self.dispatcher
    Task { @MainActor in
      let js = await dispatcher.dispatch(raw: raw)
      self.webView.evaluateJavaScript(js, completionHandler: nil)
    }
  }

  func startTicking(handler: NativeHandlers) {
    ticker?.invalidate()
    ticker = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
      MainActor.assumeIsolated {
        guard let self else { return }
        self.webView.evaluateJavaScript(
          BridgeDispatcher.emitCaptureStatus(handler.currentStatus()), completionHandler: nil)
      }
    }
  }

  func webView(_ webView: WKWebView, didFailProvisionalNavigation nav: WKNavigation!, withError e: Error) {
    let html = """
      <body style="font:14px -apple-system;padding:40px;color:#888">
      <h3>Surface not reachable</h3><p>\(redactedURL(loadURL))</p>
      <p>\(e.localizedDescription)</p>
      <p>Rebuild with <code>scripts/build-shell.sh</code> (bundles surfaces dist), then relaunch.</p></body>
      """
    webView.loadHTMLString(html, baseURL: nil)
  }

  func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
    guard let url = webView.url else { return }
    onCommittedURL?(url)
  }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
  var window: NSWindow!
  var controller: WebViewController!
  var glassHost: GlassHostView!
  var loopback: LoopbackServer?
  /// Retained so the reply-capable message handler outlives registration.
  var httpHandler: BridgeHttpHandler?
  private let env = ProcessInfo.processInfo.environment
  private var acceptanceEmitted = false
  private var acceptancePassed = true
  private var acceptanceFallbackScheduled = false

  private var acceptanceEnabled: Bool {
    env["OMI_ACCEPTANCE"] != nil || env["OMI_ACCEPTANCE_EXIT"] != nil
  }

  /// Emit a stable, secret-free acceptance line. The count is host-observed
  /// traffic, not a JS claim; URL/token custody never enters this output.
  @discardableResult
  private func emitAcceptance(phase: String) -> Bool {
    guard acceptanceEnabled else { return true }
    guard !acceptanceEmitted else { return acceptancePassed }
    let served = httpHandler?.servedCount ?? 0
    // Surface-ready/snapshot are lifecycle hints, not proof that the async
    // refresh reached the host. Keep the probe alive until traffic arrives or
    // the bounded timeout below turns the absence into a real failure.
    if served == 0 && phase != "ready-timeout" {
      scheduleAcceptanceFallback()
      return true
    }
    acceptanceEmitted = true
    acceptanceFallbackScheduled = false
    acceptancePassed = served > 0
    let bridge = httpHandler == nil ? "disabled" : "enabled"
    let status = acceptancePassed ? "PASS" : "FAIL"
    let line = "ACCEPTANCE phase=\(phase) bridge=\(bridge) servedCount=\(served) status=\(status)\n"
    FileHandle.standardError.write(Data(line.utf8))
    return acceptancePassed
  }

  private func scheduleAcceptanceFallback() {
    guard acceptanceEnabled, !acceptanceEmitted, !acceptanceFallbackScheduled else { return }
    acceptanceFallbackScheduled = true
    DispatchQueue.main.asyncAfter(deadline: .now() + 5) { [weak self] in
      guard let self, !self.acceptanceEmitted else { return }
      self.acceptanceFallbackScheduled = false
      let passed = self.emitAcceptance(phase: "ready-timeout")
      if self.env["OMI_ACCEPTANCE_EXIT"] != nil { Darwin.exit(passed ? 0 : 1) }
      if self.env["OMI_PROBE_EXIT"] != nil { NSApp.terminate(nil) }
    }
  }

  private func terminateForProbe() {
    // An acceptance-exit probe must not turn a still-in-flight refresh into an
    // immediate failure. The bounded fallback emits the terminal result.
    if acceptanceEnabled && !acceptanceEmitted && (httpHandler?.servedCount ?? 0) == 0 {
      scheduleAcceptanceFallback()
      return
    }
    let passed = emitAcceptance(phase: "exit")
    if env["OMI_ACCEPTANCE_EXIT"] != nil && !passed { Darwin.exit(1) }
    NSApp.terminate(nil)
  }

  func applicationDidFinishLaunching(_ note: Notification) {
    if let server = surfaceLoad.server {
      do {
        try server.start()
        loopback = server
      } catch {
        let alert = NSAlert()
        alert.messageText = "Loopback failed to bind"
        alert.informativeText =
          "Port \(loopbackPort) — \(error.localizedDescription)\nIndexedDB origin requires this fixed port."
        alert.runModal()
      }
    }

    let contentRect = NSRect(x: 0, y: 0, width: 934, height: 671)
    let handlers = NativeHandlers()
    // Privileged-HTTP custody lives here: the shell reads the API base URL and
    // bearer token from its own environment and never hands either to JS.
    // Dev-grade custody for this prototype (Keychain custody is owed) — but the
    // SEAM is the ship shape: surface sends a relative path, shell owns the rest.
    // No OMI_API_BASE_URL => no handler registered => the surface truthfully
    // feature-detects "no bridge" and falls back to its DEV transport.
    var httpHandler: BridgeHttpHandler?
    if let raw = env["OMI_API_BASE_URL"], let base = URL(string: raw), base.scheme != nil, base.host != nil {
      httpHandler = BridgeHttpHandler(baseURL: base, token: env["OMI_API_TOKEN"])
      FileHandle.standardError.write(
        Data("bridge-http: enabled for \(base.scheme!)://\(base.host!) (token \(env["OMI_API_TOKEN"]?.isEmpty == false ? "present" : "absent"))\n".utf8))
    } else {
      FileHandle.standardError.write(
        Data("bridge-http: disabled (set OMI_API_BASE_URL to enable privileged HTTP)\n".utf8))
    }
    self.httpHandler = httpHandler
    controller = WebViewController(
      handlers: handlers, frame: contentRect, loadURL: surfaceLoad.url, http: httpHandler)
    window = NSWindow(
      contentRect: contentRect,
      styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
      backing: .buffered, defer: false)
    window.title = "Omi"
    window.titlebarAppearsTransparent = true
    window.titleVisibility = .hidden
    window.titlebarSeparatorStyle = .none
    window.isOpaque = false
    window.backgroundColor = .clear
    window.appearance = NSAppearance(named: .aqua)
    window.hasShadow = false
    window.isMovableByWindowBackground = true
    window.isRestorable = false
    window.contentMinSize = NSSize(width: 760, height: 560)
    glassHost = GlassHostView(
      frame: contentRect,
      webView: controller.webView,
      composition: GlassHostLayout.resolve(from: surfaceLoad.url))
    controller.onCommittedURL = { [weak glassHost] url in
      glassHost?.setComposition(GlassHostLayout.resolve(from: url))
    }
    window.contentView = glassHost
    // Scratch QA bundles must always open at the approved comparison frame.
    // Explicitly set this after installing the content view: assigning a new
    // root view can otherwise inherit a stale undersized content geometry.
    window.setContentSize(contentRect.size)
    window.standardWindowButton(.closeButton)?.isHidden = true
    window.standardWindowButton(.miniaturizeButton)?.isHidden = true
    window.standardWindowButton(.zoomButton)?.isHidden = true
    window.center()
    window.makeKeyAndOrderFront(nil)
    installMenu()
    NSApp.activate(ignoringOtherApps: true)
    controller.start()
    // Diagnostic hook: OMI_PROBE_JS=<expr> prints the evaluated result to stdout
    // after load, so load strategies can be checked from a script.
    if env["OMI_PROBE_NATIVE"] != nil {
      let wv = controller.webView
      let sels: [(String, Selector)] = [
        ("copy:", #selector(NSText.copy(_:))), ("paste:", #selector(NSText.paste(_:))),
        ("selectAll:", #selector(NSText.selectAll(_:))), ("undo:", Selector(("undo:"))),
      ]
      let responds = sels.map { "\($0.0)=\(wv.responds(to: $0.1))" }.joined(separator: " ")
      let line = """
        PROBE_NATIVE: \(responds)         acceptsFirstResponder=\(wv.acceptsFirstResponder)         allowsMagnification=\(wv.allowsMagnification)         effectiveAppearance=\(wv.effectiveAppearance.name.rawValue) \
        webViewOpaque=\(wv.isOpaque) webLayerOpaque=\(wv.layer?.isOpaque ?? true) \
        windowOpaque=\(window.isOpaque) windowClear=\(window.backgroundColor == .clear) windowShadow=\(window.hasShadow) \
        windowVisible=\(window.isVisible) windowOccluded=\(!window.occlusionState.contains(.visible)) \
        appActive=\(NSApp.isActive) viewSize=\(wv.frame.size.width)x\(wv.frame.size.height)\n
        """
      FileHandle.standardError.write(Data(line.utf8))
    }
    if let probe = env["OMI_PROBE_JS"] {
      let delay = Double(env["OMI_PROBE_DELAY"] ?? "3") ?? 3
      // Extra settle time after kicking an async IIFE (Promise return is unsupported
      // on the completion-handler API; side effects still run).
      let settle = Double(env["OMI_PROBE_SETTLE"] ?? "3") ?? 3
      DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
        self?.controller.webView.evaluateJavaScript(probe) { value, error in
          let line = "PROBE_JS: \(value.map { "\($0)" } ?? "nil") error: \(error.map { "\($0)" } ?? "none")\n"
          FileHandle.standardError.write(Data(line.utf8))
          DispatchQueue.main.asyncAfter(deadline: .now() + settle) {
            self?.maybeSnapshotThenExit(after: 0)
          }
        }
      }
    } else {
      maybeSnapshotThenExit(after: 2.5)
    }
  }

  /// Optional PNG of the live WKWebView (works without Screen Recording TCC).
  /// Set OMI_SNAPSHOT_PATH=/path/out.png — used when screencapture is unavailable.
  private func maybeSnapshotThenExit(after delay: Double = 0.4) {
    guard let path = env["OMI_SNAPSHOT_PATH"], !path.isEmpty else {
      if acceptanceEnabled { _ = emitAcceptance(phase: "settled") }
      if env["OMI_PROBE_EXIT"] != nil || env["OMI_ACCEPTANCE_EXIT"] != nil {
        terminateForProbe()
      }
      return
    }
    DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
      guard let self else { return }
      let config = WKSnapshotConfiguration()
      self.controller.webView.takeSnapshot(with: config) { image, error in
        if let image {
          let url = URL(fileURLWithPath: path)
          if let tiff = image.tiffRepresentation,
            let rep = NSBitmapImageRep(data: tiff),
            let png = rep.representation(using: .png, properties: [:])
          {
            try? png.write(to: url)
            FileHandle.standardError.write(Data("SNAPSHOT: wrote \(path) (\(png.count) bytes)\n".utf8))
          }
        } else {
          FileHandle.standardError.write(
            Data("SNAPSHOT: failed \(error.map { "\($0)" } ?? "nil")\n".utf8))
        }
        if self.acceptanceEnabled { _ = self.emitAcceptance(phase: "snapshot") }
        if self.env["OMI_PROBE_EXIT"] != nil || self.env["OMI_ACCEPTANCE_EXIT"] != nil {
          self.terminateForProbe()
        }
      }
    }
  }

  func applicationWillTerminate(_ notification: Notification) {
    loopback?.stop()
  }

  func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }

  /// Standard menu bar: proves Cmd-C/V/A, Cmd-R reload, and services reach the webview.
  private func installMenu() {
    let main = NSMenu()
    let appItem = NSMenuItem()
    let appMenu = NSMenu()
    appMenu.addItem(withTitle: "About omi-core-tasks-shell", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
    appMenu.addItem(.separator())
    appMenu.addItem(withTitle: "Quit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
    appItem.submenu = appMenu
    main.addItem(appItem)

    let editItem = NSMenuItem()
    let edit = NSMenu(title: "Edit")
    for (t, sel, key) in [
      ("Undo", Selector(("undo:")), "z"), ("Redo", Selector(("redo:")), "Z"),
      ("Cut", #selector(NSText.cut(_:)), "x"), ("Copy", #selector(NSText.copy(_:)), "c"),
      ("Paste", #selector(NSText.paste(_:)), "v"), ("Select All", #selector(NSText.selectAll(_:)), "a"),
    ] { edit.addItem(withTitle: t, action: sel, keyEquivalent: key) }
    editItem.submenu = edit
    main.addItem(editItem)

    let viewItem = NSMenuItem()
    let view = NSMenu(title: "View")
    view.addItem(withTitle: "Reload Surface", action: #selector(reload), keyEquivalent: "r")
    view.addItem(withTitle: "Enter Full Screen", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
    viewItem.submenu = view
    main.addItem(viewItem)
    NSApp.mainMenu = main
  }

  @objc private func reload() { controller.webView.reload() }
}

MainActor.assumeIsolated {
  let app = NSApplication.shared
  let delegate = AppDelegate()
  app.delegate = delegate
  app.setActivationPolicy(.regular)
  objc_setAssociatedObject(app, "omi.delegate", delegate, .OBJC_ASSOCIATION_RETAIN)
  app.run()
}
