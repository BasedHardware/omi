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
      case authorizedToolExecution
      case toolActivity
      case toolResultDisplay
      case result
      case error
      case authRequired
      case authSuccess
      case cancelAck
      case controlToolResult
      case journalOperationResult
      case journalTurnChanged
      case journalBackendSync
      case journalBackendDelete
      case journalBackendReconcile
      case defaultExecutionProfileConfigured
      case surfaceSessionResolved
      case sessionExecutionProfileMigrated
      case contextSourceUpdated
      case contextSnapshot
      case legacyMainChatSessionsImported
      case externalSurfaceRunBeginResult
      case externalSurfaceToolResult
      case externalSurfaceRunCompleteResult
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
      case "authorized_tool_execution": return .authorizedToolExecution
      case "tool_activity": return .toolActivity
      case "tool_result_display": return .toolResultDisplay
      case "result": return .result
      case "error": return .error
      case "auth_required": return .authRequired
      case "auth_success": return .authSuccess
      case "cancel_ack": return .cancelAck
      case "control_tool_result": return .controlToolResult
      case "journal_operation_result": return .journalOperationResult
      case "journal_turn_changed": return .journalTurnChanged
      case "journal_backend_sync": return .journalBackendSync
      case "journal_backend_delete": return .journalBackendDelete
      case "journal_backend_reconcile": return .journalBackendReconcile
      case "default_execution_profile_configured": return .defaultExecutionProfileConfigured
      case "surface_session_resolved": return .surfaceSessionResolved
      case "session_execution_profile_migrated": return .sessionExecutionProfileMigrated
      case "context_source_updated": return .contextSourceUpdated
      case "context_snapshot": return .contextSnapshot
      case "legacy_main_chat_sessions_imported": return .legacyMainChatSessionsImported
      case "external_surface_run_begin_result": return .externalSurfaceRunBeginResult
      case "external_surface_tool_result": return .externalSurfaceToolResult
      case "external_surface_run_complete_result": return .externalSurfaceRunCompleteResult
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
    let originatingUserText: String?
    let onTextDelta: AgentBridge.TextDeltaHandler
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

  private struct ActiveJournalRequest {
    let clientId: String
    let requestId: String
    let continuation: CheckedContinuation<JournalOperationResult, Error>
  }

  private struct ActiveKernelContractRequest {
    let clientId: String
    let requestId: String
    let expectedKind: RuntimeMessage.Kind
    let continuation: CheckedContinuation<[String: Any], Error>
  }

  struct JournalOperationResult: Sendable {
    let operation: String
    let conversationId: String
    let turn: KernelJournalTurn?
    let turns: [KernelJournalTurn]
    let clearedCount: Int
    let highWaterTurnSeq: Int
    let conversationGeneration: Int
    let generationBaseTurnSeq: Int
  }

  typealias JournalTurnChangedHandler = @Sendable (KernelJournalTurn) -> Void
  typealias AuthorizedRealtimeToolHandler =
    @Sendable (AuthorizedToolExecution) async -> AuthorizedRealtimeToolExecutionResult

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
  private var activeJournalRequests: [RuntimeMessage.RequestKey: ActiveJournalRequest] = [:]
  private var activeKernelContractRequests: [RuntimeMessage.RequestKey: ActiveKernelContractRequest] = [:]
  private var journalTurnChangedHandler: JournalTurnChangedHandler?
  private var authorizedRealtimeToolHandler: AuthorizedRealtimeToolHandler?
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
    for (requestKey, request) in activeControlRequests where request.clientId == clientId {
      activeControlRequests.removeValue(forKey: requestKey)
      request.continuation.resume(throwing: BridgeError.stopped)
    }
    for (requestKey, request) in activeJournalRequests where request.clientId == clientId {
      activeJournalRequests.removeValue(forKey: requestKey)
      request.continuation.resume(throwing: BridgeError.stopped)
    }
    for (requestKey, request) in activeKernelContractRequests where request.clientId == clientId {
      activeKernelContractRequests.removeValue(forKey: requestKey)
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

  func warmupSession(clientId: String, sessionId: String, profileGeneration: Int) {
    sendJson(Self.warmupWireMessage(
      clientId: clientId,
      requestId: UUID().uuidString,
      ownerId: currentOwnerId(),
      sessionId: sessionId,
      profileGeneration: profileGeneration
    ))
  }

  func configureDefaultExecutionProfile(
    clientId: String,
    adapterId: String,
    modelProfile: String?,
    workingDirectory: String,
    expectedPreferenceGeneration: Int?
  ) async throws -> AgentDefaultExecutionProfile {
    let payload = Self.configureDefaultExecutionProfileWireMessage(
      clientId: clientId,
      requestId: UUID().uuidString,
      ownerId: currentOwnerId(),
      adapterId: adapterId,
      modelProfile: modelProfile,
      workingDirectory: workingDirectory,
      expectedPreferenceGeneration: expectedPreferenceGeneration
    )
    let result = try await kernelContractRequest(
      payload: payload,
      expectedKind: .defaultExecutionProfileConfigured
    )
    guard let profile = AgentDefaultExecutionProfile(dictionary: result) else {
      throw BridgeError.agentError("Kernel returned an invalid default execution profile")
    }
    return profile
  }

  func resolveSurfaceSession(
    clientId: String,
    surface: AgentSurfaceReference,
    title: String?,
    creationProfile: AgentSessionCreationProfile?
  ) async throws -> AgentSurfaceSession {
    let payload = Self.resolveSurfaceSessionWireMessage(
      clientId: clientId,
      requestId: UUID().uuidString,
      ownerId: currentOwnerId(),
      surface: surface,
      title: title,
      creationProfile: creationProfile
    )
    let result = try await kernelContractRequest(payload: payload, expectedKind: .surfaceSessionResolved)
    guard let session = AgentSurfaceSession(dictionary: result) else {
      throw BridgeError.agentError("Kernel returned an invalid surface session")
    }
    return session
  }

  func migrateSessionExecutionProfile(
    clientId: String,
    sessionId: String,
    expectedProfileGeneration: Int,
    adapterId: String,
    modelProfile: String?,
    workingDirectory: String
  ) async throws -> AgentSessionProfileMigration {
    let payload = Self.migrateSessionExecutionProfileWireMessage(
      clientId: clientId,
      requestId: UUID().uuidString,
      ownerId: currentOwnerId(),
      sessionId: sessionId,
      expectedProfileGeneration: expectedProfileGeneration,
      adapterId: adapterId,
      modelProfile: modelProfile,
      workingDirectory: workingDirectory
    )
    let result = try await kernelContractRequest(
      payload: payload,
      expectedKind: .sessionExecutionProfileMigrated
    )
    guard let migration = AgentSessionProfileMigration(dictionary: result) else {
      throw BridgeError.agentError("Kernel returned an invalid session execution profile migration")
    }
    return migration
  }

  func updateContextSource(
    clientId: String,
    sessionId: String,
    surfaceKind: String,
    source: AgentContextSource,
    sourceRevision: String,
    outcome: AgentContextSourceOutcome,
    capturedAtMs: Int,
    expiresAtMs: Int?,
    payload: [String: Any]
  ) async throws -> AgentContextSourceUpdateReceipt {
    let message = Self.contextSourceUpdateWireMessage(
      clientId: clientId,
      requestId: UUID().uuidString,
      ownerId: currentOwnerId(),
      sessionId: sessionId,
      surfaceKind: surfaceKind,
      source: source,
      sourceRevision: sourceRevision,
      outcome: outcome,
      capturedAtMs: capturedAtMs,
      expiresAtMs: expiresAtMs,
      payload: payload
    )
    let result = try await kernelContractRequest(payload: message, expectedKind: .contextSourceUpdated)
    guard let receipt = AgentContextSourceUpdateReceipt(dictionary: result) else {
      throw BridgeError.agentError("Kernel returned an invalid context source receipt")
    }
    return receipt
  }

  func getContextSnapshot(
    clientId: String,
    sessionId: String,
    surfaceKind: String
  ) async throws -> AgentContextSnapshot {
    let message = Self.getContextSnapshotWireMessage(
      clientId: clientId,
      requestId: UUID().uuidString,
      ownerId: currentOwnerId(),
      sessionId: sessionId,
      surfaceKind: surfaceKind
    )
    let result = try await kernelContractRequest(payload: message, expectedKind: .contextSnapshot)
    guard
      let dictionary = result["snapshot"] as? [String: Any],
      let snapshot = AgentContextSnapshot(dictionary: dictionary)
    else {
      throw BridgeError.agentError("Kernel returned an invalid context snapshot")
    }
    return snapshot
  }

  func setAuthorizedRealtimeToolHandler(_ handler: AuthorizedRealtimeToolHandler?) {
    authorizedRealtimeToolHandler = handler
  }

  func beginExternalSurfaceRun(
    clientId: String,
    harnessMode: String,
    ownerID: String,
    sessionID: String,
    turnID: String,
    prompt: String,
    mode: ExternalSurfaceRunMode
  ) async throws -> ExternalSurfaceRunBinding {
    try assertCurrentExternalOwner(ownerID)
    try await registerClient(clientId: clientId, harnessMode: harnessMode)
    let requestId = UUID().uuidString
    let result = try await kernelContractRequest(
      payload: Self.externalSurfaceRunBeginWireMessage(
        clientId: clientId,
        requestId: requestId,
        ownerId: ownerID,
        sessionId: sessionID,
        turnId: turnID,
        prompt: prompt,
        mode: mode
      ),
      expectedKind: .externalSurfaceRunBeginResult,
      timeoutNanoseconds: 10_000_000_000
    )
    guard result["ok"] as? Bool == true else {
      throw ExternalSurfaceAuthorityError.from(
        result, fallback: "external_surface_begin_failed")
    }
    guard
      result["ownerId"] as? String == ownerID,
      result["sessionId"] as? String == sessionID,
      result["turnId"] as? String == turnID,
      let runID = result["runId"] as? String,
      !runID.isEmpty,
      let attemptID = result["attemptId"] as? String,
      !attemptID.isEmpty
    else {
      throw ExternalSurfaceAuthorityError(code: "malformed_external_surface_begin_result")
    }
    return ExternalSurfaceRunBinding(
      ownerID: ownerID,
      sessionID: sessionID,
      turnID: turnID,
      runID: runID,
      attemptID: attemptID,
      duplicate: result["duplicate"] as? Bool ?? false
    )
  }

  func invokeExternalSurfaceTool(
    clientId: String,
    harnessMode: String,
    binding: ExternalSurfaceRunBinding,
    invocationID: String,
    toolName: String,
    input: [String: Any]
  ) async throws -> String {
    try assertCurrentExternalOwner(binding.ownerID)
    try await registerClient(clientId: clientId, harnessMode: harnessMode)
    let requestId = UUID().uuidString
    let result = try await kernelContractRequest(
      payload: Self.externalSurfaceToolInvokeWireMessage(
        clientId: clientId,
        requestId: requestId,
        binding: binding,
        invocationId: invocationID,
        toolName: toolName,
        input: input
      ),
      expectedKind: .externalSurfaceToolResult,
      timeoutNanoseconds: 180_000_000_000
    )
    guard result["ok"] as? Bool == true else {
      throw ExternalSurfaceAuthorityError.from(
        result, fallback: "external_surface_tool_failed")
    }
    guard
      result["ownerId"] as? String == binding.ownerID,
      result["sessionId"] as? String == binding.sessionID,
      result["runId"] as? String == binding.runID,
      result["attemptId"] as? String == binding.attemptID,
      result["invocationId"] as? String == invocationID,
      let output = result["result"] as? String
    else {
      throw ExternalSurfaceAuthorityError(code: "malformed_external_surface_tool_result")
    }
    return output
  }

  func completeExternalSurfaceRun(
    clientId: String,
    harnessMode: String,
    binding: ExternalSurfaceRunBinding,
    terminalStatus: ExternalSurfaceRunTerminalStatus,
    errorCode: String? = nil
  ) async throws -> ExternalSurfaceRunCompletion {
    try assertCurrentExternalOwner(binding.ownerID)
    try await registerClient(clientId: clientId, harnessMode: harnessMode)
    let requestId = UUID().uuidString
    let result = try await kernelContractRequest(
      payload: Self.externalSurfaceRunCompleteWireMessage(
        clientId: clientId,
        requestId: requestId,
        binding: binding,
        terminalStatus: terminalStatus,
        errorCode: errorCode
      ),
      expectedKind: .externalSurfaceRunCompleteResult,
      timeoutNanoseconds: 10_000_000_000
    )
    guard result["ok"] as? Bool == true else {
      throw ExternalSurfaceAuthorityError.from(
        result, fallback: "external_surface_complete_failed")
    }
    guard
      result["ownerId"] as? String == binding.ownerID,
      result["sessionId"] as? String == binding.sessionID,
      result["runId"] as? String == binding.runID,
      result["attemptId"] as? String == binding.attemptID,
      let rawTerminalStatus = result["terminalStatus"] as? String,
      let confirmedStatus = ExternalSurfaceRunTerminalStatus(rawValue: rawTerminalStatus),
      confirmedStatus == terminalStatus
    else {
      throw ExternalSurfaceAuthorityError(code: "malformed_external_surface_complete_result")
    }
    return ExternalSurfaceRunCompletion(
      runID: binding.runID,
      attemptID: binding.attemptID,
      terminalStatus: confirmedStatus,
      duplicate: result["duplicate"] as? Bool ?? false
    )
  }

  private func assertCurrentExternalOwner(_ ownerID: String) throws {
    guard !ownerID.isEmpty, currentOwnerId() == ownerID else {
      throw ExternalSurfaceAuthorityError(code: "external_surface_owner_changed")
    }
  }

  static func warmupWireMessage(
    clientId: String,
    requestId: String,
    ownerId: String?,
    sessionId: String,
    profileGeneration: Int
  ) -> [String: Any] {
    var message = protocolEnvelope(
      type: "warmup",
      clientId: clientId,
      requestId: requestId,
      ownerId: ownerId
    )
    message["sessionId"] = sessionId
    message["profileGeneration"] = profileGeneration
    return message
  }

  static func configureDefaultExecutionProfileWireMessage(
    clientId: String,
    requestId: String,
    ownerId: String?,
    adapterId: String,
    modelProfile: String?,
    workingDirectory: String,
    expectedPreferenceGeneration: Int?
  ) -> [String: Any] {
    var message = protocolEnvelope(
      type: "configure_default_execution_profile",
      clientId: clientId,
      requestId: requestId,
      ownerId: ownerId
    )
    message["adapterId"] = adapterId
    message["modelProfile"] = modelProfile ?? NSNull()
    message["workingDirectory"] = workingDirectory
    if let expectedPreferenceGeneration {
      message["expectedPreferenceGeneration"] = expectedPreferenceGeneration
    }
    return message
  }

  static func resolveSurfaceSessionWireMessage(
    clientId: String,
    requestId: String,
    ownerId: String?,
    surface: AgentSurfaceReference,
    title: String?,
    creationProfile: AgentSessionCreationProfile? = nil
  ) -> [String: Any] {
    var message = protocolEnvelope(
      type: "resolve_surface_session",
      clientId: clientId,
      requestId: requestId,
      ownerId: ownerId
    )
    message["surfaceKind"] = surface.surfaceKind
    message["externalRefKind"] = surface.externalRefKind
    message["externalRefId"] = surface.externalRefId
    if let title { message["title"] = title }
    if let creationProfile { message["creationProfile"] = creationProfile.dictionary }
    return message
  }

  static func migrateSessionExecutionProfileWireMessage(
    clientId: String,
    requestId: String,
    ownerId: String?,
    sessionId: String,
    expectedProfileGeneration: Int,
    adapterId: String,
    modelProfile: String?,
    workingDirectory: String
  ) -> [String: Any] {
    var message = protocolEnvelope(
      type: "migrate_session_execution_profile",
      clientId: clientId,
      requestId: requestId,
      ownerId: ownerId
    )
    message["sessionId"] = sessionId
    message["expectedProfileGeneration"] = expectedProfileGeneration
    message["adapterId"] = adapterId
    message["modelProfile"] = modelProfile ?? NSNull()
    message["workingDirectory"] = workingDirectory
    message["reason"] = "user_requested"
    return message
  }

  static func contextSourceUpdateWireMessage(
    clientId: String,
    requestId: String,
    ownerId: String?,
    sessionId: String,
    surfaceKind: String,
    source: AgentContextSource,
    sourceRevision: String,
    outcome: AgentContextSourceOutcome,
    capturedAtMs: Int,
    expiresAtMs: Int?,
    payload: [String: Any]
  ) -> [String: Any] {
    var message = protocolEnvelope(
      type: "context_source_update",
      clientId: clientId,
      requestId: requestId,
      ownerId: ownerId
    )
    message["sessionId"] = sessionId
    message["surfaceKind"] = surfaceKind
    message["source"] = source.rawValue
    message["sourceRevision"] = sourceRevision
    message["outcome"] = outcome.rawValue
    message["capturedAtMs"] = capturedAtMs
    if let expiresAtMs { message["expiresAtMs"] = expiresAtMs }
    message["payload"] = payload
    return message
  }

  static func getContextSnapshotWireMessage(
    clientId: String,
    requestId: String,
    ownerId: String?,
    sessionId: String,
    surfaceKind: String
  ) -> [String: Any] {
    var message = protocolEnvelope(
      type: "get_context_snapshot",
      clientId: clientId,
      requestId: requestId,
      ownerId: ownerId
    )
    message["sessionId"] = sessionId
    message["surfaceKind"] = surfaceKind
    return message
  }

  static func importLegacyMainChatSessionsWireMessage(
    clientId: String,
    requestId: String,
    ownerId: String,
    entries: [LegacyMainChatSessionAliasEntry]
  ) -> [String: Any] {
    var message = protocolEnvelope(
      type: "import_legacy_main_chat_sessions",
      clientId: clientId,
      requestId: requestId,
      ownerId: ownerId
    )
    message["entries"] = entries.map(\.dictionary)
    return message
  }

  static func externalSurfaceRunBeginWireMessage(
    clientId: String,
    requestId: String,
    ownerId: String,
    sessionId: String,
    turnId: String,
    prompt: String,
    mode: ExternalSurfaceRunMode
  ) -> [String: Any] {
    var message = protocolEnvelope(
      type: "external_surface_run_begin",
      clientId: clientId,
      requestId: requestId,
      ownerId: ownerId
    )
    message["sessionId"] = sessionId
    message["turnId"] = turnId
    message["prompt"] = prompt
    message["mode"] = mode.rawValue
    return message
  }

  static func externalSurfaceToolInvokeWireMessage(
    clientId: String,
    requestId: String,
    binding: ExternalSurfaceRunBinding,
    invocationId: String,
    toolName: String,
    input: [String: Any]
  ) -> [String: Any] {
    var message = protocolEnvelope(
      type: "external_surface_tool_invoke",
      clientId: clientId,
      requestId: requestId,
      ownerId: binding.ownerID
    )
    message["sessionId"] = binding.sessionID
    message["runId"] = binding.runID
    message["attemptId"] = binding.attemptID
    message["invocationId"] = invocationId
    message["toolName"] = toolName
    message["input"] = input
    return message
  }

  static func externalSurfaceRunCompleteWireMessage(
    clientId: String,
    requestId: String,
    binding: ExternalSurfaceRunBinding,
    terminalStatus: ExternalSurfaceRunTerminalStatus,
    errorCode: String?
  ) -> [String: Any] {
    var message = protocolEnvelope(
      type: "external_surface_run_complete",
      clientId: clientId,
      requestId: requestId,
      ownerId: binding.ownerID
    )
    message["sessionId"] = binding.sessionID
    message["runId"] = binding.runID
    message["attemptId"] = binding.attemptID
    message["terminalStatus"] = terminalStatus.rawValue
    if let errorCode, !errorCode.isEmpty { message["errorCode"] = errorCode }
    return message
  }

  static func queryWireMessage(
    clientId: String,
    requestId: String,
    ownerId: String?,
    sessionId: String,
    prompt: String,
    mode: String?,
    imageData: Data?,
    attachments: [AgentQueryAttachment],
    expectedContext: AgentContextFreshness?
  ) -> [String: Any] {
    var message = protocolEnvelope(
      type: "query",
      clientId: clientId,
      requestId: requestId,
      ownerId: ownerId
    )
    message["sessionId"] = sessionId
    message["prompt"] = prompt
    if let mode { message["mode"] = mode }
    if let imageData { message["imageBase64"] = imageData.base64EncodedString() }
    if !attachments.isEmpty { message["attachments"] = attachments.map(\.dictionary) }
    if let expectedContext {
      message["expectedContextSnapshotVersion"] = expectedContext.version
      message["expectedContextSnapshotGeneration"] = expectedContext.generation
    }
    return message
  }

  private static func protocolEnvelope(
    type: String,
    clientId: String,
    requestId: String,
    ownerId: String?
  ) -> [String: Any] {
    var message: [String: Any] = [
      "type": type,
      "protocolVersion": 2,
      "requestId": requestId,
      "clientId": clientId,
    ]
    if let ownerId { message["ownerId"] = ownerId }
    return message
  }

  private func kernelContractRequest(
    payload: [String: Any],
    expectedKind: RuntimeMessage.Kind,
    timeoutNanoseconds: UInt64 = 5_000_000_000
  ) async throws -> [String: Any] {
    guard isRunning else { throw BridgeError.stopped }
    guard
      let clientId = payload["clientId"] as? String,
      let requestId = payload["requestId"] as? String
    else {
      throw BridgeError.agentError("Kernel contract request is missing tracing identity")
    }
    let requestKey = RuntimeMessage.RequestKey(clientId: clientId, requestId: requestId)
    return try await withCheckedThrowingContinuation { continuation in
      activeKernelContractRequests[requestKey] = ActiveKernelContractRequest(
        clientId: clientId,
        requestId: requestId,
        expectedKind: expectedKind,
        continuation: continuation
      )
      guard sendJson(payload) else {
        activeKernelContractRequests.removeValue(forKey: requestKey)?.continuation.resume(
          throwing: BridgeError.processExited
        )
        return
      }
      Task {
        try? await Task.sleep(nanoseconds: timeoutNanoseconds)
        guard let request = self.activeKernelContractRequests.removeValue(forKey: requestKey) else { return }
        request.continuation.resume(throwing: BridgeError.timeout)
      }
    }
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

  // Startup-only reader for pre-kernel session aliases; it never writes turns or
  // participates in runtime routing after canonical surface identity exists.
  func importLegacyMainChatSessions(
    clientId: String,
    entries: [LegacyMainChatSessionAliasEntry]
  ) async throws -> LegacyMainChatSessionImportReceipt {
    guard let ownerId = currentOwnerId(), !ownerId.isEmpty else {
      throw BridgeError.authMissing
    }
    let payload = Self.importLegacyMainChatSessionsWireMessage(
      clientId: clientId,
      requestId: UUID().uuidString,
      ownerId: ownerId,
      entries: entries
    )
    let result = try await kernelContractRequest(
      payload: payload,
      expectedKind: .legacyMainChatSessionsImported
    )
    guard
      let receipt = LegacyMainChatSessionImportReceipt(dictionary: result),
      receipt.ownerId == ownerId,
      receipt.acceptedEntries == entries
    else {
      throw BridgeError.agentError("Kernel returned an invalid legacy main-chat alias receipt")
    }
    return receipt
  }

  func setJournalTurnChangedHandler(_ handler: JournalTurnChangedHandler?) {
    journalTurnChangedHandler = handler
  }

  func journalTurnChangedHandlerCount() -> Int {
    journalTurnChangedHandler == nil ? 0 : 1
  }

  /// Test-only projection seam; production events arrive from omi-agentd.
  func dispatchJournalTurnChangedForTesting(_ turn: KernelJournalTurn) {
    journalTurnChangedHandler?(turn)
  }

  func recordJournalTurn(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    turn: KernelJournalTurnWrite
  ) async throws -> KernelJournalTurn {
    let result = try await journalOperation(
      type: "journal_record_turn",
      operation: "record",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: ["turn": turn.dictionary]
    )
    guard let recorded = result.turn else {
      throw BridgeError.agentError("Kernel journal record returned no turn")
    }
    return recorded
  }

  func updateJournalTurn(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    update: KernelJournalTurnUpdate
  ) async throws -> KernelJournalTurn {
    let result = try await journalOperation(
      type: "journal_update_turn",
      operation: "update",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: ["update": update.dictionary]
    )
    guard let updated = result.turn else {
      throw BridgeError.agentError("Kernel journal update returned no turn")
    }
    return updated
  }

  func listJournalTurns(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    afterTurnSeq: Int = 0,
    limit: Int = 100
  ) async throws -> JournalOperationResult {
    return try await journalOperation(
      type: "journal_list_turns",
      operation: "list",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: [
        "afterTurnSeq": max(0, afterTurnSeq),
        "limit": max(1, min(limit, 100)),
      ]
    )
  }

  func importRemoteJournalTurn(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    turn: KernelJournalRemoteTurn
  ) async throws -> KernelJournalTurn {
    let result = try await journalOperation(
      type: "journal_import_remote_turn",
      operation: "import_remote",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: ["turn": turn.dictionary]
    )
    guard let imported = result.turn else {
      throw BridgeError.agentError("Kernel journal import returned no turn")
    }
    return imported
  }

  func clearJournalTurns(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    expectedGeneration: Int? = nil
  ) async throws -> Int {
    var payload: [String: Any] = [:]
    if let expectedGeneration { payload["expectedGeneration"] = expectedGeneration }
    return try await journalOperation(
      type: "journal_clear_turns",
      operation: "clear",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: payload
    ).clearedCount
  }

  private func journalOperation(
    type: String,
    operation: String,
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String?,
    payload: [String: Any]
  ) async throws -> JournalOperationResult {
    guard isRunning else { throw BridgeError.stopped }
    let requestId = UUID().uuidString
    let requestKey = RuntimeMessage.RequestKey(clientId: clientId, requestId: requestId)
    var dictionary: [String: Any] = [
      "type": type,
      "operation": operation,
      "protocolVersion": 2,
      "requestId": requestId,
      "clientId": clientId,
      "surfaceKind": surface.surfaceKind,
      "externalRefKind": surface.externalRefKind,
      "externalRefId": surface.externalRefId,
    ]
    if let ownerId = ownerID ?? currentOwnerId() { dictionary["ownerId"] = ownerId }
    for (key, value) in payload { dictionary[key] = value }
    return try await withCheckedThrowingContinuation { continuation in
      activeJournalRequests[requestKey] = ActiveJournalRequest(
        clientId: clientId,
        requestId: requestId,
        continuation: continuation
      )
      guard sendJson(dictionary) else {
        activeJournalRequests.removeValue(forKey: requestKey)?.continuation.resume(
          throwing: BridgeError.processExited
        )
        return
      }
      Task {
        try? await Task.sleep(nanoseconds: 5_000_000_000)
        guard let request = self.activeJournalRequests.removeValue(forKey: requestKey) else { return }
        request.continuation.resume(throwing: BridgeError.timeout)
      }
    }
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
    return try await sendDirectControlTool(
      clientId: clientId,
      harnessMode: harnessMode,
      name: name,
      input: input,
      ownerId: ownerId
    )
  }

#if DEBUG
  func debugAutomationControlTool(
    clientId: String,
    harnessMode: String,
    name: String,
    input: [String: Any],
    ownerId: String
  ) async throws -> String {
    guard AppBuild.isNonProduction else {
      throw BridgeError.agentError("Automation control is disabled on production bundles")
    }
    return try await sendDirectControlTool(
      clientId: clientId,
      harnessMode: harnessMode,
      name: name,
      input: input,
      ownerId: ownerId
    )
  }
#endif

  private func sendDirectControlTool(
    clientId: String,
    harnessMode: String,
    name: String,
    input: [String: Any],
    ownerId: String
  ) async throws -> String {
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
    sessionId: String,
    prompt: String,
    surface: AgentSurfaceReference,
    mode: String?,
    imageData: Data?,
    attachments: [AgentQueryAttachment],
    expectedContext: AgentContextFreshness?,
    onTextDelta: @escaping AgentBridge.TextDeltaHandler,
    onToolActivity: @escaping AgentBridge.ToolActivityHandler,
    onThinkingDelta: @escaping AgentBridge.ThinkingDeltaHandler,
    onToolResultDisplay: @escaping AgentBridge.ToolResultDisplayHandler,
    onAuthRequired: @escaping AgentBridge.AuthRequiredHandler,
    onAuthSuccess: @escaping AgentBridge.AuthSuccessHandler
  ) async throws -> AgentBridge.QueryResult {
    guard isRunning else { throw BridgeError.stopped }

    return try await withCheckedThrowingContinuation { continuation in
      let surfaceRef = surface
      let request = ActiveRequest(
        clientId: clientId,
        requestId: requestId,
        surfaceRef: surfaceRef,
        originatingUserText: prompt.trimmingCharacters(in: .whitespacesAndNewlines),
        onTextDelta: onTextDelta,
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

      let queryDict = Self.queryWireMessage(
        clientId: clientId,
        requestId: requestId,
        ownerId: currentOwnerId(),
        sessionId: sessionId,
        prompt: prompt,
        mode: mode,
        imageData: imageData,
        attachments: attachments,
        expectedContext: expectedContext
      )
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
#if DEBUG
    if AppBuild.isNonProduction {
      env["OMI_AGENT_ALLOW_CONTROL_ONLY"] = "1"
    }
#endif
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
    } else if preferredAdapterId == .piMono && env["OMI_AGENT_ALLOW_CONTROL_ONLY"] != "1" {
      log("AgentRuntimeProcess: pi-mono start refused, Firebase ID token is missing")
      throw BridgeError.authMissing
    } else if preferredAdapterId == .piMono {
      log("AgentRuntimeProcess: starting non-production control-only runtime without Firebase auth")
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
      // Adapter-facing tool lifecycle is projected through tool_activity. A
      // raw tool_use event has no physical execution authority in Swift.
      break

    case .authorizedToolExecution:
      handleAuthorizedToolExecution(message)

    case .cancelAck:
      if let requestKey = message.requestKey, var request = activeRequests[requestKey] {
        request.cancelAck = message
        activeRequests[requestKey] = request
      }

    case .controlToolResult:
      completeControlRequest(message)

    case .journalOperationResult:
      completeJournalRequest(message)

    case .journalTurnChanged:
      if let turn = journalTurn(from: message) {
        journalTurnChangedHandler?(turn)
      }

    case .journalBackendSync:
      handleJournalBackendSync(message)

    case .journalBackendDelete:
      handleJournalBackendDelete(message)

    case .journalBackendReconcile:
      handleJournalBackendReconcile(message)

    case .defaultExecutionProfileConfigured, .surfaceSessionResolved,
      .sessionExecutionProfileMigrated, .contextSourceUpdated, .contextSnapshot,
      .legacyMainChatSessionsImported,
      .externalSurfaceRunBeginResult, .externalSurfaceToolResult,
      .externalSurfaceRunCompleteResult:
      completeKernelContractRequest(message)

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

  private func completeKernelContractRequest(_ message: RuntimeMessage) {
    guard let requestKey = message.requestKey,
      let request = activeKernelContractRequests.removeValue(forKey: requestKey)
    else {
      log("AgentRuntimeProcess: dropping unroutable kernel contract response")
      return
    }
    guard request.expectedKind == message.kind else {
      request.continuation.resume(
        throwing: BridgeError.agentError("Kernel contract response type did not match its request")
      )
      return
    }
    request.continuation.resume(returning: message.payload)
  }

  private func handleAuthorizedToolExecution(_ message: RuntimeMessage) {
    let command: AuthorizedToolExecution
    do {
      command = try AuthorizedToolExecution.parse(
        message.payload,
        currentOwnerID: currentOwnerId())
    } catch let rejection as AuthorizedToolExecution.Rejection {
      log("AgentRuntimeProcess: rejecting physical tool command (\(rejection.code))")
      completeAuthorizedToolExecution(
        payload: message.payload,
        outcome: "failed",
        result: Self.authorizedToolExecutionError(rejection))
      return
    } catch {
      log("AgentRuntimeProcess: rejecting physical tool command (malformed_authorized_execution)")
      completeAuthorizedToolExecution(
        payload: message.payload,
        outcome: "failed",
        result: Self.authorizedToolExecutionError(.malformed))
      return
    }

    Task {
      let executionResult: AuthorizedRealtimeToolExecutionResult
      switch command.executor {
      case .chatToolExecutor:
        let surface = AgentSurfaceReference(
          surfaceKind: command.surfaceKind,
          externalRefKind: command.externalRefKind ?? "session",
          externalRefId: command.externalRefID ?? command.sessionID)
        let toolCall = ToolCall(
          name: command.canonicalToolName,
          arguments: command.input,
          thoughtSignature: nil)
        let result = await ChatToolExecutor.execute(
          toolCall,
          originatingChatMode: ChatMode(rawValue: command.runMode),
          originatingClientScope: command.surfaceKind == "floating_bar"
            && command.externalRefKind == "pill"
            ? AgentClientScope.floatingPill
            : nil,
          originatingSurfaceRef: surface,
          originatingRunId: command.runID,
          originatingUserText: command.originatingUserText,
          isOnboardingSurface: command.surfaceKind == "onboarding",
          expectedOwnerID: command.ownerID)
        if AuthorizedToolExecution.isOwnerCurrent(command.ownerID) {
          executionResult = .succeeded(result)
        } else {
          executionResult = .failed(
            Self.authorizedToolExecutionError(.ownerChangedDuringExecution))
        }
      case .realtimeHub:
        guard let handler = authorizedRealtimeToolHandler else {
          completeAuthorizedToolExecution(
            command: command,
            executionResult: .failed(
              Self.authorizedToolExecutionError(.unsupportedExecutor)))
          return
        }
        executionResult = await handler(command)
      }
      guard AuthorizedToolExecution.isOwnerCurrent(command.ownerID) else {
        completeAuthorizedToolExecution(
          command: command,
          executionResult: .failed(
            Self.authorizedToolExecutionError(.ownerChangedDuringExecution)))
        return
      }
      if command.policyRecovery == .permissionDelegationToNative,
        case .succeeded = executionResult
      {
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "other",
          from: "spawn_agent",
          to: command.canonicalToolName,
          reason: "other",
          outcome: .recovered)
      }
      completeAuthorizedToolExecution(
        command: command,
        executionResult: executionResult)
    }
  }

  private static func authorizedToolExecutionError(
    _ rejection: AuthorizedToolExecution.Rejection
  ) -> String {
    let payload: [String: Any] = [
      "ok": false,
      "error": [
        "code": rejection.code,
        "message": "The authorized physical tool command was rejected.",
      ],
    ]
    guard
      let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
      let text = String(data: data, encoding: .utf8)
    else {
      return #"{"ok":false,"error":{"code":"malformed_authorized_execution"}}"#
    }
    return text
  }

  private func completeAuthorizedToolExecution(
    command: AuthorizedToolExecution,
    executionResult: AuthorizedRealtimeToolExecutionResult
  ) {
    sendJson(Self.authorizedToolExecutionResultWireMessage(
      command: command,
      executionResult: executionResult))
  }

  static func authorizedToolExecutionResultWireMessage(
    command: AuthorizedToolExecution,
    executionResult: AuthorizedRealtimeToolExecutionResult
  ) -> [String: Any] {
    [
      "type": "authorized_tool_execution_result",
      "protocolVersion": 2,
      "invocationId": command.invocationID,
      "ownerId": command.ownerID,
      "sessionId": command.sessionID,
      "runId": command.runID,
      "attemptId": command.attemptID,
      "profileGeneration": command.profileGeneration,
      "manifestVersion": command.manifestVersion,
      "manifestDigest": command.manifestDigest,
      "daemonBootEpoch": command.daemonBootEpoch,
      "executionGeneration": command.executionGeneration,
      "inputHash": command.inputHash,
      "outcome": executionResult.wireOutcome,
      "result": executionResult.wireResult,
    ]
  }

  /// Best-effort failure result for malformed envelopes. Node only accepts it
  /// when every echoed ledger identity matches, otherwise the dispatched row
  /// safely reconciles to outcome_unknown on timeout/restart.
  private func completeAuthorizedToolExecution(
    payload: [String: Any],
    outcome: String,
    result: String
  ) {
    sendJson([
      "type": "authorized_tool_execution_result",
      "protocolVersion": 2,
      "invocationId": payload["invocationId"] as? String ?? "",
      "ownerId": payload["ownerId"] as? String ?? "",
      "sessionId": payload["sessionId"] as? String ?? "",
      "runId": payload["runId"] as? String ?? "",
      "attemptId": payload["attemptId"] as? String ?? "",
      "profileGeneration": payload["profileGeneration"] as? Int ?? 0,
      "manifestVersion": payload["manifestVersion"] as? Int ?? 0,
      "manifestDigest": payload["manifestDigest"] as? String ?? "",
      "daemonBootEpoch": payload["daemonBootEpoch"] as? String ?? "",
      "executionGeneration": payload["executionGeneration"] as? Int ?? 0,
      "inputHash": payload["inputHash"] as? String ?? "",
      "outcome": outcome,
      "result": result,
    ])
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

  private func completeJournalRequest(_ message: RuntimeMessage) {
    guard let requestKey = message.requestKey,
      let request = activeJournalRequests.removeValue(forKey: requestKey)
    else {
      log("AgentRuntimeProcess: dropping unroutable journal result")
      return
    }
    guard message.payload["ok"] as? Bool != false else {
      let code = message.payload["errorCode"] as? String ?? "journal_operation_failed"
      request.continuation.resume(throwing: BridgeError.agentError(code))
      return
    }
    let surface = AgentSurfaceReference(
      surfaceKind: message.payload["surfaceKind"] as? String ?? "",
      externalRefKind: message.payload["externalRefKind"] as? String ?? "",
      externalRefId: message.payload["externalRefId"] as? String ?? ""
    )
    let conversationGeneration = message.payload["conversationGeneration"] as? Int ?? 1
    let wrapperGenerationBase = message.payload["generationBaseTurnSeq"] as? Int ?? 0
    let turn = (message.payload["turn"] as? [String: Any]).flatMap {
      KernelJournalTurn(
        dictionary: $0,
        surfaceFallback: surface,
        conversationGenerationFallback: conversationGeneration,
        generationBaseTurnSeqFallback: wrapperGenerationBase
      )
    }
    let turns = (message.payload["turns"] as? [[String: Any]] ?? []).compactMap {
      KernelJournalTurn(
        dictionary: $0,
        surfaceFallback: surface,
        conversationGenerationFallback: conversationGeneration,
        generationBaseTurnSeqFallback: wrapperGenerationBase
      )
    }
    let highWaterTurnSeq = message.payload["highWaterTurnSeq"] as? Int ?? 0
    let generationBaseTurnSeq = message.payload["generationBaseTurnSeq"] as? Int
      ?? turns.map(\.turnSeq).min().map { max(0, $0 - 1) }
      ?? (conversationGeneration > 1 ? highWaterTurnSeq : 0)
    request.continuation.resume(returning: JournalOperationResult(
      operation: message.payload["operation"] as? String ?? "",
      conversationId: message.payload["conversationId"] as? String ?? turn?.conversationId ?? turns.first?.conversationId ?? "",
      turn: turn,
      turns: turns,
      clearedCount: message.payload["clearedCount"] as? Int ?? 0,
      highWaterTurnSeq: highWaterTurnSeq,
      conversationGeneration: conversationGeneration,
      generationBaseTurnSeq: generationBaseTurnSeq
    ))
  }

  private func journalTurn(from message: RuntimeMessage) -> KernelJournalTurn? {
    guard let dictionary = message.payload["turn"] as? [String: Any] else { return nil }
    let surface = AgentSurfaceReference(
      surfaceKind: message.payload["surfaceKind"] as? String ?? "",
      externalRefKind: message.payload["externalRefKind"] as? String ?? "",
      externalRefId: message.payload["externalRefId"] as? String ?? ""
    )
    return KernelJournalTurn(
      dictionary: dictionary,
      surfaceFallback: surface,
      conversationGenerationFallback: message.payload["conversationGeneration"] as? Int ?? 1,
      generationBaseTurnSeqFallback: message.payload["generationBaseTurnSeq"] as? Int ?? 0
    )
  }

  private func handleJournalBackendSync(_ message: RuntimeMessage) {
    guard let request = KernelJournalBackendSyncDriver.Request(payload: message.payload) else {
      sendJournalBackendSyncResult(
        requestId: message.requestId,
        clientId: message.clientId,
        ownerId: message.payload["ownerId"] as? String,
        turnId: message.payload["turnId"] as? String ?? "",
        conversationId: message.payload["conversationId"] as? String,
        conversationGeneration: message.payload["conversationGeneration"] as? Int,
        attemptCount: message.payload["attemptCount"] as? Int,
        deliveryGeneration: message.payload["deliveryGeneration"] as? Int,
        payloadHash: message.payload["payloadHash"] as? String,
        remoteId: nil,
        errorCode: "malformed_backend_sync_request"
      )
      return
    }
    Task { [weak self] in
      do {
        let receipt = try await KernelJournalBackendSyncDriver.shared.sync(request)
        await self?.sendJournalBackendSyncResult(
          requestId: message.requestId,
          clientId: message.clientId,
          ownerId: request.ownerId,
          turnId: receipt.turnId,
          conversationId: request.conversationId,
          conversationGeneration: request.conversationGeneration,
          attemptCount: request.attemptCount,
          deliveryGeneration: request.deliveryGeneration,
          payloadHash: request.payloadHash,
          remoteId: receipt.remoteId,
          errorCode: nil
        )
      } catch {
        await self?.sendJournalBackendSyncResult(
          requestId: message.requestId,
          clientId: message.clientId,
          ownerId: request.ownerId,
          turnId: request.turnId,
          conversationId: request.conversationId,
          conversationGeneration: request.conversationGeneration,
          attemptCount: request.attemptCount,
          deliveryGeneration: request.deliveryGeneration,
          payloadHash: request.payloadHash,
          remoteId: nil,
          errorCode: KernelJournalBackendSyncDriver.boundedErrorCode(for: error)
        )
      }
    }
  }

  private func sendJournalBackendSyncResult(
    requestId: String?,
    clientId: String?,
    ownerId: String?,
    turnId: String,
    conversationId: String?,
    conversationGeneration: Int?,
    attemptCount: Int?,
    deliveryGeneration: Int?,
    payloadHash: String?,
    remoteId: String?,
    errorCode: String?
  ) {
    var payload: [String: Any] = [
      "type": "journal_backend_sync_result",
      "protocolVersion": 2,
      "turnId": turnId,
      "ok": remoteId != nil,
    ]
    if let requestId { payload["requestId"] = requestId }
    if let clientId { payload["clientId"] = clientId }
    if let ownerId { payload["ownerId"] = ownerId }
    if let conversationId { payload["conversationId"] = conversationId }
    if let conversationGeneration { payload["conversationGeneration"] = conversationGeneration }
    if let attemptCount { payload["attemptCount"] = attemptCount }
    if let deliveryGeneration { payload["deliveryGeneration"] = deliveryGeneration }
    if let payloadHash { payload["payloadHash"] = payloadHash }
    if let remoteId { payload["remoteId"] = remoteId }
    if let errorCode { payload["errorCode"] = errorCode }
    sendJson(payload)
  }

  private func handleJournalBackendDelete(_ message: RuntimeMessage) {
    guard let request = KernelJournalBackendSyncDriver.DeleteRequest(payload: message.payload) else {
      sendJournalBackendDeleteResult(
        requestId: message.requestId,
        clientId: message.clientId,
        ownerId: message.payload["ownerId"] as? String,
        operationId: message.payload["operationId"] as? String ?? "",
        conversationId: message.payload["conversationId"] as? String,
        conversationGeneration: message.payload["conversationGeneration"] as? Int,
        attemptCount: message.payload["attemptCount"] as? Int,
        deliveryGeneration: message.payload["deliveryGeneration"] as? Int,
        payloadHash: message.payload["payloadHash"] as? String,
        ok: false,
        errorCode: "malformed_backend_delete_request"
      )
      return
    }

    Task { [weak self] in
      do {
        try await KernelJournalBackendSyncDriver.shared.delete(request)
        await self?.sendJournalBackendDeleteResult(
          requestId: message.requestId,
          clientId: message.clientId,
          ownerId: request.ownerId,
          operationId: request.operationId,
          conversationId: request.conversationId,
          conversationGeneration: request.conversationGeneration,
          attemptCount: request.attemptCount,
          deliveryGeneration: request.deliveryGeneration,
          payloadHash: request.payloadHash,
          ok: true,
          errorCode: nil
        )
      } catch {
        await self?.sendJournalBackendDeleteResult(
          requestId: message.requestId,
          clientId: message.clientId,
          ownerId: request.ownerId,
          operationId: request.operationId,
          conversationId: request.conversationId,
          conversationGeneration: request.conversationGeneration,
          attemptCount: request.attemptCount,
          deliveryGeneration: request.deliveryGeneration,
          payloadHash: request.payloadHash,
          ok: false,
          errorCode: KernelJournalBackendSyncDriver.boundedDeleteErrorCode(for: error)
        )
      }
    }
  }

  private func sendJournalBackendDeleteResult(
    requestId: String?,
    clientId: String?,
    ownerId: String?,
    operationId: String,
    conversationId: String?,
    conversationGeneration: Int?,
    attemptCount: Int?,
    deliveryGeneration: Int?,
    payloadHash: String?,
    ok: Bool,
    errorCode: String?
  ) {
    var payload: [String: Any] = [
      "type": "journal_backend_delete_result",
      "protocolVersion": 2,
      "operationId": operationId,
      "ok": ok,
    ]
    if let requestId { payload["requestId"] = requestId }
    if let clientId { payload["clientId"] = clientId }
    if let ownerId { payload["ownerId"] = ownerId }
    if let conversationId { payload["conversationId"] = conversationId }
    if let conversationGeneration { payload["conversationGeneration"] = conversationGeneration }
    if let attemptCount { payload["attemptCount"] = attemptCount }
    if let deliveryGeneration { payload["deliveryGeneration"] = deliveryGeneration }
    if let payloadHash { payload["payloadHash"] = payloadHash }
    if let errorCode { payload["errorCode"] = errorCode }
    sendJson(payload)
  }

  private func handleJournalBackendReconcile(_ message: RuntimeMessage) {
    guard let request = KernelJournalBackendSyncDriver.ReconcileRequest(payload: message.payload) else {
      sendJournalBackendReconcileResult(
        requestId: message.requestId,
        clientId: message.clientId,
        ownerId: message.payload["ownerId"] as? String,
        reconcileId: message.payload["reconcileId"] as? String ?? "",
        conversationId: message.payload["conversationId"] as? String,
        pageCursor: message.payload["pageCursor"] as? String,
        nextCursor: nil,
        turns: nil,
        hasMore: nil,
        errorCode: "malformed_backend_reconcile_request"
      )
      return
    }

    Task { [weak self] in
      do {
        let page = try await KernelJournalBackendSyncDriver.shared.reconcile(request)
        await self?.sendJournalBackendReconcileResult(
          requestId: message.requestId,
          clientId: message.clientId,
          ownerId: request.ownerId,
          reconcileId: request.reconcileId,
          conversationId: request.conversationId,
          pageCursor: request.pageCursor,
          nextCursor: page.nextCursor,
          turns: page.turns.map(\.dictionary),
          hasMore: page.hasMore,
          errorCode: nil
        )
      } catch {
        await self?.sendJournalBackendReconcileResult(
          requestId: message.requestId,
          clientId: message.clientId,
          ownerId: request.ownerId,
          reconcileId: request.reconcileId,
          conversationId: request.conversationId,
          pageCursor: request.pageCursor,
          nextCursor: nil,
          turns: nil,
          hasMore: nil,
          errorCode: KernelJournalBackendSyncDriver.boundedReconcileErrorCode(for: error)
        )
      }
    }
  }

  private func sendJournalBackendReconcileResult(
    requestId: String?,
    clientId: String?,
    ownerId: String?,
    reconcileId: String,
    conversationId: String?,
    pageCursor: String?,
    nextCursor: String?,
    turns: [[String: Any]]?,
    hasMore: Bool?,
    errorCode: String?
  ) {
    var payload: [String: Any] = [
      "type": "journal_backend_reconcile_result",
      "protocolVersion": 2,
      "reconcileId": reconcileId,
      "ok": errorCode == nil,
      "pageCursor": pageCursor ?? NSNull(),
    ]
    if let requestId { payload["requestId"] = requestId }
    if let clientId { payload["clientId"] = clientId }
    if let ownerId { payload["ownerId"] = ownerId }
    if let conversationId { payload["conversationId"] = conversationId }
    if errorCode == nil { payload["nextCursor"] = nextCursor ?? NSNull() }
    if let turns { payload["turns"] = turns }
    if let hasMore { payload["hasMore"] = hasMore }
    if let errorCode { payload["errorCode"] = errorCode }
    sendJson(payload)
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
    if let requestKey = message.requestKey,
      let journalRequest = activeJournalRequests.removeValue(forKey: requestKey)
    {
      log("AgentRuntimeProcess: journal operation failed (code-only)")
      journalRequest.continuation.resume(
        throwing: failure.map(BridgeError.agentRuntimeFailure) ?? BridgeError.agentError(raw)
      )
      return
    }
    if let requestKey = message.requestKey,
      let contractRequest = activeKernelContractRequests.removeValue(forKey: requestKey)
    {
      log("AgentRuntimeProcess: kernel contract request failed (code-only)")
      contractRequest.continuation.resume(
        throwing: failure.map(BridgeError.agentRuntimeFailure) ?? BridgeError.agentError(raw)
      )
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
    resumeAllRequests(throwing: error)
    resumeInitContinuations(throwing: error)
  }

  private func resumeAllRequests(throwing error: Error) {
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
    let journalRequests = activeJournalRequests.values
    activeJournalRequests.removeAll()
    for request in journalRequests {
      request.continuation.resume(throwing: error)
    }
    let contractRequests = activeKernelContractRequests.values
    activeKernelContractRequests.removeAll()
    for request in contractRequests {
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
