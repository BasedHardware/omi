import Foundation
import OmiSupport

/// Thread-safe, actor-independent holder for the debug suspend/resume (SIGSTOP /
/// SIGCONT) state used by the non-prod stall harness.
///
/// `AgentRuntimeProcess.sendJson()` does a *blocking* stdin write. If the agent is
/// frozen (SIGSTOP) and a query fills the ~64KB pipe buffer, that write blocks the
/// actor — so if the resume (SIGCONT) were also actor-isolated it could never run,
/// deadlocking the agent permanently. Routing the SIGCONT through this lock-guarded
/// holder keeps it off the actor, so resume/auto-resume always fire even while the
/// actor is stuck writing to the frozen process. Generation-guarded so a stale
/// auto-resume can't SIGCONT after an explicit resume or a newer suspend.
final class DebugSuspendControl: @unchecked Sendable {
  private let lock = NSLock()
  private var pid: pid_t?
  private var generation: UInt64 = 0
  /// Sends SIGCONT and reports success. Injectable so the generation-guard logic
  /// is unit-testable without real signals; defaults to `kill(pid, SIGCONT) == 0`.
  private let sendContinue: (pid_t) -> Bool

  init(sendContinue: @escaping (pid_t) -> Bool = { kill($0, SIGCONT) == 0 }) {
    self.sendContinue = sendContinue
  }

  /// Record a SIGSTOP; returns the generation for its safety auto-resume timer.
  func arm(pid: pid_t) -> UInt64 {
    lock.lock()
    defer { lock.unlock() }
    self.pid = pid
    generation &+= 1
    return generation
  }

  /// Explicit resume: SIGCONT the armed pid and, on success, advance the
  /// generation (cancelling the pending auto-resume). Returns the resumed pid, or
  /// nil if nothing was armed or the SIGCONT failed. On failure the state stays
  /// armed so the safety auto-resume can still recover the process. The signal is
  /// sent OUTSIDE the lock — never invoke the injectable closure while holding it.
  func resume() -> pid_t? {
    lock.lock()
    let armed = pid
    lock.unlock()
    guard let armed, sendContinue(armed) else { return nil }
    lock.lock()
    defer { lock.unlock() }
    // A newer suspend/disarm may have moved on; only clear the pid we resumed.
    if pid == armed {
      pid = nil
      generation &+= 1
    }
    return armed
  }

  /// Safety auto-resume: SIGCONT only if this generation is still the armed one.
  /// Signal sent outside the lock; state cleared only on a successful send.
  func autoResume(generation: UInt64) -> pid_t? {
    lock.lock()
    let armed = (generation == self.generation) ? pid : nil
    lock.unlock()
    guard let armed, sendContinue(armed) else { return nil }
    lock.lock()
    defer { lock.unlock() }
    if pid == armed, self.generation == generation {
      pid = nil
    }
    return armed
  }

  /// Clear on process teardown so a later resume can't SIGCONT a reused pid.
  /// `closePipes()` calls this on every teardown/relaunch path; the only residual
  /// window (OS reaping the pid before teardown runs) is benign — SIGCONT to a
  /// process that isn't stopped is a no-op — and the whole flow is non-prod only.
  func disarm() {
    lock.lock()
    defer { lock.unlock() }
    pid = nil
    generation &+= 1
  }
}

actor AgentRuntimeProcess {
  static let shared = AgentRuntimeProcess()

  nonisolated static func shouldEnablePlaywrightExtension(
    useExtension: Bool,
    token: String,
    targetHasExtension: Bool
  ) -> Bool {
    useExtension && !token.isEmpty && targetHasExtension
  }

  nonisolated static func isConfirmedOutOfMemoryDiagnostic(_ text: String) -> Bool {
    let lower = text.lowercased()
    return lower.contains("fatalprocessoutofmemory")
      || lower.contains("javascript heap out of memory")
      || lower.contains("failed to reserve virtual memory")
  }

  struct WarmupSessionConfig {
    let key: String
    let model: String?
    let systemPrompt: String?
  }

  struct RuntimeMessage {
    struct RequestKey: Hashable, Equatable {
      let clientId: String
      let requestId: String
    }

    enum Kind: Equatable {
      case initMessage
      case textDelta
      case thinkingDelta
      case toolUse
      case toolCancel
      case toolActivity
      case toolResultDisplay
      case result
      case error
      case authRequired
      case authSuccess
      case cancelAck
      case controlToolResult
      case turnRecorded
      case voiceSeedContext
      case kernelTurnTail
      case unknown(String)
    }

    let kind: Kind
    let requestId: String?
    let clientId: String?
    let protocolVersion: Int?
    let payload: [String: Any]

    var requestKey: RequestKey? {
      guard let clientId, let requestId else { return nil }
      return RequestKey(clientId: clientId, requestId: requestId)
    }

    static func parse(_ json: String) -> RuntimeMessage? {
      guard let data = json.data(using: .utf8),
        let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
        let type = dict["type"] as? String
      else {
        return nil
      }
      return RuntimeMessage(
        kind: kind(for: type),
        requestId: dict["requestId"] as? String,
        clientId: dict["clientId"] as? String,
        protocolVersion: dict["protocolVersion"] as? Int,
        payload: dict
      )
    }

    private static func kind(for type: String) -> Kind {
      switch type {
      case "init": return .initMessage
      case "text_delta": return .textDelta
      case "thinking_delta": return .thinkingDelta
      case "tool_use": return .toolUse
      case "tool_cancel": return .toolCancel
      case "tool_activity": return .toolActivity
      case "tool_result_display": return .toolResultDisplay
      case "result": return .result
      case "error": return .error
      case "auth_required": return .authRequired
      case "auth_success": return .authSuccess
      case "cancel_ack": return .cancelAck
      case "control_tool_result": return .controlToolResult
      case "turn_recorded": return .turnRecorded
      case "voice_seed_context": return .voiceSeedContext
      case "kernel_turn_tail": return .kernelTurnTail
      default: return .unknown(type)
      }
    }
  }

  private struct ClientRegistration {
    var harnessMode: String
    var onAuthRequired: AgentBridge.AuthRequiredHandler?
    var onAuthSuccess: AgentBridge.AuthSuccessHandler?
  }

  private struct ActiveRequest {
    let clientId: String
    let requestId: String
    let surfaceRef: AgentSurfaceReference?
    let onTextDelta: AgentBridge.TextDeltaHandler
    let onToolCall: AgentBridge.ToolCallHandler
    let onToolActivity: AgentBridge.ToolActivityHandler
    let onThinkingDelta: AgentBridge.ThinkingDeltaHandler
    let onToolResultDisplay: AgentBridge.ToolResultDisplayHandler
    let onAuthRequired: AgentBridge.AuthRequiredHandler
    let onAuthSuccess: AgentBridge.AuthSuccessHandler
    let continuation: CheckedContinuation<AgentBridge.QueryResult, Error>
    var isInterrupted = false
    var cancelAck: RuntimeMessage?
  }

  private struct ActiveControlRequest {
    let clientId: String
    let requestId: String
    let continuation: CheckedContinuation<String, Error>
  }

  private struct ActiveVoiceSeedRequest {
    let clientId: String
    let requestId: String
    let continuation: CheckedContinuation<(conversationId: String, context: String), Error>
  }

  struct KernelTurnTailTurn: Sendable {
    let role: String
    let content: String
    let surfaceKind: String
    let createdAtMs: Int
    let metadataJson: String
    let origin: String
  }

  struct KernelTurnTailResult: Sendable {
    let conversationId: String
    let turns: [KernelTurnTailTurn]
  }

  private struct ActiveKernelTurnTailRequest {
    let clientId: String
    let requestId: String
    let continuation: CheckedContinuation<KernelTurnTailResult, Error>
  }

  struct KernelTurnRecorded: Sendable {
    let conversationId: String
    let surfaceKind: String
    let externalRefKind: String
    let externalRefId: String
    let userText: String
    let assistantText: String
    let origin: String
    let interrupted: Bool
    let idempotencyKey: String?
    let userTurnId: String?
    let assistantTurnId: String?
  }

  typealias TurnRecordedHandler = @Sendable (KernelTurnRecorded) -> Void

  private var process: Process?
  private var stdinPipe: Pipe?
  private var stdoutPipe: Pipe?
  private var stderrPipe: Pipe?
  private var stdoutLineBuffer = Data()
  private var isRunning = false
  private var processGeneration: UInt64 = 0

  /// Debug suspend/resume state, held off-actor so SIGCONT never deadlocks behind
  /// an actor blocked writing to the frozen process. See DebugSuspendControl.
  private nonisolated let debugSuspend = DebugSuspendControl()
  private var lastExitWasOOM = false
  private var clients: [String: ClientRegistration] = [:]
  private var activeRequests: [RuntimeMessage.RequestKey: ActiveRequest] = [:]
  private var activeControlRequests: [RuntimeMessage.RequestKey: ActiveControlRequest] = [:]
  private var activeToolTasks: [String: Task<Void, Never>] = [:]
  private var activeVoiceSeedRequests: [RuntimeMessage.RequestKey: ActiveVoiceSeedRequest] = [:]
  private var activeKernelTurnTailRequests: [RuntimeMessage.RequestKey: ActiveKernelTurnTailRequest] = [:]
  /// Single UI apply gate for kernel `turn_recorded` (INV-6). Replace-only —
  /// never append; a second ChatProvider attach must not fan out duplicates.
  private var turnRecordedHandler: TurnRecordedHandler?
  private var initContinuations: [CheckedContinuation<Void, Error>] = []
  private let oomDiagnosticLatch = AgentRuntimeOOMDiagnosticLatch()
  private var receivedInit = false
  private var advertisedAgentControlTools: Set<String> = []
  private var isRestarting = false
  private var expectedCancelledRequests: Set<RuntimeMessage.RequestKey> = []

  var isAlive: Bool {
    let processRunning = process?.isRunning ?? false
    if isRunning && !processRunning {
      log(
        "AgentRuntimeProcess: stale alive latch — process no longer running "
          + "(failure_class=stale_alive_latch recovery_action=route_to_termination recovery_result=degraded)")
      DesktopDiagnosticsManager.shared.recordAgentRuntimeStaleAliveCheck()
      // Route through handleTermination so in-flight continuations are resumed
      // and the old terminationHandler is properly superseded. Only clearing the
      // latch here would leave active requests dangling if the terminationHandler
      // hasn't fired (or is about to be ignored by generation mismatch).
      handleTermination(reason: .exit)
    }
    return isRunning && processRunning
  }

  static func adapterId(forHarnessMode harnessMode: String) -> String? {
    guard let harness = AgentRuntimeRouting.harnessMode(from: harnessMode) else {
      return nil
    }
    return AgentRuntimeRouting.adapterId(for: harness).rawValue
  }

  func registerClient(clientId: String, harnessMode: String) async throws {
    guard !isRestarting else {
      throw BridgeError.restarting
    }
    var registration = clients[clientId] ?? ClientRegistration(harnessMode: harnessMode)
    registration.harnessMode = harnessMode
    clients[clientId] = registration

    if isRunning {
      try await waitForInit(timeout: 30.0)
      return
    }

    try await startProcess(preferredHarnessMode: harnessMode)
  }

  func unregisterClient(clientId: String) async {
    clients.removeValue(forKey: clientId)

    for (requestKey, request) in activeRequests where request.clientId == clientId {
      activeRequests.removeValue(forKey: requestKey)
      request.continuation.resume(throwing: BridgeError.stopped)
    }
    cancelActiveToolTasks(clientId: clientId)
    for (requestKey, request) in activeControlRequests where request.clientId == clientId {
      activeControlRequests.removeValue(forKey: requestKey)
      request.continuation.resume(throwing: BridgeError.stopped)
    }
    for (requestKey, request) in activeVoiceSeedRequests where request.clientId == clientId {
      activeVoiceSeedRequests.removeValue(forKey: requestKey)
      request.continuation.resume(throwing: BridgeError.stopped)
    }
    for (requestKey, request) in activeKernelTurnTailRequests where request.clientId == clientId {
      activeKernelTurnTailRequests.removeValue(forKey: requestKey)
      request.continuation.resume(throwing: BridgeError.stopped)
    }

    if clients.isEmpty {
      await stopProcess(resumeRequestsWith: BridgeError.stopped)
    }
  }

  func setGlobalAuthHandlers(
    clientId: String,
    onAuthRequired: AgentBridge.AuthRequiredHandler?,
    onAuthSuccess: AgentBridge.AuthSuccessHandler?
  ) {
    var registration = clients[clientId] ?? ClientRegistration(harnessMode: "piMono")
    registration.onAuthRequired = onAuthRequired
    registration.onAuthSuccess = onAuthSuccess
    clients[clientId] = registration
  }

  func restart(harnessMode: String) async throws {
    guard activeRequests.isEmpty, activeControlRequests.isEmpty else {
      log(
        "AgentRuntimeProcess: shared restart blocked while \(activeRequests.count) request(s) and \(activeControlRequests.count) control request(s) are active"
      )
      throw BridgeError.requestAlreadyActive
    }
    isRestarting = true
    defer { isRestarting = false }
    await stopProcess(resumeRequestsWith: BridgeError.stopped)
    try await startProcess(preferredHarnessMode: harnessMode)
  }

  func authenticate(methodId: String) {
    sendJson([
      "type": "authenticate",
      "methodId": methodId,
    ])
  }

  func warmupSession(clientId: String, cwd: String? = nil, sessions: [WarmupSessionConfig]) {
    var dict: [String: Any] = [
      "type": "warmup",
      "protocolVersion": 2,
      "requestId": UUID().uuidString,
      "clientId": clientId,
    ]
    if let ownerId = currentOwnerId() {
      dict["ownerId"] = ownerId
    }
    if let cwd { dict["cwd"] = cwd }
    dict["sessions"] = sessions.map { session -> [String: Any] in
      var entry: [String: Any] = [
        "key": session.key,
      ]
      if let model = session.model {
        entry["model"] = model
      }
      if let systemPrompt = session.systemPrompt {
        entry["systemPrompt"] = systemPrompt
      }
      return entry
    }
    sendJson(dict)
  }

  func invalidateSurface(clientId: String, surface: AgentSurfaceReference) {
    var dict: [String: Any] = [
      "type": "invalidate_session",
      "protocolVersion": 2,
      "requestId": UUID().uuidString,
      "clientId": clientId,
      "surfaceKind": surface.surfaceKind,
      "externalRefKind": surface.externalRefKind,
      "externalRefId": surface.externalRefId,
    ]
    if let ownerId = currentOwnerId() {
      dict["ownerId"] = ownerId
    }
    sendJson(dict)
  }

  func clearOwnerState(clientId: String) {
    var dict: [String: Any] = [
      "type": "clear_owner_state",
      "protocolVersion": 2,
      "requestId": UUID().uuidString,
      "clientId": clientId,
    ]
    if let ownerId = currentOwnerId() {
      dict["ownerId"] = ownerId
    }
    sendJson(dict)
  }

  func clearOwnerSurfaceState(clientId: String, chatId: String = "default") {
    var dict: [String: Any] = [
      "type": "clear_owner_surface_state",
      "protocolVersion": 2,
      "requestId": UUID().uuidString,
      "clientId": clientId,
      "chatId": chatId,
    ]
    if let ownerId = currentOwnerId() {
      dict["ownerId"] = ownerId
    }
    sendJson(dict)
  }

  // TODO(desktop-agent-platonic-gap-closure G6): delete importer two desktop releases after platonic ships.
  func importLegacyMainChatSessions(clientId: String, entries: [[String: String]]) {
    var dict: [String: Any] = [
      "type": "import_legacy_main_chat_sessions",
      "protocolVersion": 2,
      "requestId": UUID().uuidString,
      "clientId": clientId,
      "entries": entries,
    ]
    if let ownerId = currentOwnerId() {
      dict["ownerId"] = ownerId
    }
    sendJson(dict)
  }

  func mergeFloatingChatIntoMainChat(clientId: String, chatId: String = "default") {
    var dict: [String: Any] = [
      "type": "merge_floating_chat_into_main_chat",
      "protocolVersion": 2,
      "requestId": UUID().uuidString,
      "clientId": clientId,
      "chatId": chatId,
    ]
    if let ownerId = currentOwnerId() {
      dict["ownerId"] = ownerId
    }
    sendJson(dict)
  }

  func importConversationTurns(clientId: String, surface: AgentSurfaceReference, turns: [[String: Any]]) {
    var dict: [String: Any] = [
      "type": "import_conversation_turns",
      "protocolVersion": 2,
      "requestId": UUID().uuidString,
      "clientId": clientId,
      "surfaceKind": surface.surfaceKind,
      "externalRefKind": surface.externalRefKind,
      "externalRefId": surface.externalRefId,
      "turns": turns,
    ]
    if let ownerId = currentOwnerId() {
      dict["ownerId"] = ownerId
    }
    sendJson(dict)
  }

  func setTurnRecordedHandler(_ handler: TurnRecordedHandler?) {
    turnRecordedHandler = handler
  }

  func turnRecordedHandlerCount() -> Int {
    turnRecordedHandler == nil ? 0 : 1
  }

  /// Test-only: fire the single turn_recorded apply gate without a live node runtime.
  func dispatchTurnRecordedForTesting(_ turn: KernelTurnRecorded) {
    turnRecordedHandler?(turn)
  }

  func recordSurfaceTurn(
    clientId: String,
    surface: AgentSurfaceReference,
    userText: String,
    assistantText: String,
    origin: String,
    interrupted: Bool = false,
    idempotencyKey: String? = nil
  ) {
    var dict: [String: Any] = [
      "type": "record_surface_turn",
      "protocolVersion": 2,
      "requestId": UUID().uuidString,
      "clientId": clientId,
      "surfaceKind": surface.surfaceKind,
      "externalRefKind": surface.externalRefKind,
      "externalRefId": surface.externalRefId,
      "userText": userText,
      "assistantText": assistantText,
      "origin": origin,
      "interrupted": interrupted,
    ]
    if let idempotencyKey, !idempotencyKey.isEmpty {
      dict["idempotencyKey"] = idempotencyKey
    }
    if let ownerId = currentOwnerId() {
      dict["ownerId"] = ownerId
    }
    sendJson(dict)
  }

  func getVoiceSeedContext(
    clientId: String,
    harnessMode: String,
    surface: AgentSurfaceReference
  ) async throws -> (conversationId: String, context: String) {
    try await registerClient(clientId: clientId, harnessMode: harnessMode)
    let requestId = UUID().uuidString
    let requestKey = RuntimeMessage.RequestKey(clientId: clientId, requestId: requestId)
    return try await withCheckedThrowingContinuation { continuation in
      activeVoiceSeedRequests[requestKey] = ActiveVoiceSeedRequest(
        clientId: clientId,
        requestId: requestId,
        continuation: continuation
      )
      var dict: [String: Any] = [
        "type": "get_voice_seed_context",
        "protocolVersion": 2,
        "requestId": requestId,
        "clientId": clientId,
        "surfaceKind": surface.surfaceKind,
        "externalRefKind": surface.externalRefKind,
        "externalRefId": surface.externalRefId,
      ]
      if let ownerId = currentOwnerId() {
        dict["ownerId"] = ownerId
      }
      let sent = sendJson(dict)
      if !sent, let request = activeVoiceSeedRequests.removeValue(forKey: requestKey) {
        request.continuation.resume(throwing: BridgeError.agentError("Failed to send voice seed request"))
      }
    }
  }

  func getKernelTurnTail(
    clientId: String,
    harnessMode: String,
    limit: Int = 8,
    chatId: String = "default"
  ) async throws -> KernelTurnTailResult {
    try await registerClient(clientId: clientId, harnessMode: harnessMode)
    let requestId = UUID().uuidString
    let requestKey = RuntimeMessage.RequestKey(clientId: clientId, requestId: requestId)
    return try await withCheckedThrowingContinuation { continuation in
      activeKernelTurnTailRequests[requestKey] = ActiveKernelTurnTailRequest(
        clientId: clientId,
        requestId: requestId,
        continuation: continuation
      )
      var dict: [String: Any] = [
        "type": "get_kernel_turn_tail",
        "protocolVersion": 2,
        "requestId": requestId,
        "clientId": clientId,
        "limit": limit,
        "chatId": chatId,
      ]
      if let ownerId = currentOwnerId() {
        dict["ownerId"] = ownerId
      }
      let sent = sendJson(dict)
      if !sent, let request = activeKernelTurnTailRequests.removeValue(forKey: requestKey) {
        request.continuation.resume(throwing: BridgeError.agentError("Failed to send kernel turn tail request"))
      }
    }
  }

  func projectCrossSurfaceTurn(
    clientId: String,
    surface: AgentSurfaceReference,
    userText: String,
    assistantText: String,
    origin: String,
    idempotencyKey: String? = nil
  ) {
    var dict: [String: Any] = [
      "type": "project_cross_surface_turn",
      "protocolVersion": 2,
      "requestId": UUID().uuidString,
      "clientId": clientId,
      "surfaceKind": surface.surfaceKind,
      "externalRefKind": surface.externalRefKind,
      "externalRefId": surface.externalRefId,
      "userText": userText,
      "assistantText": assistantText,
      "origin": origin,
    ]
    if let idempotencyKey, !idempotencyKey.isEmpty {
      dict["idempotencyKey"] = idempotencyKey
    }
    if let ownerId = currentOwnerId() {
      dict["ownerId"] = ownerId
    }
    sendJson(dict)
  }

  func refreshAuthToken(_ token: String) {
    var dict: [String: Any] = [
      "type": "refresh_token",
      "token": token,
    ]
    if let ownerId = currentOwnerId() {
      dict["ownerId"] = ownerId
    }
    sendJson(dict)
  }

  func directControlTool(
    clientId: String,
    harnessMode: String,
    name: String,
    input: [String: Any]
  ) async throws -> String {
    guard let ownerId = currentOwnerId() else {
      throw BridgeError.agentError("Agent control requires a signed-in owner")
    }
    try await registerClient(clientId: clientId, harnessMode: harnessMode)
    guard advertisedAgentControlTools.contains(name) else {
      throw BridgeError.agentError("Agent runtime does not advertise direct control tool \(name)")
    }

    let requestId = UUID().uuidString
    let requestKey = RuntimeMessage.RequestKey(clientId: clientId, requestId: requestId)
    return try await withCheckedThrowingContinuation { continuation in
      activeControlRequests[requestKey] = ActiveControlRequest(
        clientId: clientId,
        requestId: requestId,
        continuation: continuation
      )
      let dict: [String: Any] = [
        "type": "direct_control_tool",
        "protocolVersion": 2,
        "requestId": requestId,
        "clientId": clientId,
        "name": name,
        "input": input,
        "ownerId": ownerId,
      ]
      let sent = sendJson(dict)
      if !sent, let request = activeControlRequests.removeValue(forKey: requestKey) {
        request.continuation.resume(throwing: BridgeError.agentError("Failed to send direct control tool request"))
      }
    }
  }

  // MARK: - Automation stall hook (non-production only)

  /// Freeze the agent's stdio stream by sending SIGSTOP to the node bridge
  /// process. With the process paused it emits no further events, so an in-flight
  /// chat send stalls exactly like a hung ACP subprocess — driving the
  /// StallDetector to `.stalled` (20s) and, if held long enough, ChatProvider's
  /// 180s send watchdog (CHAT-02). A safety auto-resume fires after `durationMs`
  /// (hard-capped) so the process can never stay frozen if `debugResumeStream`
  /// is never called. Non-production bundles only.
  func debugSuspendStream(durationMs: Int) -> [String: String] {
    guard AppBuild.isNonProduction else {
      return ["error": "suspend_agent_stream is disabled on production bundles"]
    }
    guard let process, process.isRunning, process.processIdentifier > 0 else {
      return ["error": "no running agent process to suspend"]
    }
    let pid = process.processIdentifier
    guard kill(pid, SIGSTOP) == 0 else {
      return ["error": "SIGSTOP failed for pid \(pid) (errno \(errno))"]
    }
    // Arm the off-actor control so resume/auto-resume can SIGCONT even if the
    // actor later blocks writing to this now-frozen process.
    let generation = debugSuspend.arm(pid: pid)
    // Cap the freeze window so a forgotten resume can't wedge the agent.
    let cappedMs = max(1_000, min(durationMs, 300_000))
    log("AgentRuntimeProcess: DEBUG suspended stream pid=\(pid) for \(cappedMs)ms (gen \(generation))")
    // The safety auto-resume runs off the actor (via the control), so a wedged
    // actor — e.g. one blocked writing to this frozen process — can't starve it.
    Task { [debugSuspend] in
      try? await Task.sleep(nanoseconds: UInt64(cappedMs) * 1_000_000)
      if let resumed = debugSuspend.autoResume(generation: generation) {
        log("AgentRuntimeProcess: DEBUG auto-resumed stream pid=\(resumed) (gen \(generation))")
      }
    }
    return ["suspended": "true", "pid": "\(pid)", "durationMs": "\(cappedMs)"]
  }

  /// SIGCONT the agent process immediately (early clear of a debug suspend).
  /// `nonisolated` and routed through the off-actor control so it runs even when
  /// the actor is blocked writing to the frozen process — otherwise the very
  /// resume that would unblock that write could never fire, deadlocking the agent.
  nonisolated func debugResumeStream() -> [String: String] {
    guard AppBuild.isNonProduction else {
      return ["error": "resume_agent_stream is disabled on production bundles"]
    }
    guard let pid = debugSuspend.resume() else {
      return ["error": "no suspended agent to resume"]
    }
    log("AgentRuntimeProcess: DEBUG resumed stream pid=\(pid)")
    return ["resumed": "true", "pid": "\(pid)"]
  }

  func interrupt(clientId: String, requestId: String) {
    let requestKey = RuntimeMessage.RequestKey(clientId: clientId, requestId: requestId)
    guard var request = activeRequests[requestKey] else { return }
    request.isInterrupted = true
    activeRequests[requestKey] = request
    var dict: [String: Any] = [
      "type": "interrupt",
      "protocolVersion": 2,
      "requestId": requestId,
      "clientId": clientId,
    ]
    if let ownerId = currentOwnerId() {
      dict["ownerId"] = ownerId
    }
    guard sendJson(dict) else {
      activeRequests.removeValue(forKey: requestKey)
      request.continuation.resume(throwing: BridgeError.stopped)
      return
    }
    activeRequests.removeValue(forKey: requestKey)
    expectedCancelledRequests.insert(requestKey)
    request.continuation.resume(throwing: BridgeError.stopped)
  }

  func query(
    clientId: String,
    requestId: String,
    harnessMode: String,
    prompt: String,
    systemPrompt: String,
    surface: AgentSurfaceReference,
    cwd: String?,
    mode: String?,
    model: String?,
    imageData: Data?,
    attachmentMetadataJson: String?,
    surfaceContextJson: String?,
    onTextDelta: @escaping AgentBridge.TextDeltaHandler,
    onToolCall: @escaping AgentBridge.ToolCallHandler,
    onToolActivity: @escaping AgentBridge.ToolActivityHandler,
    onThinkingDelta: @escaping AgentBridge.ThinkingDeltaHandler,
    onToolResultDisplay: @escaping AgentBridge.ToolResultDisplayHandler,
    onAuthRequired: @escaping AgentBridge.AuthRequiredHandler,
    onAuthSuccess: @escaping AgentBridge.AuthSuccessHandler
  ) async throws -> AgentBridge.QueryResult {
    try await registerClient(clientId: clientId, harnessMode: harnessMode)
    guard let adapterId = Self.adapterId(forHarnessMode: harnessMode) else {
      throw BridgeError.agentError("Unknown AI runtime mode: \(harnessMode)")
    }

    return try await withCheckedThrowingContinuation { continuation in
      let surfaceRef = surface
      let request = ActiveRequest(
        clientId: clientId,
        requestId: requestId,
        surfaceRef: surfaceRef,
        onTextDelta: onTextDelta,
        onToolCall: onToolCall,
        onToolActivity: onToolActivity,
        onThinkingDelta: onThinkingDelta,
        onToolResultDisplay: onToolResultDisplay,
        onAuthRequired: onAuthRequired,
        onAuthSuccess: onAuthSuccess,
        continuation: continuation
      )
      activeRequests[RuntimeMessage.RequestKey(clientId: clientId, requestId: requestId)] = request
      Task { @MainActor in
        AgentRuntimeStatusStore.shared.beginRequest(surface: surfaceRef)
      }

      var queryDict: [String: Any] = [
        "type": "query",
        "protocolVersion": 2,
        "id": requestId,
        "requestId": requestId,
        "clientId": clientId,
        "prompt": prompt,
        "systemPrompt": systemPrompt,
        "adapterId": adapterId,
        "surfaceKind": surface.surfaceKind,
        "externalRefKind": surface.externalRefKind,
        "externalRefId": surface.externalRefId,
      ]
      if let cwd { queryDict["cwd"] = cwd }
      if let mode { queryDict["mode"] = mode }
      if let model { queryDict["model"] = model }
      if let imageData {
        queryDict["imageBase64"] = imageData.base64EncodedString()
      }
      if let attachmentMetadataJson, !attachmentMetadataJson.isEmpty {
        queryDict["attachmentMetadataJson"] = attachmentMetadataJson
      }
      if let surfaceContextJson, !surfaceContextJson.isEmpty {
        queryDict["surfaceContextJson"] = surfaceContextJson
      }
      if let ownerId = currentOwnerId() {
        queryDict["ownerId"] = ownerId
      }
      sendJson(queryDict)
    }
  }

  private func startProcess(preferredHarnessMode: String) async throws {
    guard !isRunning else { return }
    guard let preferredHarness = AgentRuntimeRouting.harnessMode(from: preferredHarnessMode) else {
      log("AgentRuntimeProcess: refusing unknown harness mode \(preferredHarnessMode)")
      throw BridgeError.agentError("Unknown AI runtime mode: \(preferredHarnessMode)")
    }
    let preferredAdapterId = AgentRuntimeRouting.adapterId(for: preferredHarness)

    process = nil
    closePipes()
    lastExitWasOOM = false
    receivedInit = false
    advertisedAgentControlTools.removeAll()

    guard let nodePath = findNodeBinary() else {
      throw BridgeError.nodeNotFound
    }
    guard let bridgePath = findBridgeScript() else {
      throw BridgeError.bridgeScriptNotFound
    }

    let nodeExists = FileManager.default.isExecutableFile(atPath: nodePath)
    let bridgeExists = FileManager.default.fileExists(atPath: bridgePath)
    let bridgeDir = (bridgePath as NSString).deletingLastPathComponent
    let pkgJsonPath = ((bridgeDir as NSString).deletingLastPathComponent as NSString)
      .appendingPathComponent("package.json")
    let pkgJsonExists = FileManager.default.fileExists(atPath: pkgJsonPath)
    log(
      "AgentRuntimeProcess: starting node=\(nodePath) (exists=\(nodeExists)), bridge=\(bridgePath) (exists=\(bridgeExists)), package.json=\(pkgJsonExists)"
    )

    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: nodePath)
    proc.arguments = ["--max-old-space-size=256", "--max-semi-space-size=16", bridgePath]

    var env = ProcessInfo.processInfo.environment
    env["NODE_NO_WARNINGS"] = "1"
    env["HARNESS_MODE"] = preferredHarnessMode
    env["OMI_AGENT_STATE_DIR"] = Self.defaultStateDirectory()
    env["OMI_AGENT_ARTIFACTS_DIR"] = Self.defaultArtifactsDirectory()
    env.removeValue(forKey: "ANTHROPIC_API_KEY")
    env.removeValue(forKey: "CLAUDE_CODE_USE_VERTEX")
    applyLocalAgentEnvironment(to: &env)

    let rustBase = await APIClient.shared.rustBackendURL
    if !rustBase.isEmpty {
      env["OMI_API_BASE_URL"] = rustBase.hasSuffix("/") ? "\(rustBase)v2" : "\(rustBase)/v2"
    } else if preferredAdapterId == .piMono {
      log("AgentRuntimeProcess: pi-mono start refused, OMI_DESKTOP_API_URL is not configured")
      throw BridgeError.bridgeScriptNotFound
    }

    Self.removeInheritedBYOKEnvironment(from: &env)
    let byok = await Self.usableBYOKEnvironment()
    for (key, value) in byok.values {
      env[key] = value
    }
    if APIKeyService.isByokActive {
      if !byok.suppressedProviders.isEmpty {
        for provider in byok.suppressedProviders {
          log(
            "CredentialHealth: context=agent_runtime_env failure_class=byok_invalid_suppressed provider=\(provider.rawValue)"
          )
        }
      }
      log("AgentRuntimeProcess: pi-mono BYOK active, forwarding \(byok.values.count) usable user keys")
    }

    let authService = await MainActor.run { AuthService.shared }
    let forceRefreshToken = preferredAdapterId == .piMono && !DesktopLocalProfile.isEnabled
    if let token = try? await authService.getIdToken(forceRefresh: forceRefreshToken), !token.isEmpty {
      env["OMI_AUTH_TOKEN"] = token
    } else if preferredAdapterId == .piMono {
      log("AgentRuntimeProcess: pi-mono start refused, Firebase ID token is missing")
      throw BridgeError.authMissing
    }

    let nodeDir = (nodePath as NSString).deletingLastPathComponent
    let existingPath = env["PATH"] ?? "/usr/bin:/bin"
    if !existingPath.contains(nodeDir) {
      env["PATH"] = "\(nodeDir):\(existingPath)"
    }

    let defaults = UserDefaults.standard
    let useExtension =
      defaults.object(forKey: "playwrightUseExtension") == nil
      || defaults.bool(forKey: "playwrightUseExtension")
    let playwrightToken = defaults.string(forKey: "playwrightExtensionToken") ?? ""
    let playwrightTarget = BrowserAutomationTargetResolver.preferredTarget()
    let hasInstalledPlaywrightBridge =
      playwrightTarget.map { BrowserAutomationTargetResolver.isExtensionInstalled(in: $0) } ?? false
    if Self.shouldEnablePlaywrightExtension(
      useExtension: useExtension,
      token: playwrightToken,
      targetHasExtension: hasInstalledPlaywrightBridge)
    {
      env["PLAYWRIGHT_MCP_ENABLED"] = "true"
      env["PLAYWRIGHT_USE_EXTENSION"] = "true"
      env["PLAYWRIGHT_MCP_EXTENSION_TOKEN"] = playwrightToken
    } else {
      env.removeValue(forKey: "PLAYWRIGHT_MCP_ENABLED")
      env.removeValue(forKey: "PLAYWRIGHT_USE_EXTENSION")
      env.removeValue(forKey: "PLAYWRIGHT_MCP_EXTENSION_TOKEN")
    }

    proc.environment = env

    let stdin = Pipe()
    let stdout = Pipe()
    let stderr = Pipe()
    proc.standardInput = stdin
    proc.standardOutput = stdout
    proc.standardError = stderr
    stdinPipe = stdin
    stdoutPipe = stdout
    stderrPipe = stderr
    process = proc

    processGeneration &+= 1
    let expectedGeneration = processGeneration
    oomDiagnosticLatch.reset(generation: expectedGeneration)
    let oomDiagnosticLatch = oomDiagnosticLatch
    stderr.fileHandleForReading.readabilityHandler = { handle in
      let data = handle.availableData
      if !data.isEmpty, let text = String(data: data, encoding: .utf8) {
        log("AgentRuntimeProcess stderr: \(text.trimmingCharacters(in: .whitespacesAndNewlines))")
        oomDiagnosticLatch.markIfConfirmed(text, generation: expectedGeneration)
      }
    }

    proc.terminationHandler = { [weak self] terminatedProc in
      let code = terminatedProc.terminationStatus
      let reason = terminatedProc.terminationReason
      Task { [weak self] in
        await self?.handleTermination(
          exitCode: code,
          reason: reason,
          generation: expectedGeneration
        )
      }
    }

    try proc.run()
    isRunning = true
    startReadingStdout()

    do {
      try await waitForInit(timeout: 30.0)
    } catch {
      await cleanupFailedStart(process: proc, error: error)
      throw error
    }
  }

  private func applyLocalAgentEnvironment(to env: inout [String: String]) {
    // Seed auto-discovered commands for every local adapter so the shared Node
    // process can route to Hermes or OpenClaw even when it was launched for a
    // different adapter. registerClient returns early once isRunning, so the
    // startup adapter's env would otherwise be the only one the process sees.
    let home = NSHomeDirectory()
    if env["HOME"]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true {
      env["HOME"] = home
    }
    if env["HERMES_HOME"]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true {
      env["HERMES_HOME"] = "\(home)/.hermes"
    }

    let adapterPathDirs = [
      "\(home)/.hermes/hermes-agent/venv/bin",
      "\(home)/.hermes/node/bin",
      "\(home)/.hermes/hermes-agent",
    ]
    let adapterSearchDirs = adapterPathDirs + [
      "\(home)/.local/bin",
      "/opt/homebrew/bin",
      "/usr/local/bin",
    ]
    let trustedPathDirs = [
      "/opt/homebrew/bin",
      "/usr/local/bin",
    ]
    let existingPath = env["PATH"] ?? "/usr/bin:/bin"
    var pathElements: [String] = []
    for path in existingPath.split(separator: ":").map(String.init) + trustedPathDirs + adapterPathDirs {
      if !pathElements.contains(path) {
        pathElements.append(path)
      }
    }
    env["PATH"] = pathElements.joined(separator: ":")

    if env["OMI_HERMES_ADAPTER_COMMAND"]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true,
      let hermes = firstExecutable(named: "hermes", in: adapterSearchDirs)
    {
      env["OMI_HERMES_ADAPTER_COMMAND"] = "\(Self.shellQuote(hermes)) acp"
    }

    if env["OMI_OPENCLAW_ADAPTER_COMMAND"]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true,
      let openClaw = firstExecutable(named: "openclaw", in: adapterSearchDirs)
    {
      env["OMI_OPENCLAW_ADAPTER_COMMAND"] = Self.openClawAdapterCommand(openClawPath: openClaw)
    }
  }

  static func byokEnvironmentKey(for provider: BYOKProvider) -> String {
    "OMI_BYOK_\(provider.rawValue.uppercased())"
  }

  static func removeInheritedBYOKEnvironment(from env: inout [String: String]) {
    let inheritedBYOKKeys = env.keys.filter { $0.uppercased().hasPrefix("OMI_BYOK_") }
    for key in inheritedBYOKKeys {
      env.removeValue(forKey: key)
    }
  }

  @MainActor
  static func usableBYOKEnvironment() -> (values: [String: String], suppressedProviders: [BYOKProvider]) {
    guard APIKeyService.isByokActive else {
      return ([:], [])
    }

    var candidateValues: [String: String] = [:]
    var suppressedProviders: [BYOKProvider] = []
    for provider in BYOKProvider.allCases {
      guard let key = APIKeyService.byokKey(provider) else { continue }
      let fingerprint = APIKeyService.byokFingerprint(key)
      if CredentialHealthManager.shared.canUseBYOK(provider: provider, fingerprint: fingerprint) {
        candidateValues[byokEnvironmentKey(for: provider)] = key
      } else {
        suppressedProviders.append(provider)
      }
    }
    guard suppressedProviders.isEmpty, candidateValues.count == BYOKProvider.allCases.count else {
      return ([:], suppressedProviders)
    }
    return (candidateValues, [])
  }

  static func openClawAdapterCommand(openClawPath: String, fileManager: FileManager = .default) -> String {
    let nodePath = ((openClawPath as NSString).deletingLastPathComponent as NSString).appendingPathComponent("node")
    if fileManager.isExecutableFile(atPath: nodePath) {
      return "\(shellQuote(nodePath)) \(shellQuote(openClawPath)) acp"
    }
    return "\(shellQuote(openClawPath)) acp"
  }

  private static func shellQuote(_ value: String) -> String {
    "'\(value.replacingOccurrences(of: "'", with: "'\\''"))'"
  }

  private func firstExecutable(named name: String, in directories: [String]) -> String? {
    let fileManager = FileManager.default
    for dir in directories {
      let path = (dir as NSString).appendingPathComponent(name)
      if fileManager.isExecutableFile(atPath: path) {
        return path
      }
    }
    return nil
  }

  private func cleanupFailedStart(process failedProcess: Process, error: Error) async {
    log("AgentRuntimeProcess: startup failed after launch: \(error)")
    if failedProcess.isRunning {
      failedProcess.terminate()
      let start = Date()
      while failedProcess.isRunning && Date().timeIntervalSince(start) < 1.0 {
        try? await Task.sleep(nanoseconds: 50_000_000)
      }
      if failedProcess.isRunning {
        kill(failedProcess.processIdentifier, SIGKILL)
      }
    }
    if let currentProcess = process, currentProcess === failedProcess {
      process = nil
    }
    closePipes()
    isRunning = false
    receivedInit = false
    advertisedAgentControlTools.removeAll()
    resumeAllRequests(throwing: BridgeError.stopped)
    resumeInitContinuations(throwing: BridgeError.stopped)
  }

  private func waitForInit(timeout: TimeInterval) async throws {
    if receivedInit { return }

    let timeoutTask = Task {
      do {
        try await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
        self.resumeInitContinuations(throwing: BridgeError.timeout)
      } catch {
        // Cancelled because init completed first.
      }
    }
    defer { timeoutTask.cancel() }

    try await withCheckedThrowingContinuation { continuation in
      storeInitContinuation(continuation)
    }
  }

  private func storeInitContinuation(_ continuation: CheckedContinuation<Void, Error>) {
    if receivedInit {
      continuation.resume()
      return
    }
    initContinuations.append(continuation)
  }

  private func resolveInitContinuations() {
    let continuations = initContinuations
    initContinuations.removeAll()
    for continuation in continuations {
      continuation.resume()
    }
  }

  private func stopProcess(resumeRequestsWith error: BridgeError) async {
    let proc = process
    processGeneration &+= 1
    lastExitWasOOM = false
    oomDiagnosticLatch.reset(generation: processGeneration)
    sendJson(["type": "stop"])
    try? stdinPipe?.fileHandleForWriting.close()
    proc?.terminate()

    if let proc {
      let pid = proc.processIdentifier
      let start = Date()
      while proc.isRunning && Date().timeIntervalSince(start) < 3.0 {
        try? await Task.sleep(nanoseconds: 50_000_000)
      }
      if proc.isRunning && pid > 0 {
        log("AgentRuntimeProcess: process \(pid) still alive after 3s, sending SIGKILL")
        kill(pid, SIGKILL)
        try? await Task.sleep(nanoseconds: 200_000_000)
      }
    }

    process = nil
    closePipes()
    lastExitWasOOM = false
    oomDiagnosticLatch.reset(generation: processGeneration)
    isRunning = false
    receivedInit = false
    cancelActiveToolTasks()
    advertisedAgentControlTools.removeAll()
    resumeAllRequests(throwing: error)
    resumeInitContinuations(throwing: error)
  }

  private func startReadingStdout() {
    guard let stdoutPipe else { return }
    let expectedGeneration = processGeneration

    let handle = stdoutPipe.fileHandleForReading
    handle.readabilityHandler = { [weak self] handle in
      let data = handle.availableData
      guard !data.isEmpty else {
        handle.readabilityHandler = nil
        return
      }
      Task { [weak self] in
        await self?.processStdoutData(data, generation: expectedGeneration)
      }
    }
  }

  private func processStdoutData(_ data: Data, generation: UInt64) {
    // Drop stdout chunks from a previous process generation. When the bridge is
    // restarted or startup cleanup closes the pipe, a readability callback that
    // already captured the old data can still fire after the new process has
    // begun. Without this guard, stale init/result lines from the old Node
    // process could mutate the new process state or resume the wrong continuation.
    if generation != processGeneration {
      log("AgentRuntimeProcess: dropping stale stdout chunk (gen=\(generation), current=\(processGeneration))")
      return
    }
    stdoutLineBuffer.append(data)

    while let newlineIndex = stdoutLineBuffer.firstIndex(of: UInt8(ascii: "\n")) {
      let lineData = stdoutLineBuffer[stdoutLineBuffer.startIndex..<newlineIndex]
      stdoutLineBuffer = Data(stdoutLineBuffer[stdoutLineBuffer.index(after: newlineIndex)...])

      guard let line = String(data: lineData, encoding: .utf8),
        !line.trimmingCharacters(in: .whitespaces).isEmpty
      else {
        continue
      }

      if let message = RuntimeMessage.parse(line) {
        handleMessage(message)
      } else {
        log("AgentRuntimeProcess: failed to parse message: \(line.prefix(200))")
      }
    }
  }

  private func handleMessage(_ message: RuntimeMessage) {
    if let request = routedRequest(for: message), let surfaceRef = request.surfaceRef {
      Task { @MainActor in
        AgentRuntimeStatusStore.shared.ingest(message: message, surface: surfaceRef)
      }
    }

    switch message.kind {
    case .initMessage:
      log("AgentRuntimeProcess: bridge ready (sessionId=\(message.payload["sessionId"] as? String ?? ""))")
      let tools = message.payload["agentControlTools"] as? [String] ?? []
      advertisedAgentControlTools = Set(tools)
      receivedInit = true
      resolveInitContinuations()

    case .authRequired:
      let methods = message.payload["methods"] as? [[String: Any]] ?? []
      let authUrl = message.payload["authUrl"] as? String
      if let request = routedRequest(for: message) {
        request.onAuthRequired(methods, authUrl)
      } else {
        for client in clients.values {
          client.onAuthRequired?(methods, authUrl)
        }
      }

    case .authSuccess:
      if let request = routedRequest(for: message) {
        request.onAuthSuccess()
      } else {
        for client in clients.values {
          client.onAuthSuccess?()
        }
      }

    case .textDelta:
      routedRequest(for: message)?.onTextDelta(message.payload["text"] as? String ?? "")

    case .thinkingDelta:
      routedRequest(for: message)?.onThinkingDelta(message.payload["text"] as? String ?? "")

    case .toolActivity:
      routedRequest(for: message)?.onToolActivity(
        message.payload["name"] as? String ?? "",
        message.payload["status"] as? String ?? "started",
        message.payload["toolUseId"] as? String,
        message.payload["input"] as? [String: Any]
      )

    case .toolResultDisplay:
      routedRequest(for: message)?.onToolResultDisplay(
        message.payload["toolUseId"] as? String ?? "",
        message.payload["name"] as? String ?? "",
        message.payload["output"] as? String ?? ""
      )

    case .toolUse:
      handleToolUse(message)

    case .toolCancel:
      handleToolCancel(message)

    case .cancelAck:
      if let requestKey = message.requestKey, var request = activeRequests[requestKey] {
        request.cancelAck = message
        activeRequests[requestKey] = request
      }

    case .controlToolResult:
      completeControlRequest(message)

    case .voiceSeedContext:
      completeVoiceSeedRequest(message)

    case .kernelTurnTail:
      completeKernelTurnTailRequest(message)

    case .turnRecorded:
      if let recorded = kernelTurnRecorded(from: message) {
        turnRecordedHandler?(recorded)
      }

    case .result:
      completeRequest(message)

    case .error:
      failRequest(message)

    case .unknown(let type):
      log("AgentRuntimeProcess: unknown message type: \(type)")
    }
  }

  private func routedRequest(for message: RuntimeMessage) -> ActiveRequest? {
    if let requestKey = message.requestKey {
      return activeRequests[requestKey]
    }
    return nil
  }

  private func handleToolUse(_ message: RuntimeMessage) {
    let callId = message.payload["callId"] as? String ?? ""
    let name = message.payload["name"] as? String ?? ""
    let toolTaskKey = activeToolTaskKey(for: message)
    guard let request = routedRequest(for: message) else {
      log("AgentRuntimeProcess: rejecting unrouted tool call \(name)")
      completeToolCall(
        callId: callId,
        result: Self.unroutedToolCallError(toolName: name),
        requestId: message.requestId,
        clientId: message.clientId
      )
      return
    }
    if request.isInterrupted {
      log("AgentRuntimeProcess: skipping tool call after interrupt")
      return
    }
    let input = message.payload["input"] as? [String: Any] ?? [:]
    let task = Task {
      let result = await request.onToolCall(callId, name, input)
      finishToolCall(
        key: toolTaskKey,
        callId: callId,
        result: result,
        requestId: request.requestId,
        clientId: request.clientId
      )
    }
    activeToolTasks[toolTaskKey] = task
  }

  private func handleToolCancel(_ message: RuntimeMessage) {
    let key = activeToolTaskKey(for: message)
    guard let task = activeToolTasks.removeValue(forKey: key) else { return }
    task.cancel()
  }

  private func finishToolCall(key: String, callId: String, result: String, requestId: String? = nil, clientId: String? = nil) {
    guard activeToolTasks.removeValue(forKey: key) != nil else { return }
    completeToolCall(callId: callId, result: result, requestId: requestId, clientId: clientId)
  }

  private func activeToolTaskKey(for message: RuntimeMessage) -> String {
    if let requestKey = message.requestKey {
      return "\(requestKey.clientId)\u{0}\(requestKey.requestId)\u{0}\(message.payload["callId"] as? String ?? "")"
    }
    return "legacy\u{0}\(message.payload["callId"] as? String ?? "")"
  }

  private func cancelActiveToolTasks(clientId: String? = nil) {
    for key in Array(activeToolTasks.keys) {
      if let clientId, !key.hasPrefix("\(clientId)\u{0}") {
        continue
      }
      activeToolTasks.removeValue(forKey: key)?.cancel()
    }
  }

  private static func unroutedToolCallError(toolName: String) -> String {
    let payload: [String: Any] = [
      "ok": false,
      "error": [
        "code": "unrouted_tool_call",
        "message": "Tool call '\(toolName)' was rejected because it was not attached to an active trusted request.",
      ],
    ]
    guard
      let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
      let text = String(data: data, encoding: .utf8)
    else {
      return #"{"ok":false,"error":{"code":"unrouted_tool_call"}}"#
    }
    return text
  }

  private func completeToolCall(callId: String, result: String, requestId: String? = nil, clientId: String? = nil) {
    var payload: [String: Any] = [
      "type": "tool_result",
      "callId": callId,
      "result": result,
    ]
    if let requestId { payload["requestId"] = requestId }
    if let clientId { payload["clientId"] = clientId }
    sendJson(payload)
  }

  private func completeRequest(_ message: RuntimeMessage) {
    let terminalStatus = message.payload["terminalStatus"] as? String
    guard let requestKey = message.requestKey else {
      log("AgentRuntimeProcess: dropping unroutable result")
      return
    }
    guard let request = activeRequests.removeValue(forKey: requestKey) else {
      if terminalStatus == "cancelled", expectedCancelledRequests.remove(requestKey) != nil {
        return
      }
      log("AgentRuntimeProcess: dropping unroutable result")
      return
    }
    if terminalStatus == "cancelled" {
      request.continuation.resume(throwing: BridgeError.stopped)
      return
    }
    if let terminalStatus,
       ["failed", "timed_out", "orphaned"].contains(terminalStatus) {
      let failure = AgentRuntimeFailure.parse(from: message.payload["failure"])
      let raw = failure?.displayMessage ?? message.payload["text"] as? String ?? "Agent failed"
      log("AgentRuntimeProcess: agent result failed (raw): \(raw)")
      request.continuation.resume(throwing: failure.map(BridgeError.agentRuntimeFailure) ?? BridgeError.agentError(raw))
      return
    }
    request.continuation.resume(returning: queryResult(from: message))
  }

  private func completeControlRequest(_ message: RuntimeMessage) {
    guard let requestKey = message.requestKey,
      let request = activeControlRequests.removeValue(forKey: requestKey)
    else {
      log("AgentRuntimeProcess: dropping unroutable control tool result")
      return
    }
    request.continuation.resume(returning: message.payload["result"] as? String ?? "")
  }

  private func completeVoiceSeedRequest(_ message: RuntimeMessage) {
    guard let requestKey = message.requestKey,
      let request = activeVoiceSeedRequests.removeValue(forKey: requestKey)
    else {
      log("AgentRuntimeProcess: dropping unroutable voice seed context")
      return
    }
    let conversationId = message.payload["conversationId"] as? String ?? ""
    let context = message.payload["context"] as? String ?? ""
    request.continuation.resume(returning: (conversationId: conversationId, context: context))
  }

  private func completeKernelTurnTailRequest(_ message: RuntimeMessage) {
    guard let requestKey = message.requestKey,
      let request = activeKernelTurnTailRequests.removeValue(forKey: requestKey)
    else {
      log("AgentRuntimeProcess: dropping unroutable kernel turn tail")
      return
    }
    let conversationId = message.payload["conversationId"] as? String ?? ""
    let rawTurns = message.payload["turns"] as? [[String: Any]] ?? []
    let turns = rawTurns.map { row in
      KernelTurnTailTurn(
        role: row["role"] as? String ?? "",
        content: row["content"] as? String ?? "",
        surfaceKind: row["surfaceKind"] as? String ?? "",
        createdAtMs: row["createdAtMs"] as? Int ?? 0,
        metadataJson: row["metadataJson"] as? String ?? "{}",
        origin: row["origin"] as? String ?? ""
      )
    }
    request.continuation.resume(returning: KernelTurnTailResult(conversationId: conversationId, turns: turns))
  }

  private func kernelTurnRecorded(from message: RuntimeMessage) -> KernelTurnRecorded? {
    let payload = message.payload
    guard let conversationId = payload["conversationId"] as? String else { return nil }
    return KernelTurnRecorded(
      conversationId: conversationId,
      surfaceKind: payload["surfaceKind"] as? String ?? "",
      externalRefKind: payload["externalRefKind"] as? String ?? "",
      externalRefId: payload["externalRefId"] as? String ?? "",
      userText: payload["userText"] as? String ?? "",
      assistantText: payload["assistantText"] as? String ?? "",
      origin: payload["origin"] as? String ?? "",
      interrupted: payload["interrupted"] as? Bool ?? false,
      idempotencyKey: payload["idempotencyKey"] as? String,
      userTurnId: payload["userTurnId"] as? String,
      assistantTurnId: payload["assistantTurnId"] as? String
    )
  }

  private func failRequest(_ message: RuntimeMessage) {
    let failure = AgentRuntimeFailure.parse(from: message.payload["failure"])
    let raw = failure?.displayMessage ?? message.payload["message"] as? String ?? "Unknown error"
    if let requestKey = message.requestKey,
      let controlRequest = activeControlRequests.removeValue(forKey: requestKey)
    {
      log("AgentRuntimeProcess: control tool error (raw): \(raw)")
      controlRequest.continuation.resume(throwing: failure.map(BridgeError.agentRuntimeFailure) ?? BridgeError.agentError(raw))
      return
    }
    guard let requestKey = message.requestKey, let request = activeRequests.removeValue(forKey: requestKey) else {
      log("AgentRuntimeProcess: dropping unroutable error")
      return
    }
    log("AgentRuntimeProcess: agent error (raw): \(raw)")
    request.continuation.resume(throwing: failure.map(BridgeError.agentRuntimeFailure) ?? BridgeError.agentError(raw))
  }

  private func queryResult(from message: RuntimeMessage) -> AgentBridge.QueryResult {
    let payload = message.payload
    let omiSessionId = payload["sessionId"] as? String ?? ""
    let adapterSessionId = payload["adapterSessionId"] as? String
    return AgentBridge.QueryResult(
      text: payload["text"] as? String ?? "",
      costUsd: payload["costUsd"] as? Double ?? 0,
      omiSessionId: omiSessionId,
      runId: payload["runId"] as? String ?? "",
      attemptId: payload["attemptId"] as? String ?? "",
      adapterSessionId: adapterSessionId,
      terminalStatus: payload["terminalStatus"] as? String ?? "succeeded",
      inputTokens: payload["inputTokens"] as? Int ?? 0,
      outputTokens: payload["outputTokens"] as? Int ?? 0,
      cacheReadTokens: payload["cacheReadTokens"] as? Int ?? 0,
      cacheWriteTokens: payload["cacheWriteTokens"] as? Int ?? 0,
      artifacts: AgentArtifactProjection.parseList(
        fromJSONArray: payload["artifacts"] as? [[String: Any]] ?? []
      ),
      completionDeltaArtifacts: AgentArtifactProjection.parseList(
        fromJSONArray: payload["completionDeltaArtifacts"] as? [[String: Any]] ?? []
      )
    )
  }

  @discardableResult
  private func sendJson(_ dict: [String: Any]) -> Bool {
    guard let stdinPipe else { return false }
    do {
      let data = try JSONSerialization.data(withJSONObject: dict)
      guard let line = String(data: data, encoding: .utf8) else { return false }
      try stdinPipe.fileHandleForWriting.write(contentsOf: Data((line + "\n").utf8))
      return true
    } catch {
      log("AgentRuntimeProcess: failed to write stdin: \(error.localizedDescription)")
      return false
    }
  }

  private func currentOwnerId() -> String? {
    RuntimeOwnerIdentity.currentOwnerId()
  }

  private func handleTermination(
    exitCode: Int32 = -1,
    reason: Process.TerminationReason = .exit,
    generation: UInt64? = nil
  ) {
    if let generation, generation != processGeneration {
      log("AgentRuntimeProcess: ignoring stale termination (gen=\(generation), current=\(processGeneration))")
      return
    }

    if let stderrHandle = stderrPipe?.fileHandleForReading {
      stderrHandle.readabilityHandler = nil
      let remaining = stderrHandle.availableData
      if !remaining.isEmpty, let text = String(data: remaining, encoding: .utf8) {
        log("AgentRuntimeProcess stderr (final): \(text.trimmingCharacters(in: .whitespacesAndNewlines))")
        if Self.isConfirmedOutOfMemoryDiagnostic(text) {
          lastExitWasOOM = true
          oomDiagnosticLatch.markConfirmed(generation: processGeneration)
        }
      }
    }

    let likelyOOM = lastExitWasOOM || oomDiagnosticLatch.isConfirmed(generation: processGeneration)
    let error: BridgeError = likelyOOM ? .outOfMemory : .processExited
    lastExitWasOOM = false
    oomDiagnosticLatch.reset(generation: processGeneration)

    log(
      "AgentRuntimeProcess: process terminated "
        + "(failure_class=\(likelyOOM ? "out_of_memory" : "process_exited") "
        + "recovery_action=restart_on_next_send recovery_result=degraded code=\(exitCode))")
    DesktopDiagnosticsManager.shared.recordAgentRuntimeUnexpectedExit(
      exitCode: exitCode,
      oom: likelyOOM
    )
    log("AgentRuntimeProcess: process terminated (code=\(exitCode), error=\(error))")
    isRunning = false
    receivedInit = false
    advertisedAgentControlTools.removeAll()
    closePipes()
    cancelActiveToolTasks()
    resumeAllRequests(throwing: error)
    resumeInitContinuations(throwing: error)
  }

  private func resumeAllRequests(throwing error: Error) {
    cancelActiveToolTasks()
    let requests = activeRequests.values
    activeRequests.removeAll()
    for request in requests {
      request.continuation.resume(throwing: error)
    }
    let controlRequests = activeControlRequests.values
    activeControlRequests.removeAll()
    for request in controlRequests {
      request.continuation.resume(throwing: error)
    }
    let seedRequests = activeVoiceSeedRequests.values
    activeVoiceSeedRequests.removeAll()
    for request in seedRequests {
      request.continuation.resume(throwing: error)
    }
    let tailRequests = activeKernelTurnTailRequests.values
    activeKernelTurnTailRequests.removeAll()
    for request in tailRequests {
      request.continuation.resume(throwing: error)
    }
  }

  private func resumeInitContinuations(throwing error: Error) {
    let continuations = initContinuations
    initContinuations.removeAll()
    for continuation in continuations {
      continuation.resume(throwing: error)
    }
  }

  private func closePipes() {
    // Process is going away/reset — clear the suspend control so a pending resume
    // or auto-resume can't SIGCONT a reused pid.
    debugSuspend.disarm()
    if let stdinPipe {
      try? stdinPipe.fileHandleForWriting.close()
      try? stdinPipe.fileHandleForReading.close()
    }
    if let stdoutPipe {
      stdoutPipe.fileHandleForReading.readabilityHandler = nil
      try? stdoutPipe.fileHandleForReading.close()
      try? stdoutPipe.fileHandleForWriting.close()
    }
    if let stderrPipe {
      stderrPipe.fileHandleForReading.readabilityHandler = nil
      try? stderrPipe.fileHandleForReading.close()
      try? stderrPipe.fileHandleForWriting.close()
    }
    stdinPipe = nil
    stdoutPipe = nil
    stderrPipe = nil
    stdoutLineBuffer.removeAll(keepingCapacity: false)
    // Advance the generation so that any readability callback that already
    // captured the old generation is rejected by the generation guard in
    // processStdoutData(_:generation:) the moment it fires. Without this, a
    // callback that read an old init/result line can run during the awaits in
    // startProcess with the still-current generation and mutate stale state.
    processGeneration &+= 1
  }

  static func defaultStateDirectory(
    bundleIdentifier: String? = Bundle.main.bundleIdentifier,
    homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
  ) -> String {
    let bundleComponent = (bundleIdentifier?.isEmpty == false ? bundleIdentifier : "com.omi.desktop-dev")
      ?? "com.omi.desktop-dev"
    return homeDirectory
      .appendingPathComponent("Library")
      .appendingPathComponent("Application Support")
      .appendingPathComponent("Omi")
      .appendingPathComponent("AgentRuntime")
      .appendingPathComponent(bundleComponent)
      .path
  }

  static func defaultArtifactsDirectory(
    bundleIdentifier: String? = Bundle.main.bundleIdentifier,
    homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
  ) -> String {
    let bundleComponent = (bundleIdentifier?.isEmpty == false ? bundleIdentifier : "com.omi.desktop-dev")
      ?? "com.omi.desktop-dev"
    return homeDirectory
      .appendingPathComponent("Library")
      .appendingPathComponent("Application Support")
      .appendingPathComponent("Omi")
      .appendingPathComponent("Artifacts")
      .appendingPathComponent(bundleComponent)
      .path
  }

  private func findNodeBinary() -> String? {
    let bundledNode = Bundle.resourceBundle.path(forResource: "node", ofType: nil)
    if let bundledNode, FileManager.default.isExecutableFile(atPath: bundledNode) {
      return bundledNode
    }

    let candidates = [
      "/opt/homebrew/bin/node",
      "/usr/local/bin/node",
      "/usr/bin/node",
    ]
    for path in candidates where FileManager.default.isExecutableFile(atPath: path) {
      return path
    }

    let home = FileManager.default.homeDirectoryForCurrentUser.path
    let nvmDir = (home as NSString).appendingPathComponent(".nvm/versions/node")
    if let versions = try? FileManager.default.contentsOfDirectory(atPath: nvmDir) {
      let sorted = versions.sorted { lhs, rhs in
        lhs.compare(rhs, options: .numeric) == .orderedDescending
      }
      for version in sorted {
        let nodePath = (nvmDir as NSString).appendingPathComponent("\(version)/bin/node")
        if FileManager.default.isExecutableFile(atPath: nodePath) {
          return nodePath
        }
      }
    }

    let whichProcess = Process()
    whichProcess.executableURL = URL(fileURLWithPath: "/usr/bin/which")
    whichProcess.arguments = ["node"]
    let pipe = Pipe()
    whichProcess.standardOutput = pipe
    try? whichProcess.run()
    whichProcess.waitUntilExit()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    if let path = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
      !path.isEmpty,
      FileManager.default.isExecutableFile(atPath: path)
    {
      return path
    }

    return nil
  }

  private func findBridgeScript() -> String? {
    if let bundlePath = Bundle.main.resourcePath {
      let bundledScript = (bundlePath as NSString).appendingPathComponent("agent/dist/index.js")
      if FileManager.default.fileExists(atPath: bundledScript) {
        return bundledScript
      }
    }

    if let execDir = Bundle.main.executableURL?.deletingLastPathComponent() {
      let devPaths = [
        execDir.appendingPathComponent("../../../agent/dist/index.js").path,
        execDir.appendingPathComponent("../../../../agent/dist/index.js").path,
      ]
      for path in devPaths {
        let resolved = (path as NSString).standardizingPath
        if FileManager.default.fileExists(atPath: resolved) {
          return resolved
        }
      }
    }

    let cwdPath = FileManager.default.currentDirectoryPath
    let cwdCandidates = [
      "agent/dist/index.js",
      "desktop/agent/dist/index.js",
      "../desktop/agent/dist/index.js",
    ]
    for relativePath in cwdCandidates {
      let candidate = (cwdPath as NSString).appendingPathComponent(relativePath)
      let resolved = (candidate as NSString).standardizingPath
      if FileManager.default.fileExists(atPath: resolved) {
        return resolved
      }
    }

    return nil
  }
}

private final class AgentRuntimeOOMDiagnosticLatch: @unchecked Sendable {
  private let lock = NSLock()
  private var generation: UInt64?
  private var confirmed = false

  func reset(generation: UInt64) {
    lock.withLock {
      self.generation = generation
      confirmed = false
    }
  }

  func markIfConfirmed(_ text: String, generation: UInt64) {
    guard AgentRuntimeProcess.isConfirmedOutOfMemoryDiagnostic(text) else { return }
    markConfirmed(generation: generation)
  }

  func markConfirmed(generation: UInt64) {
    lock.withLock {
      guard self.generation == generation else { return }
      confirmed = true
    }
  }

  func isConfirmed(generation: UInt64) -> Bool {
    lock.withLock {
      self.generation == generation && confirmed
    }
  }
}
