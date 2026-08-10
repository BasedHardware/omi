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

/// The two provenance stamps this bundle carries: the shell it was compiled
/// from (`Contents/Resources/omi-build-stamp.json`, written by
/// scripts/build-shell.sh), and the surfaces bundle it serves
/// (`Contents/Resources/surface/omi-build-stamp.json`, written by the
/// surfaces build). They legitimately differ and are read separately — see
/// integration/lib/provenance.mjs.
///
/// Resolved via `Bundle.main.resourceURL`, the same seam `resolveSurfaceRoot()`
/// already uses successfully for this unsigned swiftc-built bundle. It is
/// plist/bundle-structure-driven lookup, not code-signature-driven, so an
/// unsigned bundle resolves it exactly like a signed one; deriving from
/// `CommandLine.arguments[0]` would duplicate that same relative-path logic
/// with none of its existing precedent.
let shellStampURL = Bundle.main.resourceURL?.appendingPathComponent("omi-build-stamp.json")
let surfaceStampURL = Bundle.main.resourceURL?
  .appendingPathComponent("surface", isDirectory: true)
  .appendingPathComponent("omi-build-stamp.json")

/// Per-run client identity for the privileged HTTP bridge (`OMI_RUN_CLIENT_ID`).
/// Threaded into `BridgeHttpHandler`'s init below rather than read from
/// `ProcessInfo` inside `BridgeHttpPolicy`, so that seam stays a pure function
/// the generated host-conformance runner can call without an environment.
/// Absent/empty means "send no header" — the backend buckets those reads
/// under its own `anonymous` key; never fabricate a value here.
let runClientId: String? = env["OMI_RUN_CLIENT_ID"].flatMap { $0.isEmpty ? nil : $0 }

/// Extract a `<commit12>/<tree12>` summary from a build-stamp JSON file for the
/// ACCEPTANCE line, or the literal `"unavailable"` when the file is missing,
/// unparseable, or is itself a `{"unavailable": ...}` fallback stamp written by
/// a build that could not compute provenance. Never a blank or fabricated
/// value — minimal hand-rolled extraction via JSONSerialization, no new
/// dependency.
func provenanceStampSummary(at url: URL?) -> String {
  guard let url, let data = try? Data(contentsOf: url) else { return "unavailable" }
  guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
    return "unavailable"
  }
  if obj["unavailable"] is String { return "unavailable" }
  guard let commit = obj["commit"] as? String, let treeHash = obj["treeHash"] as? String,
    !commit.isEmpty, !treeHash.isEmpty
  else { return "unavailable" }
  return "\(commit.prefix(12))/\(treeHash.prefix(12))"
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
  private let listen: ListenSocketHandler?
  private let chatStream: ChatStreamHandler?
  private let chatAttachmentStaging: ChatAttachmentStagingHandler?
  private var tornDown = false
  var onCommittedURL: ((URL) -> Void)?
  var onFinishedNavigation: (() -> Void)?

  init(
    handlers: NativeHandlers, frame: NSRect, loadURL: URL,
    http: BridgeHttpHandler?, listen: ListenSocketHandler?,
    chatStream: ChatStreamHandler?, chatAttachmentStaging: ChatAttachmentStagingHandler?
  ) {
    self.loadURL = loadURL
    self.http = http
    self.listen = listen
    self.chatStream = chatStream
    self.chatAttachmentStaging = chatAttachmentStaging
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
    if let listen {
      config.userContentController.add(listen, name: ListenSocketHandler.channel)
    }
    if let chatStream {
      config.userContentController.add(chatStream, name: ChatStreamHandler.channel)
    }
    if let chatAttachmentStaging {
      config.userContentController.addScriptMessageHandler(
        chatAttachmentStaging, contentWorld: .page,
        name: ChatAttachmentStagingHandler.channel)
    }
    webView.navigationDelegate = self
    if #available(macOS 13.3, *) { webView.isInspectable = true }
  }

  /// Load only after the view is in a visible window. Loading a webview that is
  /// not yet on screen leaves `document.visibilityState === "hidden"`, which
  /// suspends requestAnimationFrame and timers in the page.
  func start() {
    load(loadURL)
  }

  func load(_ url: URL) {
    if url.isFileURL {
      webView.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
    } else {
      webView.load(URLRequest(url: url))
    }
  }

  func teardown() {
    guard !tornDown else { return }
    tornDown = true
    ticker?.invalidate()
    ticker = nil
    listen?.cancelAll()
    chatStream?.teardown()
    chatAttachmentStaging?.teardown()
    let content = webView.configuration.userContentController
    content.removeScriptMessageHandler(forName: BridgeDispatcher.messageHandlerName)
    content.removeScriptMessageHandler(forName: ListenSocketHandler.channel)
    content.removeScriptMessageHandler(forName: ChatStreamHandler.channel)
    content.removeScriptMessageHandler(
      forName: BridgeHttpHandler.channel, contentWorld: .page)
    content.removeScriptMessageHandler(
      forName: ChatAttachmentStagingHandler.channel, contentWorld: .page)
    webView.navigationDelegate = nil
  }

  deinit {
    MainActor.assumeIsolated { teardown() }
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

  func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
    onFinishedNavigation?()
  }

  func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
    // A new document owns a new JS sink/registry. Observation and staging work
    // from the previous document must not route into it.
    listen?.cancelAll()
    chatStream?.cancelAll()
    chatAttachmentStaging?.cancelAll()
  }

  func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
    listen?.cancelAll()
    chatStream?.cancelAll()
    chatAttachmentStaging?.cancelAll()
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
  var listenSocketHandler: ListenSocketHandler?
  var chatStreamHandler: ChatStreamHandler?
  var chatAttachmentStagingHandler: ChatAttachmentStagingHandler?
  var consumerEvidenceDriver: ConsumerEvidenceDriver?
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
    let succeeded = httpHandler?.succeededCount ?? 0
    // Surface-ready/snapshot are lifecycle hints, not proof that the async
    // refresh reached the host. Keep the probe alive until traffic arrives or
    // the bounded timeout below turns the absence into a real failure.
    if succeeded == 0 && phase != "ready-timeout" {
      scheduleAcceptanceFallback()
      return true
    }
    acceptanceEmitted = true
    acceptanceFallbackScheduled = false
    // PASS KEYS ON SUCCESSES, NOT DISPATCHES. servedCount increments before the
    // response arrives, so a shell whose every request 401s reports a healthy
    // nonzero servedCount while the app renders an empty list. That was observed
    // directly on this branch (servedCount=4, "0 loaded items", "No results")
    // and it is the wave-9 false-green restated. A dispatched request that
    // failed is not served traffic.
    acceptancePassed = succeeded > 0
    let bridge = httpHandler == nil ? "disabled" : "enabled"
    let status = acceptancePassed ? "PASS" : "FAIL"
    let traffic = httpHandler?.trafficSummary ?? "dispatched=0 succeeded=0"
    // Appended AFTER the existing fields so dev-stack.sh's `status=PASS` /
    // `httpError=` substring greps keep matching unchanged. shellStamp is the
    // tree the shell binary was compiled from; surfaceStamp is the tree the
    // bundle it is serving was built from — they can legitimately differ and
    // are read from two separate files (see the doc comment above
    // shellStampURL). clientId echoes what was actually sent on the wire
    // (or "none" if OMI_RUN_CLIENT_ID was absent/empty, matching the backend's
    // own "anonymous" bucket for the same case) — never a fabricated value.
    let shellStamp = provenanceStampSummary(at: shellStampURL)
    let surfaceStamp = provenanceStampSummary(at: surfaceStampURL)
    let clientIdField = runClientId ?? "none"
    let line =
      "ACCEPTANCE phase=\(phase) bridge=\(bridge) \(traffic) servedCount=\(served) status=\(status)"
      + " shellStamp=\(shellStamp) surfaceStamp=\(surfaceStamp) clientId=\(clientIdField)\n"
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
    if acceptanceEnabled && !acceptanceEmitted && (httpHandler?.succeededCount ?? 0) == 0 {
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
    // Privileged-HTTP custody: SessionBootstrap resolves base URL + token via
    // Keychain → optional scratch issuer → OMI_API_TOKEN env. Neither value is
    // ever handed to JS. The SEAM is unchanged: surface sends a relative path,
    // shell owns the rest. No resolvable base URL => no handler registered =>
    // the surface truthfully feature-detects "no bridge" and falls back to DEV.
    let session = SessionBootstrap.resolve(environment: env)
    FileHandle.standardError.write(
      Data(
        "session-bootstrap: path=\(session.path.rawValue) store=\(session.storeLogDescription) token=\(session.tokenPresent ? "present" : "absent")\n"
          .utf8))
    var httpHandler: BridgeHttpHandler?
    var listenSocketHandler: ListenSocketHandler?
    var chatStreamHandler: ChatStreamHandler?
    var chatAttachmentStagingHandler: ChatAttachmentStagingHandler?
    if let base = session.baseURL {
      let keychain = KeychainCredentialStore()
      let authority = ShellTransportAuthority(
        baseURL: base, token: session.token,
        onSuccessfulSignOut: {
          do {
            try SessionBootstrap.deleteCredential(for: base, from: keychain)
          } catch {
            FileHandle.standardError.write(
              Data("bridge-http: origin-scoped credential delete failed\n".utf8))
          }
        })
      httpHandler = authority.makeHTTPHandler(clientId: runClientId)
      listenSocketHandler = authority.makeListenHandler(clientId: runClientId)
      chatStreamHandler = ChatStreamHandler(
        baseURL: base, custody: authority.custody, runId: runClientId)
      chatAttachmentStagingHandler = ChatAttachmentStagingHandler(
        baseURL: base, custody: authority.custody, runId: runClientId)
      FileHandle.standardError.write(
        Data(
          "bridge-http: enabled for \(base.scheme!)://\(base.host!) (token \(session.tokenPresent ? "present" : "absent"))\n"
            .utf8))
    } else {
      FileHandle.standardError.write(
        Data("bridge-http: disabled (set OMI_API_BASE_URL to enable privileged HTTP)\n".utf8))
    }
    self.httpHandler = httpHandler
    self.listenSocketHandler = listenSocketHandler
    self.chatStreamHandler = chatStreamHandler
    self.chatAttachmentStagingHandler = chatAttachmentStagingHandler
    controller = WebViewController(
      handlers: handlers, frame: contentRect, loadURL: surfaceLoad.url,
      http: httpHandler, listen: listenSocketHandler,
      chatStream: chatStreamHandler, chatAttachmentStaging: chatAttachmentStagingHandler)
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
    if let resultPath = env["OMI_CONSUMER_EVIDENCE_PATH"], !resultPath.isEmpty {
      let resultURL = URL(fileURLWithPath: resultPath)
      try? FileManager.default.removeItem(at: resultURL)
      do {
        guard let runClientId else { throw ConsumerEvidenceError.invalidRunId }
        let hashes = try ConsumerEvidenceTreeHashes.load(
          shellStamp: shellStampURL, surfaceStamp: surfaceStampURL)
        let collector = try ConsumerEvidenceCollector(
          resultURL: resultURL, runId: runClientId, shell: "macos", hashes: hashes)
        let driver = ConsumerEvidenceDriver(collector: collector, baseURL: surfaceLoad.url)
        consumerEvidenceDriver = driver
        controller.onFinishedNavigation = { [weak driver] in driver?.pageDidFinish() }
      } catch {
        FileHandle.standardError.write(
          Data("CONSUMER-EVIDENCE: FAIL \(error)\n".utf8))
        if env["OMI_CONSUMER_EVIDENCE_EXIT"] == "1" { Darwin.exit(1) }
      }
    }
    window.contentView = glassHost
    // Scratch QA bundles must always open at the approved comparison frame.
    // Explicitly set this after installing the content view: assigning a new
    // root view can otherwise inherit a stale undersized content geometry.
    window.setContentSize(contentRect.size)
    window.standardWindowButton(.closeButton)?.isHidden = true
    window.standardWindowButton(.miniaturizeButton)?.isHidden = true
    window.standardWindowButton(.zoomButton)?.isHidden = true
    // ── HEADLESS IS THE DEFAULT. HEADED IS OPT-IN. ──────────────────────────
    //
    // An agent loop that steals focus every 90 seconds is not usable. This shell
    // is launched by automation far more often than by a person — the launcher
    // alone starts it twice per run — and every one of those launches used to
    // pop a window to the front and take the keyboard.
    //
    // Headless costs NO evidence, which is what makes this cheap: bridge
    // traffic, JS execution, `evaluateJavaScript`, the loopback server and
    // `WKWebView.takeSnapshot` (OMI_SNAPSHOT_PATH) all work perfectly without a
    // visible window. Only WINDOW-COMPOSITED pixel evidence needs a real window
    // on screen, and that is a headed, human-initiated activity.
    //
    //   .accessory      no Dock icon, no menu bar, cannot take focus.
    //   offscreen order the window is ordered in far off-screen rather than left
    //                   unordered, because an unordered window gets its
    //                   WKWebView paint throttled — which would make snapshots
    //                   blank and quietly cost us the evidence this whole
    //                   program is about. Ordered-but-offscreen paints normally
    //                   and is invisible.
    //
    // OMI_HEADED=1 restores the old behavior in full.
    let headed = env["OMI_HEADED"] == "1"
    installMenu()
    if headed {
      NSApp.setActivationPolicy(.regular)
      window.center()
      window.makeKeyAndOrderFront(nil)
      NSApp.activate(ignoringOtherApps: true)
    } else {
      NSApp.setActivationPolicy(.accessory)
      // Far outside any plausible display arrangement, so it cannot appear on a
      // second monitor either.
      window.setFrameOrigin(NSPoint(x: -30000, y: -30000))
      window.orderBack(nil)
    }
    FileHandle.standardError.write(Data("display-mode: \(headed ? "headed" : "headless (OMI_HEADED=1 to show a window)")\n".utf8))
    if let consumerEvidenceDriver {
      consumerEvidenceDriver.start(with: controller)
    } else {
      controller.start()
    }
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
    consumerEvidenceDriver?.teardown()
    controller?.teardown()
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
  // Set the policy BEFORE the app finishes launching, not only in the delegate.
  // `.regular` here would flash a Dock icon and pull focus for the moment before
  // applicationDidFinishLaunching runs — a smaller version of exactly the
  // problem, and the kind that is easy to call fixed because the window itself
  // no longer appears.
  app.setActivationPolicy(ProcessInfo.processInfo.environment["OMI_HEADED"] == "1" ? .regular : .accessory)
  objc_setAssociatedObject(app, "omi.delegate", delegate, .OBJC_ASSOCIATION_RETAIN)
  app.run()
}
