import AppKit
import CryptoKit
import Foundation
import Network

enum DesktopAutomationLaunchOptions {
  static let enableFlag = "--automation-bridge"
  static let portPrefix = "--automation-port="
  static let captureRootPrefix = "--automation-capture-root="
  static let defaultPort: UInt16 = 47777
  static let tokenEnvironmentKey = "OMI_AUTOMATION_TOKEN"
  static let tokenFileEnvironmentKey = "OMI_AUTOMATION_TOKEN_FILE"

  private static let generatedToken = "omi_auto_\(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased())"

  static var isEnabled: Bool {
    guard AppBuild.isNonProduction else {
      return false
    }
    // Explicit opt-out always wins, so a dev build can be run "clean" if needed.
    if ProcessInfo.processInfo.environment["OMI_DISABLE_LOCAL_AUTOMATION"] == "1" {
      return false
    }
    // Auto-enable on any non-production bundle (Omi Dev + every `omi-*` named test
    // bundle) so agents can drive the app without remembering a launch flag.
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

  static var token: String {
    let env = ProcessInfo.processInfo.environment[tokenEnvironmentKey] ?? ""
    let trimmed = env.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? generatedToken : trimmed
  }

  static var tokenFileURL: URL {
    if let rawValue = ProcessInfo.processInfo.environment[tokenFileEnvironmentKey],
      !rawValue.isEmpty
    {
      return URL(fileURLWithPath: rawValue).standardizedFileURL
    }
    return URL(fileURLWithPath: NSTemporaryDirectory())
      .appendingPathComponent("omi-automation-\(port).token")
      .standardizedFileURL
  }

  static func writeTokenFileIfNeeded() {
    guard isEnabled else { return }
    let url = tokenFileURL
    do {
      try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
      try token.write(to: url, atomically: true, encoding: .utf8)
      chmod(url.path, S_IRUSR | S_IWUSR)
    } catch {
      logError("DesktopAutomationBridge: failed to write automation token file", error: error)
    }
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
  /// Coarse grouping for scanners and harness UIs.
  let category: String
  /// Screens or app surfaces this action is meant to replace AX interaction on.
  let surfaces: [String]
  /// Agent-facing risk label; the bridge is still non-production only.
  let safety: String
  /// Plain-language effects so callers can prefer read-only probes before clicks.
  let sideEffects: [String]
  /// Copy-pasteable examples for `scripts/omi-ctl action ...`.
  let examples: [String]
  /// Semantic bridge actions should be preferred over `agent-swift` clicks when covered.
  let preferSemantic: Bool

  init(
    name: String,
    summary: String,
    params: [String] = [],
    category: String? = nil,
    surfaces: [String]? = nil,
    safety: String? = nil,
    sideEffects: [String]? = nil,
    examples: [String] = [],
    preferSemantic: Bool = true
  ) {
    self.name = name
    self.summary = summary
    self.params = params
    self.category = category ?? Self.inferCategory(name)
    self.surfaces = surfaces ?? Self.inferSurfaces(name)
    self.safety = safety ?? Self.inferSafety(name)
    self.sideEffects = sideEffects ?? Self.inferSideEffects(name)
    self.examples = examples.isEmpty ? [Self.commandExample(name: name, params: params)] : examples
    self.preferSemantic = preferSemantic
  }

  private static func inferCategory(_ name: String) -> String {
    if name.contains("snapshot") || name.contains("probe") || name.contains("state")
      || name.contains("tail") || name.contains("evidence") || name.contains("qa_export")
    {
      return "read"
    }
    if name.hasPrefix("capture") {
      return "capture"
    }
    if name.contains("coordinator") {
      return "coordinator"
    }
    if name.contains("ask") || name.contains("chat") || name.contains("omni") {
      return "chat"
    }
    if name.contains("spatial_overlay") || name.contains("debug_bar") || name.contains("subagent") {
      return "visual"
    }
    if name.contains("transcription") || name.contains("refresh") {
      return "app_control"
    }
    return "general"
  }

  private static func inferSurfaces(_ name: String) -> [String] {
    if name.hasPrefix("capture_main_window") {
      return ["main_window"]
    }
    if name.hasPrefix("capture_floating_bar") || name.contains("debug_bar") {
      return ["floating_bar"]
    }
    if name.contains("main_chat") {
      return ["main_chat"]
    }
    if name.contains("ask_omi") || name == "ask" || name.contains("floating") || name.contains("subagent") {
      return ["floating_bar", "ask_omi"]
    }
    if name.contains("coordinator") {
      return ["coordinator"]
    }
    if name.contains("spatial_overlay") || name.contains("cloud_connector") {
      return ["cloud_connector_guidance"]
    }
    if name.contains("calendar") {
      return ["calendar_connector"]
    }
    if name.contains("gmail") {
      return ["gmail_connector"]
    }
    if name.contains("apple_notes") || name.contains("local_file") {
      return ["import_connectors"]
    }
    return ["app"]
  }

  private static func inferSafety(_ name: String) -> String {
    if name.contains("delete") {
      return "remote_write"
    }
    if name.contains("snapshot") || name.contains("probe") || name.contains("state")
      || name.contains("tail") || name.contains("evidence") || name.contains("qa_export")
    {
      return "read_only"
    }
    if name.hasPrefix("capture") {
      return "local_artifact"
    }
    if name.contains("ask") || name.contains("omni") || name.contains("import") {
      return "network_or_model"
    }
    return "local_ui_state"
  }

  private static func inferSideEffects(_ name: String) -> [String] {
    if name.contains("delete") {
      return ["may mutate remote user data"]
    }
    if name.hasPrefix("capture") {
      return ["writes local artifact file"]
    }
    if name.contains("ask") || name.contains("omni") {
      return ["may call model/backend services"]
    }
    if name.contains("import") {
      return ["may read local connector data", "may save imported memory data"]
    }
    if name.contains("toggle") || name.contains("debug") || name.contains("open") || name.contains("close")
      || name.contains("seed") || name.contains("swap") || name.contains("clear")
    {
      return ["mutates non-production app state"]
    }
    return []
  }

  private static func commandExample(name: String, params: [String]) -> String {
    var pieces = ["./scripts/omi-ctl", "action", name]
    for param in params {
      pieces.append("\(param)=<value>")
    }
    return pieces.joined(separator: " ")
  }
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

private struct DesktopAutomationHealth: Codable {
  let ok: Bool
  let name: String
  let bundleIdentifier: String
  let bridgePort: UInt16
  let requiresAuth: Bool
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
    name: String,
    summary: String,
    params: [String] = [],
    category: String? = nil,
    surfaces: [String]? = nil,
    safety: String? = nil,
    sideEffects: [String]? = nil,
    examples: [String] = [],
    preferSemantic: Bool = true,
    handler: @escaping Handler
  ) {
    entries[name] = Entry(
      descriptor: DesktopAutomationActionDescriptor(
        name: name,
        summary: summary,
        params: params,
        category: category,
        surfaces: surfaces,
        safety: safety,
        sideEffects: sideEffects,
        examples: examples,
        preferSemantic: preferSemantic
      ),
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

    // Drive the real push-to-talk state machine headlessly (MIC-01). ptt_start begins
    // capture like the shortcut key-down; ptt_stop finalizes like a long-hold release.
    // Releasing with no mic audio exercises the empty-batch release path — it must end
    // the turn with a hint, not hang. Both hit the exact private startListening/finalize
    // the shortcut handler calls, so no synthetic key events or cursor are involved.
    register(
      name: "ptt_start",
      summary: "Begin a push-to-talk capture (mirrors the PTT shortcut key-down)"
    ) { _ in
      PushToTalkManager.shared.beginPushToTalkForAutomation()
    }

    register(
      name: "ptt_stop",
      summary: "Finalize the in-progress push-to-talk capture (mirrors a long-hold release)"
    ) { _ in
      PushToTalkManager.shared.endPushToTalkForAutomation()
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

    // Run the post-scan local-file memory import exactly as onboarding does
    // (indexed-files snapshot → aggregate drafts → import evidence service
    // with legacy batch fallback). Lets agents verify the import pipeline
    // without driving the onboarding UI or the cursor.
    register(
      name: "onboarding_local_file_import",
      summary: "Run the post-scan local-file memory import from the indexed snapshot; returns saved count"
    ) { _ in
      let coordinator = OnboardingPagedIntroCoordinator()
      await coordinator.refreshSnapshotIfAvailable()
      return [
        "saved": String(coordinator.localFileMemoriesSaved),
        "file_count": String(coordinator.scanSnapshot?.fileCount ?? 0),
      ]
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

    // Force the floating-bar active state so the pill↔notch-island morph and the
    // "thinking" animation can be exercised without a mic. Same flags a real PTT
    // turn sets; non-prod bridge only. state = idle|listening|thinking|answering.
    register(
      name: "debug_bar_state",
      summary: "Force floating-bar state: idle|listening|thinking|answering (visual verification)",
      params: ["state"]
    ) { params in
      let s = (params["state"] ?? "thinking").lowercased()
      let mgr = FloatingControlBarManager.shared
      guard let bar = mgr.barState else { return ["error": "no bar state"] }
      if s != "idle", !mgr.isVisible { mgr.show() }
      bar.isVoiceResponseActive = (s == "answering")
      bar.isVoiceListening = (s == "listening")
      bar.isThinking = (s == "thinking")
      return ["state": s, "usesNotchIsland": bar.usesNotchIsland ? "true" : "false"]
    }

    // Send a message through the real main-window chat pipeline (ChatPage),
    // in-process via ViewModelContainer's ChatProvider — no synthetic mouse
    // or keyboard input, so it never touches the user's actual cursor.
    register(
      name: "ask_main_chat",
      summary: "Send a query to the main-window chat (typed path); exercises the full chat pipeline",
      params: ["query"]
    ) { params in
      let query = (params["query"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      guard !query.isEmpty else { return ["error": "missing 'query'"] }
      guard let provider = ChatProvider.mainInstance else {
        return ["error": "main ChatProvider not yet initialized"]
      }
      let tracer = QueryTracer(query: query, inputMode: .text)
      await QueryTracerContext.$current.withValue(tracer) {
        _ = await provider.sendMessage(query)
      }
      return ["sent": query]
    }

    // Gauntlet step 06: clear owner A kernel bindings, re-register synthetic owner B,
    // and run one assembled-context probe turn. Non-production bundles only.
    register(
      name: "swap_test_owner",
      summary: "Clear owner A kernel state, swap to synthetic owner B, and run one probe turn",
      params: ["owner_b", "query"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "swap_test_owner is disabled on production bundles"]
      }
      guard let provider = ChatProvider.mainInstance else {
        return ["error": "main ChatProvider not yet initialized"]
      }
      return await provider.automationSwapTestOwner(
        ownerBId: params["owner_b"] ?? "",
        probeQuery: params["query"] ?? ""
      )
    }

    register(
      name: "restore_test_owner",
      summary: "Restore the real owner after swap_test_owner (harness cleanup; no-op if no swap active)",
      params: []
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "restore_test_owner is disabled on production bundles"]
      }
      guard let provider = ChatProvider.mainInstance else {
        return ["error": "main ChatProvider not yet initialized"]
      }
      return await provider.automationRestoreTestOwner()
    }

    register(
      name: "main_chat_snapshot",
      summary: "Export main-chat transcript, session ids, and stream state for continuity harnesses",
      params: ["limit"]
    ) { params in
      guard let provider = ChatProvider.mainInstance else {
        return ["error": "main ChatProvider not yet initialized"]
      }
      let limit = max(1, intParam(params["limit"], default: 50))
      return provider.automationMainChatSnapshot(limit: limit)
    }

    register(
      name: "clear_owner_surface_state",
      summary: "Clear kernel main_chat turns for the active owner (non-prod continuity harness hygiene)",
      params: ["chatId"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "clear_owner_surface_state is disabled on production bundles"]
      }
      guard let provider = ChatProvider.mainInstance else {
        return ["error": "main ChatProvider not yet initialized"]
      }
      let chatId = params["chatId"]?.trimmingCharacters(in: .whitespacesAndNewlines)
      return await provider.automationClearOwnerSurfaceState(chatId: chatId?.isEmpty == false ? chatId! : "default")
    }

    register(
      name: "kernel_turn_tail",
      summary: "Return the last N kernel main_chat turns for continuity harness evidence",
      params: ["limit"]
    ) { params in
      guard let provider = ChatProvider.mainInstance else {
        return ["error": "main ChatProvider not yet initialized"]
      }
      let limit = max(1, intParam(params["limit"], default: 8))
      return await provider.automationKernelTurnTail(limit: limit)
    }

    register(
      name: "wait_main_chat_idle",
      summary: "Block until main chat is not sending or streaming (continuity harness)",
      params: ["timeoutMs", "pollMs"]
    ) { params in
      let timeoutMs = max(1_000, intParam(params["timeoutMs"], default: 180_000))
      let pollMs = max(100, intParam(params["pollMs"], default: 500))
      guard let provider = ChatProvider.mainInstance else {
        return ["error": "main ChatProvider not yet initialized"]
      }
      let deadline = Date().addingTimeInterval(Double(timeoutMs) / 1000.0)
      while Date() < deadline {
        if !provider.isSending && !provider.messages.contains(where: { $0.isStreaming }) {
          var detail = provider.automationMainChatSnapshot(limit: 8)
          detail["idle"] = "true"
          return detail
        }
        try await Task.sleep(nanoseconds: UInt64(pollMs) * 1_000_000)
      }
      var detail = provider.automationMainChatSnapshot(limit: 8)
      detail["error"] = "timeout"
      detail["timeout_ms"] = "\(timeoutMs)"
      return detail
    }

    register(
      name: "agent_runtime_evidence",
      summary: "Return omi-agentd.sqlite3 path and SHA-256 for continuity harness evidence bundles"
    ) { _ in
      let stateDir = AgentRuntimeProcess.defaultStateDirectory()
      let dbPath = (stateDir as NSString).appendingPathComponent("omi-agentd.sqlite3")
      var detail: [String: String] = [
        "state_dir": stateDir,
        "database_path": dbPath,
        "database_exists": FileManager.default.fileExists(atPath: dbPath) ? "true" : "false",
        "bundle_id": Bundle.main.bundleIdentifier ?? "",
      ]
      if FileManager.default.fileExists(atPath: dbPath),
        let data = try? Data(contentsOf: URL(fileURLWithPath: dbPath))
      {
        let digest = SHA256.hash(data: data)
        detail["database_sha256"] = digest.map { String(format: "%02x", $0) }.joined()
        detail["database_bytes"] = "\(data.count)"
      }
      return detail
    }

    register(
      name: "memories_qa_export",
      summary: "Export memory counts by tier from the live API (local QA automation)",
      params: ["limit"]
    ) { params in
      let limit = Int(params["limit"] ?? "") ?? 50
      let memories = try await APIClient.shared.getMemories(limit: limit, offset: 0)
      let shortCount = memories.filter { $0.tier == .shortTerm }.count
      let longCount = memories.filter { $0.tier == .longTerm }.count
      let samples: [[String: String]] = memories.prefix(12).map { memory in
        [
          "id": memory.id,
          "tier": memory.tier.rawValue,
          "tierIsExplicit": memory.tierIsExplicit ? "true" : "false",
          "content": String(memory.content.prefix(90)),
          "conversationId": memory.conversationId ?? "",
        ]
      }
      let samplesData = try JSONSerialization.data(withJSONObject: samples)
      let samplesJson = String(data: samplesData, encoding: .utf8) ?? "[]"
      return [
        "total": "\(memories.count)",
        "short_term": "\(shortCount)",
        "long_term": "\(longCount)",
        "samples_json": samplesJson,
      ]
    }

    register(
      name: "apple_notes_read_probe",
      summary: "Probe Apple Notes access without importing or saving memories",
      params: ["folderPath", "maxResults", "remember"]
    ) { params in
      let maxResults = min(max(intParam(params["maxResults"], default: 20), 1), 250)
      let folderPath = params["folderPath"]?.trimmingCharacters(in: .whitespacesAndNewlines)
      let remember = boolParam(params["remember"], default: false)

      do {
        let selectedFolderPath: String?
        if let folderPath, !folderPath.isEmpty {
          let resolved = try await AppleNotesReaderService.shared.validateSelectedFolder(
            path: folderPath,
            remember: remember
          )
          selectedFolderPath = resolved.path
        } else {
          selectedFolderPath = nil
        }

        let status = await AppleNotesReaderService.shared.connectionStatus(
          maxResults: maxResults,
          selectedFolderPath: selectedFolderPath
        )
        switch status {
        case .connected(let noteCount, _):
          return [
            "ok": "true",
            "classification": "readable",
            "noteCount": "\(noteCount)",
            "folderSelected": selectedFolderPath == nil ? "false" : "true",
          ]
        case .needsAccess(let message, let reasonCode):
          return [
            "ok": "false",
            "classification": reasonCode,
            "message": message,
            "needsFolderSelection": "true",
          ]
        case .error(let message, let reasonCode):
          return [
            "ok": "false",
            "classification": reasonCode,
            "message": message,
            "needsFolderSelection": "false",
          ]
        }
      } catch let error as AppleNotesReaderError {
        return [
          "ok": "false",
          "classification": error.reasonCode,
          "message": error.localizedDescription,
          "needsFolderSelection": "\(error.shouldPromptForFolderSelection)",
        ]
      } catch {
        return [
          "ok": "false",
          "classification": "unknown_error",
          "message": error.localizedDescription,
        ]
      }
    }

    register(
      name: "delete_conversation",
      summary: "Delete conversation with cascade (API + conversationDeleted notification)",
      params: ["id"]
    ) { params in
      guard let id = params["id"], !id.isEmpty else {
        return ["error": "missing 'id'"]
      }
      try await APIClient.shared.deleteConversation(id: id)
      await MainActor.run {
        if let appState = AppState.current {
          appState.deleteConversationLocally(id)
        } else {
          NotificationCenter.default.post(
            name: .conversationDeleted,
            object: nil,
            userInfo: ["conversationId": id]
          )
        }
      }
      return ["deleted": id]
    }

    register(
      name: "capture_main_window_png",
      summary: "Write PNG of the frontmost Omi window (in-process capture)",
      params: ["path"]
    ) { params in
      guard let path = params["path"], !path.isEmpty else {
        return ["error": "missing 'path'"]
      }
      return await MainActor.run { () -> [String: String] in
        guard
          let window = NSApp.windows.first(where: {
            $0.isVisible && $0.title.range(of: "omi", options: .caseInsensitive) != nil
          }),
          let contentView = window.contentView
        else {
          return ["error": "no_visible_window"]
        }
        let bounds = contentView.bounds
        guard let rep = contentView.bitmapImageRepForCachingDisplay(in: bounds) else {
          return ["error": "bitmap_rep_failed"]
        }
        contentView.cacheDisplay(in: bounds, to: rep)
        guard let data = rep.representation(using: .png, properties: [:]) else {
          return ["error": "png_encode_failed"]
        }
        do {
          try data.write(to: URL(fileURLWithPath: path))
          return ["path": path, "bytes": "\(data.count)"]
        } catch {
          return ["error": error.localizedDescription]
        }
      }
    }

    register(
      name: "capture_floating_bar_png",
      summary: "Write PNG of the floating control bar window (in-process capture)",
      params: ["path"]
    ) { params in
      guard let path = params["path"], !path.isEmpty else {
        return ["error": "missing 'path'"]
      }
      return await MainActor.run { () -> [String: String] in
        guard
          let window = NSApp.windows.compactMap({ $0 as? FloatingControlBarWindow }).first,
          window.isVisible,
          let contentView = window.contentView
        else {
          return ["error": "no_floating_bar_window"]
        }
        let bounds = contentView.bounds
        guard let rep = contentView.bitmapImageRepForCachingDisplay(in: bounds) else {
          return ["error": "bitmap_rep_failed"]
        }
        contentView.cacheDisplay(in: bounds, to: rep)
        guard let data = rep.representation(using: .png, properties: [:]) else {
          return ["error": "png_encode_failed"]
        }
        do {
          try data.write(to: URL(fileURLWithPath: path))
          return [
            "path": path,
            "bytes": "\(data.count)",
            "frame": NSStringFromRect(window.frame),
          ]
        } catch {
          return ["error": error.localizedDescription]
        }
      }
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
      name: "coordinator_awareness_snapshot",
      summary: "Read the Swift coordinator awareness projection for Agents & Attention debugging"
    ) { _ in
      let snapshot = try await DesktopCoordinatorService.shared.awarenessSnapshotJSON()
      return ["snapshot": snapshot]
    }

    register(
      name: "coordinator_action_queue",
      summary: "Read the derived Swift coordinator attention queue",
      params: ["limit"]
    ) { params in
      let limit = intParam(params["limit"], default: 20)
      let queue = try await DesktopCoordinatorService.shared.actionQueueJSON(limit: max(1, limit))
      return ["items": queue]
    }

    register(
      name: "coordinator_open_loops",
      summary: "Read unresolved agent/coordinator loops from the Swift projection"
    ) { _ in
      let loops = try await DesktopCoordinatorService.shared.openLoopsJSON()
      return ["openLoops": loops]
    }

    register(
      name: "coordinator_route_intent",
      summary: "Route an intent through deterministic coordinator projection rules",
      params: ["intent", "surfaceKind", "taskId"]
    ) { params in
      let decision = try await DesktopCoordinatorService.shared.routeIntentJSON(
        intent: params["intent"] ?? "",
        surfaceKind: params["surfaceKind"],
        taskId: params["taskId"]
      )
      return ["decision": decision]
    }

    register(
      name: "coordinator_create_dispatch",
      summary: "Create a coordinator dispatch through the runtime control path for Agents & Attention testing",
      params: ["kind", "title", "decisionPrompt", "recommendedDefault", "sourceSessionId", "sourceRunId"]
    ) { params in
      let dispatch = try await DesktopCoordinatorService.shared.createDispatchJSON(
        kind: params["kind"] ?? "routing_choice",
        title: params["title"] ?? "Coordinator attention",
        decisionPrompt: params["decisionPrompt"] ?? "Review this coordinator attention item.",
        recommendedDefault: params["recommendedDefault"],
        sourceSessionId: params["sourceSessionId"],
        sourceRunId: params["sourceRunId"]
      )
      return ["dispatch": dispatch]
    }

    register(
      name: "coordinator_resolve_dispatch",
      summary: "Resolve a coordinator dispatch through the runtime control path",
      params: ["dispatchId", "resolution"]
    ) { params in
      guard let dispatchId = params["dispatchId"], !dispatchId.isEmpty else {
        throw DesktopAutomationActionError.invalidParams("missing dispatchId")
      }
      let dispatch = try await DesktopCoordinatorService.shared.resolveDispatchJSON(
        dispatchId: dispatchId,
        resolution: params["resolution"] ?? "resolved"
      )
      return ["dispatch": dispatch]
    }

    register(
      name: "calendar_read_probe",
      summary: "Read Google Calendar through the real connector path and return classified status",
      params: ["daysBack", "daysForward", "maxResults"]
    ) { params in
      let requestedDaysBack = intParam(params["daysBack"], default: 1)
      let requestedDaysForward = intParam(params["daysForward"], default: 1)
      let requestedMaxResults = intParam(params["maxResults"], default: 1)
      let normalized = CalendarFetchParameters.normalized(
        daysBack: requestedDaysBack,
        daysForward: requestedDaysForward,
        maxResults: requestedMaxResults
      )

      do {
        let events = try await CalendarReaderService.shared.readEvents(
          daysBack: normalized.daysBack,
          daysForward: normalized.daysForward,
          maxResults: normalized.maxResults
        )
        return [
          "status": "connected",
          "classification": "readable",
          "eventCount": "\(events.count)",
          "daysBack": "\(normalized.daysBack)",
          "daysForward": "\(normalized.daysForward)",
          "maxResults": "\(normalized.maxResults)",
        ]
      } catch let error as CalendarReaderError {
        let classification: String
        switch error {
        case .noBrowserFound:
          classification = "no_browser"
        case .notSignedIn:
          classification = "not_signed_in"
        case .sessionExpired:
          classification = "session_expired"
        case .cookieDecryptionFailed:
          classification = "decrypt_failed"
        case .configurationError:
          classification = "configuration"
        case .networkError:
          classification = "network"
        case .pythonNotFound:
          classification = "python_not_found"
        }
        return [
          "status": "error",
          "classification": classification,
          "message": error.errorDescription ?? "\(error)",
          "daysBack": "\(normalized.daysBack)",
          "daysForward": "\(normalized.daysForward)",
          "maxResults": "\(normalized.maxResults)",
        ]
      }
    }

    register(
      name: "gmail_read_probe",
      summary: "Read Gmail through the real connector path and return classified status",
      params: ["maxResults", "query"]
    ) { params in
      let requestedMaxResults = intParam(params["maxResults"], default: 1)
      let maxResults = min(max(requestedMaxResults, 1), 500)
      let rawQuery = params["query"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      let query = rawQuery.isEmpty ? "newer_than:1d" : rawQuery

      do {
        let emails = try await GmailReaderService.shared.readRecentEmails(
          maxResults: maxResults,
          query: query
        )
        return [
          "status": "connected",
          "classification": "readable",
          "emailCount": "\(emails.count)",
          "maxResults": "\(maxResults)",
          "query": query,
        ]
      } catch let error as GmailReaderError {
        return [
          "status": "error",
          "classification": error.classification,
          "message": error.errorDescription ?? "\(error)",
          "maxResults": "\(maxResults)",
          "query": query,
        ]
      } catch {
        return [
          "status": "error",
          "classification": "unknown",
          "message": error.localizedDescription,
          "maxResults": "\(maxResults)",
          "query": query,
        ]
      }
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
      DesktopAutomationLaunchOptions.writeTokenFileIfNeeded()
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

    var headers: [String: String] = [:]
    var contentLength = 0
    for line in lines.dropFirst() {
      let pieces = line.split(separator: ":", maxSplits: 1)
      guard pieces.count == 2 else { continue }
      let key = pieces[0].trimmingCharacters(in: .whitespaces).lowercased()
      let value = pieces[1].trimmingCharacters(in: .whitespaces)
      headers[key] = value
      if key == "content-length" {
        contentLength = Int(value) ?? 0
      }
    }

    let bodyStart = headerRange.upperBound
    let expectedLength = data.distance(from: data.startIndex, to: bodyStart) + contentLength
    guard data.count >= expectedLength else {
      return nil
    }

    let body = Data(data[bodyStart..<data.index(bodyStart, offsetBy: contentLength)])
    return HTTPRequest(method: method, path: path, headers: headers, body: body)
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
    guard acceptsLoopbackHostAndOrigin(request.headers) else {
      return jsonResponse(
        DesktopAutomationResponse<DesktopAutomationSnapshot>(
          ok: false, result: nil, error: "invalid_host_or_origin"),
        statusCode: 403)
    }
    if request.method == "GET", request.path == "/health", request.headers["authorization"] == nil {
      return jsonResponse(
        DesktopAutomationHealth(
          ok: true,
          name: "omi-desktop-automation",
          bundleIdentifier: Bundle.main.bundleIdentifier ?? "unknown",
          bridgePort: DesktopAutomationLaunchOptions.port,
          requiresAuth: true
        )
      )
    }
    guard authenticate(request.headers["authorization"]) else {
      return jsonResponse(
        DesktopAutomationResponse<DesktopAutomationSnapshot>(
          ok: false, result: nil, error: "invalid_or_missing_automation_token"),
        statusCode: 401)
    }

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
        schemaVersion: 2,
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
      struct RemovedRoute: Codable {
        let message: String
        let replacement: String
      }
      return jsonResponse(
        DesktopAutomationResponse(
          ok: false,
          result: RemovedRoute(
            message: "The legacy Gmail import route was removed because automation responses must not expose email contents or trigger memory writes.",
            replacement: "Use POST /action with gmail_read_probe for privacy-safe Gmail status checks."
          ),
          error: "gmail_read_removed"
        ),
        statusCode: 410
      )
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

  private func acceptsLoopbackHostAndOrigin(_ headers: [String: String]) -> Bool {
    if let host = headers["host"], !isAllowedLoopbackHost(host) {
      return false
    }
    if let origin = headers["origin"], !origin.isEmpty {
      guard let url = URL(string: origin), let host = url.host, let port = url.port else {
        return false
      }
      guard (url.scheme == "http" || url.scheme == "https"), port == Int(DesktopAutomationLaunchOptions.port) else {
        return false
      }
      guard host == "127.0.0.1" || host == "localhost" || host == "[::1]" || host == "::1" else {
        return false
      }
    }
    return true
  }

  private func isAllowedLoopbackHost(_ hostHeader: String) -> Bool {
    let value = hostHeader.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    let allowed = [
      "127.0.0.1:\(DesktopAutomationLaunchOptions.port)",
      "localhost:\(DesktopAutomationLaunchOptions.port)",
      "[::1]:\(DesktopAutomationLaunchOptions.port)",
    ]
    return allowed.contains(value)
  }

  private func authenticate(_ authorization: String?) -> Bool {
    guard let authorization else {
      return false
    }
    let supplied: String
    if authorization.lowercased().hasPrefix("bearer ") {
      supplied = String(authorization.dropFirst(7))
    } else {
      supplied = authorization
    }
    return constantTimeEquals(supplied, DesktopAutomationLaunchOptions.token)
  }

  private func constantTimeEquals(_ lhs: String, _ rhs: String) -> Bool {
    let left = Array(lhs.utf8)
    let right = Array(rhs.utf8)
    var diff = left.count ^ right.count
    for index in 0..<max(left.count, right.count) {
      let a = index < left.count ? left[index] : 0
      let b = index < right.count ? right[index] : 0
      diff |= Int(a ^ b)
    }
    return diff == 0
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
    case 401: statusText = "Unauthorized"
    case 403: statusText = "Forbidden"
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
  let headers: [String: String]
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
