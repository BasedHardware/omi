import AppKit
import CryptoKit
import Foundation
import Network
import OmiSupport

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

struct DesktopAutomationSnapshot: Codable, Sendable {
  var bridgeEnabled: Bool
  var bridgePort: UInt16
  var bundleIdentifier: String
  var appState: String
  var selectedTab: String?
  var selectedTabIndex: Int?
  var selectedSettingsSection: String?
  var highlightedSettingId: String?
  var usesLegacyHomeDesign: Bool
  /// Redesigned Home stage mode: `hub`, `chat`, or `connect`. Nil when legacy home or not on Dashboard.
  var homeMode: String?
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
  /// True when the live MainActor refresh timed out and this is the last cached
  /// snapshot instead — e.g. the main thread is wedged on a blocking Keychain
  /// read during sign-in. The bridge still answers `/state` so harnesses don't
  /// hang; callers can detect that the live fields may be stale.
  var snapshotStale: Bool = false
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

struct DesktopAutomationOpenImportRequest: Codable {
  let connector: String
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
    homeMode: nil,
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

/// How long `/state` waits for the live MainActor refresh before serving the last
/// cached snapshot instead. Generous enough not to false-trip under normal load,
/// small enough that a wedged main thread can't stall the harness.
private let liveSnapshotMainActorTimeout: Duration = .seconds(3)

/// Single-resume guard for a continuation raced between two unstructured tasks.
private final class TimeoutRaceBox<T>: @unchecked Sendable {
  private var resumed = false
  private let lock = NSLock()
  private let continuation: CheckedContinuation<T?, Never>

  init(_ continuation: CheckedContinuation<T?, Never>) {
    self.continuation = continuation
  }

  func resume(_ value: T?) {
    lock.lock()
    defer { lock.unlock() }
    guard !resumed else { return }
    resumed = true
    continuation.resume(returning: value)
  }
}

/// Await `operation`, but give up after `timeout` and return `nil`.
///
/// The automation bridge uses this so a wedged MainActor — e.g. a blocking
/// Keychain read on the main thread during sign-in (`AuthService.storedIdToken`
/// → `SecItemCopyMatching`) — can't hang `/state`. Crucially the operation runs
/// in an *unstructured* task, not a `withTaskGroup` child: a task group awaits all
/// children at scope exit, so a non-cancellable wedged `MainActor.run` would hang
/// the timeout itself. Here we resume on whichever finishes first and leave the
/// abandoned operation task to complete (harmlessly) on its own later. Pure and
/// self-contained, so it is hermetically testable.
func awaitWithTimeout<T: Sendable>(
  _ timeout: Duration,
  operation: @escaping @Sendable () async -> T
) async -> T? {
  await withCheckedContinuation { (continuation: CheckedContinuation<T?, Never>) in
    let box = TimeoutRaceBox<T>(continuation)
    let operationTask = Task { box.resume(await operation()) }
    Task {
      try? await Task.sleep(for: timeout)
      box.resume(nil)
      operationTask.cancel()
    }
  }
}

private func liveAutomationSnapshot() async -> DesktopAutomationSnapshot {
  // Bound the MainActor hop: if the main thread is wedged (blocking Keychain read
  // during sign-in), fall back to the last cached snapshot so `/state` still
  // answers instead of hanging the whole bridge. See awaitWithTimeout.
  guard let live = await awaitWithTimeout(liveSnapshotMainActorTimeout, operation: liveAutomationSnapshotFromMainActor) else {
    log("DesktopAutomationBridge: live /state refresh timed out (main thread busy); serving cached snapshot")
    var stale = await cachedAutomationSnapshot()
    stale.snapshotStale = true
    return stale
  }
  return live
}

@Sendable
private func liveAutomationSnapshotFromMainActor() async -> DesktopAutomationSnapshot {
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
    snapshot.snapshotStale = false
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
private func ensureConversationsTabVisibleForAutomation() async throws {
  NotificationCenter.default.post(
    name: .navigateToSidebarItem,
    object: nil,
    userInfo: ["rawValue": SidebarNavItem.conversations.rawValue]
  )
  // Propagate cancellation instead of swallowing it with try? — if the
  // automation task is cancelled during the settle sleep, the caller should
  // not continue to post further notifications.
  try await Task.sleep(nanoseconds: 150_000_000)
}

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
  /// Non-prod harness latch so race probes stay busy without relying on LLM latency.
  private var harnessBusyUntil: Date?

  private func harnessBusyLatchActive(now: Date = Date()) -> Bool {
    guard let until = harnessBusyUntil else { return false }
    if now >= until {
      harnessBusyUntil = nil
      return false
    }
    return true
  }

  private func clearHarnessBusyLatch() {
    harnessBusyUntil = nil
  }

  private func armHarnessBusyLatch(holdBusyMs: Int) {
    let ms = max(0, holdBusyMs)
    guard ms > 0 else { return }
    harnessBusyUntil = Date().addingTimeInterval(Double(ms) / 1000.0)
  }

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

    // Runs the exact service + outcome mapping the ChatGPT/Claude import
    // sheets use, so harnesses can assert outcome copy without driving the
    // TextEditor. Writes real memories on success, like the sheet would.
    register(
      name: "memory_log_import_probe",
      summary: "Import a ChatGPT/Claude memory-log text through the real connector pipeline and return the outcome message",
      params: ["source", "text"]
    ) { params in
      guard let raw = params["source"], let source = OnboardingMemoryLogSource(rawValue: raw) else {
        throw DesktopAutomationActionError.invalidParams("source must be chatgpt or claude")
      }
      guard let text = params["text"], !text.isEmpty else {
        throw DesktopAutomationActionError.invalidParams("text must be non-empty")
      }
      switch await ConnectorImportOperations.importMemoryLog(text: text, source: source) {
      case .success(let result, let message):
        return [
          "outcome": "success",
          "message": message,
          "memories": "\(result.memoryCount ?? 0)",
        ]
      case .failure(let message):
        return ["outcome": "failure", "message": message]
      }
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

    register(
      name: "capture_test_transcript",
      summary: "Hermetic capture seam: start/inject/stop a test recording session without mic/STT",
      params: ["phase", "text", "segments"]
    ) { params in
      guard let appState = AppState.current else { return ["error": "app state unavailable"] }
      let phase = (params["phase"] ?? "inject").lowercased()
      switch phase {
      case "start":
        return await appState.automationStartCaptureTestSession()
      case "inject":
        return await appState.automationInjectCaptureTestTranscript(text: params["text"] ?? "")
      case "inject_multi":
        return await appState.automationInjectCaptureTestTranscriptMulti(
          segmentsJSON: params["segments"] ?? params["text"] ?? "")
      case "stop":
        return await appState.automationStopCaptureTestSession()
      case "lifecycle":
        let marker = params["text"] ?? "[[MARKER:capture-lifecycle]]"
        let startResult = await appState.automationStartCaptureTestSession()
        if startResult["error"] != nil {
          return startResult
        }
        _ = await appState.automationInjectCaptureTestTranscript(text: marker)
        return await appState.automationStopCaptureTestSession()
      default:
        return ["error": "phase must be start, inject, inject_multi, stop, or lifecycle"]
      }
    }

    register(
      name: "conversation_list_snapshot",
      summary: "Return conversation list counts and recent titles for harness assertions",
      params: ["limit"]
    ) { params in
      guard let appState = AppState.current else { return ["error": "app state unavailable"] }
      let limit = max(1, intParam(params["limit"], default: 5))
      let titles = appState.conversations.prefix(limit).map { $0.structured.title }
      let ids = appState.conversations.prefix(limit).map { $0.id }
      let titlesJSON: String
      let idsJSON: String
      if let data = try? JSONSerialization.data(withJSONObject: Array(titles)),
        let encoded = String(data: data, encoding: .utf8)
      {
        titlesJSON = encoded
      } else {
        titlesJSON = "[]"
      }
      if let data = try? JSONSerialization.data(withJSONObject: Array(ids)),
        let encoded = String(data: data, encoding: .utf8)
      {
        idsJSON = encoded
      } else {
        idsJSON = "[]"
      }
      let starredCount = appState.conversations.filter(\.starred).count
      if appState.folders.isEmpty {
        await appState.loadFolders()
      }
      return [
        "conversation_count": "\(appState.totalConversationsCount ?? appState.conversations.count)",
        "loaded_count": "\(appState.conversations.count)",
        "is_transcribing": appState.isTranscribing ? "true" : "false",
        "recent_titles_json": titlesJSON,
        "recent_ids_json": idsJSON,
        "folder_count": "\(appState.folders.count)",
        "starred_count": "\(starredCount)",
        "active_folder_id": appState.selectedFolderId ?? "none",
        "show_starred_only": appState.showStarredOnly ? "true" : "false",
      ]
    }

    register(
      name: "conversation_reconciliation_snapshot",
      summary: "Exercise cache-first list/detail reconciliation and open the canonical detail",
      params: []
    ) { _ in
      guard let appState = AppState.current else { return ["error": "app state unavailable"] }
      await appState.loadConversations()
      guard let seed = appState.conversations.first else {
        return ["error": "no conversation available for reconciliation"]
      }

      var cachedProjectionId: String?
      let detail = await appState.loadConversationDetail(seed) { cached in
        cachedProjectionId = cached.id
      }
      let persisted = try? await TranscriptionStorage.shared.getCachedConversation(id: detail.id)

      NotificationCenter.default.post(
        name: .desktopAutomationOpenConversationRequested,
        object: nil,
        userInfo: ["conversationId": detail.id, "showTranscript": true]
      )

      return [
        "list_loaded": appState.conversations.isEmpty ? "false" : "true",
        "cached_projection_seen": cachedProjectionId == seed.id ? "true" : "false",
        "detail_id_matches": detail.id == seed.id ? "true" : "false",
        "detail_has_revision": detail.updatedAt == nil ? "false" : "true",
        "detail_transcript_included": detail.transcriptSegmentsIncluded ? "true" : "false",
        "cache_id_matches": persisted?.id == detail.id ? "true" : "false",
        "cache_revision_matches": persisted?.updatedAt == detail.updatedAt ? "true" : "false",
        "opened_detail": "true",
      ]
    }

    register(
      name: "memories_snapshot",
      summary: "Return memories page load state for harness assertions",
      params: []
    ) { _ in
      guard AuthState.shared.isSignedIn else {
        return [
          "is_signed_in": "false",
          "load_state": "signed_out",
          "memory_count_valid": "false",
        ]
      }
      do {
        // Same local-first path MemoriesViewModel.loadMemories uses: API page → SQLite sync → count.
        let page = try await APIClient.shared.getMemoriesPage(limit: 100, offset: 0)
        try await MemoryStorage.shared.syncServerMemories(page.memories)
        let memoryCount = try await MemoryStorage.shared.getLocalMemoriesCount()
        return [
          "is_signed_in": "true",
          "load_state": "loaded",
          "memory_count": "\(memoryCount)",
          "api_page_count": "\(page.memories.count)",
          "memory_count_valid": "true",
          "has_error": "false",
        ]
      } catch {
        return [
          "is_signed_in": "true",
          "load_state": "error",
          "has_error": "true",
          "memory_count_valid": "false",
          "error_message": error.localizedDescription,
        ]
      }
    }

    register(
      name: "tasks_snapshot",
      summary: "Return tasks store counts for harness assertions",
      params: []
    ) { _ in
      guard AuthState.shared.isSignedIn else {
        return [
          "is_signed_in": "false",
          "load_state": "signed_out",
          "task_count_valid": "false",
        ]
      }
      let store = TasksStore.shared
      await store.loadTasksIfNeeded()
      let deadline = Date().addingTimeInterval(30)
      while store.isLoading, Date() < deadline {
        try? await Task.sleep(nanoseconds: 100_000_000)
      }
      let total = store.tasksWithoutDueDate.count + store.overdueTasks.count + store.todaysTasks.count
      let loadState: String
      if store.error != nil {
        loadState = "error"
      } else if store.isLoading {
        loadState = "loading"
      } else {
        loadState = "loaded"
      }
      return [
        "is_signed_in": "true",
        "load_state": loadState,
        "task_count": "\(total)",
        "overdue_count": "\(store.overdueTasks.count)",
        "today_count": "\(store.todaysTasks.count)",
        "task_count_valid": loadState == "loaded" ? "true" : "false",
        "has_error": store.error != nil ? "true" : "false",
      ]
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

    register(
      name: "ptt_turn_snapshot",
      summary: "Return the typed PTT lifecycle state and bounded diagnostic counters"
    ) { _ in
      let coordinator = VoiceTurnCoordinator.shared
      let turn = coordinator.model.turn
      let terminalReason = turn?.terminalReason?.rawValue ?? ""
      let phase = turn.map { VoiceTurnCoordinator.phaseLabel($0.phase) } ?? "idle"
      let route = turn.map { VoiceTurnCoordinator.routeLabel($0.route) } ?? "none"
      return [
        "phase": phase,
        "route": route,
        "terminal_reason": terminalReason,
        "stale_event_count": "\(coordinator.model.staleEventCount)",
        "invalid_transition_count": "\(coordinator.model.invalidTransitionCount)",
      ]
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

    // Drive the live onboarding language step exactly as its Continue button
    // does: set the selection on the on-screen coordinator, run
    // confirmLanguages() (the real backend save), and advance to the next step
    // only when the save succeeded — mirroring OnboardingLanguageStepView.
    register(
      name: "onboarding_confirm_languages",
      summary: "Select languages on the live onboarding coordinator and run the real Continue save",
      params: ["languages"]
    ) { params in
      let codes = (params["languages"] ?? "en")
        .split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
      guard let coordinator = await MainActor.run(body: { OnboardingPagedIntroCoordinator.current })
      else {
        return ["error": "no live onboarding coordinator (is onboarding on screen?)"]
      }
      await MainActor.run { coordinator.selectedLanguageCodes = codes }
      await coordinator.confirmLanguages()
      let error = await MainActor.run { coordinator.lastActionError }
      if error == nil {
        await MainActor.run { UserDefaults.standard.set(2, forKey: DefaultsKey.onboardingStep) }
        return ["status": "saved", "advanced_to_step": "2", "languages": codes.joined(separator: ",")]
      }
      return ["status": "failed", "error": error ?? "unknown"]
    }

    // Same code path as the status-menu "Reset Onboarding..." item and the
    // Settings "Reset & Restart" button — clears onboarding state and restarts
    // the app. Lets agents exercise the reset→restart→onboarding flow without
    // driving menus or the cursor.
    register(
      name: "reset_onboarding",
      summary: "Reset onboarding state and restart the app (same path as the Reset Onboarding menu item)"
    ) { _ in
      await MainActor.run {
        (AppState.current ?? AppState()).resetOnboardingAndRestart()
      }
      return ["status": "resetting and restarting"]
    }

    register(
      name: "sign_out",
      summary: "Sign out via AuthService (local Auth emulator harness only)"
    ) { _ in
      guard DesktopLocalProfile.isEnabled else {
        return ["error": "sign_out is only available with OMI_DESKTOP_LOCAL_PROFILE=1 (local Auth emulator)"]
      }
      guard AuthState.shared.isSignedIn else {
        return ["signed_out": "true", "was_signed_in": "false"]
      }
      try await MainActor.run {
        try AuthService.shared.signOut()
      }
      return [
        "signed_out": "true",
        "was_signed_in": "true",
        "is_signed_in": AuthState.shared.isSignedIn ? "true" : "false",
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

    // Drive the redesigned Home stage (inline chat / connect tray) without the
    // cursor. Each posts the notification DashboardPage observes, which calls
    // the exact functions the on-screen controls call.
    register(
      name: "home_open_chat",
      summary: "Open the inline chat on Home (same path as clicking the ask bar)"
    ) { _ in
      NotificationCenter.default.post(name: .homeStageOpenChat, object: nil)
      return nil
    }

    register(
      name: "home_connect_toggle",
      summary: "Toggle the Connect tray on Home (same path as the ask-bar Connect button)"
    ) { _ in
      NotificationCenter.default.post(name: .homeStageToggleConnect, object: nil)
      return nil
    }

    register(
      name: "home_close_panel",
      summary: "Collapse Home back to the hub (same as Esc / the close buttons)"
    ) { _ in
      NotificationCenter.default.post(name: .homeStageClose, object: nil)
      return nil
    }

    register(
      name: "home_ask",
      summary: "Send a query through the Home ask bar (opens the inline chat and sends)",
      params: ["query"]
    ) { params in
      let query = (params["query"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      guard !query.isEmpty else { return ["error": "missing 'query'"] }
      NotificationCenter.default.post(
        name: .homeStageAsk, object: nil, userInfo: ["query": query])
      return ["sent": query]
    }

    register(
      name: "home_attach",
      summary: "Stage a file in the Home ask bar (same wiring as the paperclip/drag-drop)",
      params: ["path"]
    ) { params in
      let path = (params["path"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      guard !path.isEmpty, FileManager.default.fileExists(atPath: path) else {
        return ["error": "missing or nonexistent 'path'"]
      }
      NotificationCenter.default.post(
        name: .homeStageAttach, object: nil, userInfo: ["path": path])
      return ["staged": path]
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

    register(
      name: "reset_main_chat",
      summary: "Clear main-window chat messages and start a fresh session (harness flow isolation)",
      params: []
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "reset_main_chat is disabled on production bundles"]
      }
      guard let provider = ChatProvider.mainInstance else {
        return ["error": "main ChatProvider not yet initialized"]
      }
      _ = await provider.automationClearOwnerSurfaceState(chatId: "default")
      if let error = await provider.automationResetChatForHarness() {
        return ["error": error]
      }
      return ["reset": "true"]
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

    // Fire-and-forget main-chat send for race/busy probes. Returns before the
    // turn settles so harnesses can observe isSending / concurrent rejection.
    // Optional hold_busy_ms arms a non-prod latch so R3 does not depend on LLM
    // latency keeping isSending true.
    register(
      name: "ask_main_chat_no_wait",
      summary: "Fire-and-forget main-chat send; returns immediately without waiting for the turn",
      params: ["query", "hold_busy_ms"]
    ) { params in
      let query = (params["query"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      guard !query.isEmpty else { return ["error": "missing 'query'"] }
      guard let provider = ChatProvider.mainInstance else {
        return ["error": "main ChatProvider not yet initialized"]
      }
      let isSending = provider.isSending
      let isStreaming = provider.messages.contains(where: { $0.isStreaming })
      let latchBusy = self.harnessBusyLatchActive()
      let busy = isSending || isStreaming || latchBusy
      if busy {
        return [
          "accepted": "false",
          "busy": "true",
          "is_sending": isSending ? "true" : "false",
          "is_streaming": isStreaming ? "true" : "false",
          "harness_busy_latch": latchBusy ? "true" : "false",
          "reason": "already_sending",
          "query": query,
        ]
      }
      let holdBusyMs = intParam(params["hold_busy_ms"], default: 0)
      if holdBusyMs > 0 {
        guard AppBuild.isNonProduction else {
          return ["error": "hold_busy_ms is disabled on production bundles"]
        }
        self.armHarnessBusyLatch(holdBusyMs: holdBusyMs)
      }
      Task { @MainActor in
        let tracer = QueryTracer(query: query, inputMode: .text)
        await QueryTracerContext.$current.withValue(tracer) {
          _ = await provider.sendMessage(query)
        }
      }
      return [
        "accepted": "true",
        "busy": "false",
        "is_sending": "false",
        "is_streaming": isStreaming ? "true" : "false",
        "harness_busy_latch": holdBusyMs > 0 ? "true" : "false",
        "hold_busy_ms": "\(max(0, holdBusyMs))",
        "sent": query,
      ]
    }

    register(
      name: "main_chat_busy_state",
      summary: "Return whether main chat is currently sending or streaming (race/busy probes)",
      params: []
    ) { _ in
      guard let provider = ChatProvider.mainInstance else {
        return ["error": "main ChatProvider not yet initialized"]
      }
      let isSending = provider.isSending
      let isStreaming = provider.messages.contains(where: { $0.isStreaming })
      let latchBusy = self.harnessBusyLatchActive()
      return [
        "is_sending": isSending ? "true" : "false",
        "is_streaming": isStreaming ? "true" : "false",
        "harness_busy_latch": latchBusy ? "true" : "false",
        "busy": (isSending || isStreaming || latchBusy) ? "true" : "false",
      ]
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
      name: "set_chat_drafts",
      summary: "Set main and floating composer drafts without sending (non-prod persistence harness)",
      params: ["main", "floating"],
      category: "chat",
      surfaces: ["main_chat", "ask_omi"],
      safety: "local",
      sideEffects: ["local_storage"],
      examples: ["./scripts/omi-ctl action set_chat_drafts main=main-draft floating=notch-draft"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "set_chat_drafts is disabled on production bundles"]
      }
      if let main = params["main"] {
        if let provider = ChatProvider.mainInstance {
          provider.draftText = main
        } else {
          ChatDraftStore.shared.setText(main, for: .mainChat(contextID: "omi:default"))
        }
      }
      if let floating = params["floating"] {
        if let barState = FloatingControlBarManager.shared.barState {
          barState.switchAIDraft(to: .floatingMain)
          barState.aiInputText = floating
        } else {
          ChatDraftStore.shared.setText(floating, for: .floatingMain)
        }
      }
      ChatDraftStore.shared.flush()
      return [
        "main": ChatProvider.mainInstance?.draftText
          ?? ChatDraftStore.shared.text(for: .mainChat(contextID: "omi:default")),
        "floating": FloatingControlBarManager.shared.barState?.aiInputText
          ?? ChatDraftStore.shared.text(for: .floatingMain),
      ]
    }

    register(
      name: "chat_drafts_snapshot",
      summary: "Read current main and floating composer drafts (non-prod persistence harness)",
      category: "chat",
      surfaces: ["main_chat", "ask_omi"],
      safety: "read_only"
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "chat_drafts_snapshot is disabled on production bundles"]
      }
      return [
        "main": ChatProvider.mainInstance?.draftText
          ?? ChatDraftStore.shared.text(for: .mainChat(contextID: "omi:default")),
        "floating": FloatingControlBarManager.shared.barState?.aiInputText
          ?? ChatDraftStore.shared.text(for: .floatingMain),
      ]
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
      name: "suspend_agent_stream",
      summary: "Freeze the agent stdio stream (SIGSTOP) to induce a chat stall; auto-resumes after durationMs. Non-prod only.",
      params: ["durationMs"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "suspend_agent_stream is disabled on production bundles"]
      }
      // Default just past the 180s send watchdog so CHAT-02 can assert the
      // "Response took too long" error + recoverable retry; capped at 300s.
      let durationMs = intParam(params["durationMs"], default: 190_000)
      return await AgentRuntimeProcess.shared.debugSuspendStream(durationMs: durationMs)
    }

    register(
      name: "resume_agent_stream",
      summary: "Resume a suspended agent stdio stream (SIGCONT) immediately. Non-prod only.",
      params: []
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "resume_agent_stream is disabled on production bundles"]
      }
      return await AgentRuntimeProcess.shared.debugResumeStream()
    }

    register(
      name: "floating_bar_chat_snapshot",
      summary: "Export floating-bar chat transcript and stream state for harness assertions",
      params: ["limit"]
    ) { params in
      let limit = max(1, intParam(params["limit"], default: 50))
      return FloatingControlBarManager.shared.automationFloatingBarChatSnapshot(limit: limit)
    }

    register(
      name: "wait_floating_bar_chat_idle",
      summary: "Block until floating-bar chat is not sending or streaming",
      params: ["timeoutMs", "pollMs"]
    ) { params in
      let timeoutMs = max(1_000, intParam(params["timeoutMs"], default: 180_000))
      let pollMs = max(100, intParam(params["pollMs"], default: 500))
      let deadline = Date().addingTimeInterval(Double(timeoutMs) / 1000.0)
      while Date() < deadline {
        var detail = FloatingControlBarManager.shared.automationFloatingBarChatSnapshot(limit: 8)
        if detail["error"] == nil,
           detail["is_sending"] == "false",
           detail["is_streaming"] == "false"
        {
          detail["idle"] = "true"
          return detail
        }
        try await Task.sleep(nanoseconds: UInt64(pollMs) * 1_000_000)
      }
      var detail = FloatingControlBarManager.shared.automationFloatingBarChatSnapshot(limit: 8)
      detail["error"] = "timeout"
      detail["timeout_ms"] = "\(timeoutMs)"
      return detail
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
      // Drop harness race latch so later probes are not stuck "busy" after R3.
      self.clearHarnessBusyLatch()
      let deadline = Date().addingTimeInterval(Double(timeoutMs) / 1000.0)
      while Date() < deadline {
        if !provider.isSending && !provider.messages.contains(where: { $0.isStreaming }) {
          var detail = provider.automationMainChatSnapshot(limit: 8)
          detail["idle"] = "true"
          detail["harness_busy_latch"] = "false"
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
      if let appState = await MainActor.run(body: { AppState.current }) {
        guard await appState.deleteConversation(id) else {
          throw APIError.invalidResponse
        }
      } else {
        try await APIClient.shared.deleteConversation(id: id)
        NotificationCenter.default.post(
          name: .conversationDeleted,
          object: nil,
          userInfo: ["conversationId": id]
        )
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
        let classification: String
        switch error {
        case .noBrowserFound:
          classification = "no_browser"
        case .noGmailCookies, .notSignedIn:
          classification = "not_signed_in"
        case .sessionExpired, .authFailed:
          classification = "session_expired"
        case .cookieDecryptionFailed:
          classification = "decrypt_failed"
        case .networkError:
          classification = "network"
        case .pythonNotFound:
          classification = "python_not_found"
        }
        return [
          "status": "error",
          "classification": classification,
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

    register(
      name: "open_conversation",
      summary: "Open a conversation detail view (same path as POST /conversation/open)",
      params: ["conversationId", "showTranscript"]
    ) { params in
      guard let conversationId = params["conversationId"]?.trimmingCharacters(in: .whitespacesAndNewlines),
        !conversationId.isEmpty
      else {
        return ["error": "missing conversationId"]
      }
      let showTranscript = boolParam(params["showTranscript"], default: false)
      try await ensureConversationsTabVisibleForAutomation()
      NotificationCenter.default.post(
        name: .desktopAutomationOpenConversationRequested,
        object: nil,
        userInfo: ["conversationId": conversationId, "showTranscript": showTranscript]
      )
      return [
        "opened": conversationId,
        "show_transcript": showTranscript ? "true" : "false",
      ]
    }

    register(
      name: "open_latest_conversation",
      summary: "Open the most recently loaded conversation detail view",
      params: ["showTranscript"]
    ) { params in
      guard let appState = AppState.current else {
        return ["error": "app state unavailable"]
      }
      if appState.conversations.isEmpty {
        await appState.refreshConversations()
      }
      guard let conversationId = appState.conversations.first?.id else {
        return ["error": "no conversations available"]
      }
      let showTranscript = boolParam(params["showTranscript"], default: false)
      try await ensureConversationsTabVisibleForAutomation()
      NotificationCenter.default.post(
        name: .desktopAutomationOpenConversationRequested,
        object: nil,
        userInfo: ["conversationId": conversationId, "showTranscript": showTranscript]
      )
      return [
        "opened": conversationId,
        "show_transcript": showTranscript ? "true" : "false",
      ]
    }

    register(
      name: "conversation_detail_snapshot",
      summary: "Return open conversation detail fields for harness assertions",
      params: ["conversationId"]
    ) { params in
      var requestedId = params["conversationId"]?.trimmingCharacters(in: .whitespacesAndNewlines)
      if requestedId == "latest" {
        if let appState = AppState.current, appState.conversations.isEmpty {
          await appState.refreshConversations()
        }
        requestedId = AppState.current?.conversations.first?.id
      }
      let automation = ConversationDetailAutomationState.shared
      let conversationId = (requestedId?.isEmpty == false ? requestedId : automation.openConversationId)
      guard let conversationId, !conversationId.isEmpty else {
        return [
          "detail_open": "false",
          "error": "no open conversation",
        ]
      }
      let detailOpen = automation.openConversationId == conversationId
      let drawerOpen = detailOpen && automation.transcriptDrawerOpen
      do {
        let conversation = try await APIClient.shared.getConversation(id: conversationId)
        let segmentCount = conversation.transcriptSegments.count
        return [
          "detail_open": detailOpen ? "true" : "false",
          "conversation_id": conversationId,
          "title": conversation.structured.title,
          "segment_count": "\(segmentCount)",
          "transcript_drawer_open": drawerOpen ? "true" : "false",
          "folder_id": conversation.folderId ?? "none",
          "starred": conversation.starred ? "true" : "false",
        ]
      } catch {
        guard let appState = AppState.current,
          let cached = appState.conversations.first(where: { $0.id == conversationId })
        else {
          return [
            "detail_open": detailOpen ? "true" : "false",
            "conversation_id": conversationId,
            "transcript_drawer_open": drawerOpen ? "true" : "false",
            "error": error.localizedDescription,
          ]
        }
        return [
          "detail_open": detailOpen ? "true" : "false",
          "conversation_id": conversationId,
          "title": cached.structured.title,
          "segment_count": "\(cached.transcriptSegments.count)",
          "transcript_drawer_open": drawerOpen ? "true" : "false",
          "folder_id": cached.folderId ?? "none",
          "starred": cached.starred ? "true" : "false",
        ]
      }
    }

    register(
      name: "create_test_memory",
      summary: "Create a hermetic test memory via the real API",
      params: ["content", "source"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "create_test_memory is disabled on production bundles"]
      }
      let content = params["content"] ?? "[[MARKER:memory-crud]] hermetic desktop memory"
      let response = try await APIClient.shared.createMemory(
        content: content,
        source: params["source"] ?? "harness"
      )
      if let page = try? await APIClient.shared.getMemoriesPage(limit: 100, offset: 0) {
        try? await MemoryStorage.shared.syncServerMemories(page.memories)
      }
      let memoryCount = (try? await MemoryStorage.shared.getLocalMemoriesCount()) ?? 0
      return [
        "created": "true",
        "memory_id": response.id,
        "memory_count": "\(memoryCount)",
      ]
    }

    register(
      name: "edit_test_memory",
      summary: "Edit a hermetic test memory via the real API",
      params: ["id", "marker", "content"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "edit_test_memory is disabled on production bundles"]
      }
      let content = params["content"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      guard !content.isEmpty else {
        return ["error": "missing content"]
      }
      let id: String?
      if let explicit = params["id"]?.trimmingCharacters(in: .whitespacesAndNewlines), !explicit.isEmpty {
        id = explicit
      } else if let marker = params["marker"]?.trimmingCharacters(in: .whitespacesAndNewlines), !marker.isEmpty {
        let page = try await APIClient.shared.getMemoriesPage(limit: 100, offset: 0)
        id = page.memories.first(where: { $0.content.contains(marker) })?.id
      } else {
        id = nil
      }
      guard let id, !id.isEmpty else {
        return ["error": "missing id or marker match"]
      }
      try await APIClient.shared.editMemory(id: id, content: content)
      if let page = try? await APIClient.shared.getMemoriesPage(limit: 100, offset: 0) {
        try? await MemoryStorage.shared.syncServerMemories(page.memories)
      }
      return [
        "edited": id,
        "content": content,
      ]
    }

    register(
      name: "delete_test_memory",
      summary: "Delete a hermetic test memory via the real API",
      params: ["id", "marker"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "delete_test_memory is disabled on production bundles"]
      }
      let id: String?
      if let explicit = params["id"]?.trimmingCharacters(in: .whitespacesAndNewlines), !explicit.isEmpty {
        id = explicit
      } else if let marker = params["marker"]?.trimmingCharacters(in: .whitespacesAndNewlines), !marker.isEmpty {
        let page = try await APIClient.shared.getMemoriesPage(limit: 100, offset: 0)
        id = page.memories.first(where: { $0.content.contains(marker) })?.id
      } else {
        id = nil
      }
      guard let id, !id.isEmpty else {
        return ["error": "missing id or marker match"]
      }
      try await APIClient.shared.deleteMemory(id: id)
      try? await MemoryStorage.shared.deleteMemoryByBackendId(id)
      if let page = try? await APIClient.shared.getMemoriesPage(limit: 100, offset: 0) {
        try? await MemoryStorage.shared.syncServerMemories(page.memories)
      }
      let memoryCount = (try? await MemoryStorage.shared.getLocalMemoriesCount()) ?? 0
      return [
        "deleted": id,
        "memory_count": "\(memoryCount)",
      ]
    }

    register(
      name: "vocabulary_snapshot",
      summary: "Return transcription custom vocabulary for harness assertions"
    ) { _ in
      let terms = AssistantSettings.shared.transcriptionVocabulary
      let termsJSON: String
      if let data = try? JSONSerialization.data(withJSONObject: terms),
        let encoded = String(data: data, encoding: .utf8)
      {
        termsJSON = encoded
      } else {
        termsJSON = "[]"
      }
      return [
        "term_count": "\(terms.count)",
        "terms_json": termsJSON,
      ]
    }

    register(
      name: "vocabulary_set_terms",
      summary: "Set transcription custom vocabulary (local + backend)",
      params: ["terms"]
    ) { params in
      let raw = params["terms"] ?? ""
      let terms = raw.split(separator: ",")
        .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }
      AssistantSettings.shared.transcriptionVocabulary = terms
      _ = try await APIClient.shared.updateTranscriptionPreferences(vocabulary: terms)
      return [
        "saved": "true",
        "term_count": "\(terms.count)",
      ]
    }

    register(
      name: "goals_snapshot",
      summary: "Return dashboard goals state for harness assertions"
    ) { _ in
      let goals: [Goal]
      if let apiGoals = try? await APIClient.shared.getGoals() {
        goals = apiGoals
      } else if let localGoals = try? await GoalStorage.shared.getLocalGoals() {
        goals = localGoals
      } else {
        goals = []
      }
      let titles = goals.map(\.title)
      let titlesJSON: String
      if let data = try? JSONSerialization.data(withJSONObject: titles),
        let encoded = String(data: data, encoding: .utf8)
      {
        titlesJSON = encoded
      } else {
        titlesJSON = "[]"
      }
      return [
        "goal_count": "\(goals.count)",
        "titles_json": titlesJSON,
      ]
    }

    register(
      name: "create_test_goal",
      summary: "Create a hermetic dashboard goal via the real API",
      params: ["title", "targetValue", "currentValue"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "create_test_goal is disabled on production bundles"]
      }
      let title = params["title"] ?? "[[MARKER:goals-dashboard]] harness goal"
      let targetValue = Double(params["targetValue"] ?? "") ?? 10
      let currentValue = Double(params["currentValue"] ?? "") ?? 0
      let goal = try await APIClient.shared.createGoal(
        title: title,
        goalType: .numeric,
        targetValue: targetValue,
        currentValue: currentValue,
        source: "harness"
      )
      _ = try? await GoalStorage.shared.syncServerGoal(goal)
      let goals = (try? await GoalStorage.shared.getLocalGoals()) ?? []
      return [
        "created": "true",
        "goal_id": goal.id,
        "goal_count": "\(goals.count)",
      ]
    }

    register(
      name: "apps_catalog_snapshot",
      summary: "Return apps marketplace catalog counts for harness assertions"
    ) { _ in
      let v2 = try await APIClient.shared.getAppsV2()
      let marketplaceCount = v2.groups.reduce(0) { $0 + $1.data.count }
      let installed = try await APIClient.shared.searchApps(installedOnly: true, limit: 200)
      return [
        "marketplace_count": "\(marketplaceCount)",
        "group_count": "\(v2.meta.groupCount)",
        "capability_count": "\(v2.meta.capabilities.count)",
        "installed_count": "\(installed.count)",
      ]
    }

    register(
      name: "subscription_snapshot",
      summary: "Return cached subscription/plan info from the billing API"
    ) { _ in
      let response = try await APIClient.shared.getUserSubscription()
      let subscription = response.subscription
      return [
        "plan": subscription.plan.rawValue,
        "status": subscription.status.rawValue,
        "show_subscription_ui": response.showSubscriptionUI ? "true" : "false",
        "transcription_seconds_used": "\(response.transcriptionSecondsUsed)",
        "transcription_seconds_limit": "\(response.transcriptionSecondsLimit)",
      ]
    }

    register(
      name: "settings_privacy_snapshot",
      summary: "Return privacy toggle defaults (store recordings, cloud sync, tracking)"
    ) { _ in
      async let recordingTask = APIClient.shared.getRecordingPermission()
      async let cloudSyncTask = APIClient.shared.getPrivateCloudSync()
      let (recording, cloudSync) = try await (recordingTask, cloudSyncTask)
      let trackingEnabled = PostHogManager.shared.hasOptedOut
      return [
        "store_recordings": recording.enabled ? "true" : "false",
        "cloud_sync": cloudSync.enabled ? "true" : "false",
        "tracking_enabled": trackingEnabled ? "true" : "false",
      ]
    }

    register(
      name: "create_test_folder",
      summary: "Create a hermetic conversation folder via the real API",
      params: ["name"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "create_test_folder is disabled on production bundles"]
      }
      let name = params["name"] ?? "[[MARKER:conversation-folders]] harness folder"
      guard let appState = AppState.current else {
        return ["error": "app state unavailable"]
      }
      guard let folder = await appState.createFolder(name: name) else {
        return ["error": "failed to create folder"]
      }
      return [
        "created": "true",
        "folder_id": folder.id,
        "folder_name": folder.name,
        "folder_count": "\(appState.folders.count)",
      ]
    }

    register(
      name: "set_conversation_starred",
      summary: "Set conversation starred status via the real API",
      params: ["conversationId", "starred"]
    ) { params in
      guard let conversationId = params["conversationId"]?.trimmingCharacters(in: .whitespacesAndNewlines),
        !conversationId.isEmpty
      else {
        return ["error": "missing conversationId"]
      }
      let resolvedConversationId: String
      if conversationId == "latest" {
        guard let appState = AppState.current else {
          return ["error": "app state unavailable"]
        }
        if appState.conversations.isEmpty {
          await appState.refreshConversations()
        }
        guard let latestId = appState.conversations.first?.id else {
          return ["error": "no conversations available"]
        }
        resolvedConversationId = latestId
      } else {
        resolvedConversationId = conversationId
      }
      let starred = boolParam(params["starred"], default: true)
      guard let appState = AppState.current else {
        return ["error": "app state unavailable"]
      }
      try await appState.conversationRepository.setStarred(
        id: resolvedConversationId, starred: starred)
      return [
        "conversation_id": resolvedConversationId,
        "starred": starred ? "true" : "false",
      ]
    }

    register(
      name: "set_conversation_folder",
      summary: "Move a conversation into a folder via the real API",
      params: ["conversationId", "folderId"]
    ) { params in
      let rawConversationId = params["conversationId"]?.trimmingCharacters(in: .whitespacesAndNewlines)
      guard let rawConversationId, !rawConversationId.isEmpty else {
        return ["error": "missing conversationId"]
      }
      let conversationId: String
      if rawConversationId == "latest" {
        guard let appState = AppState.current else {
          return ["error": "app state unavailable"]
        }
        if appState.conversations.isEmpty {
          await appState.refreshConversations()
        }
        guard let latestId = appState.conversations.first?.id else {
          return ["error": "no conversations available"]
        }
        conversationId = latestId
      } else {
        conversationId = rawConversationId
      }
      let folderId = params["folderId"]?.trimmingCharacters(in: .whitespacesAndNewlines)
      let resolvedFolderId = (folderId?.isEmpty == false && folderId != "none") ? folderId : nil
      guard let appState = AppState.current else {
        return ["error": "app state unavailable"]
      }
      await appState.moveConversationToFolder(conversationId, folderId: resolvedFolderId)
      return [
        "conversation_id": conversationId,
        "folder_id": resolvedFolderId ?? "none",
      ]
    }

    register(
      name: "set_transcription_language",
      summary: "Set transcription language (local + backend)",
      params: ["language", "autoDetect"]
    ) { params in
      guard let rawLanguage = params["language"]?.trimmingCharacters(in: .whitespacesAndNewlines),
        !rawLanguage.isEmpty
      else {
        return ["error": "missing language"]
      }
      let normalized = AssistantSettings.normalizeTranscriptionLanguageCode(rawLanguage)
      if let autoDetectRaw = params["autoDetect"] {
        AssistantSettings.shared.transcriptionAutoDetect = boolParam(autoDetectRaw, default: true)
      }
      AssistantSettings.shared.transcriptionLanguage = normalized
      _ = try await APIClient.shared.updateUserLanguage(normalized)
      return [
        "saved": "true",
        "language": normalized,
        "auto_detect": AssistantSettings.shared.transcriptionAutoDetect ? "true" : "false",
        "effective_language": AssistantSettings.shared.effectiveTranscriptionLanguage,
      ]
    }

    register(
      name: "transcription_language_snapshot",
      summary: "Return transcription language settings for harness assertions"
    ) { _ in
      let settings = AssistantSettings.shared
      return [
        "language": settings.transcriptionLanguage,
        "auto_detect": settings.transcriptionAutoDetect ? "true" : "false",
        "effective_language": settings.effectiveTranscriptionLanguage,
      ]
    }

    register(
      name: "memory_graph_snapshot",
      summary: "Return knowledge graph node/edge counts (no SceneKit rendering)",
      params: []
    ) { _ in
      do {
        let graph = try await APIClient.shared.getKnowledgeGraph()
        return [
          "node_count": "\(graph.nodes.count)",
          "edge_count": "\(graph.edges.count)",
          "is_empty": graph.nodes.isEmpty ? "true" : "false",
        ]
      } catch {
        return [
          "node_count": "0",
          "edge_count": "0",
          "is_empty": "true",
          "has_error": "true",
          "error_message": error.localizedDescription,
        ]
      }
    }

    register(
      name: "open_quick_note",
      summary: "Open Quick Note via Rewind notes path (same as dashboard Quick Note button)"
    ) { _ in
      NotificationCenter.default.post(name: .navigateToRewindNotes, object: nil)
      return [
        "posted": "navigateToRewindNotes",
        "expected_tab_index": "\(SidebarNavItem.rewind.rawValue)",
      ]
    }

    register(
      name: "about_snapshot",
      summary: "Return About settings version/build/bundle metadata"
    ) { _ in
      let updater = UpdaterViewModel.shared
      return [
        "version": updater.currentVersion,
        "build": updater.buildNumber,
        "bundle_id": AppBuild.bundleIdentifier,
        "channel": updater.activeChannelLabel,
      ]
    }

    register(
      name: "settings_notifications_snapshot",
      summary: "Return notification settings and local permission state"
    ) { _ in
      async let settingsTask = APIClient.shared.getNotificationSettings()
      let settings = try await settingsTask
      let appState = await MainActor.run { AppState.current }
      let hasPermission = appState?.hasNotificationPermission ?? false
      let bannersDisabled = appState?.isNotificationBannerDisabled ?? false
      return [
        "enabled": settings.enabled ? "true" : "false",
        "frequency": "\(settings.frequency)",
        "frequency_label": settings.frequencyDescription,
        "has_permission": hasPermission ? "true" : "false",
        "banners_disabled": bannersDisabled ? "true" : "false",
      ]
    }

    register(
      name: "set_notification_settings",
      summary: "Update notification settings via the real API",
      params: ["enabled", "frequency"]
    ) { params in
      let enabled = params["enabled"].map { boolParam($0, default: true) }
      let frequency = params["frequency"].flatMap { Int($0) }
      let response = try await APIClient.shared.updateNotificationSettings(
        enabled: enabled,
        frequency: frequency
      )
      return [
        "saved": "true",
        "enabled": response.enabled ? "true" : "false",
        "frequency": "\(response.frequency)",
      ]
    }

    register(
      name: "rewind_settings_snapshot",
      summary: "Return Rewind settings retention and excluded-app counts"
    ) { _ in
      let settings = RewindSettings.shared
      let stats = await RewindIndexer.shared.getStats()
      return [
        "retention_days": "\(settings.retentionDays)",
        "capture_interval": String(format: "%.1f", settings.captureInterval),
        "excluded_app_count": "\(settings.excludedApps.count)",
        "indexed_frames": "\(stats?.indexed ?? 0)",
        "total_frames": "\(stats?.total ?? 0)",
        "storage_bytes": "\(stats?.storageSize ?? 0)",
      ]
    }

    register(
      name: "navigate_via_shortcut",
      summary: "Post the same sidebar navigation notification as Cmd+1..6 / Cmd+, shortcuts",
      params: ["shortcut"]
    ) { params in
      let shortcut = (params["shortcut"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
      guard !shortcut.isEmpty else {
        return ["error": "missing shortcut (1-6 or comma)"]
      }
      let item: SidebarNavItem?
      switch shortcut {
      case "1", "home", "dashboard": item = .dashboard
      case "2", "conversations": item = .conversations
      case "3", "memories": item = .memories
      case "4", "tasks": item = .tasks
      case "5", "rewind": item = .rewind
      case "6", "apps": item = .apps
      case ",", "comma", "settings": item = .settings
      default: item = nil
      }
      guard let item else {
        return ["error": "unsupported shortcut '\(shortcut)'"]
      }
      NotificationCenter.default.post(
        name: .navigateToSidebarItem,
        object: nil,
        userInfo: ["rawValue": item.rawValue]
      )
      return [
        "navigated": item.title,
        "selected_tab_index": "\(item.rawValue)",
      ]
    }

    register(
      name: "advanced_settings_snapshot",
      summary: "Return safe Advanced settings booleans (never raw BYOK keys)",
      params: []
    ) { _ in
      let focus = FocusAssistantSettings.shared
      let task = TaskAssistantSettings.shared
      let insight = InsightAssistantSettings.shared
      let memory = MemoryAssistantSettings.shared
      let assistant = AssistantSettings.shared
      return [
        "focus_enabled": focus.isEnabled ? "true" : "false",
        "task_enabled": task.isEnabled ? "true" : "false",
        "task_chat_agent_enabled": TaskAgentSettings.shared.isChatEnabled ? "true" : "false",
        "insight_enabled": insight.isEnabled ? "true" : "false",
        "memory_enabled": memory.isEnabled ? "true" : "false",
        "screen_analysis_enabled": assistant.screenAnalysisEnabled ? "true" : "false",
        "transcription_enabled": assistant.transcriptionEnabled ? "true" : "false",
        "multi_chat_enabled": UserDefaults.standard.bool(forKey: .multiChatEnabled) ? "true" : "false",
      ]
    }

    register(
      name: "settings_aichat_snapshot",
      summary: "Return AI Chat settings safe fields (provider mode, working directory presence)",
      params: []
    ) { _ in
      let bridgeMode = UserDefaults.standard.string(forKey: .chatBridgeMode) ?? "piMono"
      let workingDirectory = UserDefaults.standard.string(forKey: .aiChatWorkingDirectory) ?? ""
      let multiChat = UserDefaults.standard.bool(forKey: .multiChatEnabled)
      return [
        "bridge_mode": bridgeMode,
        "working_directory_set": workingDirectory.isEmpty ? "false" : "true",
        "multi_chat_enabled": multiChat ? "true" : "false",
      ]
    }

    register(
      name: "assign_speaker_fixture",
      summary: "Assign a person name to a conversation segment (hermetic speaker naming)",
      params: ["conversationId", "segmentIndex", "personName"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "assign_speaker_fixture is disabled on production bundles"]
      }
      guard let appState = AppState.current else {
        return ["error": "app state unavailable"]
      }
      let personName = params["personName"]?.trimmingCharacters(in: .whitespacesAndNewlines)
        ?? "[[MARKER:speaker-naming]] Harness Speaker"
      let segmentIndex = max(0, Int(params["segmentIndex"] ?? "") ?? 0)

      var conversationId = params["conversationId"]?.trimmingCharacters(in: .whitespacesAndNewlines)
      if conversationId == "latest" || conversationId?.isEmpty != false {
        if appState.conversations.isEmpty {
          await appState.refreshConversations()
        }
        conversationId = appState.conversations.first?.id
      }
      guard let conversationId, !conversationId.isEmpty else {
        return ["error": "no conversation available"]
      }

      let conversation = try await APIClient.shared.getConversation(id: conversationId)
      guard segmentIndex < conversation.transcriptSegments.count else {
        return [
          "error": "segment index out of range",
          "segment_count": "\(conversation.transcriptSegments.count)",
        ]
      }
      let segment = conversation.transcriptSegments[segmentIndex]
      guard let person = await appState.createPerson(name: personName) else {
        return ["error": "failed to create person"]
      }
      let assigned = await appState.assignSpeakerToSegments(
        conversationId: conversationId,
        segmentIds: [segment.id],
        personId: person.id,
        isUser: false
      )
      guard assigned else {
        return ["error": "assign segments failed"]
      }
      let refreshed = try await APIClient.shared.getConversation(id: conversationId)
      let assignedSegment = refreshed.transcriptSegments.first(where: { $0.id == segment.id })
      return [
        "assigned": "true",
        "conversation_id": conversationId,
        "segment_id": segment.id,
        "segment_index": "\(segmentIndex)",
        "person_id": person.id,
        "person_name": person.name,
        "speaker_label": assignedSegment?.speaker ?? segment.speaker ?? "",
        "segment_count": "\(refreshed.transcriptSegments.count)",
      ]
    }

    register(
      name: "conversation_share_probe",
      summary: "Hermetic share affordance probe — fetches share link without clipboard",
      params: ["conversationId"]
    ) { params in
      let rawConversationId = params["conversationId"]?.trimmingCharacters(in: .whitespacesAndNewlines)
      guard let rawConversationId, !rawConversationId.isEmpty else {
        return ["error": "missing conversationId"]
      }
      let conversationId: String
      if rawConversationId == "latest" {
        guard let appState = AppState.current else {
          return ["error": "app state unavailable"]
        }
        if appState.conversations.isEmpty {
          await appState.refreshConversations()
        }
        guard let latestId = appState.conversations.first?.id else {
          return ["error": "no conversations available"]
        }
        conversationId = latestId
      } else {
        conversationId = rawConversationId
      }
      let shareURL = try await APIClient.shared.getConversationShareLink(id: conversationId)
      let shareAvailable = !shareURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      return [
        "conversation_id": conversationId,
        "share_available": shareAvailable ? "true" : "false",
        "share_url_present": shareAvailable ? "true" : "false",
      ]
    }

    // SET-02: assemble the exact payload FeedbackView.submitFeedback() would
    // attach — the report title + the desktop_diagnostics.json attachment + the
    // log-attachment metadata — WITHOUT calling SentrySDK, so a harness can grep
    // the diagnostics JSON for secrets without firing a real Sentry event. The
    // title and diagnostics JSON come from the same builders the real submit
    // uses (feedbackReportTitle / writeDiagnosticsAttachment), so the dry-run
    // can't diverge from what ships. The raw log is attached unredacted to Sentry
    // by design (trusted sink, explicit user report); we surface only its
    // metadata here — never its contents — so the bridge response can't leak it.
    register(
      name: "dump_feedback_payload_dryrun",
      summary: "Assemble the feedback report payload (title + desktop_diagnostics.json + log-attachment metadata) without submitting to Sentry; returns the diagnostics JSON for secret-scanning. Non-prod only.",
      params: ["message"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "dump_feedback_payload_dryrun is disabled on production bundles"]
      }
      let message = (params["message"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      var detail: [String: String] = [
        "sentry_message": feedbackReportTitle(for: message),
        "diagnostics_filename": feedbackDiagnosticsAttachmentFilename,
        "sentry_capture_invoked": "false",
        "would_submit_to_sentry": "false",
      ]

      if let url = DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment() {
        defer { try? FileManager.default.removeItem(at: url) }
        if let data = try? Data(contentsOf: url), let json = String(data: data, encoding: .utf8) {
          detail["diagnostics_json"] = json
          detail["diagnostics_byte_count"] = "\(data.count)"
        } else {
          detail["diagnostics_error"] = "unreadable_attachment"
        }
      } else {
        detail["diagnostics_error"] = "attachment_write_failed"
      }

      let logPath = omiLogFilePath()
      let logExists = FileManager.default.fileExists(atPath: logPath)
      detail["log_attachment_filename"] = (logPath as NSString).lastPathComponent
      detail["log_attachment_exists"] = logExists ? "true" : "false"
      if logExists,
        let attributes = try? FileManager.default.attributesOfItem(atPath: logPath),
        let size = attributes[.size] as? NSNumber
      {
        // int64Value, not intValue (Int32): the log can exceed 2 GB in a long dev session.
        detail["log_attachment_bytes"] = "\(size.int64Value)"
      }
      return detail
    }

    // Deliberately wedge the main thread for durationMs so harnesses can prove the
    // `/state` fallback: the bridge must keep answering `/state` from the cached
    // snapshot (snapshotStale=true) while the MainActor is blocked, instead of
    // hanging as it did when a sign-in Keychain read wedged the main thread. The
    // sleep is scheduled async so this action's own response returns first; the
    // wedge then races the next `/state` live refresh. Non-prod only; mirrors
    // `suspend_agent_stream`'s role for the agent-stall path.
    register(
      name: "debug_block_main_thread",
      summary: "Block the main thread for durationMs to exercise the /state wedged-MainActor fallback. Non-prod only.",
      params: ["durationMs"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "debug_block_main_thread is disabled on production bundles"]
      }
      let durationMs = min(max(intParam(params["durationMs"], default: 5000), 100), 20000)
      // Delay the wedge briefly so this action's own POST /action response (which
      // itself builds a live snapshot via a MainActor hop) returns *before* the
      // main thread blocks — otherwise the response would be queued behind the
      // sleep and take the full 3s /state fallback, which looks like a hang.
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
        Thread.sleep(forTimeInterval: Double(durationMs) / 1000.0)
      }
      return ["blocking_main_thread_ms": "\(durationMs)"]
    }

    // PERM-06: trigger the permission-flow "Quit & Reopen" restart — the exact
    // AppState.restartApp() path used after granting Accessibility / Screen
    // Recording — so a harness can prove the SAME bundle relaunches with the
    // session intact. Distinct from `reset_onboarding`, which mutates onboarding
    // state. The restart is scheduled after a short delay so this action's HTTP
    // response flushes before restartApp() terminates the process. Non-prod only.
    register(
      name: "quit_and_reopen",
      summary: "Trigger the permission-flow Quit & Reopen restart (AppState.restartApp) — relaunches the same bundle; auth/onboarding session persists. Non-prod only.",
      params: ["delayMs"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "quit_and_reopen is disabled on production bundles"]
      }
      guard let appState = AppState.current else {
        return ["error": "app state unavailable"]
      }
      if UpdaterViewModel.isUpdateInProgress {
        return ["error": "sparkle update in progress — restart is deferred to Sparkle"]
      }
      let bundleId = Bundle.main.bundleIdentifier ?? ""
      let relaunchPath = Bundle.main.bundleURL.path
      let delayMs = min(max(intParam(params["delayMs"], default: 400), 100), 5000)
      DispatchQueue.main.asyncAfter(deadline: .now() + Double(delayMs) / 1000.0) {
        appState.restartApp()
      }
      return [
        "restarting": "true",
        "bundle_id": bundleId,
        "relaunch_path": relaunchPath,
        "delay_ms": "\(delayMs)",
      ]
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
  private var bindAttempts = 0
  private let maxBindAttempts = 3

  private init() {}

  func startIfNeeded() {
    guard DesktopAutomationLaunchOptions.isEnabled else { return }
    guard listener == nil else { return }
    bindAttempts = 0
    attemptStartListener()
  }

  private func attemptStartListener() {
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
      listener.stateUpdateHandler = { [weak self] (state: NWListener.State) in
        log("DesktopAutomationBridge: listener state changed to \(String(describing: state))")
        if case .failed(let error) = state {
          self?.handleListenerBindFailure(error: error)
        }
      }
      listener.start(queue: queue)
      self.listener = listener
      bindAttempts = 0
      DesktopAutomationLaunchOptions.writeTokenFileIfNeeded()
      Task { @MainActor in DesktopAutomationActionRegistry.shared.registerBuiltins() }
      log(
        "DesktopAutomationBridge: listening on http://127.0.0.1:\(DesktopAutomationLaunchOptions.port)"
      )
    } catch {
      handleListenerBindFailure(error: error)
    }
  }

  private func handleListenerBindFailure(error: Error) {
    listener?.cancel()
    listener = nil
    bindAttempts += 1
    let reason = error.localizedDescription
    if bindAttempts < maxBindAttempts {
      log(
        "DesktopAutomationBridge: bind failed (attempt \(bindAttempts)/\(maxBindAttempts)), retrying: \(reason)")
      queue.asyncAfter(deadline: .now() + Double(bindAttempts)) { [weak self] in
        self?.attemptStartListener()
      }
      return
    }
    log(
      "DesktopAutomationBridge: bind failed after \(maxBindAttempts) attempts "
        + "(failure_class=bind_failed recovery_action=retry_exhausted recovery_result=exhausted): \(reason)")
    logError("DesktopAutomationBridge: failed to start listener", error: error)
    DesktopDiagnosticsManager.shared.recordAutomationBridgeBindFailed(
      port: Int(DesktopAutomationLaunchOptions.port),
      reason: reason
    )
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
          "POST /open-import",
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
    case ("POST", "/open-import"):
      struct OpenResult: Codable { let connector: String }
      let payload: DesktopAutomationOpenImportRequest
      do {
        payload = try JSONDecoder().decode(
          DesktopAutomationOpenImportRequest.self, from: request.body)
      } catch {
        return jsonResponse(
          DesktopAutomationResponse<OpenResult>(
            ok: false, result: nil, error: error.localizedDescription),
          statusCode: 400)
      }
      let knownIDs = await MainActor.run { ImportConnector.all.map(\.id) }
      guard knownIDs.contains(payload.connector) else {
        return jsonResponse(
          DesktopAutomationResponse<OpenResult>(
            ok: false, result: nil, error: "unknown connector: \(payload.connector)"),
          statusCode: 400)
      }
      do {
        await MainActor.run {
          NSApp.activate()
          if let window = NSApp.windows.first(where: { $0.title.lowercased().hasPrefix("omi") }) {
            window.makeKeyAndOrderFront(nil)
          }
          NotificationCenter.default.post(
            name: .desktopAutomationOpenImportRequested, object: nil,
            userInfo: ["connector": payload.connector])
        }
        try await Task.sleep(for: .milliseconds(300))
        return jsonResponse(
          DesktopAutomationResponse(
            ok: true, result: OpenResult(connector: payload.connector), error: nil))
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
    try await ensureConversationsTabVisibleForAutomation()
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
