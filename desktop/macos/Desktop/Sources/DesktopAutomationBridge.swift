import AppKit
import Foundation
import Network

enum DesktopAutomationLaunchOptions {
  static let enableFlag = "--automation-bridge"
  static let portPrefix = "--automation-port="
  static let captureRootPrefix = "--automation-capture-root="
  static let defaultPort: UInt16 = 47777

  static var isEnabled: Bool {
    // Explicit opt-out always wins, so a dev build can be run "clean" if needed.
    if ProcessInfo.processInfo.environment["OMI_DISABLE_LOCAL_AUTOMATION"] == "1" {
      return false
    }
    // Auto-enable on any non-production bundle (Omi Dev + every `omi-*` named test
    // bundle) so agents can drive the app without remembering a launch flag. The
    // listener only binds to 127.0.0.1 and is never enabled on the production bundle.
    return CommandLine.arguments.contains(enableFlag)
      || ProcessInfo.processInfo.environment["OMI_ENABLE_LOCAL_AUTOMATION"] == "1"
      || AppBuild.isNonProduction
  }

  static var port: UInt16 {
    for argument in CommandLine.arguments {
      guard argument.hasPrefix(portPrefix) else { continue }
      let rawValue = String(argument.dropFirst(portPrefix.count))
      if let parsed = UInt16(rawValue) {
        return parsed
      }
    }

    if let rawValue = ProcessInfo.processInfo.environment["OMI_AUTOMATION_PORT"],
      let parsed = UInt16(rawValue)
    {
      return parsed
    }

    return defaultPort
  }

  static var captureRoot: URL {
    for argument in CommandLine.arguments {
      guard argument.hasPrefix(captureRootPrefix) else { continue }
      let rawValue = String(argument.dropFirst(captureRootPrefix.count))
      if !rawValue.isEmpty {
        return URL(fileURLWithPath: rawValue).standardizedFileURL
      }
    }

    if let rawValue = ProcessInfo.processInfo.environment["OMI_AUTOMATION_CAPTURE_ROOT"],
      !rawValue.isEmpty
    {
      return URL(fileURLWithPath: rawValue).standardizedFileURL
    }

    return URL(fileURLWithPath: NSTemporaryDirectory())
      .appendingPathComponent("omi-harness", isDirectory: true)
      .standardizedFileURL
  }
}

struct DesktopAutomationSnapshot: Codable {
  var bridgeEnabled: Bool
  var bridgePort: UInt16
  var bundleIdentifier: String
  var appState: String
  var selectedTab: String?
  var selectedTabIndex: Int?
  var selectedSettingsSection: String?
  var highlightedSettingId: String?
  var usesLegacyHomeDesign: Bool
  var showsPrimarySidebar: Bool
  var isSidebarCollapsed: Bool
  var hasCompletedOnboarding: Bool
  var isSignedIn: Bool
  var isRestoringAuth: Bool
  var isAppActive: Bool
  var mainWindowTitle: String?
  var floatingBarVisible: Bool
  var askOmiOpen: Bool
  var askOmiFocused: Bool
  var floatingBarFrame: String?
  var floatingBarVoiceListening: Bool
  var floatingBarVoiceResponseActive: Bool
  var floatingBarUsesNotchIsland: Bool
  var updatedAt: String
}

struct DesktopAutomationNavigationRequest: Codable {
  let target: String
  let settingsSection: String?
  let highlightedSettingId: String?
  let activateApp: Bool?
  let settleMs: Int?
}

struct DesktopAutomationOpenConversationRequest: Codable {
  let conversationId: String
  let showTranscript: Bool?
  let activateApp: Bool?
  let settleMs: Int?
}

struct DesktopAutomationVisualExportRequest: Codable {
  let path: String
  let target: String?
}

struct DesktopAutomationVisualExportResult: Codable {
  let path: String
  let width: Int
  let height: Int
}

struct DesktopAutomationExecuteExportRequest: Codable {
  let destination: String
}

/// Describes a semantic action exposed over `GET /actions` so an agent can discover
/// what it can drive without inspecting the UI tree.
struct DesktopAutomationActionDescriptor: Codable {
  let name: String
  let summary: String
  /// Names of params the handler reads (hints for the caller; not enforced).
  let params: [String]
}

/// Returned by `POST /action`: what ran, any handler detail, and the resulting state.
struct DesktopAutomationActionResult: Codable {
  let action: String
  let detail: [String: String]?
  let state: DesktopAutomationSnapshot
}

struct DesktopAutomationCapabilities: Codable {
  let schemaVersion: Int
  let routes: [String]
  let lanes: [String]
  let waits: [String]
  let assertions: [String]
  let artifactTypes: [String]
  let actions: [DesktopAutomationActionDescriptor]
}

struct DesktopAutomationRouteTrace: Codable {
  let method: String
  let path: String
  let statusCode: Int
  let durationMs: Double
  let finishedAt: String
}

enum DesktopAutomationActionError: LocalizedError {
  case unknownAction(String)
  case invalidParams(String)

  var errorDescription: String? {
    switch self {
    case .unknownAction(let name): return "unknown_action: \(name)"
    case .invalidParams(let detail): return "invalid_params: \(detail)"
    }
  }
}

private struct DesktopAutomationResponse<T: Codable>: Codable {
  let ok: Bool
  let result: T?
  let error: String?
}

final class DesktopAutomationStateStore {
  static let shared = DesktopAutomationStateStore()
  private let lock = NSLock()

  private var snapshot = DesktopAutomationSnapshot(
    bridgeEnabled: DesktopAutomationLaunchOptions.isEnabled,
    bridgePort: DesktopAutomationLaunchOptions.port,
    bundleIdentifier: Bundle.main.bundleIdentifier ?? "unknown",
    appState: "launching",
    selectedTab: nil,
    selectedTabIndex: nil,
    selectedSettingsSection: nil,
    highlightedSettingId: nil,
    usesLegacyHomeDesign: false,
    showsPrimarySidebar: false,
    isSidebarCollapsed: true,
    hasCompletedOnboarding: false,
    isSignedIn: false,
    isRestoringAuth: true,
    isAppActive: false,
    mainWindowTitle: nil,
    floatingBarVisible: false,
    askOmiOpen: false,
    askOmiFocused: false,
    floatingBarFrame: nil,
    floatingBarVoiceListening: false,
    floatingBarVoiceResponseActive: false,
    floatingBarUsesNotchIsland: false,
    updatedAt: ISO8601DateFormatter().string(from: Date())
  )

  func update(_ snapshot: DesktopAutomationSnapshot) {
    lock.lock()
    defer { lock.unlock() }
    self.snapshot = snapshot
  }

  func updateLiveFields(_ update: (inout DesktopAutomationSnapshot) -> Void) -> DesktopAutomationSnapshot {
    lock.lock()
    defer { lock.unlock() }
    update(&snapshot)
    return snapshot
  }

  func current() -> DesktopAutomationSnapshot {
    lock.lock()
    defer { lock.unlock() }
    return snapshot
  }
}

private func liveAutomationSnapshot() async -> DesktopAutomationSnapshot {
  let floating = await MainActor.run {
    let floating = FloatingControlBarManager.shared.automationState
    return (
      isVisible: floating.isVisible,
      isAskOmiOpen: floating.isAskOmiOpen,
      isAskOmiFocused: floating.isAskOmiFocused,
      frame: floating.frame,
      isVoiceListening: floating.isVoiceListening,
      isVoiceResponseActive: floating.isVoiceResponseActive,
      usesNotchIsland: floating.usesNotchIsland,
      isAppActive: NSApp.isActive
    )
  }
  return DesktopAutomationStateStore.shared.updateLiveFields { snapshot in
    snapshot.floatingBarVisible = floating.isVisible
    snapshot.askOmiOpen = floating.isAskOmiOpen
    snapshot.askOmiFocused = floating.isAskOmiFocused
    snapshot.floatingBarFrame = floating.frame
    snapshot.floatingBarVoiceListening = floating.isVoiceListening
    snapshot.floatingBarVoiceResponseActive = floating.isVoiceResponseActive
    snapshot.floatingBarUsesNotchIsland = floating.usesNotchIsland
    snapshot.isAppActive = floating.isAppActive
    snapshot.updatedAt = ISO8601DateFormatter().string(from: Date())
  }
}

private func cachedAutomationSnapshot() async -> DesktopAutomationSnapshot {
  var snapshot = DesktopAutomationStateStore.shared.current()
  snapshot.updatedAt = ISO8601DateFormatter().string(from: Date())
  return snapshot
}

actor DesktopAutomationTraceStore {
  static let shared = DesktopAutomationTraceStore()

  private var traces: [DesktopAutomationRouteTrace] = []
  private let formatter = ISO8601DateFormatter()

  func record(method: String, path: String, statusCode: Int, durationMs: Double) {
    traces.append(
      DesktopAutomationRouteTrace(
        method: method,
        path: path,
        statusCode: statusCode,
        durationMs: durationMs,
        finishedAt: formatter.string(from: Date())
      )
    )
    if traces.count > 200 {
      traces.removeFirst(traces.count - 200)
    }
  }

  func recent(limit: Int = 50) -> [DesktopAutomationRouteTrace] {
    Array(traces.suffix(max(1, min(limit, 200))))
  }

  func clear() {
    traces.removeAll(keepingCapacity: true)
  }
}

/// In-process registry of semantic, cursor-free actions the automation bridge can
/// run. Handlers invoke the app's real code (notifications, services) directly, so
/// no synthetic mouse events are ever generated — this is the deterministic
/// "command channel" equivalent of the Flutter app's Marionette driver.
///
/// Built-ins are registered at bridge startup. Feature code can register more via
/// `register(name:summary:params:handler:)` (e.g. from a view model's lifecycle) and
/// remove them with `unregister(_:)`.
@MainActor
final class DesktopAutomationActionRegistry {
  static let shared = DesktopAutomationActionRegistry()

  /// Handler runs on the main actor and returns optional string detail for the caller.
  typealias Handler = (_ params: [String: String]) async throws -> [String: String]?

  private struct Entry {
    let descriptor: DesktopAutomationActionDescriptor
    let run: Handler
  }

  private var entries: [String: Entry] = [:]
  private var didRegisterBuiltins = false

  func register(
    name: String, summary: String, params: [String] = [], handler: @escaping Handler
  ) {
    entries[name] = Entry(
      descriptor: DesktopAutomationActionDescriptor(name: name, summary: summary, params: params),
      run: handler)
  }

  func unregister(_ name: String) {
    entries[name] = nil
  }

  func descriptors() -> [DesktopAutomationActionDescriptor] {
    entries.values.map(\.descriptor).sorted { $0.name < $1.name }
  }

  func perform(_ name: String, params: [String: String]) async throws -> [String: String]? {
    guard let entry = entries[name] else {
      throw DesktopAutomationActionError.unknownAction(name)
    }
    return try await entry.run(params)
  }

  /// Register the always-available actions that don't need any view's `@State` —
  /// they post the same notifications / hit the same services as the real controls,
  /// so they exercise the genuine code paths. Idempotent.
  func registerBuiltins() {
    guard !didRegisterBuiltins else { return }
    didRegisterBuiltins = true

    AICloneHarness.register(on: self)
    TelegramLoginHarness.register(on: self)
    AICloneSendModeHarness.register(on: self)
    AICloneChatHarness.register(on: self)

    register(
      name: "refresh_all_data",
      summary: "Refresh conversations, chat, tasks, and memories (same as Cmd+R)"
    ) { _ in
      NotificationCenter.default.post(name: .refreshAllData, object: nil)
      return nil
    }

    register(
      name: "toggle_transcription",
      summary: "Enable or disable live transcription (mirrors the menu-bar toggle)",
      params: ["enabled"]
    ) { params in
      let enabled = boolParam(params["enabled"], default: true)
      AssistantSettings.shared.transcriptionEnabled = enabled
      NotificationCenter.default.post(
        name: .toggleTranscriptionRequested, object: nil, userInfo: ["enabled": enabled])
      return ["enabled": enabled ? "true" : "false"]
    }

    // Fake-voice end-to-end test: inject a raw PCM16/16kHz-mono file through the
    // real realtime omni STT path and return the transcript. No mic, no human.
    register(
      name: "omni_test_turn",
      summary: "Inject a raw PCM16/16kHz mono file through the omni STT path; returns the transcript",
      params: ["pcm", "timeout", "provider"]
    ) { params in
      guard let path = params["pcm"],
            let data = try? Data(contentsOf: URL(fileURLWithPath: path)), !data.isEmpty else {
        return ["error": "missing or unreadable 'pcm' file (expected raw s16le 16k mono)"]
      }
      let provider = params["provider"].flatMap(RealtimeOmniProvider.init(rawValue:))
        ?? RealtimeOmniSettings.shared.effectiveProvider
      let base = DesktopBackendEnvironment.pythonBaseURL()
      let authHeader: String
      do {
        authHeader = try await AuthService.shared.getAuthHeader()
      } catch {
        return ["error": "auth failed: \(error.localizedDescription)"]
      }
      let timeout = Double(params["timeout"] ?? "") ?? 20
      let harness = RealtimeOmniTestHarness(
        provider: provider, relayBaseURL: base, authHeader: authHeader, pcm16k: data)
      return await harness.run(timeoutSeconds: timeout)
    }

    // Send a typed query through the real floating-bar AI path
    // (openAIInputWithQuery → routeQuery → sendAIQuery → ChatProvider → bridge).
    // Used to drive cache/latency benchmarks without a mic or the cursor.
    register(
      name: "open_ask_omi",
      summary: "Open the Ask Omi input panel and return app-side open/focus timing",
      params: ["reset", "wait"]
    ) { params in
      let reset = boolParam(params["reset"], default: false)
      let wait = boolParam(params["wait"], default: true)
      return await FloatingControlBarManager.shared.openAskOmiForAutomation(
        reset: reset, wait: wait)
    }

    register(
      name: "close_ask_omi",
      summary: "Close the Ask Omi input panel if it is open",
      params: ["wait"]
    ) { params in
      let wait = boolParam(params["wait"], default: true)
      return await FloatingControlBarManager.shared.closeAskOmiForAutomation(wait: wait)
    }

    register(
      name: "ask",
      summary: "Send a query to the floating-bar AI (typed path); exercises the full chat pipeline",
      params: ["query"]
    ) { params in
      let query = (params["query"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      guard !query.isEmpty else { return ["error": "missing 'query'"] }
      if !FloatingControlBarManager.shared.isVisible {
        FloatingControlBarManager.shared.show()
      }
      FloatingControlBarManager.shared.openAIInputWithQuery(query, fromVoice: false)
      return ["sent": query]
    }

    register(
      name: "agent_install_prompt_state",
      summary: "Return the current floating-bar missing-agent install prompt, if present"
    ) { _ in
      FloatingControlBarManager.shared.agentInstallPromptStateForAutomation()
    }

    register(
      name: "agent_install_prompt_trigger",
      summary: "Press the current install prompt's primary action (install or sign-in)"
    ) { _ in
      FloatingControlBarManager.shared.triggerAgentInstallPromptPrimaryAction()
    }

    register(
      name: "hermes_connect_state",
      summary: "Return Hermes install/auth state and the connect flow phase"
    ) { _ in
      let availability = LocalAgentProviderDetector.availability(for: .hermes)
      let service = HermesConnectService.shared
      // Reflect current auth (and, when connected, ensure the free-model default
      // is provisioned) before reporting state.
      service.refreshConnectionState()
      var result: [String: String] = [
        "installed": LocalAgentProviderDetector.executablePath(for: .hermes) == nil ? "false" : "true",
        "availability": availability.isAvailable
          ? "available" : (availability.needsAuthentication ? "needsAuthentication" : "missing"),
        "nousAuthenticated": HermesAuthProbe.isNousAuthenticated() ? "true" : "false",
        "phase": service.phase.automationValue,
      ]
      if case .waitingForApproval(let url, let code) = service.phase {
        result["verificationURL"] = url.absoluteString
        result["userCode"] = code ?? ""
      }
      if case .failed(let message) = service.phase {
        result["failureMessage"] = message
      }
      return result
    }

    register(
      name: "hermes_connect_start",
      summary: "Start the Hermes → Nous device-code sign-in (opens browser)"
    ) { _ in
      HermesConnectService.shared.connect()
      return ["phase": HermesConnectService.shared.phase.automationValue]
    }

    register(
      name: "hermes_connect_cancel",
      summary: "Cancel an in-flight Hermes sign-in"
    ) { _ in
      HermesConnectService.shared.cancel()
      return ["phase": HermesConnectService.shared.phase.automationValue]
    }

    register(
      name: "openclaw_connect_state",
      summary: "Return OpenClaw install/onboard state and the connect flow phase"
    ) { _ in
      let availability = LocalAgentProviderDetector.availability(for: .openclaw)
      let service = OpenClawConnectService.shared
      service.refreshConnectionState()
      return [
        "installed": LocalAgentProviderDetector.executablePath(for: .openclaw) == nil ? "false" : "true",
        "availability": availability.isAvailable
          ? "available" : (availability.needsAuthentication ? "needsAuthentication" : "missing"),
        "onboarded": OpenClawOnboardProbe.isOnboarded() ? "true" : "false",
        "phase": service.phase.automationValue,
      ]
    }

    register(
      name: "openclaw_connect_start",
      summary: "Run OpenClaw's non-interactive onboarding (Gateway + Claude auth)"
    ) { _ in
      OpenClawConnectService.shared.connect()
      return ["phase": OpenClawConnectService.shared.phase.automationValue]
    }

    register(
      name: "openclaw_connect_cancel",
      summary: "Cancel an in-flight OpenClaw setup (including the manual-key watch)"
    ) { _ in
      OpenClawConnectService.shared.cancel()
      return ["phase": OpenClawConnectService.shared.phase.automationValue]
    }

    register(
      name: "openclaw_set_claude_probe",
      summary: "Test hook: force the Claude Code availability probe for OpenClaw onboarding (value=available|missing|clear)",
      params: ["value"]
    ) { params in
      let service = OpenClawConnectService.shared
      switch params["value"] ?? "clear" {
      case "available": service.claudeCodeAvailabilityOverrideForTesting = true
      case "missing": service.claudeCodeAvailabilityOverrideForTesting = false
      default: service.claudeCodeAvailabilityOverrideForTesting = nil
      }
      return [
        "override": params["value"] ?? "clear",
        "phase": service.phase.automationValue,
      ]
    }

    register(
      name: "seed_subagents",
      summary: "Seed synthetic floating-bar subagents for deterministic UI benchmarks",
      params: ["count"]
    ) { params in
      let count = intParam(params["count"], default: 3)
      return await FloatingControlBarManager.shared.seedSubagentsForAutomation(count: count)
    }

    register(
      name: "open_seeded_subagent",
      summary: "Open a seeded subagent in the floating-bar chat",
      params: ["index", "wait"]
    ) { params in
      let index = intParam(params["index"], default: 0)
      let wait = boolParam(params["wait"], default: true)
      return await FloatingControlBarManager.shared.openSeededSubagentForAutomation(index: index, wait: wait)
    }

    register(
      name: "back_from_subagent",
      summary: "Return from the selected subagent to the main Ask Omi chat",
      params: ["wait"]
    ) { params in
      let wait = boolParam(params["wait"], default: true)
      return await FloatingControlBarManager.shared.backFromSubagentForAutomation(wait: wait)
    }

    register(
      name: "spatial_overlay_present_fixture",
      summary: "Present a deterministic spatial-overlay fixture for dogfood harnesses",
      params: ["fixture", "settleMs"]
    ) { params in
      guard let fixture = SpatialOverlayDogfoodFixture(rawValue: params["fixture"] ?? "") else {
        throw DesktopAutomationActionError.invalidParams(
          "unknown fixture; expected one of \(SpatialOverlayDogfoodFixture.allCases.map(\.rawValue).joined(separator: ","))"
        )
      }
      let state = CloudConnectorGuidanceOverlay.shared.presentAutomationFixture(fixture)
      return state
    }

    register(
      name: "spatial_overlay_state",
      summary: "Return the current spatial-overlay dogfood state"
    ) { _ in
      CloudConnectorGuidanceOverlay.shared.automationState()
    }

    register(
      name: "spatial_overlay_dismiss",
      summary: "Dismiss the current spatial-overlay dogfood overlay"
    ) { _ in
      CloudConnectorGuidanceOverlay.shared.dismiss()
      return ["dismissed": "true", "visible": "false"]
    }

    register(
      name: "cloud_connector_guidance_probe",
      summary: "Read-only diagnostic of the live Claude Add detection (no overlay, no clicks)"
    ) { _ in
      await MainActor.run { CloudConnectorFormAutomation.claudeAddGuidanceDiagnostics() }
    }

    register(
      name: "spatial_overlay_present_instruction",
      summary: "Present the Screen Recording fallback instruction card (dogfood/visual)"
    ) { params in
      let title = params["title"] ?? "Allow Screen Recording for Omi"
      let subtitle =
        params["subtitle"]
        ?? "Turn on Omi under Screen & System Audio Recording, then return to Claude and click Add."
      let anchor = CloudConnectorGuidanceOverlay.anchorRect(fromParam: params["anchor"])
      CloudConnectorGuidanceOverlay.shared.presentInstructionCard(
        title: title, subtitle: subtitle, near: anchor)
      return CloudConnectorGuidanceOverlay.shared.automationState()
    }
  }
}

/// Coerce a string param ("true"/"1"/"yes") into a Bool, falling back when absent.
private func boolParam(_ raw: String?, default fallback: Bool) -> Bool {
  guard let raw = raw?.trimmingCharacters(in: .whitespaces).lowercased(), !raw.isEmpty else {
    return fallback
  }
  return ["1", "true", "yes", "on"].contains(raw)
}

private func intParam(_ raw: String?, default fallback: Int) -> Int {
  guard let raw = raw?.trimmingCharacters(in: .whitespaces), !raw.isEmpty else {
    return fallback
  }
  return Int(raw) ?? fallback
}

final class DesktopAutomationBridge {
  static let shared = DesktopAutomationBridge()

  private let queue = DispatchQueue(label: "com.omi.desktop.automation-bridge")
  private var listener: NWListener?

  private init() {}

  func startIfNeeded() {
    guard DesktopAutomationLaunchOptions.isEnabled else { return }
    guard listener == nil else { return }

    do {
      let parameters = NWParameters.tcp
      parameters.allowLocalEndpointReuse = true
      guard let port = NWEndpoint.Port(rawValue: DesktopAutomationLaunchOptions.port) else {
        log("DesktopAutomationBridge: invalid port \(DesktopAutomationLaunchOptions.port)")
        return
      }
      guard let loopback = IPv4Address("127.0.0.1") else {
        log("DesktopAutomationBridge: failed to resolve loopback address")
        return
      }
      parameters.requiredLocalEndpoint = .hostPort(host: .ipv4(loopback), port: port)

      let listener = try NWListener(using: parameters)
      listener.newConnectionHandler = { [weak self] connection in
        self?.handleConnection(connection)
      }
      listener.stateUpdateHandler = { (state: NWListener.State) in
        log("DesktopAutomationBridge: listener state changed to \(String(describing: state))")
      }
      listener.start(queue: queue)
      self.listener = listener
      Task { @MainActor in DesktopAutomationActionRegistry.shared.registerBuiltins() }
      log(
        "DesktopAutomationBridge: listening on http://127.0.0.1:\(DesktopAutomationLaunchOptions.port)"
      )
    } catch {
      logError("DesktopAutomationBridge: failed to start listener", error: error)
    }
  }

  private func handleConnection(_ connection: NWConnection) {
    connection.start(queue: queue)
    receiveRequest(on: connection, buffer: Data())
  }

  private func receiveRequest(on connection: NWConnection, buffer: Data) {
    connection.receive(minimumIncompleteLength: 1, maximumLength: 64 * 1024) {
      [weak self] data, _, isComplete, error in
      guard let self else { return }

      if let error {
        self.sendError(
          "receive_failed: \(error.localizedDescription)", statusCode: 500, on: connection)
        return
      }

      var accumulated = buffer
      if let data {
        accumulated.append(data)
      }

      if let request = self.parseRequest(from: accumulated) {
        Task {
          let response = await self.route(request: request)
          self.send(response, on: connection)
        }
        return
      }

      if isComplete {
        self.sendError("incomplete_request", statusCode: 400, on: connection)
        return
      }

      self.receiveRequest(on: connection, buffer: accumulated)
    }
  }

  private func parseRequest(from data: Data) -> HTTPRequest? {
    guard let headerRange = data.range(of: Data("\r\n\r\n".utf8)) else {
      return nil
    }

    let headerData = data[..<headerRange.lowerBound]
    guard let headerString = String(data: headerData, encoding: .utf8) else {
      return nil
    }

    let lines = headerString.components(separatedBy: "\r\n")
    guard let requestLine = lines.first else { return nil }
    let requestParts = requestLine.split(separator: " ")
    guard requestParts.count >= 2 else { return nil }

    let method = String(requestParts[0])
    let path = String(requestParts[1])

    var contentLength = 0
    for line in lines.dropFirst() {
      let pieces = line.split(separator: ":", maxSplits: 1)
      guard pieces.count == 2 else { continue }
      if pieces[0].lowercased() == "content-length" {
        contentLength = Int(pieces[1].trimmingCharacters(in: .whitespaces)) ?? 0
      }
    }

    let bodyStart = headerRange.upperBound
    let expectedLength = data.distance(from: data.startIndex, to: bodyStart) + contentLength
    guard data.count >= expectedLength else {
      return nil
    }

    let body = Data(data[bodyStart..<data.index(bodyStart, offsetBy: contentLength)])
    return HTTPRequest(method: method, path: path, body: body)
  }

  /// Parse a `POST /action` body: `{ "name": "...", "params": { "k": "v", ... } }`.
  /// Param values are coerced to strings (bools → "true"/"false", numbers → digits)
  /// so callers can send natural JSON types.
  private func parseActionRequest(from body: Data) -> (name: String, params: [String: String])? {
    guard let object = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
      let name = object["name"] as? String, !name.isEmpty
    else {
      return nil
    }

    var params: [String: String] = [:]
    if let raw = object["params"] as? [String: Any] {
      for (key, value) in raw {
        if let string = value as? String {
          params[key] = string
        } else if let number = value as? NSNumber {
          if CFGetTypeID(number) == CFBooleanGetTypeID() {
            params[key] = number.boolValue ? "true" : "false"
          } else {
            params[key] = number.stringValue
          }
        } else {
          params[key] = String(describing: value)
        }
      }
    }
    return (name, params)
  }

  private func route(request: HTTPRequest) async -> HTTPResponse {
    let started = DispatchTime.now().uptimeNanoseconds
    let response = await routeUntimed(request: request)
    let elapsedMs = Double(DispatchTime.now().uptimeNanoseconds - started) / 1_000_000
    await DesktopAutomationTraceStore.shared.record(
      method: request.method,
      path: request.path,
      statusCode: response.statusCode,
      durationMs: (elapsedMs * 100).rounded() / 100
    )
    return response
  }

  private func routeUntimed(request: HTTPRequest) async -> HTTPResponse {
    switch (request.method, request.path) {
    case ("GET", "/health"):
      let snapshot = await cachedAutomationSnapshot()
      return jsonResponse(DesktopAutomationResponse(ok: true, result: snapshot, error: nil))
    case ("GET", "/state"):
      let snapshot = await liveAutomationSnapshot()
      return jsonResponse(DesktopAutomationResponse(ok: true, result: snapshot, error: nil))
    case ("GET", "/traces/recent"):
      let traces = await DesktopAutomationTraceStore.shared.recent()
      return jsonResponse(DesktopAutomationResponse(ok: true, result: traces, error: nil))
    case ("POST", "/traces/clear"):
      await DesktopAutomationTraceStore.shared.clear()
      return jsonResponse(DesktopAutomationResponse(ok: true, result: "cleared", error: nil))
    case ("POST", "/navigate"):
      do {
        let payload = try JSONDecoder().decode(
          DesktopAutomationNavigationRequest.self, from: request.body)
        try await dispatchNavigation(payload)
        try await sleepForAutomationSettle(payload.settleMs)
        let snapshot = await cachedAutomationSnapshot()
        return jsonResponse(DesktopAutomationResponse(ok: true, result: snapshot, error: nil))
      } catch {
        return jsonResponse(
          DesktopAutomationResponse<DesktopAutomationSnapshot>(
            ok: false,
            result: nil,
            error: error.localizedDescription
          ),
          statusCode: 400
        )
      }
    case ("POST", "/conversation/open"):
      do {
        let payload = try JSONDecoder().decode(
          DesktopAutomationOpenConversationRequest.self, from: request.body)
        try await dispatchOpenConversation(payload)
        try await sleepForAutomationSettle(payload.settleMs)
        let snapshot = await cachedAutomationSnapshot()
        return jsonResponse(DesktopAutomationResponse(ok: true, result: snapshot, error: nil))
      } catch {
        return jsonResponse(
          DesktopAutomationResponse<DesktopAutomationSnapshot>(
            ok: false,
            result: nil,
            error: error.localizedDescription
          ),
          statusCode: 400
        )
      }
    case ("POST", "/execute-export"):
      struct ExecResult: Codable { let taskTitle: String }
      do {
        let payload = try JSONDecoder().decode(
          DesktopAutomationExecuteExportRequest.self, from: request.body)
        guard let destination = MemoryExportDestination(rawValue: payload.destination) else {
          return jsonResponse(
            DesktopAutomationResponse<ExecResult>(
              ok: false, result: nil, error: "unknown destination: \(payload.destination)"),
            statusCode: 400)
        }
        let outcome = try await MemoryExportExecutor.run(destination)
        return jsonResponse(
          DesktopAutomationResponse(
            ok: true, result: ExecResult(taskTitle: outcome.taskTitle), error: nil))
      } catch {
        return jsonResponse(
          DesktopAutomationResponse<ExecResult>(
            ok: false, result: nil, error: error.localizedDescription),
          statusCode: 500)
      }
    case ("GET", "/actions"):
      let descriptors = await DesktopAutomationActionRegistry.shared.descriptors()
      return jsonResponse(DesktopAutomationResponse(ok: true, result: descriptors, error: nil))
    case ("GET", "/capabilities"):
      let descriptors = await DesktopAutomationActionRegistry.shared.descriptors()
      let capabilities = DesktopAutomationCapabilities(
        schemaVersion: 1,
        routes: [
          "GET /health",
          "GET /state",
          "GET /capabilities",
          "GET /actions",
          "GET /traces/recent",
          "POST /traces/clear",
          "POST /navigate",
          "POST /conversation/open",
          "POST /action",
          "POST /visual/export",
        ],
        lanes: ["bridge", "visual", "ui"],
        waits: ["state", "log", "trace"],
        assertions: ["state", "log", "trace", "ax"],
        artifactTypes: ["state", "bridge_response", "visual_png", "logs", "traces", "summary"],
        actions: descriptors
      )
      return jsonResponse(DesktopAutomationResponse(ok: true, result: capabilities, error: nil))
    case ("POST", "/action"):
      guard let parsed = parseActionRequest(from: request.body) else {
        return jsonResponse(
          DesktopAutomationResponse<DesktopAutomationActionResult>(
            ok: false, result: nil, error: "invalid_action_request"),
          statusCode: 400
        )
      }
      do {
        let detail = try await DesktopAutomationActionRegistry.shared.perform(
          parsed.name, params: parsed.params)
        try await sleepForAutomationSettle(intParam(parsed.params["settleMs"], default: 0))
        let snapshot = await liveAutomationSnapshot()
        let result = DesktopAutomationActionResult(
          action: parsed.name, detail: detail, state: snapshot)
        return jsonResponse(DesktopAutomationResponse(ok: true, result: result, error: nil))
      } catch {
        return jsonResponse(
          DesktopAutomationResponse<DesktopAutomationActionResult>(
            ok: false, result: nil, error: error.localizedDescription),
          statusCode: 400
        )
      }
    case ("POST", "/visual/export"):
      do {
        let payload = try JSONDecoder().decode(
          DesktopAutomationVisualExportRequest.self, from: request.body)
        let result = try await exportWindow(payload)
        return jsonResponse(DesktopAutomationResponse(ok: true, result: result, error: nil))
      } catch {
        return jsonResponse(
          DesktopAutomationResponse<DesktopAutomationVisualExportResult>(
            ok: false, result: nil, error: error.localizedDescription),
          statusCode: 500
        )
      }
    case ("POST", "/open-export"):
      struct OpenResult: Codable { let destination: String }
      do {
        let payload = try JSONDecoder().decode(
          DesktopAutomationExecuteExportRequest.self, from: request.body)
        guard MemoryExportDestination(rawValue: payload.destination) != nil else {
          return jsonResponse(
            DesktopAutomationResponse<OpenResult>(
              ok: false, result: nil, error: "unknown destination: \(payload.destination)"),
            statusCode: 400)
        }
        await MainActor.run {
          NSApp.activate()
          if let window = NSApp.windows.first(where: { $0.title.lowercased().hasPrefix("omi") }) {
            window.makeKeyAndOrderFront(nil)
          }
          NotificationCenter.default.post(
            name: .desktopAutomationOpenExportRequested, object: nil,
            userInfo: ["destination": payload.destination])
        }
        try await Task.sleep(for: .milliseconds(300))
        return jsonResponse(
          DesktopAutomationResponse(
            ok: true, result: OpenResult(destination: payload.destination), error: nil))
      } catch {
        return jsonResponse(
          DesktopAutomationResponse<OpenResult>(
            ok: false, result: nil, error: error.localizedDescription),
          statusCode: 500)
      }
    case ("POST", "/gmail-read"):
      do {
        let emails = try await GmailReaderService.shared.readRecentEmails(maxResults: 50)
        let result = await GmailReaderService.shared.saveAsMemories(emails: emails)
        struct GmailReadResult: Codable {
          let emailCount: Int
          let memoriesSaved: Int
          let memoriesFailed: Int
          let emails: [GmailEmailSummary]
        }
        struct GmailEmailSummary: Codable {
          let from: String
          let subject: String
          let snippet: String
          let date: String
          let isUnread: Bool
        }
        let formatter = ISO8601DateFormatter()
        let summaries = emails.prefix(50).map { e in
          GmailEmailSummary(
            from: e.from, subject: e.subject, snippet: e.snippet,
            date: formatter.string(from: e.date), isUnread: e.isUnread)
        }
        let gmailResult = GmailReadResult(
          emailCount: emails.count,
          memoriesSaved: result.saved,
          memoriesFailed: result.failed,
          emails: summaries
        )
        return jsonResponse(DesktopAutomationResponse(ok: true, result: gmailResult, error: nil))
      } catch {
        struct ErrorResult: Codable { let message: String }
        return jsonResponse(
          DesktopAutomationResponse(ok: false, result: ErrorResult(message: error.localizedDescription), error: error.localizedDescription),
          statusCode: 500
        )
      }
    default:
      return jsonResponse(
        DesktopAutomationResponse<DesktopAutomationSnapshot>(
          ok: false,
          result: nil,
          error: "unsupported_route"
        ),
        statusCode: 404
      )
    }
  }

  private func dispatchNavigation(_ payload: DesktopAutomationNavigationRequest) async throws {
    await activateMainWindowIfNeeded(payload.activateApp ?? true)
    await MainActor.run {
      NotificationCenter.default.post(
        name: .desktopAutomationNavigateRequested,
        object: nil,
        userInfo: [
          "target": payload.target,
          "settingsSection": payload.settingsSection as Any,
          "highlightedSettingId": payload.highlightedSettingId as Any,
        ]
      )
    }
  }

  private func dispatchOpenConversation(_ payload: DesktopAutomationOpenConversationRequest) async throws {
    await activateMainWindowIfNeeded(payload.activateApp ?? true)
    await MainActor.run {
      NotificationCenter.default.post(
        name: .desktopAutomationOpenConversationRequested,
        object: nil,
        userInfo: [
          "conversationId": payload.conversationId,
          "showTranscript": payload.showTranscript ?? false,
        ]
      )
    }
  }

  private func activateMainWindowIfNeeded(_ activateApp: Bool) async {
    guard activateApp else { return }
    await MainActor.run {
      NSApp.activate()
      if let window = NSApp.windows.first(where: { $0.title.lowercased().hasPrefix("omi") }) {
        window.makeKeyAndOrderFront(nil)
      }
    }
  }

  private func sleepForAutomationSettle(_ milliseconds: Int?) async throws {
    let clamped = max(0, min(milliseconds ?? 0, 5_000))
    guard clamped > 0 else { return }
    try await Task.sleep(for: .milliseconds(clamped))
  }

  private func exportWindow(
    _ payload: DesktopAutomationVisualExportRequest
  ) async throws -> DesktopAutomationVisualExportResult {
    try await MainActor.run {
      let fileManager = FileManager.default
      let url = URL(fileURLWithPath: payload.path).standardizedFileURL
      let captureRoot = DesktopAutomationLaunchOptions.captureRoot.resolvingSymlinksInPath()
      try fileManager.createDirectory(at: captureRoot, withIntermediateDirectories: true)
      let parent = url.deletingLastPathComponent()
      let resolvedParent = parent.resolvingSymlinksInPath()
      let resolvedURL = resolvedParent.appendingPathComponent(url.lastPathComponent)
      guard resolvedURL.path == captureRoot.path || resolvedURL.path.hasPrefix(captureRoot.path + "/") else {
        throw DesktopAutomationActionError.invalidParams(
          "visual export path must be under \(captureRoot.path)")
      }
      if let values = try? url.resourceValues(forKeys: [.isSymbolicLinkKey]),
        values.isSymbolicLink == true
      {
        throw DesktopAutomationActionError.invalidParams("visual export path must not be a symlink")
      }
      try fileManager.createDirectory(
        at: parent, withIntermediateDirectories: true)
      let postCreateParent = parent.resolvingSymlinksInPath()
      let writeURL = postCreateParent.appendingPathComponent(url.lastPathComponent)
      guard writeURL.path == captureRoot.path || writeURL.path.hasPrefix(captureRoot.path + "/") else {
        throw DesktopAutomationActionError.invalidParams(
          "visual export path must be under \(captureRoot.path)")
      }

      let window: NSWindow?
      if payload.target == "floating" {
        window = NSApp.windows.first(where: { $0 is FloatingControlBarWindow && $0.isVisible })
      } else if payload.target == "overlay" {
        window = CloudConnectorGuidanceOverlay.shared.automationWindow
      } else {
        window = NSApp.windows.first(where: { window in
          window.title.lowercased().hasPrefix("omi") || window.isMainWindow || window.isKeyWindow
        })
      }

      guard
        let window,
        let contentView = window.contentView
      else {
        throw DesktopAutomationActionError.invalidParams("\(payload.target ?? "main") window not available")
      }

      contentView.needsLayout = true
      contentView.layoutSubtreeIfNeeded()

      let bounds = contentView.bounds
      guard !bounds.isEmpty,
        let bitmap = contentView.bitmapImageRepForCachingDisplay(in: bounds)
      else {
        throw DesktopAutomationActionError.invalidParams("\(payload.target ?? "main") window has no renderable content")
      }

      contentView.cacheDisplay(in: bounds, to: bitmap)
      guard let pngData = bitmap.representation(using: .png, properties: [:]) else {
        throw DesktopAutomationActionError.invalidParams("failed to encode png")
      }

      try pngData.write(to: writeURL, options: [.atomic])
      return DesktopAutomationVisualExportResult(
        path: writeURL.path,
        width: bitmap.pixelsWide,
        height: bitmap.pixelsHigh
      )
    }
  }

  private func jsonResponse<T: Codable>(_ payload: T, statusCode: Int = 200) -> HTTPResponse {
    do {
      let body = try JSONEncoder.pretty.encode(payload)
      return HTTPResponse(
        statusCode: statusCode,
        headers: ["Content-Type": "application/json"],
        body: body
      )
    } catch {
      let fallback = Data("{\"ok\":false,\"error\":\"encode_failed\"}".utf8)
      return HTTPResponse(
        statusCode: 500,
        headers: ["Content-Type": "application/json"],
        body: fallback
      )
    }
  }

  private func sendError(_ message: String, statusCode: Int, on connection: NWConnection) {
    let response = jsonResponse(
      DesktopAutomationResponse<DesktopAutomationSnapshot>(ok: false, result: nil, error: message),
      statusCode: statusCode
    )
    send(response, on: connection)
  }

  private func send(_ response: HTTPResponse, on connection: NWConnection) {
    let statusText: String
    switch response.statusCode {
    case 200: statusText = "OK"
    case 400: statusText = "Bad Request"
    case 404: statusText = "Not Found"
    default: statusText = "Internal Server Error"
    }

    var headerLines = [
      "HTTP/1.1 \(response.statusCode) \(statusText)",
      "Content-Length: \(response.body.count)",
      "Connection: close",
    ]
    for (key, value) in response.headers {
      headerLines.append("\(key): \(value)")
    }
    headerLines.append("")
    headerLines.append("")

    var data = Data(headerLines.joined(separator: "\r\n").utf8)
    data.append(response.body)

    connection.send(
      content: data,
      completion: .contentProcessed { _ in
        connection.cancel()
      })
  }
}

private struct HTTPRequest {
  let method: String
  let path: String
  let body: Data
}

private struct HTTPResponse {
  let statusCode: Int
  let headers: [String: String]
  let body: Data
}

extension JSONEncoder {
  fileprivate static var pretty: JSONEncoder {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    return encoder
  }
}
