import AppKit
import Foundation

// MARK: - Link state

/// The public-facing linking state the WhatsApp UI drives against. Mirrors the sidecar's
/// state machine (`unlinked | connecting | waiting_qr | linked | logged_out`), plus local
/// process states.
enum WhatsAppLinkState: Equatable, Sendable {
  /// Sidecar not running (nothing spawned yet, or it exited).
  case stopped
  /// Sidecar spawned, waiting for its ready handshake.
  case starting
  /// Sidecar up, no saved session, no link attempt in progress.
  case unlinked
  /// Negotiating with WhatsApp servers (fresh link or session resume).
  case connecting
  /// A QR code is ready to scan (base64 PNG data URL).
  case waitingScan(qrDataUrl: String)
  /// Linked and usable. `phone` is the account's number (digits only).
  case linked(phone: String)
  /// The phone unlinked this device — the saved session was cleared.
  case loggedOut
  /// A terminal-ish local failure (node missing, sidecar crashed, …).
  case error(String)

  var isLinked: Bool {
    if case .linked = self { return true }
    return false
  }
}

enum WhatsAppSendError: LocalizedError {
  case notLinked
  case sidecarUnavailable(String)
  case sendFailed(String)
  case contactNotResolvable(String)

  var errorDescription: String? {
    switch self {
    case .notLinked:
      return "WhatsApp isn't linked yet — scan the QR code from the AI Clone page first."
    case .sidecarUnavailable(let detail):
      return "The WhatsApp connector couldn't start: \(detail)"
    case .sendFailed(let detail):
      return "Couldn't send the WhatsApp message: \(detail)"
    case .contactNotResolvable(let name):
      return
        "Couldn't match \"\(name)\" to a WhatsApp number. Ask them to message you once, or make sure the chat name matches a contact."
    }
  }
}

// MARK: - Observable model for SwiftUI

/// Bridges the actor's link state onto the main actor so SwiftUI can observe it.
/// The actor owns the truth; this is a thin, published mirror (same pattern as
/// `TelegramLoginModel`).
@MainActor
final class WhatsAppLinkModel: ObservableObject {
  static let shared = WhatsAppLinkModel()
  @Published private(set) var state: WhatsAppLinkState = .stopped

  fileprivate func apply(_ newState: WhatsAppLinkState) {
    state = newState
  }
}

// MARK: - Service

/// WhatsApp send + live-receive service — the WhatsApp counterpart to
/// `IMessageSendService` / `TelegramSendService`, so the AI Clone send-mode layer treats
/// all three platforms uniformly:
///   * `send(to:text:)`
///   * `startListening(onNewMessage:)` / `stopListening()`
///
/// Unlike the other two, WhatsApp has no local database or official API for personal
/// accounts. This talks to a local-only Node sidecar (`whatsapp-sidecar/`) running Baileys,
/// which joins the account via WhatsApp's own "Linked Devices" (the WhatsApp Web mechanism).
/// That is an UNOFFICIAL connection method — the app treats it with extra caution: sends
/// only ever happen through the send-mode coordinator's kill-switch/mode gates, and enabling
/// Autonomous for a WhatsApp contact additionally requires a one-time explicit risk
/// acknowledgment (see `AICloneSendModeService`).
///
/// The sidecar is spawned on demand (mirroring `AgentRuntimeProcess`'s node lifecycle),
/// bound to 127.0.0.1 with a per-spawn bearer token, and tethered to this process — it
/// exits when the app dies, so no orphaned Node processes.
actor WhatsAppSendService {
  static let shared = WhatsAppSendService()

  /// Poll cadence for new-message detection while listening.
  private static let eventPollInterval: TimeInterval = 2.5

  // MARK: Process + HTTP state

  private var process: Process?
  private var stdinPipe: Pipe?
  private var port: Int = WhatsAppSendService.defaultPort
  private var token = ""
  private var readySignaled = false
  private var currentState: WhatsAppLinkState = .stopped

  private var listenerTask: Task<Void, Never>?
  private var onNewMessage:
    (@Sendable (_ phone: String, _ fromMe: Bool, _ text: String, _ date: Date, _ senderName: String?) -> Void)?
  /// Highest event `seq` consumed. Seeded to the sidecar's latest on listen start so we
  /// never replay events buffered before listening began.
  private var eventCursor: Int64 = -1

  /// Synchronous handle for `applicationWillTerminate` (can't await an actor there).
  private static let quitTerminator = ProcessTerminator()

  private static var defaultPort: Int {
    if let raw = ProcessInfo.processInfo.environment["OMI_WA_PORT"], let value = Int(raw) {
      return value
    }
    return 47790
  }

  /// Session persists here so relinking isn't needed after the first QR scan.
  static var sessionDirectory: URL {
    let base =
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
      ?? FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support", isDirectory: true)
    return base.appendingPathComponent("Omi/whatsapp-session", isDirectory: true)
  }

  // MARK: - Public state

  func state() -> WhatsAppLinkState { currentState }

  /// True when a previous session exists on disk — the sidecar will resume it without a QR.
  nonisolated static func hasSavedSession() -> Bool {
    FileManager.default.fileExists(
      atPath: sessionDirectory.appendingPathComponent("creds.json").path)
  }

  // MARK: - Linking

  /// Ensure the sidecar is running and begin (or resume) linking. Returns the resulting
  /// state; the UI keeps polling `refreshStatus()` afterward for QR/linked transitions.
  @discardableResult
  func startLinking() async -> WhatsAppLinkState {
    do {
      try await ensureSidecar()
      _ = try await request(path: "/link/start", method: "POST")
      return await refreshStatus()
    } catch {
      let message = (error as? WhatsAppSendError)?.localizedDescription ?? error.localizedDescription
      await setState(.error(message))
      return currentState
    }
  }

  /// One status poll against the sidecar; updates and returns the published state.
  @discardableResult
  func refreshStatus() async -> WhatsAppLinkState {
    guard process?.isRunning == true else {
      if case .error = currentState { return currentState }
      await setState(.stopped)
      return currentState
    }
    do {
      let json = try await request(path: "/link/status", method: "GET")
      await setState(Self.linkState(fromStatusJson: json))
    } catch {
      await setState(.error("Lost contact with the WhatsApp connector."))
    }
    return currentState
  }

  /// Unlink: tells WhatsApp to log this device out and clears the saved session.
  func logout() async {
    guard process?.isRunning == true else { return }
    _ = try? await request(path: "/logout", method: "POST")
    _ = await refreshStatus()
  }

  /// Map the sidecar's `/link/status` JSON onto the Swift state. Pure for testability.
  nonisolated static func linkState(fromStatusJson json: [String: Any]) -> WhatsAppLinkState {
    switch json["state"] as? String {
    case "linked":
      return .linked(phone: json["phone"] as? String ?? "")
    case "waiting_qr":
      if let qr = json["qrDataUrl"] as? String, !qr.isEmpty {
        return .waitingScan(qrDataUrl: qr)
      }
      return .connecting
    case "connecting":
      return .connecting
    case "logged_out":
      return .loggedOut
    case "unlinked":
      return .unlinked
    default:
      return .error("Unknown WhatsApp connector state")
    }
  }

  // MARK: - Sending

  /// Send a plain-text message. `to` is a phone number (digits, `+`/spaces tolerated) or a
  /// full `…@s.whatsapp.net` JID. Requires a linked session; throws otherwise.
  func send(to: String, text: String) async throws {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { throw WhatsAppSendError.sendFailed("empty message") }
    try await ensureSidecar()
    guard (await refreshStatus()).isLinked else { throw WhatsAppSendError.notLinked }
    do {
      _ = try await request(path: "/send", method: "POST", body: ["to": to, "text": trimmed])
    } catch let error as SidecarHTTPError {
      throw WhatsAppSendError.sendFailed(error.message)
    }
  }

  /// Resolve a contact display name to a phone number using the linked account's synced
  /// contacts. Returns nil when there is no unambiguous match.
  func resolvePhone(forName name: String) async -> String? {
    guard process?.isRunning == true, currentState.isLinked else { return nil }
    guard
      let encoded = name.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
      let json = try? await request(path: "/resolve?name=\(encoded)", method: "GET"),
      let phone = json["phone"] as? String, !phone.isEmpty
    else { return nil }
    return phone
  }

  // MARK: - Listening

  /// Begin polling the sidecar for new 1:1 messages. The callback fires for both directions
  /// (`fromMe` distinguishes them), mirroring the other platforms; `senderName` carries the
  /// sender's WhatsApp push-name so the send-mode layer can match imported contacts by name.
  func startListening(
    onNewMessage: @escaping @Sendable (
      _ phone: String, _ fromMe: Bool, _ text: String, _ date: Date, _ senderName: String?
    ) -> Void
  ) {
    self.onNewMessage = onNewMessage
    guard listenerTask == nil else { return }
    eventCursor = -1
    listenerTask = Task { [weak self] in
      while !Task.isCancelled {
        await self?.pollEvents()
        try? await Task.sleep(nanoseconds: UInt64(Self.eventPollInterval * 1_000_000_000))
      }
    }
  }

  func stopListening() {
    listenerTask?.cancel()
    listenerTask = nil
    onNewMessage = nil
    eventCursor = -1
  }

  private func pollEvents() async {
    guard onNewMessage != nil, process?.isRunning == true else { return }
    // First pass anchors the cursor to the sidecar's latest seq — never replay buffered
    // history from before listening started (same baseline pattern as IMessageSendService).
    let sinceParam = max(0, eventCursor)
    guard let json = try? await request(path: "/events?since=\(sinceParam)", method: "GET"),
      let latest = json["latest"] as? Int64 ?? (json["latest"] as? Int).map(Int64.init)
    else { return }
    if eventCursor < 0 {
      eventCursor = latest
      return
    }
    eventCursor = max(eventCursor, latest)
    guard let events = json["events"] as? [[String: Any]], !events.isEmpty,
      let onNewMessage
    else { return }
    for event in events {
      guard let phone = event["phone"] as? String, !phone.isEmpty,
        let text = event["text"] as? String, !text.isEmpty
      else { continue }
      let fromMe = event["fromMe"] as? Bool ?? false
      let timestamp = (event["timestamp"] as? Double) ?? Double(event["timestamp"] as? Int ?? 0)
      let senderName = event["senderName"] as? String
      onNewMessage(phone, fromMe, text, Date(timeIntervalSince1970: timestamp), senderName)
    }
  }

  // MARK: - Sidecar process lifecycle

  /// Spawn the sidecar if it isn't running. Mirrors `AgentRuntimeProcess`: find node, find
  /// the script, pipe stdin (the tether that kills the child if we die), wait for the ready
  /// line on stdout.
  func ensureSidecar() async throws {
    if process?.isRunning == true { return }
    process = nil
    readySignaled = false
    await setState(.starting)

    guard let nodePath = Self.findNodeBinary() else {
      await setState(.error("Node.js not found — install node (brew install node)."))
      throw WhatsAppSendError.sidecarUnavailable("node binary not found")
    }
    guard let scriptPath = Self.findSidecarScript() else {
      await setState(.error("WhatsApp connector files are missing from this build."))
      throw WhatsAppSendError.sidecarUnavailable("sidecar script not found")
    }
    let sidecarRoot = ((scriptPath as NSString).deletingLastPathComponent as NSString)
      .deletingLastPathComponent
    let modulesPath = (sidecarRoot as NSString).appendingPathComponent("node_modules/@whiskeysockets")
    guard FileManager.default.fileExists(atPath: modulesPath) else {
      await setState(.error("WhatsApp connector dependencies missing (run npm install in whatsapp-sidecar)."))
      throw WhatsAppSendError.sidecarUnavailable("node_modules missing at \(sidecarRoot)")
    }

    token = UUID().uuidString
    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: nodePath)
    proc.arguments = ["--max-old-space-size=192", scriptPath]
    proc.currentDirectoryURL = URL(fileURLWithPath: sidecarRoot)

    var env = ProcessInfo.processInfo.environment
    env["NODE_NO_WARNINGS"] = "1"
    env["OMI_WA_PORT"] = String(port)
    env["OMI_WA_TOKEN"] = token
    env["OMI_WA_SESSION_DIR"] = Self.sessionDirectory.path
    env["OMI_WA_PARENT_PID"] = String(ProcessInfo.processInfo.processIdentifier)
    proc.environment = env

    let stdin = Pipe()
    let stdout = Pipe()
    let stderr = Pipe()
    proc.standardInput = stdin
    proc.standardOutput = stdout
    proc.standardError = stderr

    stderr.fileHandleForReading.readabilityHandler = { handle in
      let data = handle.availableData
      if !data.isEmpty, let text = String(data: data, encoding: .utf8) {
        log("WhatsAppSendService sidecar stderr: \(text.trimmingCharacters(in: .whitespacesAndNewlines).prefix(400))")
      }
    }

    proc.terminationHandler = { [weak self] terminated in
      log("WhatsAppSendService: sidecar exited (code=\(terminated.terminationStatus))")
      Task { await self?.handleSidecarExit() }
    }

    do {
      try proc.run()
    } catch {
      await setState(.error("Couldn't start the WhatsApp connector: \(error.localizedDescription)"))
      throw WhatsAppSendError.sidecarUnavailable(error.localizedDescription)
    }
    process = proc
    stdinPipe = stdin
    Self.quitTerminator.set(proc)
    log("WhatsAppSendService: sidecar started (pid=\(proc.processIdentifier), port=\(port))")

    // Wait for the single-line ready handshake on stdout (or early exit).
    let ready = await Self.waitForReadyLine(handle: stdout.fileHandleForReading, timeout: 15)
    stdout.fileHandleForReading.readabilityHandler = nil
    guard ready, proc.isRunning else {
      await stopSidecar()
      await setState(.error("The WhatsApp connector didn't start correctly."))
      throw WhatsAppSendError.sidecarUnavailable("ready handshake timed out")
    }
    readySignaled = true
    _ = await refreshStatus()
  }

  /// Terminate the sidecar (listening stops; the saved session on disk is untouched).
  func stopSidecar() async {
    stopListening()
    guard let proc = process else { return }
    try? stdinPipe?.fileHandleForWriting.close()
    proc.terminate()
    let start = Date()
    while proc.isRunning && Date().timeIntervalSince(start) < 2.0 {
      try? await Task.sleep(nanoseconds: 50_000_000)
    }
    if proc.isRunning {
      kill(proc.processIdentifier, SIGKILL)
    }
    process = nil
    stdinPipe = nil
    Self.quitTerminator.set(nil)
    await setState(.stopped)
  }

  private func handleSidecarExit() async {
    process = nil
    stdinPipe = nil
    Self.quitTerminator.set(nil)
    // Startup failures set their own `.error` state; only a post-ready exit becomes .stopped.
    guard readySignaled else { return }
    if case .error = currentState { return }
    await setState(.stopped)
  }

  /// Best-effort synchronous kill for `applicationWillTerminate`. The stdin tether and the
  /// sidecar's parent-PID watchdog make this redundant, but exiting cleanly is politer.
  nonisolated static func terminateSidecarOnQuit() {
    quitTerminator.terminate()
  }

  private static func waitForReadyLine(handle: FileHandle, timeout: TimeInterval) async -> Bool {
    await withCheckedContinuation { continuation in
      let box = ContinuationBox(continuation)
      handle.readabilityHandler = { fileHandle in
        let data = fileHandle.availableData
        if data.isEmpty {
          fileHandle.readabilityHandler = nil
          box.resume(false)
          return
        }
        guard let text = box.appendAndSnapshot(data) else { return }
        if text.contains("\"type\":\"ready\"") {
          fileHandle.readabilityHandler = nil
          box.resume(true)
        } else if text.contains("\"type\":\"error\"") {
          fileHandle.readabilityHandler = nil
          log("WhatsAppSendService: sidecar reported startup error: \(text.prefix(300))")
          box.resume(false)
        }
      }
      Task {
        try? await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
        box.resume(false)
      }
    }
  }

  /// One-shot continuation guard: the ready handshake can be resolved by the reader, the
  /// timeout, or an early EOF — whichever fires first wins, the rest are no-ops.
  private final class ContinuationBox: @unchecked Sendable {
    private let lock = NSLock()
    private var continuation: CheckedContinuation<Bool, Never>?
    private var buffer = Data()
    init(_ continuation: CheckedContinuation<Bool, Never>) { self.continuation = continuation }
    func resume(_ value: Bool) {
      lock.lock()
      let taken = continuation
      continuation = nil
      lock.unlock()
      taken?.resume(returning: value)
    }
    /// Accumulate stdout bytes and return the buffered text so far (nil if not valid UTF-8).
    func appendAndSnapshot(_ data: Data) -> String? {
      lock.lock()
      buffer.append(data)
      let snapshot = String(data: buffer, encoding: .utf8)
      lock.unlock()
      return snapshot
    }
  }

  /// Lock-guarded Process holder so `applicationWillTerminate` (synchronous, non-actor)
  /// can terminate the sidecar without hopping onto the actor.
  private final class ProcessTerminator: @unchecked Sendable {
    private let lock = NSLock()
    private var process: Process?
    func set(_ proc: Process?) {
      lock.lock()
      process = proc
      lock.unlock()
    }
    func terminate() {
      lock.lock()
      let proc = process
      process = nil
      lock.unlock()
      if let proc, proc.isRunning { proc.terminate() }
    }
  }

  // MARK: - HTTP plumbing

  private struct SidecarHTTPError: Error {
    let status: Int
    let message: String
  }

  private func request(
    path: String, method: String, body: [String: Any]? = nil
  ) async throws -> [String: Any] {
    var urlRequest = URLRequest(url: URL(string: "http://127.0.0.1:\(port)\(path)")!)
    urlRequest.httpMethod = method
    urlRequest.timeoutInterval = 20
    urlRequest.setValue(token, forHTTPHeaderField: "x-omi-token")
    if let body {
      urlRequest.httpBody = try JSONSerialization.data(withJSONObject: body)
      urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
    }
    let (data, response) = try await URLSession.shared.data(for: urlRequest)
    let json = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    let status = (response as? HTTPURLResponse)?.statusCode ?? 0
    guard (200..<300).contains(status) else {
      throw SidecarHTTPError(
        status: status, message: json["error"] as? String ?? "HTTP \(status)")
    }
    return json
  }

  // MARK: - State plumbing

  private func setState(_ newState: WhatsAppLinkState) async {
    currentState = newState
    await MainActor.run { WhatsAppLinkModel.shared.apply(newState) }
  }

  // MARK: - Binary/script discovery (mirrors AgentRuntimeProcess)

  private static func findNodeBinary() -> String? {
    let bundledNode = Bundle.resourceBundle.path(forResource: "node", ofType: nil)
    if let bundledNode, FileManager.default.isExecutableFile(atPath: bundledNode) {
      return bundledNode
    }
    let candidates = ["/opt/homebrew/bin/node", "/usr/local/bin/node", "/usr/bin/node"]
    for path in candidates where FileManager.default.isExecutableFile(atPath: path) {
      return path
    }
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    let nvmDir = (home as NSString).appendingPathComponent(".nvm/versions/node")
    if let versions = try? FileManager.default.contentsOfDirectory(atPath: nvmDir) {
      for version in versions.sorted(by: { $0.compare($1, options: .numeric) == .orderedDescending }) {
        let nodePath = (nvmDir as NSString).appendingPathComponent("\(version)/bin/node")
        if FileManager.default.isExecutableFile(atPath: nodePath) {
          return nodePath
        }
      }
    }
    return nil
  }

  private static func findSidecarScript() -> String? {
    let relative = "whatsapp-sidecar/src/index.js"
    if let bundlePath = Bundle.main.resourcePath {
      let bundled = (bundlePath as NSString).appendingPathComponent(relative)
      if FileManager.default.fileExists(atPath: bundled) {
        return bundled
      }
    }
    if let execDir = Bundle.main.executableURL?.deletingLastPathComponent() {
      let devPaths = [
        execDir.appendingPathComponent("../../../\(relative)").path,
        execDir.appendingPathComponent("../../../../\(relative)").path,
      ]
      for path in devPaths {
        let resolved = (path as NSString).standardizingPath
        if FileManager.default.fileExists(atPath: resolved) {
          return resolved
        }
      }
    }
    let cwd = FileManager.default.currentDirectoryPath
    for candidate in [relative, "desktop/macos/\(relative)", "../desktop/macos/\(relative)"] {
      let resolved = ((cwd as NSString).appendingPathComponent(candidate) as NSString).standardizingPath
      if FileManager.default.fileExists(atPath: resolved) {
        return resolved
      }
    }
    // Dev fallback: the app runs from /Applications but the repo lives in the home dir.
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    let repoPath = (home as NSString).appendingPathComponent("omi/desktop/macos/\(relative)")
    if FileManager.default.fileExists(atPath: repoPath) {
      return repoPath
    }
    return nil
  }
}
