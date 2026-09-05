import AppKit
import CryptoKit
import Foundation
import Network
import OmiSupport
import OmiTheme
import VoiceTurnDomain

enum DesktopAutomationLaunchOptions {
  static let enableFlag = "--automation-bridge"
  static let portPrefix = "--automation-port="
  static let captureRootPrefix = "--automation-capture-root="
  static let uiPresentationPrefix = "--automation-ui="
  static let uiPresentationEnvironmentKey = "OMI_AUTOMATION_UI_MODE"
  static let defaultPort: UInt16 = 47777
  static let tokenEnvironmentKey = "OMI_AUTOMATION_TOKEN"
  static let tokenFileEnvironmentKey = "OMI_AUTOMATION_TOKEN_FILE"

  private static let generatedToken =
    "omi_auto_\(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased())"

  static var isEnabled: Bool {
    isEnabled(
      allowsLocalAutomation: AppBuild.allowsLocalAutomation,
      arguments: CommandLine.arguments,
      environment: ProcessInfo.processInfo.environment
    )
  }

  static func isEnabled(
    allowsLocalAutomation: Bool,
    arguments: [String],
    environment: [String: String]
  ) -> Bool {
    guard allowsLocalAutomation else {
      return false
    }
    // Explicit opt-out always wins, so a dev build can be run "clean" if needed.
    if environment["OMI_DISABLE_LOCAL_AUTOMATION"] == "1" {
      return false
    }
    // Auto-enable on local bundles (Omi Dev + every `omi-*` named test bundle) so agents
    // can drive the app without remembering a launch flag. Published previews are excluded
    // by `allowsLocalAutomation` above even if their process environment is contaminated.
    return arguments.contains(enableFlag)
      || environment["OMI_ENABLE_LOCAL_AUTOMATION"] == "1"
      || allowsLocalAutomation
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

  static var uiPresentationMode: DesktopAutomationUIPresentationMode {
    uiPresentationMode(
      allowsLocalAutomation: AppBuild.allowsLocalAutomation,
      arguments: CommandLine.arguments,
      environment: ProcessInfo.processInfo.environment)
  }

  static func uiPresentationMode(
    allowsLocalAutomation: Bool,
    arguments: [String],
    environment: [String: String]
  ) -> DesktopAutomationUIPresentationMode {
    guard allowsLocalAutomation else { return .normal }
    for argument in arguments where argument.hasPrefix(uiPresentationPrefix) {
      let rawValue = String(argument.dropFirst(uiPresentationPrefix.count)).lowercased()
      return DesktopAutomationUIPresentationMode(rawValue: rawValue) ?? .normal
    }
    let rawValue = environment[uiPresentationEnvironmentKey]?.trimmingCharacters(in: .whitespacesAndNewlines)
      .lowercased()
    return rawValue.flatMap(DesktopAutomationUIPresentationMode.init(rawValue:)) ?? .normal
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
  /// The app has one shell. Flows and the navigation-visibility policy still read
  /// `shellVariant`, so it is pinned here rather than removed from the contract.
  static let singleShellVariant = "chat_first"

  var bridgeEnabled: Bool
  var bridgePort: UInt16
  var bundleIdentifier: String
  var appState: String
  var selectedTab: String?
  var selectedTabIndex: Int?
  var selectedSettingsSection: String?
  var highlightedSettingId: String?
  /// Home stage mode: `hub`, `chat`, or `connect`. `DashboardPage` was the only view that ever
  /// rendered that stage and it no longer exists, so this is now always nil. Kept in the snapshot
  /// so an older flow reading it sees "no stage" rather than a missing key.
  var homeMode: String?
  /// Always `chat_first` on a mounted shell: the app has exactly one. Nil only before the shell has
  /// reported state. Never a local preference.
  var shellVariant: String?
  /// Stable typed route for the one shell.
  var chatFirstRoute: String?
  /// Set only by the mounted Chat-first destination after it has appeared. This
  /// keeps a successful navigation response equivalent to the target being
  /// visible, rather than merely accepted by the root reducer.
  var visibleChatFirstRoute: String?
  /// Shape-only focus telemetry for route acknowledgement; entity IDs stay local.
  var pendingFocusKind: String?
  var acknowledgedFocusKind: String?
  /// The focused entity is available only through the local non-production
  /// bridge so named-bundle probes can prove the acknowledgement target. It is
  /// never an analytics dimension or a persisted navigation value.
  var focusedEntityID: String?
  var isFocusedEntityAcknowledged: Bool
  /// Retained for snapshot compatibility; the legacy sidebar shell is gone, so it is always false.
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
  /// The current hold has been recognised as a dictation (the notch's red tint).
  var floatingBarVoiceDictating: Bool
  var floatingBarVoiceResponseActive: Bool
  var floatingBarUsesNotchIsland: Bool
  var updatedAt: String
  /// True when the live MainActor refresh timed out and this is the last cached
  /// snapshot instead — e.g. the main thread is wedged on a blocking Keychain
  /// read during sign-in. The bridge still answers `/state` so harnesses don't
  /// hang; callers can detect that the live fields may be stale.
  var snapshotStale: Bool = false
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
  let processID: Int32
  let logFilePath: String
  let logLaunchID: String
  let bridgePort: UInt16
  let requiresAuth: Bool
  let backendEnvironment: String
  let pythonBackendURL: String
  let rustBackendURL: String
  let agentRuntimeRunning: Bool
  let agentRuntimeExpectedProtocolVersion: Int
  let agentRuntimeProtocolVersion: Int?
  let agentRuntimeVersion: String?
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

enum DesktopAutomationRevisionComparator {
  static func matchesAtMillisecondPrecision(_ lhs: Date?, _ rhs: Date?) -> Bool {
    guard let lhs, let rhs else { return lhs == nil && rhs == nil }
    let lhsMilliseconds = Int64((lhs.timeIntervalSince1970 * 1_000).rounded())
    let rhsMilliseconds = Int64((rhs.timeIntervalSince1970 * 1_000).rounded())
    return lhsMilliseconds == rhsMilliseconds
  }
}

private func automationSafeErrorDetail(_ raw: String) -> String {
  var detail = raw.replacingOccurrences(of: #"[\r\n\t]+"#, with: " ", options: .regularExpression)
  let redactions: [(String, String)] = [
    (#"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"#, "[redacted-jwt]"),
    (#"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}"#, "Bearer [redacted]"),
    (#"sk-[A-Za-z0-9_-]{20,}"#, "sk-[redacted]"),
  ]
  for (pattern, replacement) in redactions {
    detail = detail.replacingOccurrences(of: pattern, with: replacement, options: .regularExpression)
  }
  return String(detail.prefix(500))
}

private func automationActionErrorDescription(_ error: Error) -> String {
  if case APIError.httpError(let statusCode, let detail) = error {
    let suffix = detail.map { " detail=\(automationSafeErrorDetail($0))" } ?? ""
    return "api_http_error status=\(statusCode)\(suffix)"
  }
  return automationSafeErrorDetail(error.localizedDescription)
}

private struct DesktopAutomationResponse<T: Codable>: Codable {
  let ok: Bool
  let result: T?
  let error: String?
}

final class DesktopAutomationStateStore {
  nonisolated(unsafe) static let shared = DesktopAutomationStateStore()
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
    homeMode: nil,
    shellVariant: nil,
    chatFirstRoute: nil,
    visibleChatFirstRoute: nil,
    pendingFocusKind: nil,
    acknowledgedFocusKind: nil,
    focusedEntityID: nil,
    isFocusedEntityAcknowledged: false,
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
    floatingBarVoiceDictating: false,
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

  func resume(_ value: sending T?) {
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

func liveAutomationSnapshot() async -> DesktopAutomationSnapshot {
  // Bound the MainActor hop: if the main thread is wedged (blocking Keychain read
  // during sign-in), fall back to the last cached snapshot so `/state` still
  // answers instead of hanging the whole bridge. See awaitWithTimeout.
  guard let live = await awaitWithTimeout(liveSnapshotMainActorTimeout, operation: liveAutomationSnapshotFromMainActor)
  else {
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
      isVoiceDictating: floating.isVoiceDictating,
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
    snapshot.floatingBarVoiceDictating = floating.isVoiceDictating
    snapshot.floatingBarVoiceResponseActive = floating.isVoiceResponseActive
    snapshot.floatingBarUsesNotchIsland = floating.usesNotchIsland
    snapshot.isAppActive = floating.isAppActive
    snapshot.updatedAt = ISO8601DateFormatter().string(from: Date())
    snapshot.snapshotStale = false
  }
}

func cachedAutomationSnapshot() async -> DesktopAutomationSnapshot {
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

private func requestAutomationConversationOpen(conversationId: String, showTranscript: Bool) async {
  await MainActor.run {
    ConversationDetailAutomationState.shared.requestOpen(
      conversationId: conversationId,
      showTranscript: showTranscript
    )
    NotificationCenter.default.post(name: .desktopAutomationOpenConversationRequested, object: nil)
  }
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

  /// A 1x1 PNG, for the hermetic half of `screen_frame_quick_look_probe`. Literal bytes rather
  /// than a rendered image so the probe has no dependency on capture history, a backend, or AppKit
  /// drawing — the thing it is verifying is the panel, not the picture.
  static let onePixelPNGBase64 =
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

  private var entries: [String: Entry] = [:]
  private var didRegisterBuiltins = false
  /// Non-prod harness latch so race probes stay busy without relying on LLM latency.
  private var harnessBusyUntil: Date?
  /// The current typed floating-bar submission and its pre-submit timeline size.
  /// The wait action must observe this turn before it may accept an idle state.
  private var pendingFloatingBarSubmission: (generation: Int, baselineMessageCount: Int)?
  private var floatingBarSubmissionGeneration = 0

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

  func unregister(_ name: String) { entries[name] = nil }

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
    registerOpenOmiShortcutActionsForQA()
    register(
      name: "set_automation_ui_presentation",
      summary:
        "Park automation windows quietly, reveal them briefly for Accessibility, or restore normal user presentation",
      params: ["mode", "activate"],
      category: "app_control",
      surfaces: ["app"],
      safety: "local_ui_state",
      sideEffects: ["changes non-production window placement and input handling"],
      examples: [
        "./scripts/omi-ctl ui quiet",
        "./scripts/omi-ctl ui interactive --activate",
        "./scripts/omi-ctl ui normal --activate",
      ]
    ) { params in
      // This registry is reachable only through DesktopAutomationBridge, whose listener cannot start
      // for production-family or published-preview bundles. Keep the handler itself exercisable in a
      // hermetic test instead of duplicating the bridge's stronger process boundary here.
      guard let requested = params["mode"]?.lowercased() else {
        return [
          "mode": DesktopAutomationWindowPresentation.currentMode.rawValue,
          "available_modes": DesktopAutomationUIPresentationMode.allCases.map(\.rawValue).joined(
            separator: ","),
        ]
      }
      guard let mode = DesktopAutomationUIPresentationMode(rawValue: requested) else {
        throw DesktopAutomationActionError.invalidParams(
          "mode must be normal, quiet, or interactive")
      }
      let activate = boolParam(params["activate"], default: false)
      let previous = DesktopAutomationWindowPresentation.setMode(mode, activate: activate)
      return [
        "previous_mode": previous.rawValue,
        "mode": DesktopAutomationWindowPresentation.currentMode.rawValue,
        "activated": activate ? "true" : "false",
      ]
    }
    // Cursor-free Home-stage and first-use-popup drivers: see their own files for the shared failure mode.
    registerHomeStageActions()
    registerActivationActions()
    registerFirstUsePopupActions()
    register(
      name: "refresh_all_data",
      summary: "Refresh conversations, chat, tasks, and memories (same as Cmd+R)"
    ) { _ in
      NotificationCenter.default.post(name: .refreshAllData, object: nil)
      return nil
    }

    // Posts a real keyDown+keyUp pair through the app's own event queue, so local
    // NSEvent monitors and SwiftUI key equivalents see it exactly like a physical
    // keypress — lets a headless harness drive keyboard navigation without
    // Accessibility permission or a frontmost window. Non-prod only.
    register(
      name: "post_key",
      summary:
        "Post a keyDown+keyUp NSEvent through the app event queue (e.g. key_code=124 for right arrow). Non-prod only.",
      params: ["key_code", "modifiers"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "post_key is disabled on production bundles"]
      }
      guard let codeText = params["key_code"], let keyCode = UInt16(codeText) else {
        throw DesktopAutomationActionError.invalidParams("key_code must be a numeric macOS key code")
      }
      var modifiers: NSEvent.ModifierFlags = []
      for token in (params["modifiers"] ?? "").split(separator: ",") {
        switch token.trimmingCharacters(in: .whitespaces).lowercased() {
        case "command", "cmd": modifiers.insert(.command)
        case "shift": modifiers.insert(.shift)
        case "option", "alt": modifiers.insert(.option)
        case "control", "ctrl": modifiers.insert(.control)
        case "function", "fn": modifiers.insert(.function)
        case "": break
        default:
          throw DesktopAutomationActionError.invalidParams("unknown modifier '\(token)'")
        }
      }
      // Arrow keys carry their function-key character and the flags a physical
      // press would have, so consumers that look at characters/flags match too.
      let arrowCharacters: [UInt16: String] = [
        123: "\u{F702}", 124: "\u{F703}", 125: "\u{F701}", 126: "\u{F700}",
      ]
      let characters = arrowCharacters[keyCode] ?? ""
      if arrowCharacters[keyCode] != nil {
        modifiers.formUnion([.function, .numericPad])
      }
      let window = NSApp.keyWindow ?? NSApp.mainWindow
      var posted = 0
      for phase in [NSEvent.EventType.keyDown, .keyUp] {
        if let event = NSEvent.keyEvent(
          with: phase, location: .zero, modifierFlags: modifiers,
          timestamp: ProcessInfo.processInfo.systemUptime,
          windowNumber: window?.windowNumber ?? 0, context: nil,
          characters: characters, charactersIgnoringModifiers: characters,
          isARepeat: false, keyCode: keyCode)
        {
          NSApp.postEvent(event, atStart: false)
          posted += 1
        }
      }
      return [
        "posted_events": "\(posted)",
        "key_code": "\(keyCode)",
        "window": window.map { $0.title.isEmpty ? "untitled" : $0.title } ?? "none",
      ]
    }
    // CHAT-05: read the free-tier monthly chat usage-limiter state so a harness can
    // prove the counter is deterministic without spending LLM calls. Read-only.
    register(
      name: "usage_limiter_snapshot",
      summary: "Read the free-tier monthly chat usage-limiter state (deterministic counter) — CHAT-05 harness read."
    ) { _ in
      await MainActor.run {
        let limiter = FloatingBarUsageLimiter.shared
        let banner = ChatQuotaBanner.current(
          quota: limiter.serverQuota,
          optimisticDelta: limiter.optimisticDelta,
          dismissed: ChatQuotaBannerDismissals.shared.dismissed)
        return [
          "is_limit_reached": limiter.isLimitReached ? "true" : "false",
          "remaining_queries": "\(limiter.remainingQueries)",
          "limit_description": limiter.limitDescription,
          "banner_threshold": banner.map { "\($0.threshold)" } ?? "none",
          "rendered_banner_threshold": ChatQuotaBannerPresentation.shared.rendered
            .map { "\($0.threshold)" } ?? "none",
          "rendered_banner_title": ChatQuotaBannerPresentation.shared.rendered?.title ?? "",
          "banner_title": banner?.title ?? "",
          "banner_message": banner?.message ?? "",
        ]
      }
    }

    // CHAT-05: reset the usage-limiter counter so a harness can prove it is
    // dev-resettable (the criterion's second half) without driving real LLM usage.
    register(
      name: "reset_usage_limiter",
      summary: "Reset the free-tier monthly chat usage-limiter counter (dev-resettable proof) — CHAT-05. Non-prod only."
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "reset_usage_limiter is disabled on production bundles"]
      }
      return await MainActor.run {
        let limiter = FloatingBarUsageLimiter.shared
        limiter.reset()
        return [
          "reset": "true",
          "is_limit_reached": limiter.isLimitReached ? "true" : "false",
          "remaining_queries": "\(limiter.remainingQueries)",
        ]
      }
    }
    // Seeds the quota snapshot the chat-quota warnings key off, so a harness can
    // walk 90/100 without spending a month of real questions. Non-prod only.
    register(
      name: "apply_usage_quota",
      summary: "Seed the chat usage-quota snapshot (threshold-warning harness). Non-prod only.",
      params: ["used", "limit", "plan", "unit", "is_overage_plan", "reset_at"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "apply_usage_quota is disabled on production bundles"]
      }
      guard let used = params["used"].flatMap(Double.init) else {
        throw DesktopAutomationActionError.invalidParams("used must be a number")
      }
      var json: [String: Any] = [
        "plan": params["plan"] ?? "Operator",
        "plan_type": "operator",
        "unit": params["unit"] ?? "questions",
        "used": used,
        "percent": 0,
        "allowed": true,
      ]
      if let limit = params["limit"].flatMap(Double.init) {
        json["limit"] = limit
        json["allowed"] = used < limit
      }
      if let resetAt = params["reset_at"].flatMap(Int.init) { json["reset_at"] = resetAt }
      if let overage = params["is_overage_plan"] { json["is_overage_plan"] = overage == "true" }
      let data = try JSONSerialization.data(withJSONObject: json)
      let quota = try JSONDecoder().decode(APIClient.ChatUsageQuota.self, from: data)
      return await MainActor.run {
        let limiter = FloatingBarUsageLimiter.shared
        limiter.applyQuota(quota)
        // Seeding a cycle must produce the banner it asks for; a dismissal left
        // over from an earlier run would silently suppress it.
        ChatQuotaBannerDismissals.shared.reset()
        return [
          "applied": "true",
          "used": "\(quota.used)",
          "limit": "\(quota.limit ?? -1)",
          "is_limit_reached": limiter.isLimitReached ? "true" : "false",
        ]
      }
    }
    register(
      name: "task_capture_fixture",
      summary: "Evaluate canonical screen-capture policy facts without screenshot bytes",
      params: ["facts_json"]
    ) { params in
      guard let json = params["facts_json"], let data = json.data(using: .utf8) else {
        throw DesktopAutomationActionError.invalidParams("facts_json must be canonical capture facts JSON")
      }
      guard let payload = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
        throw DesktopAutomationActionError.invalidParams("facts_json must be a JSON object")
      }
      func value<T>(_ camel: String, _ snake: String, default fallback: T) -> T {
        payload[camel] as? T ?? payload[snake] as? T ?? fallback
      }
      let facts = ScreenCaptureFacts(
        explicitCommand: value("explicitCommand", "explicit_command", default: false),
        clearCommitment: value("clearCommitment", "clear_commitment", default: false),
        concreteDeliverable: value("concreteDeliverable", "concrete_deliverable", default: false),
        directRequest: value("directRequest", "direct_request", default: false),
        inferredNextStep: value("inferredNextStep", "inferred_next_step", default: false),
        owner: value("owner", "owner", default: "unknown"),
        publicBroadcast: value("publicBroadcast", "public_broadcast", default: false),
        directMention: value("directMention", "direct_mention", default: false),
        alreadyDone: value("alreadyDone", "already_done", default: false),
        duplicateOf: payload["duplicateOf"] as? String ?? payload["duplicate_of"] as? String,
        refinesTask: payload["refinesTask"] as? String ?? payload["refines_task"] as? String,
        captureConfidence: value("captureConfidence", "capture_confidence", default: 0.5),
        ownershipConfidence: value("ownershipConfidence", "ownership_confidence", default: 0.5)
      )
      return ["outcome": ScreenCapturePolicy.evaluate(facts).rawValue]
    }

    register(
      name: "configure_contextual_task_interruptions",
      summary: "Configure the non-production contextual task interruption gate",
      params: [
        "enabled", "shipped_cohorts_enabled", "daily_limit", "minimum_spacing_seconds",
        "notifications_enabled", "frequency", "task_notifications_enabled",
      ]
    ) { params in
      var configuration = ProactiveTaskInterruptionSettings.load()
      configuration.userOptedIn = boolParam(params["enabled"], default: false)
      configuration.shippedCohortsEnabled = boolParam(
        params["shipped_cohorts_enabled"], default: false)
      configuration.dailyLimit = max(0, intParam(params["daily_limit"], default: configuration.dailyLimit))
      configuration.minimumSpacing = TimeInterval(
        max(
          0, intParam(params["minimum_spacing_seconds"], default: Int(configuration.minimumSpacing))))
      ProactiveTaskInterruptionSettings.save(configuration)
      if params["notifications_enabled"] != nil {
        UserDefaults.standard.set(
          boolParam(params["notifications_enabled"], default: false),
          forKey: NotificationService.masterEnabledDefaultsKey
        )
      }
      if params["frequency"] != nil {
        UserDefaults.standard.set(
          max(0, min(5, intParam(params["frequency"], default: 0))),
          forKey: NotificationService.frequencyDefaultsKey
        )
      }
      if params["task_notifications_enabled"] != nil {
        TaskAssistantSettings.shared.notificationsEnabled = boolParam(
          params["task_notifications_enabled"], default: false)
      }
      return [
        "enabled": configuration.userOptedIn ? "true" : "false",
        "shipped_cohorts_enabled": configuration.shippedCohortsEnabled ? "true" : "false",
        "cohort": ProactiveTaskCohort.current.rawValue,
      ]
    }

    register(
      name: "probe_contextual_task_interruption",
      summary: "Evaluate a synthetic bounded recommendation through the real interruption gate",
      params: ["can_wait", "expires_in_seconds"]
    ) { params in
      guard let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else {
        return ["error": "runtime_owner_unavailable"]
      }
      let nonce = UUID().uuidString.lowercased()
      let trace = NotificationService.shared.sendContextualTaskInterruption(
        TaskInterruptionCandidate(
          recommendationID: "automation:\(nonce)",
          interventionID: "automation-intervention:\(nonce)",
          dedupeKey: "automation-dedupe:\(nonce)",
          headline: "Review a relevant update",
          whyNow: "The linked context changed materially.",
          recommendedAction: "Review update",
          expiresAt: Date().addingTimeInterval(
            TimeInterval(
              intParam(params["expires_in_seconds"], default: 300))),
          canWait: boolParam(params["can_wait"], default: false)
        ),
        authorizationSnapshot: authorizationSnapshot
      )
      return [
        "reason": trace.reason.rawValue,
        "cohort": trace.cohort.rawValue,
        "dedupe_hash": trace.dedupeHash,
        "intervention_id": trace.interventionID,
      ]
    }

    register(
      name: "probe_suggestion_nudge",
      summary: "Run the real suggestion grounding/evaluation/delivery path on the latest frame",
      params: ["app", "window_title"],
      safety: "network_or_model",
      sideEffects: [
        "may call model/backend services",
        "may deliver a user-visible suggestion when notification controls allow",
      ]
    ) { params in
      let app = params["app"].flatMap { $0.isEmpty ? nil : $0 }
      let title = params["window_title"].flatMap { $0.isEmpty ? nil : $0 }
      return await ProactiveAssistantsPlugin.shared.probeSuggestionNudge(
        appOverride: app,
        windowTitleOverride: title
      )
    }

    registerContextBucketDirectorProbe()
    register(
      name: "set_contextual_task_focus",
      summary: "Set deterministic focus suppression for contextual task interruptions",
      params: ["suppressed"]
    ) { params in
      let suppressed = boolParam(params["suppressed"], default: true)
      UserDefaults.standard.set(
        suppressed, forKey: ProactiveTaskInterruptionSettings.focusSuppressedKey)
      return ["suppressed": suppressed ? "true" : "false"]
    }

    register(
      name: "observe_task_context",
      summary: "Submit a normalized task-context event and optionally flush re-evaluation",
      params: [
        "kind", "reference", "subject_kind", "subject_id", "workstream_id", "urgency", "flush",
      ]
    ) { params in
      guard let kind = TaskContextEventKind(rawValue: params["kind"] ?? "app_window") else {
        throw DesktopAutomationActionError.invalidParams("kind is invalid")
      }
      guard let reference = params["reference"], !reference.isEmpty else {
        throw DesktopAutomationActionError.invalidParams("reference is required")
      }
      let subject: TaskContextSubject?
      if let subjectID = params["subject_id"], !subjectID.isEmpty,
        let kind = OmiAPI.RecommendationSubjectKind(rawValue: params["subject_kind"] ?? "task")
      {
        subject = TaskContextSubject(
          kind: kind,
          id: subjectID,
          workstreamID: params["workstream_id"]?.isEmpty == false ? params["workstream_id"] : nil
        )
      } else {
        subject = nil
      }
      guard
        let event = TaskLocalContextEvent.normalized(
          kind: kind,
          rawReference: reference,
          subject: subject,
          urgency: TaskContextUrgency(rawValue: params["urgency"] ?? "can_wait") ?? .canWait
        )
      else {
        throw DesktopAutomationActionError.invalidParams("context event could not be normalized")
      }
      let matched = await ContextSubjectBindingService.shared.resolve(event)
      let referenceHash = matched.referenceHash
      await TaskContextualResurfacingService.shared.observe(matched)
      let shouldFlush = boolParam(params["flush"], default: true)
      if shouldFlush { await TaskContextualResurfacingService.shared.flush() }
      return [
        "reference_hash": referenceHash,
        "pending_workstreams": "\(await TaskContextualResurfacingService.shared.pendingWorkstreamCount())",
        "flushed": shouldFlush ? "true" : "false",
      ]
    }

    register(
      name: "prepare_task_artifact_fixture",
      summary: "Persist an allowlisted prepared artifact through the workstream kernel",
      params: ["workstream_id", "logical_key", "kind", "content", "execution_ready", "grant_id"]
    ) { params in
      guard let workstreamID = params["workstream_id"], !workstreamID.isEmpty,
        let logicalKey = params["logical_key"], !logicalKey.isEmpty,
        let kind = params["kind"], !kind.isEmpty,
        let content = params["content"], !content.isEmpty
      else {
        throw DesktopAutomationActionError.invalidParams(
          "workstream_id, logical_key, kind, and content are required")
      }
      var configuration = ProactiveTaskInterruptionSettings.load()
      configuration.allowedPreparationKinds.insert(kind)
      ProactiveTaskInterruptionSettings.save(configuration)
      let referenceDigest = SHA256.hash(data: Data("automation-preparation:\(logicalKey)".utf8))
        .map { String(format: "%02x", $0) }.joined()
      let evidence = OmiAPI.EvidenceRef(
        deviceId: ClientDeviceService.shared.clientDeviceId,
        excerptHash: "sha256:\(referenceDigest)",
        id: "sha256:\(referenceDigest)",
        kind: .local_screen,
        scope: .device_local,
        version: "automation-preparation.v1"
      )
      let grantID: String
      if let supplied = params["grant_id"], !supplied.isEmpty {
        grantID = supplied
      } else {
        func object(_ raw: String) throws -> [String: Any] {
          guard let data = raw.data(using: .utf8),
            let value = try JSONSerialization.jsonObject(with: data) as? [String: Any]
          else { throw DesktopAutomationActionError.invalidParams("kernel returned invalid JSON") }
          return value
        }
        let prepared = try object(
          try await TaskChatRuntime.controlTool(
            name: "prepare_workstream_continuity",
            input: ["workstreamId": workstreamID, "taskIds": []]
          ))
        guard let session = prepared["session"] as? [String: Any],
          let sessionID = session["agentSessionId"] as? String
        else { throw DesktopAutomationActionError.invalidParams("kernel session unavailable") }
        let capability = "desktop.workstream.artifact.prepare"
        let operation = "prepare_artifact"
        let resource = "workstream:\(workstreamID)"
        let expiry = Int(Date().addingTimeInterval(5 * 60).timeIntervalSince1970 * 1_000)
        let dispatch = try object(
          try await TaskChatRuntime.controlTool(
            name: "create_desktop_dispatch",
            input: [
              "kind": "approval",
              "priority": 1,
              "title": "Automation prepared artifact fixture",
              "decisionPrompt": "Authorize this non-production artifact fixture?",
              "sourceSessionId": sessionID,
              "capability": capability,
              "operation": operation,
              "resourceRef": resource,
              "payload": ["automation_fixture": true],
              "expiresAtMs": expiry,
            ]
          ))
        guard let dispatchObject = dispatch["dispatch"] as? [String: Any],
          let dispatchID = dispatchObject["dispatchId"] as? String
        else { throw DesktopAutomationActionError.invalidParams("kernel dispatch unavailable") }
        let resolved = try object(
          try await TaskChatRuntime.controlTool(
            name: "resolve_desktop_dispatch",
            input: [
              "dispatchId": dispatchID,
              "status": "resolved",
              "resolvedBy": "desktop_automation",
              "resolution": ["decision": "allow"],
              "grant": [
                "sessionId": sessionID,
                "capability": capability,
                "operation": operation,
                "resourcePattern": resource,
                "effect": "allow",
                "source": "user",
                "expiresAtMs": expiry,
              ],
            ]
          ))
        guard let grant = resolved["grant"] as? [String: Any],
          let createdGrantID = grant["grantId"] as? String
        else { throw DesktopAutomationActionError.invalidParams("kernel grant unavailable") }
        grantID = createdGrantID
      }
      let artifact = try await KernelPreparedArtifactBridge().prepare(
        ProactiveTaskArtifactProposal(
          workstreamID: workstreamID,
          logicalKey: logicalKey,
          kind: kind,
          content: Data(content.utf8),
          evidenceRefs: [evidence],
          executionReady: boolParam(params["execution_ready"], default: true),
          coordinatorGrantID: grantID
        ),
        configuration: configuration
      )
      return [
        "prepared": artifact == nil ? "false" : "true",
        "version": artifact.map { "\($0.version)" } ?? "",
        "content_hash": artifact?.contentHash ?? "",
        "file": artifact?.fileURL.path ?? "",
        "supersedes_artifact_id": artifact?.supersedesArtifactID ?? "",
        "delivery_count": artifact.map { "\($0.deliveryIDs.count)" } ?? "0",
      ]
    }

    // Runs the exact service + outcome mapping the ChatGPT/Claude import
    // sheets use, so harnesses can assert outcome copy without driving the
    // TextEditor. Writes real memories on success, like the sheet would.
    register(
      name: "memory_log_import_probe",
      summary:
        "Import a ChatGPT/Claude memory-log text through the real connector pipeline and return the outcome message",
      params: ["source", "text", "fixture"]
    ) { params in
      guard let raw = params["source"], let source = OnboardingMemoryLogSource(rawValue: raw) else {
        throw DesktopAutomationActionError.invalidParams("source must be chatgpt or claude")
      }
      guard let text = params["text"], !text.isEmpty else {
        throw DesktopAutomationActionError.invalidParams("text must be non-empty")
      }
      let outcome: ConnectorImportOperations.Outcome
      if params["fixture"] == "structured" {
        guard AppBuild.isNonProduction else {
          return ["error": "structured memory-log fixture is disabled on production bundles"]
        }
        // Offline providers intentionally return a marker echo rather than JSON.
        // Inject only the extracted provider result; the real connector operation
        // still owns validation, durable save, and user-facing outcome mapping.
        outcome = await ConnectorImportOperations.importMemoryLog(
          text: text,
          source: source,
          extractedFixture: OnboardingMemoryLogImportService.ExtractedMemoryLog(
            memories: [text],
            profileSummary: "desktop qualification fixture"
          )
        )
      } else {
        outcome = await ConnectorImportOperations.importMemoryLog(text: text, source: source)
      }
      switch outcome {
      case .success(let result, let message):
        return [
          "outcome": "success",
          "message": message,
          "memories": "\(result.memoryCount ?? 0)",
        ]
      case .failure(let message, failureClass: _):
        return ["outcome": "failure", "message": message]
      }
    }

    register(
      name: "toggle_transcription",
      summary: "Enable or disable live transcription (mirrors the menu-bar toggle)",
      params: ["enabled"]
    ) { params in
      let enabled = boolParam(params["enabled"], default: true)
      AssistantSettings.shared.audioRecordingMode = enabled ? .onlyMeetings : .off
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
      case "meeting_start", "meeting_end":
        return ["conversation_role": appState.automationObserveMeetingBoundary(active: phase == "meeting_start")]
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
        return ["error": "phase must be start, inject, inject_multi, meeting_start, meeting_end, stop, or lifecycle"]
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

      await requestAutomationConversationOpen(conversationId: detail.id, showTranscript: true)

      return [
        "list_loaded": appState.conversations.isEmpty ? "false" : "true",
        "cached_projection_seen": cachedProjectionId == seed.id ? "true" : "false",
        "detail_id_matches": detail.id == seed.id ? "true" : "false",
        "detail_has_revision": detail.updatedAt == nil ? "false" : "true",
        "detail_transcript_included": detail.transcriptSegmentsIncluded ? "true" : "false",
        "cache_id_matches": persisted?.id == detail.id ? "true" : "false",
        "cache_revision_matches": DesktopAutomationRevisionComparator.matchesAtMillisecondPrecision(
          persisted?.updatedAt, detail.updatedAt)
          ? "true" : "false",
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
      name: "ptt_quick_tap",
      summary: "Mirror one quick tap of a modifier-only PTT key; two inside the double-tap window lock"
    ) { _ in
      PushToTalkManager.shared.quickTapPushToTalkForAutomation()
    }
    register(
      name: "ptt_stop",
      summary: "Finalize the in-progress push-to-talk capture (mirrors a long-hold release)"
    ) { _ in
      PushToTalkManager.shared.endPushToTalkForAutomation()
    }

    // Manager-level PTT harness: this crosses the real shortcut lifecycle,
    // routing decision, realtime admission, warm buffering, and replay seam.
    // Unlike `ptt_test_turn`, it does not bypass PushToTalkManager; unlike a
    // physical test, it needs neither microphone permission nor a device.
    // `pace_ms` spaces the 100 ms chunks in wall time (pass 100 for a real-time
    // hold), which is what lets the wake-word probes and the hub's warm
    // deadline run on the timeline a physical hold has. `settle_ms` waits after
    // release for the closing transcription, polish, and paste to land.
    register(
      name: "ptt_manager_turn",
      summary:
        "Inject a PCM16/16k mono hold through PushToTalkManager and realtime admission; returns lifecycle diagnostics",
      params: ["pcm", "pace_ms", "settle_ms", "chunk_bytes"]
    ) { params in
      guard let path = params["pcm"],
        let pcm16k = try? Data(contentsOf: URL(fileURLWithPath: path)),
        !pcm16k.isEmpty
      else { return ["error": "missing or unreadable 'pcm' file (expected raw s16le 16k mono)"] }
      // Bounded so the nanosecond conversion below cannot trap on a typo.
      let maxWaitMs: UInt64 = 10 * 60 * 1_000
      let paceMs = min(UInt64(params["pace_ms"] ?? "") ?? 0, maxWaitMs)
      let settleMs = min(UInt64(params["settle_ms"] ?? "") ?? 0, maxWaitMs)
      // Default 100 ms. Pass 342 to mimic what the CoreAudio IOProc hands a
      // 48 kHz device's capture after resampling — chunk size has already
      // hidden one bug that only a real microphone showed. Always a whole
      // number of 16-bit samples, so an odd size cannot shear the PCM framing.
      let requestedChunk = Int(params["chunk_bytes"] ?? "") ?? 3_200
      let chunkSize = max(2, requestedChunk - requestedChunk % 2)

      var result = PushToTalkManager.shared.beginRealtimePushToTalkForAutomation()
      guard result["listening"] == "true" else { return result }
      var offset = 0
      var injected = 0
      while offset < pcm16k.count {
        let end = min(offset + chunkSize, pcm16k.count)
        if PushToTalkManager.shared.injectRealtimePTTAutomationAudio(pcm16k.subdata(in: offset..<end)) {
          injected += end - offset
        }
        offset = end
        if paceMs > 0 { try? await Task.sleep(nanoseconds: paceMs * 1_000_000) }
      }
      let stopped = PushToTalkManager.shared.endPushToTalkForAutomation()
      if settleMs > 0 { try? await Task.sleep(nanoseconds: settleMs * 1_000_000) }
      result["injected_bytes"] = "\(injected)"
      result["finalized"] = stopped["finalized"] ?? "false"
      for (key, value) in RealtimeHubController.shared.automationPTTDiagnostics() {
        result[key] = value
      }
      for (key, value) in PushToTalkManager.shared.voiceTypingAutomationDiagnostics() {
        result[key] = value
      }
      return result
    }

    // The dictation pipeline without a voice turn: transcribe a recording the
    // way a key-up does (backend, then on-device; on-device only with
    // network=false), clean it up, and paste it into the frontmost app. Lets a
    // harness verify the paste and the fallback order with no microphone and,
    // with network=false, no sign-in.
    register(
      name: "voice_typing_dictate",
      summary: "Run a PCM16/16k recording through the dictation pipeline and paste the result into the frontmost app",
      params: ["pcm", "network"]
    ) { params in
      guard let path = params["pcm"],
        let pcm16k = try? Data(contentsOf: URL(fileURLWithPath: path)),
        !pcm16k.isEmpty
      else { return ["error": "missing or unreadable 'pcm' file (expected raw s16le 16k mono)"] }
      let allowNetwork = (params["network"] ?? "true").lowercased() != "false"
      return await PushToTalkManager.shared.dictateForAutomation(pcm16k: pcm16k, allowNetwork: allowNetwork)
    }

    register(
      name: "ptt_turn_snapshot",
      summary: "Return typed PTT lifecycle state, pending-tool fences, and safe screen-evidence diagnostics"
    ) { _ in
      RealtimeHubController.shared.automationPTTDiagnostics()
    }

    // Fake-voice end-to-end test: inject a raw PCM16/16kHz-mono file through the
    // real realtime omni STT path and return the transcript. No mic, no human.
    register(
      name: "omni_test_turn",
      summary: "Inject a raw PCM16/16kHz mono file through the omni STT path; returns the transcript",
      params: ["pcm", "timeout", "provider"]
    ) { params in
      guard let path = params["pcm"],
        let data = try? Data(contentsOf: URL(fileURLWithPath: path)), !data.isEmpty
      else {
        return ["error": "missing or unreadable 'pcm' file (expected raw s16le 16k mono)"]
      }
      let provider =
        params["provider"].flatMap(RealtimeOmniProvider.init(rawValue:))
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
      summary: "Sign out via AuthService (local Auth emulator harness only)",
      params: ["accepted_account_deletion"]
    ) { params in
      guard DesktopLocalProfile.isEnabled else {
        return ["error": "sign_out is only available with OMI_DESKTOP_LOCAL_PROFILE=1 (local Auth emulator)"]
      }
      let acceptedAccountDeletion = boolParam(params["accepted_account_deletion"], default: false)
      guard AuthState.shared.isSignedIn else {
        return ["signed_out": "true", "was_signed_in": "false"]
      }
      try await AuthService.shared.signOut(acceptedAccountDeletion: acceptedAccountDeletion)
      return [
        "accepted_account_deletion": acceptedAccountDeletion ? "true" : "false",
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

    register(
      name: "ask",
      summary: "Send a query to the floating-bar AI (typed path); exercises the full chat pipeline",
      params: ["query"]
    ) { params in
      let query = (params["query"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      guard !query.isEmpty else { return ["error": "missing 'query'"] }
      let baselineSnapshot = FloatingControlBarManager.shared.automationFloatingBarChatSnapshot(limit: 1)
      guard baselineSnapshot["error"] == nil,
        let baselineRaw = baselineSnapshot["message_count"],
        let baseline = Int(baselineRaw)
      else {
        return ["error": baselineSnapshot["error"] ?? "floating chat timeline unavailable"]
      }
      self.floatingBarSubmissionGeneration += 1
      let generation = self.floatingBarSubmissionGeneration
      self.pendingFloatingBarSubmission = (generation: generation, baselineMessageCount: baseline)
      if !FloatingControlBarManager.shared.isVisible {
        FloatingControlBarManager.shared.show()
      }
      FloatingControlBarManager.shared.openAIInputWithQuery(query, fromVoice: false)
      return ["sent": query, "submission_generation": "\(generation)"]
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
      guard let debugState = VoiceTurnDebugPresentationState(rawValue: s) else {
        return ["error": "state must be idle, listening, thinking, or answering"]
      }
      let mgr = FloatingControlBarManager.shared
      guard let bar = mgr.barState else { return ["error": "no bar state"] }
      if s != "idle", !mgr.isVisible { mgr.show() }
      guard VoiceTurnCoordinator.shared.applyDebugPresentationState(debugState) else {
        return ["error": "a non-debug voice turn is active"]
      }
      return ["state": s, "usesNotchIsland": bar.usesNotchIsland ? "true" : "false"]
    }

    register(
      name: "debug_reach_error",
      summary: "Show the actionable 'Couldn't reach Omi' card on the bar (Retry/Skip) for visual verification",
      params: []
    ) { _ in
      let mgr = FloatingControlBarManager.shared
      guard mgr.barState != nil else { return ["error": "no bar state"] }
      if !mgr.isVisible { mgr.show() }
      mgr.showReachError(message: "Error 502") {
        log("debug_reach_error: Retry tapped")
      }
      return ["shown": "true"]
    }

    // Drives the real post-meeting completion signal so the entire production
    // chain runs (banner service → conversation + recipients fetch → persistent
    // share card). Same NotificationCenter signal the finalization service posts.
    register(
      name: "trigger_meeting_completion",
      summary:
        "Post the real meeting-completion signal for a conversation id (presents the meeting summary share card). Non-prod only.",
      params: ["conversation_id"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "trigger_meeting_completion is disabled on production bundles"]
      }
      guard let conversationID = params["conversation_id"], !conversationID.isEmpty else {
        throw DesktopAutomationActionError.invalidParams("conversation_id is required")
      }
      NotificationCenter.default.post(
        name: .desktopMeetingConversationDidComplete,
        object: MeetingCompletionNotification(conversationIDs: [conversationID]))
      return ["posted": conversationID]
    }

    // Reads whatever notch card is on screen, so a flow can assert the card a
    // person actually sees rather than trusting that a trigger fired.
    register(
      name: "notification_state",
      summary: "Read the notch notification currently on screen (title, message, persistence).",
      params: []
    ) { _ in
      guard let bar = FloatingControlBarManager.shared.barState,
        let notification = bar.currentNotification
      else {
        return ["present": "false"]
      }
      return [
        "present": "true",
        "title": notification.title,
        "message": notification.message,
        "persistent": notification.isPersistent ? "true" : "false",
      ]
    }

    // Presents the same "Omi is taking notes" notice the meeting boundary
    // posts once a detected meeting has rotated into its recording session.
    register(
      name: "trigger_meeting_started_notice",
      summary:
        "Present the meeting-started note-taking notice (the card shown when a meeting is detected). Non-prod only.",
      params: []
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "trigger_meeting_started_notice is disabled on production bundles"]
      }
      MeetingNoteTakingNotice.present()
      return ["presented": "true"]
    }

    // Cursor-free driver for the meeting summary share card: `state` reads the
    // presented card, `copy`/`send` run the same MeetingSummaryShareActions the
    // card's buttons call, `close` is the user dismissal path.
    register(
      name: "meeting_summary_share",
      summary:
        "Inspect or drive the presented meeting summary share card (action=state|copy|send|close). Non-prod only.",
      params: ["action"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "meeting_summary_share is disabled on production bundles"]
      }
      let mgr = FloatingControlBarManager.shared
      guard let bar = mgr.barState else { return ["error": "no bar state"] }
      guard let notification = bar.currentNotification,
        case .meetingSummaryShare(let conversationID, let recipients)? = notification.action
      else {
        return ["present": "false"]
      }
      switch (params["action"] ?? "state").lowercased() {
      case "state":
        return [
          "present": "true",
          "assistant_id": notification.assistantId,
          "title": notification.title,
          "message": notification.message,
          "persistent": notification.isPersistent ? "true" : "false",
          "conversation_id": conversationID,
          "recipients": recipients.map(\.email).joined(separator: ","),
        ]
      case "copy":
        let feedback = await MeetingSummaryShareActions.copyLink(conversationID: conversationID)
        return ["copied": feedback == .copied ? "true" : "false"]
      case "send":
        // `email` mirrors what the owner types into the Share field; with no
        // address supplied the detected suggestion is used, which is exactly
        // what the field prefills with.
        // Drive the card's own Send handler so its phase (sending → sent /
        // failed) is exercised, not just the network call underneath it.
        let typed = params["email"]?.trimmingCharacters(in: .whitespaces) ?? ""
        let address = typed.isEmpty ? (recipients.first?.email ?? "") : typed
        guard !address.isEmpty else {
          return ["error": "no recipient: pass email=<address>"]
        }
        NotificationCenter.default.post(
          name: .meetingSummaryShareSubmit, object: address)
        return ["submitted": address]
      case "share":
        NotificationCenter.default.post(name: .meetingSummaryShareBeginAddressing, object: nil)
        return ["addressing": "true"]
      case "close":
        mgr.dismissCurrentNotification()
        return ["closed": "true"]
      default:
        throw DesktopAutomationActionError.invalidParams(
          "action must be state, share, copy, send, or close")
      }
    }

    // Cursor-free click diagnosis: report which window (any app's) is topmost at a screen point,
    // and — when it is one of ours — the exact view AppKit hit-tests there. Exists because "I
    // click X and nothing happens" is otherwise undiagnosable without synthesizing real clicks.
    register(
      name: "debug_hit_probe",
      summary: "Report topmost window + hit-tested view at screen point (top-left coords)",
      params: ["x", "y"]
    ) { params in
      guard let x = Double(params["x"] ?? ""), let y = Double(params["y"] ?? "") else {
        return ["error": "need x and y (screen top-left coords)"]
      }
      guard let primary = NSScreen.screens.first else { return ["error": "no screens"] }
      let cocoaPoint = NSPoint(x: x, y: primary.frame.maxY - y)
      var result: [String: String] = [
        "screen_point_cg": "(\(Int(x)), \(Int(y)))",
        "screen_point_cocoa": NSStringFromPoint(cocoaPoint),
        "screens": NSScreen.screens.map { NSStringFromRect($0.frame) }.joined(separator: " | "),
      ]
      // Our own windows containing the point, front-to-back. Reliable where the window-server
      // query is not; foreign overlap is diagnosed from outside via CGWindowList.
      let containing = NSApp.windows
        .filter { $0.isVisible && $0.frame.contains(cocoaPoint) }
        .sorted { $0.orderedIndex < $1.orderedIndex }
      result["own_windows_at_point"] =
        containing.isEmpty
        ? "none"
        : containing.map { window in
          var extras = ""
          let local = NSPoint(
            x: cocoaPoint.x - window.frame.minX, y: cocoaPoint.y - window.frame.minY)
          if let bar = window as? FloatingControlBarWindow {
            extras =
              " acceptsHit=\(bar.automationAcceptsMouseHit(inContentPoint: local)) ignores=\(window.ignoresMouseEvents)"
          } else {
            // Shell click-through verdict (ShellClickThrough.swift): whether this point owns the
            // pointer, per the same policy the ignoresMouseEvents sync runs.
            let accepts = ShellClickThroughPolicy.acceptsMouseHit(
              localPoint: local,
              windowSize: window.frame.size,
              isResizable: window.styleMask.contains(.resizable),
              contentContains: { InkGlassHitRegions.shared.containsPoint($0, in: window) })
            extras =
              " shellAccepts=\(accepts) glassSurfaces=\(InkGlassHitRegions.shared.surfaceCount(in: window))"
              + " ignores=\(window.ignoresMouseEvents)"
          }
          return
            "\(String(describing: type(of: window)))(\"\(window.title)\" level=\(window.level.rawValue) key=\(window.isKeyWindow) idx=\(window.orderedIndex)\(extras))"
        }.joined(separator: " ; ")
      if let window = containing.first {
        let inWindow = window.convertPoint(fromScreen: cocoaPoint)
        result["point_in_window"] = NSStringFromPoint(inWindow)
        if let root = window.contentView?.superview ?? window.contentView {
          let inRoot = root.convert(inWindow, from: nil)
          let hit = root.hitTest(inRoot)
          var chain: [String] = []
          var view = hit
          while let v = view, chain.count < 8 {
            chain.append(String(describing: type(of: v)))
            view = v.superview
          }
          result["hit_view_chain"] = chain.isEmpty ? "nil (click falls through)" : chain.joined(separator: " < ")
        }
      }
      return result
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
      if let error = await provider.automationResetMainChatForHarness() {
        return ["error": error]
      }
      return ["reset": "true"]
    }

    register(
      name: "present_onboarding_opener",
      summary: "Compose and show the post-onboarding opener in the empty-chat slot (QA rendering seam)",
      params: []
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "present_onboarding_opener is disabled on production bundles"]
      }
      guard let provider = ChatProvider.mainInstance else {
        return ["error": "main ChatProvider not yet initialized"]
      }
      provider.presentOnboardingOpener()
      return [
        "presented": "true",
        "starter_count": "\(provider.onboardingOpener?.starters.count ?? 0)",
      ]
    }

    // Send a message through the real main-window chat pipeline (Home),
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
      // Report the provider's own admission decision. This used to answer
      // `sent` unconditionally, so a send the busy guard refused was reported
      // as delivered and the refusal was invisible to every harness.
      guard provider.canAcceptSend else {
        return [
          "accepted": "false",
          "busy": "true",
          "is_sending": provider.isSending ? "true" : "false",
          "is_streaming": provider.messages.contains(where: { $0.isStreaming }) ? "true" : "false",
          "reason": "already_sending",
          "query": query,
        ]
      }
      let tracer = QueryTracer(query: query, inputMode: .text)
      await QueryTracerContext.$current.withValue(tracer) {
        _ = await provider.sendMessage(query)
      }
      return ["accepted": "true", "sent": query]
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
      summary:
        "Freeze the agent stdio stream (SIGSTOP) to induce a chat stall; auto-resumes after durationMs. Non-prod only.",
      params: ["durationMs"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "suspend_agent_stream is disabled on production bundles"]
      }
      // Default just past the 60s send watchdog so CHAT-02 can assert the
      // "Response took too long" error + recoverable retry; capped at 300s.
      let durationMs = intParam(params["durationMs"], default: 70_000)
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
      // debugResumeStream is nonisolated (off-actor SIGCONT) so it returns promptly
      // even when the actor is blocked writing to the frozen process.
      return AgentRuntimeProcess.shared.debugResumeStream()
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
      summary: "Block until the latest submitted floating-bar turn is observed and becomes idle",
      params: ["timeoutMs", "pollMs"]
    ) { params in
      let timeoutMs = max(1_000, intParam(params["timeoutMs"], default: 180_000))
      let pollMs = max(100, intParam(params["pollMs"], default: 500))
      guard let submission = self.pendingFloatingBarSubmission else {
        return ["error": "no pending floating-bar submission to observe"]
      }
      let deadline = Date().addingTimeInterval(Double(timeoutMs) / 1000.0)
      var observedSubmission = false
      while Date() < deadline {
        var detail = FloatingControlBarManager.shared.automationFloatingBarChatSnapshot(limit: 8)
        let messageCount = Int(detail["message_count"] ?? "") ?? 0
        observedSubmission =
          observedSubmission
          || messageCount > submission.baselineMessageCount
          || detail["is_sending"] == "true"
          || detail["is_streaming"] == "true"
        if observedSubmission,
          detail["error"] == nil,
          detail["is_sending"] == "false",
          detail["is_streaming"] == "false"
        {
          detail["idle"] = "true"
          detail["submission_observed"] = "true"
          detail["submission_generation"] = "\(submission.generation)"
          if self.pendingFloatingBarSubmission?.generation == submission.generation {
            self.pendingFloatingBarSubmission = nil
          }
          return detail
        }
        try await Task.sleep(nanoseconds: UInt64(pollMs) * 1_000_000)
      }
      var detail = FloatingControlBarManager.shared.automationFloatingBarChatSnapshot(limit: 8)
      detail["error"] = "timeout"
      detail["timeout_ms"] = "\(timeoutMs)"
      detail["submission_observed"] = observedSubmission ? "true" : "false"
      detail["submission_generation"] = "\(submission.generation)"
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
      let remember = boolParam(params["remember"], default: false)

      do {
        let selectedFolderPath: String?
        if let requestedFolder = try AppleNotesReadProbe.resolveRequestedFolder(path: params["folderPath"]) {
          let resolved = try await AppleNotesReaderService.shared.validateSelectedFolder(
            path: requestedFolder.path,
            remember: remember
          )
          selectedFolderPath = resolved.path
        } else {
          selectedFolderPath = nil
        }

        let status = await AppleNotesReaderService.shared.connectionStatus(
          maxResults: maxResults,
          selectedFolderPath: selectedFolderPath,
          userInitiated: true
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
      params: ["path", "surface"]
    ) { params in
      guard let path = params["path"], !path.isEmpty else {
        return ["error": "missing 'path'"]
      }
      return await MainActor.run { () -> [String: String] in
        guard
          let window = NSApp.windows.first(where: {
            $0.isVisible && $0.title.range(of: "omi", options: .caseInsensitive) != nil
          })
        else {
          return ["error": "no_visible_window"]
        }
        let requestedSheet = params["surface"] == "sheet"
        let captureWindow = requestedSheet ? (window.attachedSheet ?? window) : window
        guard let contentView = captureWindow.contentView else {
          return ["error": "no_content_view"]
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
          var result = [
            "path": path,
            "bytes": "\(data.count)",
            "captured_surface": requestedSheet && window.attachedSheet != nil ? "sheet" : "window",
            "frame_x": "\(Int(window.frame.origin.x.rounded()))",
            "frame_y": "\(Int(window.frame.origin.y.rounded()))",
            "frame_width": "\(Int(window.frame.width.rounded()))",
            "frame_height": "\(Int(window.frame.height.rounded()))",
            "backing_scale": String(format: "%.1f", window.backingScaleFactor),
          ]
          if let sheet = window.attachedSheet {
            result["has_sheet"] = "true"
            result["sheet_frame_x"] = "\(Int(sheet.frame.origin.x.rounded()))"
            result["sheet_frame_y"] = "\(Int(sheet.frame.origin.y.rounded()))"
            result["sheet_frame_width"] = "\(Int(sheet.frame.width.rounded()))"
            result["sheet_frame_height"] = "\(Int(sheet.frame.height.rounded()))"
          } else {
            result["has_sheet"] = "false"
          }
          return result
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

    // Cursor-free notch hover driver: enter/exit run the same pointer update
    // the tracking view calls from mouse events; state reads the island's
    // visibility inputs so a stuck reveal or menu can be caught mechanically.
    register(
      name: "notch_hover",
      summary: "Simulate notch pointer enter/exit or read island state (non-prod). action=enter|exit|state",
      params: ["action"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "notch_hover is disabled on production bundles"]
      }
      guard let bar = FloatingControlBarManager.shared.window else {
        return ["error": "no floating bar window"]
      }
      switch params["action"] ?? "state" {
      case "enter":
        bar.automationSimulateNotchPointer(inside: true)
      case "exit":
        bar.automationSimulateNotchPointer(inside: false)
      case "state":
        break
      default:
        throw DesktopAutomationActionError.invalidParams("action must be enter, exit, or state")
      }
      return bar.automationNotchStateSnapshot
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
      name: "integration_nudge_evaluate",
      summary:
        "Read-only: which integration a given frontmost app/window maps to, and whether a nudge would fire",
      params: ["bundle_id", "window_title"],
      category: "read",
      safety: "read_only"
    ) { params in
      await IntegrationNudgeAutomation.evaluate(
        bundleID: params["bundle_id"],
        windowTitle: params["window_title"]
      )
    }

    register(
      name: "integration_nudge_present",
      summary: "Present the integration-connect card for one catalog entry (QA of the real card path)",
      params: ["telemetry_id"],
      category: "write",
      surfaces: ["floating_bar"],
      safety: "presents_ui"
    ) { params in
      await MainActor.run { IntegrationNudgeAutomation.present(telemetryID: params["telemetry_id"] ?? "") }
    }

    register(
      name: "cloud_connector_guidance_probe",
      summary: "Read-only diagnostic of the live Claude Add detection (no overlay, no clicks)"
    ) { _ in
      await MainActor.run { CloudConnectorFormAutomation.claudeAddGuidanceDiagnostics() }
    }

    register(
      name: "coordinator_awareness_snapshot",
      summary: "Read the Swift coordinator awareness projection for Agents & Attention debugging",
      params: ["limit"]
    ) { params in
      let limit = max(1, min(200, intParam(params["limit"], default: 50)))
      let snapshot = try await DesktopCoordinatorService.shared.awarenessSnapshotJSON(limit: limit)
      return ["snapshot": snapshot]
    }

    register(
      name: "agent_lifecycle_convergence_snapshot",
      summary: "Read canonical child-run status alongside the rendered pill and journal-completion projection",
      params: ["runIds"],
      category: "read",
      surfaces: ["floating_bar", "main_chat", "realtime"],
      safety: "read_only"
    ) { params in
      let runIDs = Set(
        (params["runIds"] ?? "")
          .split(separator: ",")
          .map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
          .filter { !$0.isEmpty }
          .prefix(20)
      )
      return ["snapshot": await AgentPillsManager.shared.lifecycleConvergenceSnapshot(runIDs: runIDs)]
    }

    register(
      name: "coordinator_inspect_run",
      summary: "Inspect one owner-scoped kernel run and its bounded tool-invocation ledger",
      params: ["runId"]
    ) { params in
      guard let runId = params["runId"]?.trimmingCharacters(in: .whitespacesAndNewlines),
        !runId.isEmpty
      else {
        throw DesktopAutomationActionError.invalidParams("missing runId")
      }
      let run = try await DesktopCoordinatorService.shared.inspectRun(runId: runId)
      return ["run": run]
    }

    register(
      name: "coordinator_continue_agent",
      summary: "Continue one owner-scoped canonical agent session and return its new run handles",
      params: ["sessionId", "prompt", "surfaceKind"]
    ) { params in
      guard let sessionId = params["sessionId"]?.trimmingCharacters(in: .whitespacesAndNewlines),
        !sessionId.isEmpty
      else {
        throw DesktopAutomationActionError.invalidParams("missing sessionId")
      }
      guard let prompt = params["prompt"]?.trimmingCharacters(in: .whitespacesAndNewlines),
        !prompt.isEmpty
      else {
        throw DesktopAutomationActionError.invalidParams("missing prompt")
      }
      let inspection = try await DesktopCoordinatorService.shared.continueAgent(
        sessionId: sessionId,
        prompt: prompt,
        originSurface: DesktopCoordinatorOriginSurface(surfaceKind: params["surfaceKind"]),
        model: nil,
        cwd: nil
      )
      return [
        "session_id": inspection.sessionId ?? "",
        "run_id": inspection.runId ?? "",
        "attempt_id": inspection.attemptId ?? "",
        "status": inspection.status,
        "error": inspection.errorMessage ?? "",
      ]
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
      summary: "Route a structured proposal through the canonical agent kernel",
      params: [
        "intent", "surfaceKind", "taskId", "proposal", "snapshotVersion",
        "sessionId", "runId", "parentRunId", "provider", "agentCount",
      ]
    ) { params in
      let proposal: DesktopCoordinatorIntentProposal
      switch params["proposal"] {
      case "spawn_agent": proposal = .spawnAgent
      case "continue_run": proposal = .continueRun
      case "clarify": proposal = .clarify(missing: ["automation_input"])
      default: proposal = .answerInline
      }
      let syntaxFacts = DesktopCoordinatorIntentSyntaxFacts(
        delegationNegated: nil,
        explicitSessionId: params["sessionId"],
        explicitRunId: params["runId"],
        parentRunId: params["parentRunId"],
        explicitProvider: params["provider"],
        requestedAgentCount: params["agentCount"].flatMap(Int.init))
      let decision = try await DesktopCoordinatorService.shared.routeIntentJSON(
        intent: params["intent"] ?? "",
        surfaceKind: params["surfaceKind"],
        taskId: params["taskId"],
        snapshotVersion: params["snapshotVersion"],
        proposal: proposal,
        syntaxFacts: syntaxFacts
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
          maxResults: normalized.maxResults,
          userInitiated: true
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
          query: query,
          userInitiated: true
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
      name: "preview_screen_recording_drag_helper",
      summary: "Open Screen Recording settings and show the drag-to-enable helper"
    ) { _ in
      await MainActor.run { ScreenCaptureService.openScreenRecordingPreferences() }
      return CloudConnectorGuidanceOverlay.shared.automationState()
    }

    register(
      name: "open_conversation",
      summary: "Open a conversation detail view (same path as POST /conversation/open)",
      params: ["conversationId", "showTranscript", "timeoutMs"]
    ) { params in
      guard let conversationId = params["conversationId"]?.trimmingCharacters(in: .whitespacesAndNewlines),
        !conversationId.isEmpty
      else {
        return ["error": "missing conversationId"]
      }
      let showTranscript = boolParam(params["showTranscript"], default: false)
      try await ensureConversationsTabVisibleForAutomation()
      await requestAutomationConversationOpen(conversationId: conversationId, showTranscript: showTranscript)
      let timeoutMs = max(500, intParam(params["timeoutMs"], default: 5_000))
      let deadline = Date().addingTimeInterval(Double(timeoutMs) / 1_000)
      while ConversationDetailAutomationState.shared.openConversationId != conversationId,
        Date() < deadline
      {
        try await Task.sleep(nanoseconds: 50_000_000)
      }
      return [
        "opened": conversationId,
        "show_transcript": showTranscript ? "true" : "false",
        "detail_open": ConversationDetailAutomationState.shared.openConversationId == conversationId ? "true" : "false",
      ]
    }

    register(
      name: "set_conversations_search",
      summary: "Set the Conversations page search query (drives the real debounced search path)",
      params: ["query"]
    ) { params in
      try await ensureConversationsTabVisibleForAutomation()
      NotificationCenter.default.post(
        name: .desktopAutomationSetConversationsSearchRequested,
        object: nil,
        userInfo: ["query": params["query"] ?? ""]
      )
      return ["query": params["query"] ?? ""]
    }

    register(
      name: "open_latest_conversation",
      summary: "Open the most recently loaded conversation detail view",
      params: ["showTranscript", "timeoutMs"]
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
      await requestAutomationConversationOpen(conversationId: conversationId, showTranscript: showTranscript)
      let timeoutMs = max(500, intParam(params["timeoutMs"], default: 5_000))
      let deadline = Date().addingTimeInterval(Double(timeoutMs) / 1_000)
      while ConversationDetailAutomationState.shared.openConversationId != conversationId,
        Date() < deadline
      {
        try await Task.sleep(nanoseconds: 50_000_000)
      }
      return [
        "opened": conversationId,
        "show_transcript": showTranscript ? "true" : "false",
        "detail_open": ConversationDetailAutomationState.shared.openConversationId == conversationId ? "true" : "false",
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
      // Persist remotely first. A Settings-page hydration already in flight may
      // write its response into UserDefaults; the final assignment makes this
      // completed mutation authoritative without relying on a settle delay.
      let saved = try await APIClient.shared.updateTranscriptionPreferences(vocabulary: terms)
      AssistantSettings.shared.transcriptionVocabulary = saved.vocabulary
      return [
        "saved": "true",
        "term_count": "\(saved.vocabulary.count)",
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
        source: "user"
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
      let installed = try await APIClient.shared.searchApps(installedOnly: true, limit: 100)
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

    register(name: "permissions_snapshot", summary: "Every permission row the Permissions page shows") {
      _ in await PermissionsSnapshot.capture()
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
      name: "memory_graph_rebuild",
      summary:
        "Regenerate the server-side knowledge graph from the signed-in account's memories",
      params: []
    ) { _ in
      // Mutating and not undoable: the backend deletes the stored graph before
      // the background rebuild runs, so a caller that loses the race sees an
      // empty graph. Exposed for cursor-free QA of the Brain Map's own rebuild
      // control, which is otherwise only reachable by clicking.
      do {
        let response = try await APIClient.shared.rebuildKnowledgeGraph()
        return [
          "status": response.status,
          "nodes_count": "\(response.nodesCount ?? 0)",
          "edges_count": "\(response.edgesCount ?? 0)",
        ]
      } catch {
        return [
          "has_error": "true",
          "error_message": error.localizedDescription,
        ]
      }
    }

    register(
      name: "memory_graph_snapshot",
      summary: "Return knowledge graph node/edge counts (no SceneKit rendering)",
      params: ["label"]
    ) { params in
      do {
        let graph = try await APIClient.shared.getKnowledgeGraph()
        let atlas = MemoryAtlasProjection(graph: graph.atlasResponse, userName: nil)
        var detail = [
          "node_count": "\(graph.nodes.count)",
          "edge_count": "\(graph.edges.count)",
          "catalog_memory_count": "\(graph.catalogNodes?.count ?? 0)",
          "atlas_mark_count": "\(atlas.snapshot.nodes.count)",
          "is_empty": graph.nodes.isEmpty ? "true" : "false",
        ]
        // A label resolves to the ids and citations the inspector needs.
        if let query = params["label"]?.lowercased(), !query.isEmpty {
          if let match = graph.nodes.first(where: { $0.label.lowercased().contains(query) }) {
            let edges = graph.edges.filter { $0.sourceId == match.id || $0.targetId == match.id }
            detail["match_id"] = match.id
            detail["match_label"] = match.label
            detail["match_edge_count"] = "\(edges.count)"
            detail["match_cited_memory_count"] = "\(Set(edges.flatMap(\.memoryIds)).count)"
            if let first = edges.first {
              detail["match_first_edge_id"] = first.id
              detail["match_first_edge_memory_count"] = "\(first.memoryIds.count)"
            }
          } else {
            detail["match_id"] = ""
          }
        }
        return detail
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
      name: "memory_atlas_select",
      summary: "Select a Brain Map entity or connection so the inspector can be checked cursor-free",
      params: ["target", "node_id", "label", "edge_id", "clear"]
    ) { params in
      let target = params["target"] == "inline" ? "inline" : "page"
      var userInfo: [String: Any] = ["target": target]
      if let nodeID = params["node_id"], !nodeID.isEmpty { userInfo["node_id"] = nodeID }
      if let label = params["label"], !label.isEmpty { userInfo["label"] = label }
      if let edgeID = params["edge_id"], !edgeID.isEmpty { userInfo["edge_id"] = edgeID }
      if params["clear"] == "true" { userInfo["clear"] = true }
      await MainActor.run {
        NotificationCenter.default.post(
          name: .desktopAutomationMemoryAtlasSelectRequested,
          object: nil,
          userInfo: userInfo
        )
      }
      return [
        "posted": "true",
        "target": target,
        "node_id": params["node_id"] ?? "",
        "label": params["label"] ?? "",
        "edge_id": params["edge_id"] ?? "",
        "clear": params["clear"] ?? "false",
      ]
    }

    register(
      name: "memories_open_detail",
      summary: "Open a memory's detail panel by backend id (omit the id to close it)",
      params: ["memory_id"]
    ) { params in
      let memoryId = params["memory_id"] ?? ""
      await MainActor.run {
        NotificationCenter.default.post(
          name: .desktopAutomationMemoryDetailOpenRequested,
          object: nil,
          userInfo: memoryId.isEmpty ? [:] : ["memory_id": memoryId]
        )
      }
      return ["posted": "true", "memory_id": memoryId]
    }

    register(
      name: "open_memory_atlas",
      summary: "Open the canonical memory atlas page for non-production UI and performance harnesses"
    ) { _ in
      await MainActor.run {
        NotificationCenter.default.post(
          name: .desktopAutomationOpenMemoryAtlasRequested,
          object: nil
        )
      }
      return ["opened": "true", "target": "page"]
    }

    register(
      name: "memory_atlas_set_viewport",
      summary: "Set memory atlas zoom and pan for deterministic non-production performance sweeps",
      params: ["target", "zoom", "pan_x", "pan_y", "reset"]
    ) { params in
      let target = params["target"] == "inline" ? "inline" : "page"
      var userInfo: [String: Any] = ["target": target]
      if let zoom = params["zoom"].flatMap(Double.init) { userInfo["zoom"] = zoom }
      if let panX = params["pan_x"].flatMap(Double.init) { userInfo["pan_x"] = panX }
      if let panY = params["pan_y"].flatMap(Double.init) { userInfo["pan_y"] = panY }
      if let reset = params["reset"] { userInfo["reset"] = reset == "true" }
      await MainActor.run {
        NotificationCenter.default.post(
          name: .desktopAutomationMemoryAtlasViewportRequested,
          object: nil,
          userInfo: userInfo
        )
      }
      return [
        "posted": "true",
        "target": target,
        "zoom": params["zoom"] ?? "unchanged",
        "pan_x": params["pan_x"] ?? "unchanged",
        "pan_y": params["pan_y"] ?? "unchanged",
      ]
    }

    register(
      name: "memory_atlas_enter_region",
      summary: "Go into a Brain Map neighbourhood by caption, or leave the one you are in",
      params: ["target", "caption", "leave"]
    ) { params in
      let target = params["target"] == "inline" ? "inline" : "page"
      var userInfo: [String: Any] = ["target": target]
      if let caption = params["caption"] { userInfo["caption"] = caption }
      if let leave = params["leave"] { userInfo["leave"] = leave == "true" }
      await MainActor.run {
        NotificationCenter.default.post(
          name: .desktopAutomationMemoryAtlasRegionRequested,
          object: nil,
          userInfo: userInfo
        )
      }
      return [
        "posted": "true", "target": target,
        "caption": params["caption"] ?? "", "leave": params["leave"] ?? "false",
      ]
    }

    register(
      name: "memory_atlas_set_time",
      summary: "Scrub or play the memory atlas time axis for deterministic non-production checks",
      params: ["target", "fraction", "play", "reset_to_start", "reset"]
    ) { params in
      let target = params["target"] == "inline" ? "inline" : "page"
      var userInfo: [String: Any] = ["target": target]
      if let fraction = params["fraction"].flatMap(Double.init) { userInfo["fraction"] = fraction }
      if let play = params["play"] { userInfo["play"] = play == "true" }
      if let resetToStart = params["reset_to_start"] { userInfo["reset_to_start"] = resetToStart == "true" }
      if let reset = params["reset"] { userInfo["reset"] = reset == "true" }
      await MainActor.run {
        NotificationCenter.default.post(
          name: .desktopAutomationMemoryAtlasTimeRequested,
          object: nil,
          userInfo: userInfo
        )
      }
      return [
        "posted": "true",
        "target": target,
        "fraction": params["fraction"] ?? "unchanged",
        "play": params["play"] ?? "unchanged",
      ]
    }

    register(
      name: "open_quick_note",
      summary: "Open Quick Note via Rewind notes path (same as dashboard Quick Note button)"
    ) { _ in
      NotificationCenter.default.post(name: .navigateToRewindNotes, object: nil)
      return [
        "posted": "navigateToRewindNotes",
        "expected_tab_index": "\(SidebarNavItem.conversations.rawValue)",
        "expected_memory_destination": "\(MemoryHubDestination.rewind.rawValue)",
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

    registerNotificationActions()
    registerRatingPromptActions()
    registerRemotePromptActions()
    registerRealtimeHubActions()
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
    registerRewindArtifactRecoveryGauntlet()
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
      // Settings sub-sections ride the same notifications the app already posts
      // for its own deep-links (the Tasks gear, the floating-bar context menu),
      // so QA can land on a specific pane without any cursor input.
      case "tasksettings", "advancedsettings":
        NotificationCenter.default.post(name: .navigateToTaskSettings, object: nil)
        return ["navigated": "Settings › Advanced"]
      case "floatingbarsettings":
        NotificationCenter.default.post(name: .navigateToFloatingBarSettings, object: nil)
        return ["navigated": "Settings › Floating Bar"]
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
      let task = TaskAssistantSettings.shared
      let insight = InsightAssistantSettings.shared
      let memory = MemoryAssistantSettings.shared
      let assistant = AssistantSettings.shared
      return [
        "task_enabled": task.isEnabled ? "true" : "false",
        "task_chat_agent_enabled": TaskAgentSettings.shared.isChatEnabled ? "true" : "false",
        "insight_enabled": insight.isEnabled ? "true" : "false",
        "memory_enabled": memory.isEnabled ? "true" : "false",
        "screen_analysis_enabled": assistant.screenAnalysisEnabled ? "true" : "false",
        "transcription_enabled": assistant.audioRecordingMode != .off ? "true" : "false",
        "audio_recording_mode": assistant.audioRecordingMode.rawValue,
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
      let personName =
        params["personName"]?.trimmingCharacters(in: .whitespacesAndNewlines)
        ?? "[[MARKER:speaker-naming]] Harness Speaker"
      let segmentIndex = max(0, Int(params["segmentIndex"] ?? "") ?? 0)

      // Raw mode: drive assignSpeakerToSegments with the ids exactly as given,
      // without resolving the conversation first — the seam that exercises the
      // local-first fallback for conversations the backend does not have yet.
      if let rawConversationId = params["rawConversationId"]?.trimmingCharacters(
        in: .whitespacesAndNewlines), !rawConversationId.isEmpty
      {
        let rawSegmentIds = (params["rawSegmentIds"] ?? "").split(separator: ",").map(String.init)
        guard !rawSegmentIds.isEmpty else { return ["error": "rawSegmentIds required in raw mode"] }
        guard let person = await appState.createPerson(name: personName) else {
          return ["error": "failed to create person"]
        }
        let assigned = await appState.assignSpeakerToSegments(
          conversationId: rawConversationId,
          segmentIds: rawSegmentIds,
          personId: person.id,
          isUser: false
        )
        return [
          "raw_mode": "true",
          "assigned": assigned ? "true" : "false",
          "conversation_id": rawConversationId,
          "person_id": person.id,
        ]
      }

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
      name: "screen_frame_quick_look_probe",
      summary: "Open screenshots in Quick Look and read the panel back",
      params: ["conversationId", "source", "dismiss"]
    ) { params in
      // Quick Look's panel is a system window, so no capture path in this app can photograph it —
      // see `ScreenFrameQuickLook.probeState()`. This is how the responder-chain claim, the
      // materialisation of signed URLs into files, and the panel actually opening are verified.
      if params["dismiss"] == "true" {
        await ScreenFrameQuickLook.shared.dismissForProbe()
        return ["dismissed": "true"]
      }
      // Two sources, because they materialise by completely different routes: a meeting frame is a
      // signed URL to download, a Rewind moment is usually a frame inside a video chunk to decode.
      // A probe that only exercised one would leave the other unproven.
      let source = params["source"] ?? "conversation"
      let frames: [QuickLookFrame]
      let subject: String
      if source == "synthetic" {
        // The hermetic case. It needs neither a signed URL nor a Rewind chunk, so it can run on a
        // fresh bundle with no capture history and no backend — which is what makes it usable as
        // an e2e step. `URLSession` serves `file://` for a data task, so this reaches the panel
        // through exactly the same materialise-then-present path a real frame does.
        let seed = FileManager.default.temporaryDirectory
          .appendingPathComponent("omi-quick-look-probe.png")
        guard let png = Data(base64Encoded: Self.onePixelPNGBase64) else {
          return ["error": "probe_seed_undecodable"]
        }
        do {
          try png.write(to: seed, options: .atomic)
        } catch {
          return ["error": "probe_seed_unwritable: \(error.localizedDescription)"]
        }
        frames = [QuickLookFrame(id: "probe", source: .remote(seed), title: "Quick Look probe")]
        subject = "synthetic"
      } else if source == "rewind" {
        let recent = try await RewindDatabase.shared.getRecentScreenshots(limit: 6)
        frames = recent.map { QuickLookFrame(screenshot: $0) }
        subject = "rewind"
      } else {
        let rawConversationId = params["conversationId"]?
          .trimmingCharacters(in: .whitespacesAndNewlines)
        guard let rawConversationId, !rawConversationId.isEmpty else {
          return ["error": "missing conversationId"]
        }
        let set = try await APIClient.shared.getConversationScreenFrames(
          conversationID: rawConversationId)
        let ordered = (set.banner.map { [$0] } ?? []) + set.strip
        frames = ordered.compactMap { QuickLookFrame(frame: $0) }
        subject = rawConversationId
      }
      guard let first = frames.first else {
        return ["error": "no_frames", "conversation_id": subject]
      }
      await MainActor.run {
        ScreenFrameQuickLook.shared.present(frames, startingAt: first.id)
      }
      // `present` fetches the clicked frame before it shows anything, so the panel is not up the
      // instant this returns. Poll rather than sleep a guessed interval.
      // Both conditions, not just visibility: an ordered-out panel can still report itself visible
      // while its data source is gone, so polling on `panel_visible` alone returns the *previous*
      // presentation's window and reads zero ready items off the new one.
      for _ in 0..<40 {
        let state = await MainActor.run { ScreenFrameQuickLook.shared.probeState() }
        if state["panel_visible"] == "true", state["panel_controlled"] == "true",
          state["ready_count"] != "0"
        {
          break
        }
        try? await Task.sleep(nanoseconds: 100_000_000)
      }
      var result = await MainActor.run { ScreenFrameQuickLook.shared.probeState() }
      result["conversation_id"] = subject
      result["source"] = source
      result["requested_count"] = "\(frames.count)"
      return result
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
    // attach — the report title plus a redacted incident diagnostics attachment —
    // WITHOUT calling SentrySDK. The dry-run uses the same builders as the real
    // submit path, so a harness can secret-scan the attachment without a cloud
    // side effect and cannot drift toward a raw-log upload.
    register(
      name: "dump_feedback_payload_dryrun",
      summary:
        "Assemble the feedback report payload (title + redacted desktop_diagnostics.json) without submitting to Sentry; returns the diagnostics JSON for secret-scanning. Non-prod only.",
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

      if let url = DesktopDiagnosticsManager.shared.writeIncidentDiagnosticsAttachment(
        area: "other",
        failureClass: "user_report",
        phase: "other"
      ) {
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

    // AUTH-03: force the stored idToken's expiry into the past through AuthService's own
    // storage abstraction, so a harness can relaunch and prove the app REFRESHES an
    // expired token without signing the user out. The old harness trick
    // (`defaults write <bundle> auth_tokenExpiry -float 1000`) tampers a key the app no
    // longer reads now that tokens are keychain-backed — it measured nothing and reported
    // a false regression. This seam is storage-agnostic and never exposes token material.
    // Non-prod only (double-gated: here and inside AuthService).
    register(
      name: "expire_auth_token",
      summary:
        "Expire the stored idToken via AuthService's real storage path (keychain or UserDefaults) so a relaunch must refresh it without signing out — AUTH-03. Status only, no token material. Non-prod only.",
      params: []
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "expire_auth_token is disabled on production bundles"]
      }
      return await MainActor.run { AuthService.shared.expireStoredTokenForAutomation() }
    }

    // AUTH-03 read-back: which backend actually holds the tokens, and is the stored
    // idToken currently expired? Lets a harness assert "expired -> relaunch -> refreshed,
    // still signed in" against the REAL storage rather than a UserDefaults key the app may
    // no longer use. Presence/expiry booleans only — never token material. Non-prod only.
    register(
      name: "auth_token_status",
      summary:
        "Read-only auth token status (signed_in, storage backend, has_id_token, has_refresh_token, is_token_expired) — AUTH-03. No token material. Non-prod only.",
      params: []
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "auth_token_status is disabled on production bundles"]
      }
      return await MainActor.run { AuthService.shared.tokenStatusForAutomation() }
    }

    // CHAT-07: post `NSWorkspace.didWakeNotification` on the WORKSPACE notification
    // center — the top of the real wake chain. Every production consumer then fires
    // exactly as on a physical wake: RealtimeHubController re-warms/defers its
    // session ("system_wake"), and AppState's observer re-broadcasts the
    // default-center `.systemDidWake` for downstream consumers. (Posting only the
    // default-center `.systemDidWake` would MISS RealtimeHub, which observes the
    // workspace center directly.) Transcription restart stays guarded by
    // wasTranscribingBeforeSleep, so a synthetic wake is a safe no-op there.
    // Read-only with respect to user data; non-prod only.
    register(
      name: "simulate_system_wake",
      summary:
        "Post NSWorkspace.didWakeNotification on the workspace center (the top of the real wake chain: RealtimeHub re-warm + AppState .systemDidWake re-broadcast) so post-wake restart paths run without a real sleep — CHAT-07 harness. Non-prod only.",
      params: []
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "simulate_system_wake is disabled on production bundles"]
      }
      await MainActor.run {
        NSWorkspace.shared.notificationCenter.post(
          name: NSWorkspace.didWakeNotification, object: nil)
      }
      log("DesktopAutomationBridge: simulate_system_wake posted NSWorkspace.didWakeNotification")
      return ["posted": "NSWorkspace.didWakeNotification"]
    }

    // PERM-06: trigger the permission-flow "Quit & Reopen" restart — the exact
    // AppState.restartApp() path used after granting Accessibility / Screen
    // Recording — so a harness can prove the SAME bundle relaunches with the
    // session intact. Distinct from `reset_onboarding`, which mutates onboarding
    // state. The restart is scheduled after a short delay so this action's HTTP
    // response flushes before restartApp() terminates the process. Non-prod only.
    register(
      name: "quit_and_reopen",
      summary:
        "Trigger the permission-flow Quit & Reopen restart (AppState.restartApp) — relaunches the same bundle; auth/onboarding session persists. Non-prod only.",
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
func boolParam(_ raw: String?, default fallback: Bool) -> Bool {
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

final class DesktopAutomationBridge: @unchecked Sendable {
  static let shared = DesktopAutomationBridge()

  private let queue = DispatchQueue(label: "com.omi.desktop.automation-bridge")
  private var listener: NWListener?
  private var bindAttempts = 0
  private let maxBindAttempts = 3

  /// Upper bound on a request body's declared Content-Length. Requests over this
  /// are rejected before the body is sliced (see parseRequest); the automation
  /// bridge only ever receives small JSON action payloads.
  static let maxRequestBodyBytes = 8 * 1024 * 1024

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

  private func parseRequest(from data: Data) -> DesktopAutomationHTTPRequest? {
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
        // Reject negative/absurd lengths before the body-slice range and the
        // `distance + contentLength` addition below (which would trap/overflow).
        // Reachable pre-auth from any local process, so fail closed.
        guard
          let parsed = LoopbackHTTPParsing.parseContentLength(value, maxBytes: Self.maxRequestBodyBytes)
        else {
          return nil
        }
        contentLength = parsed
      }
    }

    let bodyStart = headerRange.upperBound
    let expectedLength = data.distance(from: data.startIndex, to: bodyStart) + contentLength
    guard data.count >= expectedLength else {
      return nil
    }

    let body = Data(data[bodyStart..<data.index(bodyStart, offsetBy: contentLength)])
    return DesktopAutomationHTTPRequest(method: method, path: path, headers: headers, body: body)
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

  private func route(request: DesktopAutomationHTTPRequest) async -> DesktopAutomationHTTPResponse {
    let started = DispatchTime.now().uptimeNanoseconds
    let response = await self.response(for: request)
    let elapsedMs = Double(DispatchTime.now().uptimeNanoseconds - started) / 1_000_000
    await DesktopAutomationTraceStore.shared.record(
      method: request.method,
      path: request.path,
      statusCode: response.statusCode,
      durationMs: (elapsedMs * 100).rounded() / 100
    )
    return response
  }

  /// Internal executable route seam used by both the loopback listener and
  /// behavioral tests. Keeping auth, dispatch, and JSON encoding on this path
  /// prevents tests from validating a parallel fake router.
  func response(for request: DesktopAutomationHTTPRequest) async -> DesktopAutomationHTTPResponse {
    guard acceptsLoopbackHostAndOrigin(request.headers) else {
      return jsonResponse(
        DesktopAutomationResponse<DesktopAutomationSnapshot>(
          ok: false, result: nil, error: "invalid_host_or_origin"),
        statusCode: 403)
    }
    if request.method == "GET", request.path == "/health", request.headers["authorization"] == nil {
      let runtime = await AgentRuntimeProcess.shared.diagnosticsSnapshot()
      return jsonResponse(
        DesktopAutomationHealth(
          ok: true,
          name: "omi-desktop-automation",
          bundleIdentifier: Bundle.main.bundleIdentifier ?? "unknown",
          processID: getpid(),
          logFilePath: omiLogFilePath(),
          logLaunchID: omiLogLaunchID(),
          bridgePort: DesktopAutomationLaunchOptions.port,
          requiresAuth: true,
          backendEnvironment: DesktopBackendEnvironment.shouldUseDevelopmentBackends ? "development" : "production",
          pythonBackendURL: DesktopBackendEnvironment.pythonBaseURL(),
          rustBackendURL: DesktopBackendEnvironment.rustBackendURL(),
          agentRuntimeRunning: runtime.running,
          agentRuntimeExpectedProtocolVersion: AgentRuntimeProcess.expectedProtocolVersion,
          agentRuntimeProtocolVersion: runtime.protocolVersion,
          agentRuntimeVersion: runtime.runtimeVersion
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
        let snapshot = try await navigationSnapshot(for: payload)
        try await sleepForAutomationSettle(payload.settleMs)
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
        ] + DesktopAutomationPresentationRoute.allCases.map(\.capability),
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
            ok: false, result: nil, error: automationActionErrorDescription(error)),
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
    case ("POST", let path) where path == DesktopAutomationPresentationRoute.openExport.rawValue:
      struct OpenResult: Codable {
        let destination: String
        let generation: UInt64
      }
      guard
        let payload = try? JSONDecoder().decode(
          DesktopAutomationExecuteExportRequest.self, from: request.body)
      else {
        return jsonResponse(
          DesktopAutomationResponse<OpenResult>(
            ok: false, result: nil, error: "invalid_request"),
          statusCode: 400)
      }
      let gate = await currentAutomationPresentationGate()
      let outcome = await DesktopAutomationPresentationRequestHandler.shared.openExport(
        identifier: payload.destination,
        knownIdentifiers: Set(MemoryExportDestination.allCases.map(\.rawValue)),
        gate: gate
      )
      guard let command = outcome.command else {
        return jsonResponse(
          DesktopAutomationResponse<OpenResult>(
            ok: false, result: nil, error: outcome.errorCode),
          statusCode: outcome.statusCode)
      }
      return jsonResponse(
        DesktopAutomationResponse(
          ok: true,
          result: OpenResult(
            destination: payload.destination,
            generation: command.generation
          ),
          error: nil
        ))
    case ("POST", let path) where path == DesktopAutomationPresentationRoute.openImport.rawValue:
      struct OpenResult: Codable {
        let connector: String
        let generation: UInt64
      }
      guard
        let payload = try? JSONDecoder().decode(
          DesktopAutomationOpenImportRequest.self, from: request.body)
      else {
        return jsonResponse(
          DesktopAutomationResponse<OpenResult>(
            ok: false, result: nil, error: "invalid_request"),
          statusCode: 400)
      }
      let knownIDs = await MainActor.run { ImportConnector.all.map(\.id) }
      let gate = await currentAutomationPresentationGate()
      let outcome = await DesktopAutomationPresentationRequestHandler.shared.openImport(
        identifier: payload.connector,
        knownIdentifiers: Set(knownIDs),
        gate: gate
      )
      guard let command = outcome.command else {
        return jsonResponse(
          DesktopAutomationResponse<OpenResult>(
            ok: false, result: nil, error: outcome.errorCode),
          statusCode: outcome.statusCode)
      }
      return jsonResponse(
        DesktopAutomationResponse(
          ok: true,
          result: OpenResult(
            connector: payload.connector,
            generation: command.generation
          ),
          error: nil
        ))
    case ("POST", "/gmail-read"):
      struct RemovedRoute: Codable {
        let message: String
        let replacement: String
      }
      return jsonResponse(
        DesktopAutomationResponse(
          ok: false,
          result: RemovedRoute(
            message:
              "The legacy Gmail import route was removed because automation responses must not expose email contents or trigger memory writes.",
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
    let activateApp = DesktopAutomationNavigationDelivery.resolvesActivation(
      explicit: payload.activateApp)
    await activateMainWindowIfNeeded(activateApp)
    await MainActor.run {
      NotificationCenter.default.post(
        name: .desktopAutomationNavigateRequested,
        object: nil,
        userInfo: DesktopAutomationNavigationDelivery.userInfo(
          for: payload,
          activateApp: activateApp)
      )
    }
  }

  @MainActor
  private func currentAutomationPresentationGate() -> DesktopAutomationPresentationGate {
    let authState = AuthState.shared
    if authState.isRestoringAuth {
      return .presentationUnavailable
    }
    guard authState.isSignedIn else {
      return .signedOut
    }
    guard let appState = AppState.current else {
      return .presentationUnavailable
    }
    return appState.hasCompletedOnboarding ? .ready : .onboardingIncomplete
  }

  private func dispatchOpenConversation(_ payload: DesktopAutomationOpenConversationRequest) async throws {
    await activateMainWindowIfNeeded(
      DesktopAutomationNavigationDelivery.resolvesActivation(explicit: payload.activateApp))
    try await ensureConversationsTabVisibleForAutomation()
    await requestAutomationConversationOpen(
      conversationId: payload.conversationId,
      showTranscript: payload.showTranscript ?? false
    )
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
      } else if payload.target == "task_thread" {
        window = NSApp.windows.first(where: { $0.title == "Omi — Task thread scenario" && $0.isVisible })
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
      guard url.scheme == "http" || url.scheme == "https", port == Int(DesktopAutomationLaunchOptions.port) else {
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

  private func jsonResponse<T: Codable>(
    _ payload: T,
    statusCode: Int = 200
  ) -> DesktopAutomationHTTPResponse {
    do {
      let body = try JSONEncoder.pretty.encode(payload)
      return DesktopAutomationHTTPResponse(
        statusCode: statusCode,
        headers: ["Content-Type": "application/json"],
        body: body
      )
    } catch {
      let fallback = Data("{\"ok\":false,\"error\":\"encode_failed\"}".utf8)
      return DesktopAutomationHTTPResponse(
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

  private func send(_ response: DesktopAutomationHTTPResponse, on connection: NWConnection) {
    connection.send(
      content: response.serializedHTTP1Data(),
      completion: .contentProcessed { _ in
        connection.cancel()
      })
  }
}

struct DesktopAutomationHTTPRequest {
  let method: String
  let path: String
  let headers: [String: String]
  let body: Data
}

struct DesktopAutomationHTTPResponse {
  let statusCode: Int
  let headers: [String: String]
  let body: Data

  func serializedHTTP1Data() -> Data {
    var headerLines = [
      "HTTP/1.1 \(statusCode) \(Self.reasonPhrase(for: statusCode))",
      "Content-Length: \(body.count)",
      "Connection: close",
    ]
    for (key, value) in headers {
      headerLines.append("\(key): \(value)")
    }
    headerLines.append("")
    headerLines.append("")

    var data = Data(headerLines.joined(separator: "\r\n").utf8)
    data.append(body)
    return data
  }

  private static func reasonPhrase(for statusCode: Int) -> String {
    switch statusCode {
    case 200: return "OK"
    case 400: return "Bad Request"
    case 401: return "Unauthorized"
    case 403: return "Forbidden"
    case 404: return "Not Found"
    case 409: return "Conflict"
    case 410: return "Gone"
    case 500: return "Internal Server Error"
    case 503: return "Service Unavailable"
    case 504: return "Gateway Timeout"
    default: return "Unknown Status"
    }
  }
}

extension JSONEncoder {
  fileprivate static var pretty: JSONEncoder {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    return encoder
  }
}
