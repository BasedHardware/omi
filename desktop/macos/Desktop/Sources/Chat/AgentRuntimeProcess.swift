import Foundation
import OmiSupport

/// Sendable carrier for `[String: Any]` JSON payloads that must cross actor or
/// isolation boundaries. The dictionary is parsed once and treated as immutable
/// thereafter, so unchecked Sendable conformance is safe.
struct RuntimeJSONPayloadBox: @unchecked Sendable {
  let value: [String: Any]
  init(_ value: [String: Any]) { self.value = value }
}
extension Notification.Name {
  /// Posted on MainActor after the runtime handshake makes direct control
  /// tools admissible. Carries no owner id or request content.
  static let agentRuntimeDidBecomeReady = Notification.Name("com.omi.desktop.agentRuntimeDidBecomeReady")
}

/// Shares one asynchronous runtime launch across every client admitted while
/// that launch is suspended. The key is deliberately exact (owner-session
/// authorization plus authority epoch), so work admitted under a newer owner
/// generation never joins an older credential-bearing launch.
actor AgentRuntimeStartupSingleFlight<Key: Equatable & Sendable, Output: Sendable> {
  private struct Attempt {
    let id: UUID
    let key: Key
    let task: Task<Output, Error>
  }

  private var attempt: Attempt?
  private var participantCount = 0

  func run(
    key: Key,
    operation: @escaping @Sendable () async throws -> Output
  ) async throws -> Output {
    participantCount += 1
    defer { participantCount -= 1 }
    if let attempt {
      guard attempt.key == key else { throw BridgeError.restarting }
      return try await attempt.task.value
    }

    let id = UUID()
    let task = Task { try await operation() }
    attempt = Attempt(id: id, key: key, task: task)
    do {
      let output = try await task.value
      clearAttempt(id: id)
      return output
    } catch {
      clearAttempt(id: id)
      throw error
    }
  }

  func participantCountForTesting() -> Int {
    participantCount
  }

  /// A reducer can enter `.starting` just before the owning task reaches this
  /// actor. Callers must distinguish that short launch-admission window from a
  /// real in-flight launch; treating both as "wait for init" strands the first
  /// launch forever.
  func hasActiveAttempt() -> Bool {
    attempt != nil
  }

  private func clearAttempt(id: UUID) {
    guard attempt?.id == id else { return }
    attempt = nil
  }
}

/// Decides whether a caller joins an existing launch. `.starting` alone is not
/// sufficient evidence: the reducer records admission before the single-flight
/// actor has installed its attempt, and the first launcher must proceed.
enum AgentRuntimeStartupAdmission {
  static func shouldJoin(
    lifecycleState: AgentRuntimeBridgeLifecycle.State,
    hasActiveStartupAttempt: Bool
  ) -> Bool {
    lifecycleState == .running || (lifecycleState == .starting && hasActiveStartupAttempt)
  }
}

/// Serializes the pipe read and sequence assignment performed by Foundation's
/// readability callback. The callback may be re-entered on different threads;
/// sequencing only after `availableData` would still allow a later read to be
/// delivered first if the earlier callback were preempted between those steps.
final class AgentRuntimeStdoutChunkReader: @unchecked Sendable {
  private let lock = NSLock()
  private var nextSequence: UInt64 = 0

  func read(from handle: FileHandle) -> (sequence: UInt64, data: Data) {
    lock.lock()
    defer { lock.unlock() }
    let data = handle.availableData
    let sequence = nextSequence
    if !data.isEmpty {
      nextSequence &+= 1
    }
    return (sequence, data)
  }
}

/// Journal writes use SQLite `BEGIN IMMEDIATE`, whose configured busy window is
/// five seconds. Keep the client deadline strictly beyond that database window
/// so a successful commit still has time to traverse the JSONL IPC boundary.
struct AgentRuntimeJournalTimeoutPolicy {
  static let sqliteBusyWindowNanoseconds: UInt64 = 5_000_000_000
  static let ipcSlackNanoseconds: UInt64 = 5_000_000_000
  static let deadlineNanoseconds = sqliteBusyWindowNanoseconds + ipcSlackNanoseconds

  static func allowsCorrelatedResult(elapsedNanoseconds: UInt64) -> Bool {
    elapsedNanoseconds < deadlineNanoseconds
  }
}

/// Kernel context needs a bounded but startup-tolerant readiness budget. These
/// requests only establish the pinned session and rendered context; they never
/// run the user's model query, which is tracked on its own request path.
enum AgentRuntimeKernelContractTimeoutPolicy {
  static let defaultDeadlineNanoseconds: UInt64 = 5_000_000_000
  static let contextReadinessDeadlineNanoseconds: UInt64 = 15_000_000_000

  static func deadlineNanoseconds(for operation: String) -> UInt64 {
    switch operation {
    case "resolve_surface_session", "context_source_update", "get_context_snapshot":
      return contextReadinessDeadlineNanoseconds
    default:
      return defaultDeadlineNanoseconds
    }
  }
}

/// Actor-owned reorder and framing buffer for the runtime's JSONL stdout.
/// Tasks created by a readability callback are not scheduling-ordered, so an
/// N+1 chunk can reach the actor before N. Hold later chunks until every prior
/// sequence is present, then extract complete lines from the canonical order.
struct AgentRuntimeOrderedStdoutBuffer {
  private var nextSequence: UInt64 = 0
  private var pendingChunks: [UInt64: Data] = [:]
  private var lineBuffer = Data()

  mutating func ingest(_ data: Data, sequence: UInt64) -> [Data] {
    guard !data.isEmpty, sequence >= nextSequence else { return [] }
    guard pendingChunks[sequence] == nil else { return [] }
    pendingChunks[sequence] = data

    var lines: [Data] = []
    while let chunk = pendingChunks.removeValue(forKey: nextSequence) {
      nextSequence &+= 1
      lineBuffer.append(chunk)
      while let newlineIndex = lineBuffer.firstIndex(of: UInt8(ascii: "\n")) {
        lines.append(Data(lineBuffer[lineBuffer.startIndex..<newlineIndex]))
        lineBuffer = Data(lineBuffer[lineBuffer.index(after: newlineIndex)...])
      }
    }
    return lines
  }

  mutating func reset() {
    nextSequence = 0
    pendingChunks.removeAll(keepingCapacity: false)
    lineBuffer.removeAll(keepingCapacity: false)
  }
}

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
  nonisolated static let expectedProtocolVersion = 2
  nonisolated static let requiredRuntimeCapabilities: Set<String> = [
    "journal_import_remote_turn",
    "runtime_adapter_availability",
    "chat_first_capability_projection",
  ]
  private static let ownerTransitionClientID = "runtime-owner-transition"

  struct RuntimeHandshake: Equatable, Sendable {
    let protocolVersion: Int
    let runtimeVersion: String
    let capabilities: Set<String>
  }

  struct DiagnosticsSnapshot: Equatable, Sendable {
    let running: Bool
    let protocolVersion: Int?
    let runtimeVersion: String?
  }

  struct RuntimeOwnerAuthorityStatus: Equatable, Sendable {
    let epoch: UInt64
    let ownerID: String?
    let credentialOwnerID: String?
    let processRunning: Bool

    func isSynchronized(ownerID: String, requiresCredentials: Bool) -> Bool {
      processRunning && self.ownerID == ownerID
        && (!requiresCredentials || credentialOwnerID == ownerID)
    }
  }

  nonisolated static func shouldEnablePlaywrightExtension(
    useExtension: Bool,
    token: String,
    targetHasExtension: Bool
  ) -> Bool {
    useExtension && !token.isEmpty && targetHasExtension
  }

  nonisolated static func validateRuntimeHandshake(
    _ message: RuntimeMessage
  ) throws -> RuntimeHandshake {
    guard message.kind == .initMessage,
      let protocolVersion = message.protocolVersion,
      protocolVersion == expectedProtocolVersion
    else {
      throw BridgeError.agentError("Agent runtime protocol is incompatible")
    }
    let runtimeVersion =
      (message.payload["runtimeVersion"] as? String)?
      .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    guard !runtimeVersion.isEmpty else {
      throw BridgeError.agentError("Agent runtime did not identify its version")
    }
    let capabilities = Set(message.payload["runtimeCapabilities"] as? [String] ?? [])
    guard requiredRuntimeCapabilities.isSubset(of: capabilities) else {
      throw BridgeError.agentError("Agent runtime is missing required capabilities")
    }
    return RuntimeHandshake(
      protocolVersion: protocolVersion,
      runtimeVersion: runtimeVersion,
      capabilities: capabilities
    )
  }

  nonisolated static func isConfirmedOutOfMemoryDiagnostic(_ text: String) -> Bool {
    let lower = text.lowercased()
    return lower.contains("fatalprocessoutofmemory")
      || lower.contains("javascript heap out of memory")
      || lower.contains("failed to reserve virtual memory")
  }

  struct RuntimeMessage: @unchecked Sendable {
    struct RequestKey: Hashable, Equatable, Sendable {
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
      case chatFirstDeferralDelivery
      case defaultExecutionProfileConfigured
      case surfaceSessionResolved
      case sessionExecutionProfileMigrated
      case contextSourceUpdated
      case contextSnapshot
      case legacyMainChatSessionsImported
      case externalSurfaceRunBeginResult
      case externalSurfaceToolResult
      case externalSurfaceRunCompleteResult
      case ownerRuntimeRevoked
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
      case "chat_first_deferral_delivery": return .chatFirstDeferralDelivery
      case "default_execution_profile_configured": return .defaultExecutionProfileConfigured
      case "surface_session_resolved": return .surfaceSessionResolved
      case "session_execution_profile_migrated": return .sessionExecutionProfileMigrated
      case "context_source_updated": return .contextSourceUpdated
      case "context_snapshot": return .contextSnapshot
      case "legacy_main_chat_sessions_imported": return .legacyMainChatSessionsImported
      case "external_surface_run_begin_result": return .externalSurfaceRunBeginResult
      case "external_surface_tool_result": return .externalSurfaceToolResult
      case "external_surface_run_complete_result": return .externalSurfaceRunCompleteResult
      case "owner_runtime_revoked": return .ownerRuntimeRevoked
      default: return .unknown(type)
      }
    }
  }

  private struct ClientRegistration {
    var registrationID: UUID
    var harnessMode: String
    var authAuthorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
    var onAuthRequired: AgentBridge.AuthRequiredHandler?
    var onAuthSuccess: AgentBridge.AuthSuccessHandler?

    init(
      registrationID: UUID = UUID(),
      harnessMode: String,
      authAuthorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil,
      onAuthRequired: AgentBridge.AuthRequiredHandler? = nil,
      onAuthSuccess: AgentBridge.AuthSuccessHandler? = nil
    ) {
      self.registrationID = registrationID
      self.harnessMode = harnessMode
      self.authAuthorizationSnapshot = authAuthorizationSnapshot
      self.onAuthRequired = onAuthRequired
      self.onAuthSuccess = onAuthSuccess
    }
  }

  private struct StartupKey: Equatable, Sendable {
    let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
    let admissionAuthorityEpoch: UInt64
  }

  private struct StartupReceipt: Equatable, Sendable {
    let authorityEpoch: UInt64
    let processGeneration: UInt64
  }

  private struct StopFlight {
    let id: UUID
    var waiters: [CheckedContinuation<Void, Never>] = []
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
    let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
    let continuation: CheckedContinuation<AgentBridge.QueryResult, Error>
    var isInterrupted = false
    var cancelAck: RuntimeMessage?
  }

  private struct ActiveControlRequest {
    let clientId: String
    let requestId: String
    let expectedOwnerId: String
    let expectedOwnerEpoch: UInt64
    let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
    let continuation: CheckedContinuation<String, Error>
  }

  private struct ActiveJournalRequest {
    let clientId: String
    let requestId: String
    let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
    let continuation: CheckedContinuation<JournalOperationResult, Error>
  }

  private struct ActiveKernelContractRequest {
    let clientId: String
    let requestId: String
    let operation: String
    let expectedKind: RuntimeMessage.Kind
    let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
    let sentAtUptime: TimeInterval
    let continuation: CheckedContinuation<RuntimeJSONPayloadBox, Error>
  }

  private struct TimedOutKernelContractRequest {
    let operation: String
    let expectedKind: RuntimeMessage.Kind
    let timedOutAtUptime: TimeInterval
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
    let accepted: Bool? = nil
    let duplicate: Bool? = nil
    let continuityKey: String? = nil
    let suppressedByTailQuestion: Bool = false
    let suppressedByStreamingTail: Bool = false
    let materializationStoppedByTail: Bool = false
    let materializationReceipts: [ChatFirstMaterializationReceipt] = []
    let coldStartSequenceTerminalReceipts: [ChatFirstColdStartSequenceTerminalReceipt] = []
    let acknowledgedReceiptCount: Int = 0
  }

  struct QuestionInteractionReply: Sendable {
    let accepted: Bool
    let duplicate: Bool
    let continuityKey: String
    let parentTurn: KernelJournalTurn?
    let userTurn: KernelJournalTurn
    let assistantTurn: KernelJournalTurn
  }

  struct ChatFirstIntentsMaterialization: Sendable {
    let accepted: Bool
    let stoppedByTail: Bool
    let receipts: [ChatFirstMaterializationReceipt]
  }

  typealias JournalTurnChangedHandler = @Sendable (KernelJournalTurn) -> Void
  typealias AuthorizedRealtimeToolHandler =
    @Sendable (AuthorizedToolExecution) async -> AuthorizedRealtimeToolExecutionResult

  private var process: Process?
  private var stdinPipe: Pipe?
  private var stdoutPipe: Pipe?
  private var stderrPipe: Pipe?
  private var stdoutBuffer = AgentRuntimeOrderedStdoutBuffer()
  private var processGeneration: UInt64 = 0
  private var runtimeOwnerAuthorityEpoch: UInt64 = 0
  private var synchronizedRuntimeOwnerID: String?
  private var synchronizedRuntimeCredentialOwnerID: String?
  private var directControlOwnerEpoch: UInt64 = 0
  private var observedDirectControlOwnerId: String?

  /// Debug suspend/resume state, held off-actor so SIGCONT never deadlocks behind
  /// an actor blocked writing to the frozen process. See DebugSuspendControl.
  private nonisolated let debugSuspend = DebugSuspendControl()
  private var lastExitWasOOM = false
  private var clients: [String: ClientRegistration] = [:]
  private var activeRequests: [RuntimeMessage.RequestKey: ActiveRequest] = [:]
  private var activeControlRequests: [RuntimeMessage.RequestKey: ActiveControlRequest] = [:]
  private var activeControlTimeoutTasks: [RuntimeMessage.RequestKey: Task<Void, Never>] = [:]
  private var activeJournalRequests: [RuntimeMessage.RequestKey: ActiveJournalRequest] = [:]
  private var activeKernelContractRequests: [RuntimeMessage.RequestKey: ActiveKernelContractRequest] = [:]
  private var timedOutKernelContractRequests: [RuntimeMessage.RequestKey: TimedOutKernelContractRequest] = [:]
  private var activeAuthorizedToolExecutionTasks: [UUID: Task<Void, Never>] = [:]
  private var journalTurnChangedHandler: JournalTurnChangedHandler?
  private var authorizedRealtimeToolHandler: AuthorizedRealtimeToolHandler?
  private var initContinuations: [CheckedContinuation<Void, Error>] = []
  private let oomDiagnosticLatch = AgentRuntimeOOMDiagnosticLatch()
  private var advertisedAgentControlTools: Set<String> = []
  private var runtimeAdapterIDs: Set<String> = []
  private var negotiatedProtocolVersion: Int?
  private var negotiatedRuntimeVersion: String?
  private var stopFlight: StopFlight?
  private var expectedCancelledRequests: Set<RuntimeMessage.RequestKey> = []
  // Lifecycle facts are reduced by the pure state machine; process/pipe handles
  // remain local implementation resources rather than a second lifecycle truth.
  private var bridgeLifecycle = AgentRuntimeBridgeLifecycle()
  private let startupSingleFlight =
    AgentRuntimeStartupSingleFlight<StartupKey, StartupReceipt>()

  // `bridgeLifecycle` is the semantic source of truth. Process handles are
  // intentionally only physical resources: they can be live before the JSONL
  // handshake, but no request is admitted until the reducer reaches running.
  private var isBridgeReady: Bool {
    bridgeLifecycle.state == .running && process?.isRunning == true
  }

  private var isRestarting: Bool {
    [.modeSwitching, .draining, .restarting].contains(bridgeLifecycle.state)
  }

  private var isStopping: Bool {
    bridgeLifecycle.state == .draining
  }

  var isAlive: Bool {
    let processRunning = process?.isRunning ?? false
    if process != nil && !processRunning {
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
    return processRunning
  }

  func diagnosticsSnapshot() -> DiagnosticsSnapshot {
    DiagnosticsSnapshot(
      running: isBridgeReady,
      protocolVersion: negotiatedProtocolVersion,
      runtimeVersion: negotiatedRuntimeVersion
    )
  }

  /// Read-only admission probe for UI recovery loops. A process handle alone
  /// is not enough: direct control is valid only after the JSONL handshake.
  func isReadyForDirectControl() -> Bool {
    isBridgeReady
  }

  func runtimeOwnerAuthorityStatus() -> RuntimeOwnerAuthorityStatus {
    RuntimeOwnerAuthorityStatus(
      epoch: runtimeOwnerAuthorityEpoch,
      ownerID: synchronizedRuntimeOwnerID,
      credentialOwnerID: synchronizedRuntimeCredentialOwnerID,
      processRunning: process?.isRunning ?? false
    )
  }

  /// The Node registry is the authority for adapter activation. Swift must not
  /// re-run local executable detection before advertising a realtime provider.
  func registeredDirectedProviderIDs() -> [String] {
    runtimeAdapterIDs.intersection(["hermes", "openclaw"]).sorted()
  }

  static func adapterId(forHarnessMode harnessMode: String) -> String? {
    guard let harness = AgentRuntimeRouting.harnessMode(from: harnessMode) else {
      return nil
    }
    return AgentRuntimeRouting.adapterId(for: harness).rawValue
  }

  func registerClient(
    clientId: String,
    harnessMode: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws {
    guard !isRestarting else {
      throw BridgeError.restarting
    }
    guard
      let authorizationSnapshot = authorizationSnapshot
        ?? RuntimeOwnerIdentity.captureAuthorizationSnapshot()
    else {
      throw BridgeError.authMissing
    }
    let admissionAuthorityEpoch = runtimeOwnerAuthorityEpoch
    try assertStartupAuthority(
      authorizationSnapshot,
      expectedAuthorityEpoch: admissionAuthorityEpoch)
    let previousRegistration = clients[clientId]
    let registrationID = UUID()
    var registration = previousRegistration ?? ClientRegistration(harnessMode: harnessMode)
    registration.registrationID = registrationID
    registration.harnessMode = harnessMode
    clients[clientId] = registration
    do {
      let startupIsInFlight: Bool
      if bridgeLifecycle.state == .starting {
        startupIsInFlight = await startupSingleFlight.hasActiveAttempt()
      } else {
        startupIsInFlight = false
      }
      if AgentRuntimeStartupAdmission.shouldJoin(
        lifecycleState: bridgeLifecycle.state,
        hasActiveStartupAttempt: startupIsInFlight
      ) {
        try await waitForInit(timeout: 30.0)
        try assertStartupAuthority(
          authorizationSnapshot,
          expectedAuthorityEpoch: admissionAuthorityEpoch)
        try assertClientRegistration(clientId: clientId, registrationID: registrationID)
        return
      }

      try await startProcess(
        preferredHarnessMode: harnessMode,
        authorizationSnapshot: authorizationSnapshot,
        admissionAuthorityEpoch: admissionAuthorityEpoch)
      try assertAuthorization(authorizationSnapshot)
      try assertClientRegistration(clientId: clientId, registrationID: registrationID)
    } catch {
      if clients[clientId]?.registrationID == registrationID {
        if let previousRegistration {
          clients[clientId] = previousRegistration
        } else {
          clients.removeValue(forKey: clientId)
        }
      }
      throw error
    }
  }

  func unregisterClient(clientId: String) async {
    clients.removeValue(forKey: clientId)

    for (requestKey, request) in activeRequests where request.clientId == clientId {
      activeRequests.removeValue(forKey: requestKey)
      request.continuation.resume(throwing: BridgeError.stopped)
    }
    for (requestKey, request) in activeControlRequests where request.clientId == clientId {
      if let activeRequest = takeActiveControlRequest(requestKey) {
        activeRequest.continuation.resume(throwing: BridgeError.stopped)
      }
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
      await stopProcessSingleFlight(resumeRequestsWith: BridgeError.stopped)
    }
  }

  func setGlobalAuthHandlers(
    clientId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?,
    onAuthRequired: AgentBridge.AuthRequiredHandler?,
    onAuthSuccess: AgentBridge.AuthSuccessHandler?
  ) -> Bool {
    // Handler configuration is not registration. Creating a client here lets a
    // handler-before-start call survive a failed/cancelled admission and keep
    // the shared daemon alive as a ghost client.
    guard var registration = clients[clientId] else { return false }
    registration.authAuthorizationSnapshot = authorizationSnapshot
    registration.onAuthRequired = onAuthRequired
    registration.onAuthSuccess = onAuthSuccess
    clients[clientId] = registration
    return true
  }

  func restart(
    clientId: String,
    harnessMode: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws {
    guard !isRestarting else { throw BridgeError.restarting }
    guard activeRequests.isEmpty, activeControlRequests.isEmpty else {
      log(
        "AgentRuntimeProcess: shared restart blocked while \(activeRequests.count) request(s) and \(activeControlRequests.count) control request(s) are active"
      )
      throw BridgeError.requestAlreadyActive
    }
    // Validate before mutating the reducer. A caller can be unregistered
    // between a UI restart action and this actor turn; that must leave the
    // bridge usable for a later registration, not stranded in `.draining`.
    guard let registrationID = clients[clientId]?.registrationID else {
      throw BridgeError.stopped
    }
    _ = bridgeLifecycle.reduce(.modeSwitchRequested)
    _ = bridgeLifecycle.reduce(.drainRequested)
    do {
      await stopProcessSingleFlight(resumeRequestsWith: BridgeError.stopped)
      _ = bridgeLifecycle.reduce(.restart)
      try Task.checkCancellation()
      try assertClientRegistration(clientId: clientId, registrationID: registrationID)
      guard
        let authorizationSnapshot = authorizationSnapshot
          ?? RuntimeOwnerIdentity.captureAuthorizationSnapshot()
      else {
        throw BridgeError.authMissing
      }
      try await startProcess(
        preferredHarnessMode: harnessMode,
        authorizationSnapshot: authorizationSnapshot,
        admissionAuthorityEpoch: runtimeOwnerAuthorityEpoch)
      try assertAuthorization(authorizationSnapshot)
      try assertClientRegistration(clientId: clientId, registrationID: registrationID)
    } catch {
      // A cancelled or unregistered caller cannot own a pending restart. Keep
      // typed start failures intact, but return abandoned drain/restart paths
      // to stopped so a subsequent registration can launch normally.
      if [.draining, .restarting].contains(bridgeLifecycle.state) {
        _ = bridgeLifecycle.reduce(.kill)
      }
      throw error
    }
  }

  private func assertStartupAuthority(
    _ snapshot: RuntimeOwnerAuthorizationSnapshot,
    expectedAuthorityEpoch: UInt64
  ) throws {
    guard !isStopping,
      runtimeOwnerAuthorityEpoch == expectedAuthorityEpoch,
      RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot)
    else {
      throw BridgeError.authMissing
    }
  }

  private func stopProcessSingleFlight(resumeRequestsWith error: BridgeError) async {
    if let flight = stopFlight {
      await waitForStopFlight(id: flight.id)
      return
    }

    let id = UUID()
    stopFlight = StopFlight(id: id)
    await stopProcess(resumeRequestsWith: error)
    finishStopFlight(id: id)
  }

  private func waitForStopFlight(id: UUID) async {
    await withCheckedContinuation { continuation in
      guard var flight = stopFlight, flight.id == id else {
        continuation.resume()
        return
      }
      flight.waiters.append(continuation)
      stopFlight = flight
    }
  }

  private func finishStopFlight(id: UUID) {
    guard let flight = stopFlight, flight.id == id else { return }
    stopFlight = nil
    flight.waiters.forEach { $0.resume() }
  }

  private func assertClientRegistration(
    clientId: String,
    registrationID: UUID
  ) throws {
    guard clients[clientId]?.registrationID == registrationID else {
      throw BridgeError.stopped
    }
  }

  private func assertAuthorization(
    _ snapshot: RuntimeOwnerAuthorizationSnapshot,
    expectedOwnerID: String? = nil
  ) throws {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot) else {
      throw BridgeError.authMissing
    }
    if let expectedOwnerID {
      let normalized = expectedOwnerID.trimmingCharacters(in: .whitespacesAndNewlines)
      guard normalized == snapshot.ownerID else { throw BridgeError.authMissing }
    }
  }

  func warmupSession(
    clientId: String,
    sessionId: String,
    profileGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
    sendJson(
      Self.warmupWireMessage(
        clientId: clientId,
        requestId: UUID().uuidString,
        ownerId: authorizationSnapshot.ownerID,
        sessionId: sessionId,
        profileGeneration: profileGeneration
      ))
  }

  func configureDefaultExecutionProfile(
    clientId: String,
    adapterId: String,
    modelProfile: String?,
    workingDirectory: String,
    expectedPreferenceGeneration: Int?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> AgentDefaultExecutionProfile {
    try assertAuthorization(authorizationSnapshot)
    let payload = Self.configureDefaultExecutionProfileWireMessage(
      clientId: clientId,
      requestId: UUID().uuidString,
      ownerId: authorizationSnapshot.ownerID,
      adapterId: adapterId,
      modelProfile: modelProfile,
      workingDirectory: workingDirectory,
      expectedPreferenceGeneration: expectedPreferenceGeneration
    )
    let result = try await kernelContractRequest(
      payload: payload,
      expectedKind: .defaultExecutionProfileConfigured,
      authorizationSnapshot: authorizationSnapshot
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
    creationProfile: AgentSessionCreationProfile?,
    chatFirstCapability: ChatFirstCapabilityProjection? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> AgentSurfaceSession {
    try assertAuthorization(authorizationSnapshot)
    let payload = Self.resolveSurfaceSessionWireMessage(
      clientId: clientId,
      requestId: UUID().uuidString,
      ownerId: authorizationSnapshot.ownerID,
      surface: surface,
      title: title,
      creationProfile: creationProfile,
      chatFirstCapability: chatFirstCapability
    )
    let result = try await kernelContractRequest(
      payload: payload,
      expectedKind: .surfaceSessionResolved,
      authorizationSnapshot: authorizationSnapshot)
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
    workingDirectory: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> AgentSessionProfileMigration {
    try assertAuthorization(authorizationSnapshot)
    let payload = Self.migrateSessionExecutionProfileWireMessage(
      clientId: clientId,
      requestId: UUID().uuidString,
      ownerId: authorizationSnapshot.ownerID,
      sessionId: sessionId,
      expectedProfileGeneration: expectedProfileGeneration,
      adapterId: adapterId,
      modelProfile: modelProfile,
      workingDirectory: workingDirectory
    )
    let result = try await kernelContractRequest(
      payload: payload,
      expectedKind: .sessionExecutionProfileMigrated,
      authorizationSnapshot: authorizationSnapshot
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
    payload: RuntimeJSONPayloadBox,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> AgentContextSourceUpdateReceipt {
    try assertAuthorization(authorizationSnapshot)
    let message = Self.contextSourceUpdateWireMessage(
      clientId: clientId,
      requestId: UUID().uuidString,
      ownerId: authorizationSnapshot.ownerID,
      sessionId: sessionId,
      surfaceKind: surfaceKind,
      source: source,
      sourceRevision: sourceRevision,
      outcome: outcome,
      capturedAtMs: capturedAtMs,
      expiresAtMs: expiresAtMs,
      payload: payload.value
    )
    let result = try await kernelContractRequest(
      payload: message,
      expectedKind: .contextSourceUpdated,
      authorizationSnapshot: authorizationSnapshot)
    guard let receipt = AgentContextSourceUpdateReceipt(dictionary: result) else {
      throw BridgeError.agentError("Kernel returned an invalid context source receipt")
    }
    return receipt
  }

  func getContextSnapshot(
    clientId: String,
    sessionId: String,
    surfaceKind: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> AgentContextSnapshot {
    try assertAuthorization(authorizationSnapshot)
    let message = Self.getContextSnapshotWireMessage(
      clientId: clientId,
      requestId: UUID().uuidString,
      ownerId: authorizationSnapshot.ownerID,
      sessionId: sessionId,
      surfaceKind: surfaceKind
    )
    let result = try await kernelContractRequest(
      payload: message,
      expectedKind: .contextSnapshot,
      authorizationSnapshot: authorizationSnapshot)
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

  /// Correlated pre-visibility owner barrier. This method never registers a
  /// client or starts Node: an absent child already proves no process-local work
  /// can survive. Any malformed/nack/timeout path kills and confirms exit before
  /// returning to the owner transition.
  func revokeOwnerRuntime(
    previousOwnerID: String,
    cleanupCapability: RuntimeOwnerTransitionCleanupCapability
  ) async {
    let ownerID = previousOwnerID.trimmingCharacters(in: .whitespacesAndNewlines)
    do {
      try assertTransitionCleanupAuthority(
        cleanupCapability,
        previousOwnerID: ownerID)
    } catch {
      log("AgentRuntimeProcess: owner revoke rejected invalid cleanup capability")
      if process?.isRunning == true {
        await stopProcessSingleFlight(resumeRequestsWith: .stopped)
      } else {
        markRuntimeOwnerAuthorityDirty()
      }
      return
    }
    await cancelAndDrainAuthorizedToolExecutionTasks()
    guard !ownerID.isEmpty else {
      if process?.isRunning == true { await stopProcessSingleFlight(resumeRequestsWith: .stopped) }
      return
    }
    guard process?.isRunning == true else {
      markRuntimeOwnerAuthorityDirty()
      return
    }

    do {
      let requestId = UUID().uuidString
      let result = try await kernelContractRequest(
        payload: Self.revokeOwnerRuntimeWireMessage(
          clientId: Self.ownerTransitionClientID,
          requestId: requestId,
          ownerId: ownerID),
        expectedKind: .ownerRuntimeRevoked,
        authorizationSnapshot: nil,
        timeoutNanoseconds: 10_000_000_000
      )
      try assertTransitionCleanupAuthority(
        cleanupCapability,
        previousOwnerID: ownerID)
      guard result["ok"] as? Bool == true else {
        throw ExternalSurfaceAuthorityError.from(
          result,
          fallback: "owner_runtime_revoke_failed")
      }
      guard
        result["ownerId"] as? String == ownerID,
        result["revokedRunIds"] as? [String] != nil,
        result["invalidatedBindingIds"] as? [String] != nil
      else {
        throw ExternalSurfaceAuthorityError(code: "malformed_owner_runtime_revoked")
      }
      // Account replacement is intentionally a hard process boundary. The ACK
      // proves every durable A run/tool is terminal; stopping next guarantees no
      // adapter credential or process-local memory can survive into B.
      await stopProcessSingleFlight(resumeRequestsWith: .stopped)
    } catch {
      log(
        "AgentRuntimeProcess: owner revoke barrier failed; stopping child before owner visibility "
          + "(error=\(error.localizedDescription))")
      await stopProcessSingleFlight(resumeRequestsWith: .stopped)
    }
  }

  nonisolated static func revokeOwnerRuntimeWireMessage(
    clientId: String,
    requestId: String,
    ownerId: String
  ) -> [String: Any] {
    [
      "type": "revoke_owner_runtime",
      "protocolVersion": 2,
      "requestId": requestId,
      "clientId": clientId,
      "ownerId": ownerId,
    ]
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
    guard
      let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(
        expectedOwnerID: ownerID)
    else {
      throw ExternalSurfaceAuthorityError(code: "external_surface_owner_changed")
    }
    try assertCurrentExternalOwner(ownerID)
    // Direct control is an owner-scoped runtime protocol, not an interactive
    // client lease. Once the runtime has completed its handshake, registering
    // another client here can race the client that owns startup and strand a
    // read such as `list_agent_sessions`. Only acquire a client lease when we
    // actually need to start or join an unavailable runtime.
    if !isBridgeReady {
      try await registerClient(
        clientId: clientId,
        harnessMode: harnessMode,
        authorizationSnapshot: authorizationSnapshot)
    }
    // Process startup/initialization may suspend for up to its bounded init
    // timeout. Revalidate immediately before the begin mutation so cancelling a
    // pending owner-A task during an A→B transition cannot create a late run.
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      throw ExternalSurfaceAuthorityError(code: "external_surface_owner_changed")
    }
    try assertCurrentExternalOwner(ownerID)
    try ensureRuntimeOwnerAuthority(
      expectedOwnerID: ownerID,
      authorizationSnapshot: authorizationSnapshot)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      throw ExternalSurfaceAuthorityError(code: "external_surface_owner_changed")
    }
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
      authorizationSnapshot: authorizationSnapshot,
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
    guard
      let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(
        expectedOwnerID: binding.ownerID)
    else {
      throw ExternalSurfaceAuthorityError(code: "external_surface_owner_changed")
    }
    try assertCurrentExternalOwner(binding.ownerID)
    // Direct-control reads are owner-scoped protocol messages, not another
    // interactive client lease. Re-registering while the shared runtime is
    // already live mutates its startup lease on every reconciliation tick and
    // can delay otherwise small reads behind concurrent projections.
    if !isBridgeReady {
      try await registerClient(
        clientId: clientId,
        harnessMode: harnessMode,
        authorizationSnapshot: authorizationSnapshot)
    }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      throw ExternalSurfaceAuthorityError(code: "external_surface_owner_changed")
    }
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
      authorizationSnapshot: authorizationSnapshot,
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
    errorCode: String? = nil,
    transitionCleanupCapability: RuntimeOwnerTransitionCleanupCapability? = nil
  ) async throws -> ExternalSurfaceRunCompletion {
    let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
    if let transitionCleanupCapability {
      try assertTransitionCleanupAuthority(
        transitionCleanupCapability,
        previousOwnerID: binding.ownerID)
      // A cleanup capability may close only a run that already exists in the
      // live daemon. It must never start a new daemon or establish an owner.
      guard process?.isRunning == true else {
        throw ExternalSurfaceAuthorityError(code: "external_surface_runtime_unavailable")
      }
      authorizationSnapshot = nil
    } else {
      guard
        let captured = RuntimeOwnerIdentity.captureAuthorizationSnapshot(
          expectedOwnerID: binding.ownerID)
      else {
        throw ExternalSurfaceAuthorityError(code: "external_surface_owner_changed")
      }
      authorizationSnapshot = captured
      try assertCurrentExternalOwner(binding.ownerID)
      try await registerClient(
        clientId: clientId,
        harnessMode: harnessMode,
        authorizationSnapshot: captured)
    }
    // Revalidate after any actor suspension and immediately before the wire
    // mutation. A later transition generation cannot reuse this capability.
    if let transitionCleanupCapability {
      try assertTransitionCleanupAuthority(
        transitionCleanupCapability,
        previousOwnerID: binding.ownerID)
    } else {
      try assertCurrentExternalOwner(binding.ownerID)
    }
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
      authorizationSnapshot: authorizationSnapshot,
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

  private func ensureRuntimeOwnerAuthority(
    expectedOwnerID: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) throws {
    let normalized = expectedOwnerID.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalized.isEmpty,
      authorizationSnapshot.ownerID == normalized,
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
    else {
      throw ExternalSurfaceAuthorityError(code: "external_surface_owner_changed")
    }
    if synchronizedRuntimeOwnerID == normalized { return }
    guard
      refreshRuntimeOwner(
        expectedOwnerId: normalized,
        authorizationSnapshot: authorizationSnapshot)
    else {
      throw ExternalSurfaceAuthorityError(code: "external_surface_owner_handshake_failed")
    }
  }

  private func assertTransitionCleanupAuthority(
    _ capability: RuntimeOwnerTransitionCleanupCapability,
    previousOwnerID: String
  ) throws {
    guard
      RuntimeOwnerIdentity.authorizesTransitionCleanup(
        capability,
        previousOwnerID: previousOwnerID)
    else {
      throw ExternalSurfaceAuthorityError(
        code: "external_surface_transition_cleanup_revoked")
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
    creationProfile: AgentSessionCreationProfile? = nil,
    chatFirstCapability: ChatFirstCapabilityProjection? = nil
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
    if let chatFirstCapability { message["chatFirstCapability"] = chatFirstCapability.dictionary }
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
    producingTurnId: String?,
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
    if let producingTurnId, !producingTurnId.isEmpty { message["producingTurnId"] = producingTurnId }
    if let expectedContext {
      message["expectedContextSnapshotVersion"] = expectedContext.version
      message["expectedContextSnapshotGeneration"] = expectedContext.generation
      message["expectedContextRendererFingerprint"] = expectedContext.rendererFingerprint
      message["expectedCapabilityVersion"] = expectedContext.capabilityVersion
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
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?,
    timeoutNanoseconds: UInt64? = nil
  ) async throws -> [String: Any] {
    guard isBridgeReady else { throw BridgeError.stopped }
    if let authorizationSnapshot {
      try assertAuthorization(authorizationSnapshot)
    }
    guard
      let clientId = payload["clientId"] as? String,
      let requestId = payload["requestId"] as? String
    else {
      throw BridgeError.agentError("Kernel contract request is missing tracing identity")
    }
    let operation = payload["type"] as? String ?? "unknown"
    let deadlineNanoseconds =
      timeoutNanoseconds
      ?? AgentRuntimeKernelContractTimeoutPolicy.deadlineNanoseconds(for: operation)
    let requestKey = RuntimeMessage.RequestKey(clientId: clientId, requestId: requestId)
    let box = try await withCheckedThrowingContinuation { continuation in
      activeKernelContractRequests[requestKey] = ActiveKernelContractRequest(
        clientId: clientId,
        requestId: requestId,
        operation: operation,
        expectedKind: expectedKind,
        authorizationSnapshot: authorizationSnapshot,
        sentAtUptime: ProcessInfo.processInfo.systemUptime,
        continuation: continuation
      )
      guard sendJson(payload) else {
        activeKernelContractRequests.removeValue(forKey: requestKey)?.continuation.resume(
          throwing: BridgeError.processExited
        )
        timedOutKernelContractRequests.removeValue(forKey: requestKey)
        return
      }
      Task {
        try? await Task.sleep(nanoseconds: deadlineNanoseconds)
        guard let request = self.activeKernelContractRequests.removeValue(forKey: requestKey) else { return }
        let now = ProcessInfo.processInfo.systemUptime
        self.timedOutKernelContractRequests[requestKey] = TimedOutKernelContractRequest(
          operation: request.operation,
          expectedKind: request.expectedKind,
          timedOutAtUptime: now
        )
        self.trimTimedOutKernelContractRequests()
        let elapsedMilliseconds = Int((now - request.sentAtUptime) * 1_000)
        log(
          "AgentRuntimeProcess: kernel contract timeout operation=\(request.operation) "
            + "expected=\(String(describing: request.expectedKind)) elapsed_ms=\(elapsedMilliseconds)"
        )
        request.continuation.resume(throwing: BridgeError.timeout)
      }
    }
    return box.value
  }

  private func trimTimedOutKernelContractRequests() {
    let cutoff = ProcessInfo.processInfo.systemUptime - 60
    timedOutKernelContractRequests = timedOutKernelContractRequests.filter {
      $0.value.timedOutAtUptime >= cutoff
    }
    if timedOutKernelContractRequests.count > 32,
      let oldest = timedOutKernelContractRequests.min(by: {
        $0.value.timedOutAtUptime < $1.value.timedOutAtUptime
      })?.key
    {
      timedOutKernelContractRequests.removeValue(forKey: oldest)
    }
  }

  func invalidateSurface(
    clientId: String,
    surface: AgentSurfaceReference,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
    var dict: [String: Any] = [
      "type": "invalidate_session",
      "protocolVersion": 2,
      "requestId": UUID().uuidString,
      "clientId": clientId,
      "surfaceKind": surface.surfaceKind,
      "externalRefKind": surface.externalRefKind,
      "externalRefId": surface.externalRefId,
    ]
    dict["ownerId"] = authorizationSnapshot.ownerID
    sendJson(dict)
  }

  // Startup-only reader for pre-kernel session aliases; it never writes turns or
  // participates in runtime routing after canonical surface identity exists.
  func importLegacyMainChatSessions(
    clientId: String,
    entries: [LegacyMainChatSessionAliasEntry],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> LegacyMainChatSessionImportReceipt {
    try assertAuthorization(authorizationSnapshot)
    let ownerId = authorizationSnapshot.ownerID
    let payload = Self.importLegacyMainChatSessionsWireMessage(
      clientId: clientId,
      requestId: UUID().uuidString,
      ownerId: ownerId,
      entries: entries
    )
    let result = try await kernelContractRequest(
      payload: payload,
      expectedKind: .legacyMainChatSessionsImported,
      authorizationSnapshot: authorizationSnapshot
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
    recordLifecycleJournalMutation(turn)
    journalTurnChangedHandler?(turn)
  }

  /// Test-only observation seam for lifecycle events that production receives
  /// through the JSONL runtime boundary.
  func bridgeLifecycleSnapshotForTesting() -> AgentRuntimeBridgeLifecycle {
    bridgeLifecycle
  }

  func recordJournalTurn(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    turn: KernelJournalTurnWrite,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> KernelJournalTurn {
    let result = try await journalOperation(
      type: "journal_record_turn",
      operation: "record",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: ["turn": turn.dictionary],
      authorizationSnapshot: authorizationSnapshot
    )
    guard let recorded = result.turn else {
      throw BridgeError.agentError("Kernel journal record returned no turn")
    }
    recordLifecycleJournalMutation(recorded)
    return recorded
  }

  func recordJournalExchange(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String,
    turns: [KernelJournalTurnWrite],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> JournalOperationResult {
    let result = try await journalOperation(
      type: "journal_record_exchange",
      operation: "record_exchange",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: ["turns": turns.map(\.dictionary)],
      authorizationSnapshot: authorizationSnapshot
    )
    for recorded in result.turns {
      recordLifecycleJournalMutation(recorded)
    }
    return result
  }

  func updateJournalTurn(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    update: KernelJournalTurnUpdate,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> KernelJournalTurn {
    let result = try await journalOperation(
      type: "journal_update_turn",
      operation: "update",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: ["update": update.dictionary],
      authorizationSnapshot: authorizationSnapshot
    )
    guard let updated = result.turn else {
      throw BridgeError.agentError("Kernel journal update returned no turn")
    }
    recordLifecycleJournalMutation(updated)
    return updated
  }

  func terminalizeJournalTurn(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String,
    terminalization: KernelJournalTurnTerminalization,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> KernelJournalTurn {
    let result = try await journalOperation(
      type: "journal_terminalize_turn",
      operation: "terminalize",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: ["terminalization": terminalization.dictionary],
      authorizationSnapshot: authorizationSnapshot
    )
    guard let turn = result.turn else {
      throw BridgeError.agentError("Kernel journal terminalization returned no turn")
    }
    recordLifecycleJournalMutation(turn)
    return turn
  }

  func listJournalTurns(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    afterTurnSeq: Int = 0,
    limit: Int = 100,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
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
      ],
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func importRemoteJournalTurn(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    turn: KernelJournalRemoteTurn,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> KernelJournalTurn {
    let result = try await journalOperation(
      type: "journal_import_remote_turn",
      operation: "import_remote",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: ["turn": turn.dictionary],
      authorizationSnapshot: authorizationSnapshot
    )
    guard let imported = result.turn else {
      throw BridgeError.agentError("Kernel journal import returned no turn")
    }
    recordLifecycleJournalMutation(imported)
    return imported
  }

  func clearJournalTurns(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    expectedGeneration: Int? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> Int {
    var payload: [String: Any] = [:]
    if let expectedGeneration { payload["expectedGeneration"] = expectedGeneration }
    return try await journalOperation(
      type: "journal_clear_turns",
      operation: "clear",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: payload,
      authorizationSnapshot: authorizationSnapshot
    ).clearedCount
  }

  /// Append server-validated structured blocks to exactly the assistant turn
  /// produced by this capability's run/attempt. The Node kernel re-checks the
  /// live capability and performs the sole journal mutation.
  func appendChatFirstBlocks(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String,
    sessionID: String,
    runID: String,
    attemptID: String,
    capabilityRef: String,
    controlGeneration: Int,
    blocks: [[String: Any]],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> KernelJournalTurn {
    guard surface.surfaceKind == "main_chat",
      controlGeneration >= 0,
      !blocks.isEmpty,
      blocks.count <= 8
    else {
      throw BridgeError.agentError("Invalid chat-first journal append")
    }
    let result = try await journalOperation(
      type: "append_chat_first_blocks",
      operation: "append_chat_first_blocks",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: [
        "sessionId": sessionID,
        "runId": runID,
        "attemptId": attemptID,
        "capabilityRef": capabilityRef,
        "controlGeneration": controlGeneration,
        "blocks": blocks,
      ],
      authorizationSnapshot: authorizationSnapshot
    )
    guard let turn = result.turn else {
      throw BridgeError.agentError("Chat-first journal append returned no turn")
    }
    recordLifecycleJournalMutation(turn)
    return turn
  }

  /// The journal derives the stored question payload and only accepts the
  /// current main-Chat tail. Swift cannot send an answer string or select an
  /// arbitrary parent row through this operation.
  func recordQuestionInteractionReply(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String,
    sessionID: String,
    questionID: String,
    optionID: String,
    controlGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> QuestionInteractionReply {
    guard surface.surfaceKind == "main_chat",
      controlGeneration >= 0,
      !sessionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
      !questionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
      !optionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else {
      throw BridgeError.agentError("Invalid question interaction")
    }
    let result = try await journalOperation(
      type: "record_question_interaction_reply",
      operation: "record_question_interaction_reply",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: [
        "sessionId": sessionID,
        "questionId": questionID,
        "optionId": optionID,
        "controlGeneration": controlGeneration,
      ],
      authorizationSnapshot: authorizationSnapshot
    )
    guard result.accepted == true,
      let continuityKey = result.continuityKey,
      let userTurn = result.turns.first(where: { $0.role == "user" }),
      let assistantTurn = result.turns.first(where: { $0.role == "assistant" })
    else {
      throw BridgeError.agentError("Question is no longer actionable")
    }
    for turn in [result.turn, userTurn, assistantTurn] {
      if let turn { recordLifecycleJournalMutation(turn) }
    }
    return QuestionInteractionReply(
      accepted: true,
      duplicate: result.duplicate == true,
      continuityKey: continuityKey,
      parentTurn: result.turn,
      userTurn: userTurn,
      assistantTurn: assistantTurn
    )
  }

  /// Materialize one ordered server batch through the kernel, which owns the
  /// canonical assistant rows, tail suppression, and receipt identities.
  func materializeChatFirstIntents(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String,
    sessionID: String,
    controlGeneration: Int,
    intents: [ChatFirstPromptIntent],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> ChatFirstIntentsMaterialization {
    guard surface.surfaceKind == "main_chat",
      controlGeneration >= 0,
      !intents.isEmpty,
      intents.count <= 8,
      intents.allSatisfy({ $0.accountGeneration == controlGeneration && $0.kernelBlocks != nil }),
      !sessionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else {
      throw BridgeError.agentError("Invalid chat-first materialization")
    }
    let result = try await journalOperation(
      type: "materialize_chat_first_intents",
      operation: "materialize_chat_first_intents",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: [
        "sessionId": sessionID,
        "controlGeneration": controlGeneration,
        "intents": intents.compactMap { intent in
          guard let blocks = intent.kernelBlocks else { return nil }
          return [
            "intentId": intent.intentID,
            "continuityKey": intent.continuityKey,
            "source": intent.source.rawValue,
            "blocks": blocks,
          ] as [String: Any]
        },
      ],
      authorizationSnapshot: authorizationSnapshot
    )
    for turn in result.turns {
      recordLifecycleJournalMutation(turn)
    }
    return ChatFirstIntentsMaterialization(
      accepted: result.accepted == true,
      stoppedByTail: result.materializationStoppedByTail,
      receipts: result.materializationReceipts
    )
  }

  func listChatFirstMaterializationReceipts(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String,
    sessionID: String,
    controlGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> ChatFirstPromptReceiptBatch {
    guard surface.surfaceKind == "main_chat", controlGeneration >= 0 else {
      throw BridgeError.agentError("Invalid chat-first receipt listing")
    }
    let result = try await journalOperation(
      type: "list_chat_first_materialization_receipts",
      operation: "list_chat_first_materialization_receipts",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: ["sessionId": sessionID, "controlGeneration": controlGeneration, "limit": 16],
      authorizationSnapshot: authorizationSnapshot
    )
    return ChatFirstPromptReceiptBatch(
      materializationReceipts: result.materializationReceipts,
      coldStartSequenceTerminalReceipts: result.coldStartSequenceTerminalReceipts
    )
  }

  @discardableResult
  func acknowledgeChatFirstMaterializationReceipts(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String,
    sessionID: String,
    controlGeneration: Int,
    receipts: ChatFirstPromptReceiptBatch,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> Int {
    guard surface.surfaceKind == "main_chat",
      controlGeneration >= 0,
      receipts.materializationReceipts.count <= 16,
      receipts.coldStartSequenceTerminalReceipts.count <= 16
    else {
      throw BridgeError.agentError("Invalid chat-first receipt acknowledgement")
    }
    let result = try await journalOperation(
      type: "acknowledge_chat_first_materialization_receipts",
      operation: "acknowledge_chat_first_materialization_receipts",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: [
        "sessionId": sessionID,
        "controlGeneration": controlGeneration,
        "receipts": receipts.materializationReceipts.map {
          ["intentId": $0.intentID, "receiptId": $0.receiptID]
        },
        "coldStartSequenceTerminalReceipts": receipts.coldStartSequenceTerminalReceipts.map {
          [
            "sequenceId": $0.sequenceID,
            "receiptId": $0.receiptID,
            "terminalState": $0.terminalState.rawValue,
          ]
        },
      ],
      authorizationSnapshot: authorizationSnapshot
    )
    return result.acknowledgedReceiptCount
  }

  private func journalOperation(
    type: String,
    operation: String,
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String?,
    payload: [String: Any],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> JournalOperationResult {
    try assertAuthorization(authorizationSnapshot, expectedOwnerID: ownerID)
    guard isBridgeReady else { throw BridgeError.stopped }
    let requestId = UUID().uuidString
    let requestKey = RuntimeMessage.RequestKey(clientId: clientId, requestId: requestId)
    let dictionary = Self.journalOperationWireMessage(
      type: type,
      operation: operation,
      clientId: clientId,
      requestId: requestId,
      ownerId: authorizationSnapshot.ownerID,
      surface: surface,
      payload: payload
    )
    return try await withCheckedThrowingContinuation { continuation in
      activeJournalRequests[requestKey] = ActiveJournalRequest(
        clientId: clientId,
        requestId: requestId,
        authorizationSnapshot: authorizationSnapshot,
        continuation: continuation
      )
      guard sendJson(dictionary) else {
        activeJournalRequests.removeValue(forKey: requestKey)?.continuation.resume(
          throwing: BridgeError.processExited
        )
        return
      }
      Task {
        try? await Task.sleep(
          nanoseconds: AgentRuntimeJournalTimeoutPolicy.deadlineNanoseconds
        )
        guard let request = self.activeJournalRequests.removeValue(forKey: requestKey) else { return }
        request.continuation.resume(throwing: BridgeError.timeout)
      }
    }
  }

  static func journalOperationWireMessage(
    type: String,
    operation: String,
    clientId: String,
    requestId: String,
    ownerId: String?,
    surface: AgentSurfaceReference,
    payload: [String: Any]
  ) -> [String: Any] {
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
    if let ownerId { dictionary["ownerId"] = ownerId }
    for (key, value) in payload { dictionary[key] = value }
    return dictionary
  }

  private func markRuntimeOwnerAuthorityDirty() {
    cancelAuthorizedToolExecutionTasks()
    runtimeOwnerAuthorityEpoch &+= 1
    synchronizedRuntimeOwnerID = nil
    synchronizedRuntimeCredentialOwnerID = nil
    for clientID in Array(clients.keys) {
      clients[clientID]?.authAuthorizationSnapshot = nil
      clients[clientID]?.onAuthRequired = nil
      clients[clientID]?.onAuthSuccess = nil
    }
  }

  private func markRuntimeOwnerAuthoritySynchronized(
    ownerID: String,
    includesCredentials: Bool
  ) {
    let normalized = ownerID.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalized.isEmpty else { return }
    if synchronizedRuntimeOwnerID != normalized
      && synchronizedRuntimeCredentialOwnerID != normalized
    {
      synchronizedRuntimeCredentialOwnerID = nil
    }
    synchronizedRuntimeOwnerID = normalized
    if includesCredentials {
      synchronizedRuntimeCredentialOwnerID = normalized
    }
  }

  @discardableResult
  func refreshAuthToken(
    _ token: String,
    expectedOwnerId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) -> Bool {
    if let authorizationSnapshot,
      !RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
    {
      return false
    }
    let activeOwnerId = currentOwnerId()
    guard
      let message = Self.refreshTokenWireMessage(
        token: token,
        expectedOwnerId: expectedOwnerId,
        currentOwnerId: activeOwnerId
      )
    else {
      _ = observeDirectControlOwner(activeOwnerId)
      return false
    }
    let authorizedOwnerID = message["ownerId"] as? String ?? expectedOwnerId
    _ = observeDirectControlOwner(authorizedOwnerID)
    let sent = sendJson(message)
    if sent {
      markRuntimeOwnerAuthoritySynchronized(
        ownerID: authorizedOwnerID,
        includesCredentials: true)
    }
    return sent
  }

  nonisolated static func refreshTokenWireMessage(
    token: String,
    expectedOwnerId: String,
    currentOwnerId: String?
  ) -> [String: Any]? {
    let expected = expectedOwnerId.trimmingCharacters(in: .whitespacesAndNewlines)
    let current = currentOwnerId?.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !token.isEmpty, !expected.isEmpty, current == expected else { return nil }
    return [
      "type": "refresh_token",
      "token": token,
      "ownerId": expected,
    ]
  }

  /// Establishes daemon owner authority for local adapters that do not consume
  /// a Firebase token. This must precede every owner-scoped session/journal RPC.
  @discardableResult
  func refreshRuntimeOwner(
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) -> Bool {
    if let authorizationSnapshot,
      !RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
    {
      _ = observeDirectControlOwner(nil)
      return false
    }
    guard let ownerId = authorizationSnapshot?.ownerID ?? currentOwnerId(), !ownerId.isEmpty,
      expectedOwnerId == nil
        || expectedOwnerId?.trimmingCharacters(in: .whitespacesAndNewlines) == ownerId
    else {
      _ = observeDirectControlOwner(nil)
      return false
    }
    _ = observeDirectControlOwner(ownerId)
    let sent = sendJson(Self.runtimeOwnerHandshakeWireMessage(ownerId: ownerId))
    if sent {
      markRuntimeOwnerAuthoritySynchronized(
        ownerID: ownerId,
        includesCredentials: false)
    }
    return sent
  }

  static func runtimeOwnerHandshakeWireMessage(ownerId: String) -> [String: Any] {
    [
      "type": "refresh_owner",
      "ownerId": ownerId,
    ]
  }

  func directControlTool(
    clientId: String,
    harnessMode: String,
    name: String,
    input: RuntimeJSONPayloadBox,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> String {
    guard
      let authorizationSnapshot = authorizationSnapshot
        ?? RuntimeOwnerIdentity.captureAuthorizationSnapshot()
    else {
      throw BridgeError.authMissing
    }
    try assertAuthorization(authorizationSnapshot)
    let ownerId = authorizationSnapshot.ownerID
    return try await sendDirectControlTool(
      clientId: clientId,
      harnessMode: harnessMode,
      name: name,
      input: input.value,
      ownerId: ownerId,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  #if DEBUG
    func debugAutomationControlTool(
      clientId: String,
      harnessMode: String,
      name: String,
      input: RuntimeJSONPayloadBox,
      ownerId: String
    ) async throws -> String {
      guard AppBuild.isNonProduction else {
        throw BridgeError.agentError("Automation control is disabled on production bundles")
      }
      return try await sendDirectControlTool(
        clientId: clientId,
        harnessMode: harnessMode,
        name: name,
        input: input.value,
        ownerId: ownerId,
        authorizationSnapshot: RuntimeOwnerIdentity.captureAuthorizationSnapshot(
          expectedOwnerID: ownerId)
      )
    }
  #endif

  private func sendDirectControlTool(
    clientId: String,
    harnessMode: String,
    name: String,
    input: [String: Any],
    ownerId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> String {
    guard let authorizationSnapshot else {
      throw BridgeError.authMissing
    }
    // A direct control call is an owner-scoped request on the already-live
    // JSONL bridge, not a new interactive client. Re-registering it on every
    // read mutates the startup lease and can queue a small canonical read
    // behind concurrent projection work. Only acquire a client lease while
    // there is no completed runtime handshake to carry this request.
    if !isBridgeReady {
      try await registerClient(
        clientId: clientId,
        harnessMode: harnessMode,
        authorizationSnapshot: authorizationSnapshot)
    }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      throw BridgeError.authMissing
    }
    guard advertisedAgentControlTools.contains(name) else {
      throw BridgeError.agentError("Agent runtime does not advertise direct control tool \(name)")
    }

    let requestId = UUID().uuidString
    let requestKey = RuntimeMessage.RequestKey(clientId: clientId, requestId: requestId)
    let ownerEpoch = observeDirectControlOwner(ownerId)
    let timeoutNanoseconds = Self.directControlTimeoutNanoseconds(for: name)
    return try await withCheckedThrowingContinuation { continuation in
      activeControlRequests[requestKey] = ActiveControlRequest(
        clientId: clientId,
        requestId: requestId,
        expectedOwnerId: ownerId,
        expectedOwnerEpoch: ownerEpoch,
        authorizationSnapshot: authorizationSnapshot,
        continuation: continuation
      )
      activeControlTimeoutTasks[requestKey] = Task.detached { [weak self] in
        try? await Task.sleep(nanoseconds: timeoutNanoseconds)
        guard !Task.isCancelled else { return }
        await self?.timeoutControlRequest(requestKey, toolName: name)
      }
      let dict = Self.directControlToolWireMessage(
        clientId: clientId,
        requestId: requestId,
        ownerId: ownerId,
        name: name,
        input: input)
      let sent = sendJson(dict)
      if !sent, let request = takeActiveControlRequest(requestKey) {
        request.continuation.resume(throwing: BridgeError.agentError("Failed to send direct control tool request"))
      }
    }
  }

  /// Direct control reads are intentionally short so reconciliation cannot
  /// block on a stalled runtime. Commands that synchronously return a child
  /// run's result must instead use the full agent-run deadline: a 15-second
  /// transport timeout can otherwise abandon a valid continuation while the
  /// runtime is still completing it.
  nonisolated static func directControlTimeoutNanoseconds(for toolName: String) -> UInt64 {
    switch toolName {
    case "list_agent_sessions", "get_agent_run", "build_desktop_awareness_snapshot":
      return 2_000_000_000
    case "run_agent_and_wait", "send_agent_message":
      return 180_000_000_000
    default:
      return 15_000_000_000
    }
  }

  private func takeActiveControlRequest(
    _ requestKey: RuntimeMessage.RequestKey
  ) -> ActiveControlRequest? {
    activeControlTimeoutTasks.removeValue(forKey: requestKey)?.cancel()
    return activeControlRequests.removeValue(forKey: requestKey)
  }

  private func timeoutControlRequest(
    _ requestKey: RuntimeMessage.RequestKey,
    toolName: String
  ) {
    guard let request = takeActiveControlRequest(requestKey) else { return }
    log("AgentRuntimeProcess: direct control tool timed out name=\(toolName)")
    request.continuation.resume(throwing: BridgeError.timeout)
  }

  static func directControlToolWireMessage(
    clientId: String,
    requestId: String,
    ownerId: String,
    name: String,
    input: [String: Any]
  ) -> [String: Any] {
    [
      "type": "direct_control_tool",
      "protocolVersion": 2,
      "requestId": requestId,
      "clientId": clientId,
      "ownerId": ownerId,
      "name": name,
      "input": input,
    ]
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

  func interrupt(
    clientId: String,
    requestId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
    let requestKey = RuntimeMessage.RequestKey(clientId: clientId, requestId: requestId)
    guard var request = activeRequests[requestKey] else { return }
    guard request.authorizationSnapshot == authorizationSnapshot else { return }
    request.isInterrupted = true
    activeRequests[requestKey] = request
    var dict: [String: Any] = [
      "type": "interrupt",
      "protocolVersion": 2,
      "requestId": requestId,
      "clientId": clientId,
    ]
    dict["ownerId"] = authorizationSnapshot.ownerID
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
    producingTurnId: String?,
    expectedContext: AgentContextFreshness?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    onTextDelta: @escaping AgentBridge.TextDeltaHandler,
    onToolActivity: @escaping AgentBridge.ToolActivityHandler,
    onThinkingDelta: @escaping AgentBridge.ThinkingDeltaHandler,
    onToolResultDisplay: @escaping AgentBridge.ToolResultDisplayHandler,
    onAuthRequired: @escaping AgentBridge.AuthRequiredHandler,
    onAuthSuccess: @escaping AgentBridge.AuthSuccessHandler
  ) async throws -> AgentBridge.QueryResult {
    guard isBridgeReady else { throw BridgeError.stopped }
    try assertAuthorization(authorizationSnapshot)

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
        authorizationSnapshot: authorizationSnapshot,
        continuation: continuation
      )
      activeRequests[RuntimeMessage.RequestKey(clientId: clientId, requestId: requestId)] = request
      Task { @MainActor in
        AgentRuntimeStatusStore.shared.beginRequest(surface: surfaceRef)
      }

      let queryDict = Self.queryWireMessage(
        clientId: clientId,
        requestId: requestId,
        ownerId: authorizationSnapshot.ownerID,
        sessionId: sessionId,
        prompt: prompt,
        mode: mode,
        imageData: imageData,
        attachments: attachments,
        producingTurnId: producingTurnId,
        expectedContext: expectedContext
      )
      sendJson(queryDict)
    }
  }

  private func startProcess(
    preferredHarnessMode: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    admissionAuthorityEpoch: UInt64
  ) async throws {
    let startupIsInFlight: Bool
    if bridgeLifecycle.state == .starting {
      startupIsInFlight = await startupSingleFlight.hasActiveAttempt()
    } else {
      startupIsInFlight = false
    }
    if AgentRuntimeStartupAdmission.shouldJoin(
      lifecycleState: bridgeLifecycle.state,
      hasActiveStartupAttempt: startupIsInFlight
    ) {
      try await waitForInit(timeout: 30.0)
      try assertAuthorization(authorizationSnapshot)
      return
    }
    _ = bridgeLifecycle.reduce(.spawn)
    let key = StartupKey(
      authorizationSnapshot: authorizationSnapshot,
      admissionAuthorityEpoch: admissionAuthorityEpoch)
    let receipt: StartupReceipt
    do {
      receipt = try await startupSingleFlight.run(key: key) { [weak self] in
        guard let self else { throw BridgeError.stopped }
        return try await self.performStartProcess(
          preferredHarnessMode: preferredHarnessMode,
          authorizationSnapshot: authorizationSnapshot,
          admissionAuthorityEpoch: admissionAuthorityEpoch)
      }
    } catch {
      if [.starting, .failedStart].contains(bridgeLifecycle.state) {
        let failure = Self.startFailure(for: error)
        if bridgeLifecycle.state == .starting {
          recordBridgeStartFailure(failure)
        }
        if let bridgeError = error as? BridgeError, case .authMissing = bridgeError {
          throw error
        }
        if let bridgeError = error as? BridgeError, case .failedToStart(_) = bridgeError {
          throw bridgeError
        }
        throw BridgeError.failedToStart(failure)
      }
      throw error
    }
    guard bridgeLifecycle.state == .running, process?.isRunning == true,
      processGeneration == receipt.processGeneration,
      runtimeOwnerAuthorityEpoch == receipt.authorityEpoch,
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
    else {
      throw BridgeError.authMissing
    }
  }

  private func performStartProcess(
    preferredHarnessMode: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    admissionAuthorityEpoch: UInt64
  ) async throws -> StartupReceipt {
    // `startProcess` owns the launch through `startupSingleFlight`. Do not use
    // the reducer's `.starting` state as a join signal here: the launch owner
    // intentionally sets it *before* this operation is scheduled.
    guard process?.isRunning != true else {
      try await waitForInit(timeout: 30.0)
      try assertAuthorization(authorizationSnapshot)
      return StartupReceipt(
        authorityEpoch: runtimeOwnerAuthorityEpoch,
        processGeneration: processGeneration)
    }
    // A previous process may have exited while a non-cooperative physical tool
    // task was still unwinding. Never launch/re-authorize a replacement daemon
    // until every old-owner Swift execution has actually returned.
    await cancelAndDrainAuthorizedToolExecutionTasks()
    if process?.isRunning == true {
      try await waitForInit(timeout: 30.0)
      try assertAuthorization(authorizationSnapshot)
      return StartupReceipt(
        authorityEpoch: runtimeOwnerAuthorityEpoch,
        processGeneration: processGeneration)
    }
    try assertStartupAuthority(
      authorizationSnapshot,
      expectedAuthorityEpoch: admissionAuthorityEpoch)
    guard let preferredHarness = AgentRuntimeRouting.harnessMode(from: preferredHarnessMode) else {
      log("AgentRuntimeProcess: refusing unknown harness mode \(preferredHarnessMode)")
      throw BridgeError.agentError("Unknown AI runtime mode: \(preferredHarnessMode)")
    }
    let preferredAdapterId = AgentRuntimeRouting.adapterId(for: preferredHarness)

    process = nil
    closePipes()
    lastExitWasOOM = false
    advertisedAgentControlTools.removeAll()
    runtimeAdapterIDs.removeAll()
    negotiatedProtocolVersion = nil
    negotiatedRuntimeVersion = nil

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
    try assertStartupAuthority(
      authorizationSnapshot,
      expectedAuthorityEpoch: admissionAuthorityEpoch)
    if !rustBase.isEmpty {
      env["OMI_API_BASE_URL"] = rustBase.hasSuffix("/") ? "\(rustBase)v2" : "\(rustBase)/v2"
    } else if preferredAdapterId == .piMono {
      log("AgentRuntimeProcess: pi-mono start refused, OMI_DESKTOP_API_URL is not configured")
      throw BridgeError.bridgeScriptNotFound
    }

    Self.removeInheritedBYOKEnvironment(from: &env)
    let byok = await Self.usableBYOKEnvironment()
    try assertStartupAuthority(
      authorizationSnapshot,
      expectedAuthorityEpoch: admissionAuthorityEpoch)
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
    let authHeader = try? await authService.getAuthHeader(
      forceRefresh: forceRefreshToken,
      expectedUserId: authorizationSnapshot.ownerID)
    try assertStartupAuthority(
      authorizationSnapshot,
      expectedAuthorityEpoch: admissionAuthorityEpoch)
    if let authHeader,
      let token = Self.bearerToken(from: authHeader)
    {
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

    try assertStartupAuthority(
      authorizationSnapshot,
      expectedAuthorityEpoch: admissionAuthorityEpoch)
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

    do {
      try proc.run()
      markRuntimeOwnerAuthorityDirty()
      let launchedAuthorityEpoch = runtimeOwnerAuthorityEpoch
      if env["OMI_AUTH_TOKEN"]?.isEmpty == false {
        synchronizedRuntimeCredentialOwnerID = authorizationSnapshot.ownerID
      }
      startReadingStdout()

      try await waitForInit(timeout: 30.0)
      try assertStartupAuthority(
        authorizationSnapshot,
        expectedAuthorityEpoch: launchedAuthorityEpoch)
      return StartupReceipt(
        authorityEpoch: launchedAuthorityEpoch,
        processGeneration: expectedGeneration)
    } catch {
      await cleanupFailedStart(process: proc, error: error)
      throw BridgeError.failedToStart(Self.startFailure(for: error))
    }
  }

  private func applyLocalAgentEnvironment(to env: inout [String: String]) {
    // Seed auto-discovered commands for every local adapter so the shared Node
    // process can route to Hermes or OpenClaw even when it was launched for a
    // different adapter. registerClient returns early once the reducer is
    // startup adapter's env would otherwise be the only one the process sees.
    let home = NSHomeDirectory()
    if env["HOME"]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true {
      env["HOME"] = home
    }
    if env["HERMES_HOME"]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true {
      env["HERMES_HOME"] = "\(home)/.hermes"
    }

    let adapterPathDirs = Self.localAdapterSearchDirectories(home: home)
    let existingPath = env["PATH"] ?? "/usr/bin:/bin"
    var pathElements: [String] = []
    for path in existingPath.split(separator: ":").map(String.init) + adapterPathDirs {
      if !pathElements.contains(path) {
        pathElements.append(path)
      }
    }
    env["PATH"] = pathElements.joined(separator: ":")

    // The same injected PATH/home contract used by the testable detector feeds
    // the Node registry. PTT receives only the registry projection later; it
    // never performs a competing executable lookup of its own.
    if env["OMI_HERMES_ADAPTER_COMMAND"]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true,
      case .available(command: let hermes) = LocalAgentProviderDetector.availability(
        for: .hermes,
        environment: env,
        homeDirectory: home
      ).status
    {
      env["OMI_HERMES_ADAPTER_COMMAND"] = "\(Self.shellQuote(hermes)) acp"
    }

    if env["OMI_OPENCLAW_ADAPTER_COMMAND"]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true,
      case .available(command: let openClaw) = LocalAgentProviderDetector.availability(
        for: .openclaw,
        environment: env,
        homeDirectory: home
      ).status
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

  /// Directly launched app bundles do not inherit the shell's FNM multishell
  /// PATH entry. Search the stable Node-install roots as well, so a globally
  /// installed OpenClaw CLI remains available to the shared agent bridge.
  static func localAdapterSearchDirectories(
    home: String,
    fileManager: FileManager = .default
  ) -> [String] {
    let adapterPathDirs = [
      "\(home)/.hermes/hermes-agent/venv/bin",
      "\(home)/.hermes/node/bin",
      "\(home)/.hermes/hermes-agent",
      "\(home)/.local/bin",
    ]
    let managedNodeRoots = [
      "\(home)/.nvm/versions/node",
      "\(home)/.fnm/node-versions",
      "\(home)/.local/share/fnm/node-versions",
      "\(home)/.nodenv/versions",
      "\(home)/.asdf/installs/nodejs",
    ]
    // User-managed Node installations take precedence over machine-wide fallbacks.
    return Self.uniquePaths(
      adapterPathDirs
        + managedNodeRoots.flatMap {
          Self.nodeInstallBinDirectories(root: $0, fileManager: fileManager)
        }
        + [
          "/opt/homebrew/bin",
          "/usr/local/bin",
        ])
  }

  private static func nodeInstallBinDirectories(root: String, fileManager: FileManager) -> [String] {
    guard let versions = try? fileManager.contentsOfDirectory(atPath: root) else { return [] }
    return versions.compactMap { version in
      let versionDirectory = (root as NSString).appendingPathComponent(version)
      let directBin = (versionDirectory as NSString).appendingPathComponent("bin")
      if fileManager.fileExists(atPath: directBin) { return directBin }
      let installationBin = (versionDirectory as NSString).appendingPathComponent("installation/bin")
      if fileManager.fileExists(atPath: installationBin) { return installationBin }
      return nil
    }
  }

  private static func uniquePaths(_ paths: [String]) -> [String] {
    paths.reduce(into: [String]()) { result, path in
      guard !path.isEmpty, !result.contains(path) else { return }
      result.append(path)
    }
  }

  private nonisolated static func bearerToken(from header: String) -> String? {
    let prefix = "Bearer "
    guard header.hasPrefix(prefix) else { return nil }
    let token = String(header.dropFirst(prefix.count))
      .trimmingCharacters(in: .whitespacesAndNewlines)
    return token.isEmpty ? nil : token
  }

  private static func shellQuote(_ value: String) -> String {
    "'\(value.replacingOccurrences(of: "'", with: "'\\''"))'"
  }

  static func firstExecutable(
    named name: String,
    in directories: [String],
    fileManager: FileManager = .default
  ) -> String? {
    for dir in directories {
      let path = (dir as NSString).appendingPathComponent(name)
      if fileManager.isExecutableFile(atPath: path) {
        return path
      }
    }
    return nil
  }

  static func startFailure(for error: Error) -> AgentRuntimeBridgeLifecycle.StartFailure {
    guard let bridgeError = error as? BridgeError else { return .launchFailed }
    switch bridgeError {
    case .timeout:
      return .handshakeTimedOut
    case .processExited, .outOfMemory:
      return .exitedDuringStartup
    case .agentError:
      return .incompatibleHandshake
    case .nodeNotFound, .bridgeScriptNotFound, .notRunning, .encodingError,
      .failedToStart, .stopped, .restarting, .requestAlreadyActive,
      .agentRuntimeFailure, .quotaExceeded, .authMissing:
      return .launchFailed
    }
  }

  /// A terminal kernel turn is a durable replay boundary. Feed the reducer at
  /// the runtime boundary rather than maintaining a second ad-hoc set in each
  /// chat or PTT surface.
  private func recordLifecycleJournalMutation(_ turn: KernelJournalTurn) {
    _ = bridgeLifecycle.reduce(
      .kernelJournalWrite(
        turnID: turn.turnId,
        terminal: turn.status == .completed || turn.status == .failed))
  }

  private func recordBridgeStartFailure(_ failure: AgentRuntimeBridgeLifecycle.StartFailure) {
    let effects = bridgeLifecycle.reduce(.spawnFailure(failure))
    guard effects.contains(.surfaceFailedStart(failure)) else { return }
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "agent_runtime",
      from: "starting",
      to: "failed_start",
      reason: failure.rawValue,
      outcome: .exhausted,
      extra: [
        "failure_class": failure.rawValue,
        "recovery_action": "retry_start",
        "recovery_result": "exhausted",
      ])
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
        while failedProcess.isRunning {
          try? await Task.sleep(nanoseconds: 20_000_000)
        }
      }
    }
    if let currentProcess = process, currentProcess === failedProcess {
      process = nil
    }
    closePipes()
    recordBridgeStartFailure(Self.startFailure(for: error))
    await cancelAndDrainAuthorizedToolExecutionTasks()
    markRuntimeOwnerAuthorityDirty()
    advertisedAgentControlTools.removeAll()
    runtimeAdapterIDs.removeAll()
    negotiatedProtocolVersion = nil
    negotiatedRuntimeVersion = nil
    resumeAllRequests(throwing: BridgeError.stopped)
    resumeInitContinuations(throwing: BridgeError.stopped)
  }

  private func waitForInit(timeout: TimeInterval) async throws {
    if bridgeLifecycle.state == .running { return }

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
    if bridgeLifecycle.state == .running {
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
    await cancelAndDrainAuthorizedToolExecutionTasks()
    markRuntimeOwnerAuthorityDirty()
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
        while proc.isRunning {
          try? await Task.sleep(nanoseconds: 20_000_000)
        }
      }
    }

    process = nil
    closePipes()
    lastExitWasOOM = false
    oomDiagnosticLatch.reset(generation: processGeneration)
    _ = bridgeLifecycle.reduce(.kill)
    advertisedAgentControlTools.removeAll()
    runtimeAdapterIDs.removeAll()
    negotiatedProtocolVersion = nil
    negotiatedRuntimeVersion = nil
    resumeAllRequests(throwing: error)
    resumeInitContinuations(throwing: error)
  }

  private func startReadingStdout() {
    guard let stdoutPipe else { return }
    let expectedGeneration = processGeneration
    stdoutBuffer.reset()
    let chunkReader = AgentRuntimeStdoutChunkReader()

    let handle = stdoutPipe.fileHandleForReading
    handle.readabilityHandler = { [weak self] handle in
      let chunk = chunkReader.read(from: handle)
      guard !chunk.data.isEmpty else {
        handle.readabilityHandler = nil
        return
      }
      Task { [weak self] in
        await self?.processStdoutData(
          chunk.data,
          sequence: chunk.sequence,
          generation: expectedGeneration
        )
      }
    }
  }

  private func processStdoutData(_ data: Data, sequence: UInt64, generation: UInt64) {
    // Drop stdout chunks from a previous process generation. When the bridge is
    // restarted or startup cleanup closes the pipe, a readability callback that
    // already captured the old data can still fire after the new process has
    // begun. Without this guard, stale init/result lines from the old Node
    // process could mutate the new process state or resume the wrong continuation.
    if generation != processGeneration {
      log("AgentRuntimeProcess: dropping stale stdout chunk (gen=\(generation), current=\(processGeneration))")
      return
    }
    for lineData in stdoutBuffer.ingest(data, sequence: sequence) {
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
      let authorizationSnapshot = request.authorizationSnapshot
      Task { @MainActor in
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
          return
        }
        AgentRuntimeStatusStore.shared.ingest(message: message, surface: surfaceRef)
      }
    }

    switch message.kind {
    case .initMessage:
      let handshake: RuntimeHandshake
      do {
        handshake = try Self.validateRuntimeHandshake(message)
      } catch {
        log("AgentRuntimeProcess: rejecting incompatible runtime handshake")
        resumeInitContinuations(throwing: error)
        return
      }
      negotiatedProtocolVersion = handshake.protocolVersion
      negotiatedRuntimeVersion = handshake.runtimeVersion
      log(
        "AgentRuntimeProcess: bridge ready "
          + "(protocol=\(message.protocolVersion.map(String.init) ?? "unknown"), "
          + "runtime=\(negotiatedRuntimeVersion ?? "unknown"))")
      let tools = message.payload["agentControlTools"] as? [String] ?? []
      advertisedAgentControlTools = Set(tools)
      runtimeAdapterIDs = Set(message.payload["runtimeAdapterIds"] as? [String] ?? [])
      _ = bridgeLifecycle.reduce(.handshakeSucceeded)
      resolveInitContinuations()
      Task { @MainActor in
        NotificationCenter.default.post(name: .agentRuntimeDidBecomeReady, object: nil)
      }

    case .authRequired:
      let methods = message.payload["methods"] as? [[String: Any]] ?? []
      let authUrl = message.payload["authUrl"] as? String
      if let request = routedRequest(for: message) {
        request.onAuthRequired(methods, authUrl)
      } else if message.requestKey == nil {
        let eventOwnerID = message.payload["ownerId"] as? String
        for client in clients.values
        where client.authAuthorizationSnapshot.map({ snapshot in
          RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot)
            && (eventOwnerID == nil || snapshot.ownerID == eventOwnerID)
        }) == true {
          client.onAuthRequired?(methods, authUrl)
        }
      }

    case .authSuccess:
      if let request = routedRequest(for: message) {
        request.onAuthSuccess()
      } else if message.requestKey == nil {
        let eventOwnerID = message.payload["ownerId"] as? String
        for client in clients.values
        where client.authAuthorizationSnapshot.map({ snapshot in
          RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot)
            && (eventOwnerID == nil || snapshot.ownerID == eventOwnerID)
        }) == true {
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
      guard messageOwnerIsCurrentlyAuthorized(message) else {
        completeAuthorizedToolExecution(
          payload: message.payload,
          outcome: "failed",
          result: Self.authorizedToolExecutionError(.ownerChangedDuringExecution))
        return
      }
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
      if messageOwnerIsCurrentlyAuthorized(message), let turn = journalTurn(from: message) {
        recordLifecycleJournalMutation(turn)
        journalTurnChangedHandler?(turn)
      }

    case .journalBackendSync:
      if messageOwnerIsCurrentlyAuthorized(message) { handleJournalBackendSync(message) }

    case .journalBackendDelete:
      if messageOwnerIsCurrentlyAuthorized(message) { handleJournalBackendDelete(message) }

    case .journalBackendReconcile:
      if messageOwnerIsCurrentlyAuthorized(message) { handleJournalBackendReconcile(message) }

    case .chatFirstDeferralDelivery:
      if messageOwnerIsCurrentlyAuthorized(message) { handleChatFirstDeferralDelivery(message) }

    case .defaultExecutionProfileConfigured, .surfaceSessionResolved,
      .sessionExecutionProfileMigrated, .contextSourceUpdated, .contextSnapshot,
      .legacyMainChatSessionsImported,
      .externalSurfaceRunBeginResult, .externalSurfaceToolResult,
      .externalSurfaceRunCompleteResult, .ownerRuntimeRevoked:
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
      guard let request = activeRequests[requestKey],
        RuntimeOwnerIdentity.isAuthorizationCurrent(request.authorizationSnapshot)
      else { return nil }
      return request
    }
    return nil
  }

  private func messageOwnerIsCurrentlyAuthorized(_ message: RuntimeMessage) -> Bool {
    guard let ownerID = message.payload["ownerId"] as? String else { return false }
    return RuntimeOwnerIdentity.captureAuthorizationSnapshot(
      expectedOwnerID: ownerID) != nil
  }

  private func completeKernelContractRequest(_ message: RuntimeMessage) {
    guard let requestKey = message.requestKey else {
      log("AgentRuntimeProcess: dropping unroutable kernel contract response")
      return
    }
    guard let request = activeKernelContractRequests.removeValue(forKey: requestKey) else {
      guard let timedOut = timedOutKernelContractRequests.removeValue(forKey: requestKey) else {
        log("AgentRuntimeProcess: dropping unroutable kernel contract response")
        return
      }
      let elapsedMilliseconds = Int(
        (ProcessInfo.processInfo.systemUptime - timedOut.timedOutAtUptime) * 1_000
      )
      log(
        "AgentRuntimeProcess: dropping late kernel contract response operation=\(timedOut.operation) "
          + "expected=\(String(describing: timedOut.expectedKind)) "
          + "received=\(String(describing: message.kind)) late_ms=\(elapsedMilliseconds)"
      )
      return
    }
    timedOutKernelContractRequests.removeValue(forKey: requestKey)
    guard request.expectedKind == message.kind else {
      log(
        "AgentRuntimeProcess: kernel contract response type mismatch operation=\(request.operation) "
          + "expected=\(String(describing: request.expectedKind)) received=\(String(describing: message.kind))"
      )
      request.continuation.resume(
        throwing: BridgeError.agentError("Kernel contract response type did not match its request")
      )
      return
    }
    if let authorizationSnapshot = request.authorizationSnapshot,
      !RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
    {
      request.continuation.resume(throwing: BridgeError.authMissing)
      return
    }
    request.continuation.resume(returning: RuntimeJSONPayloadBox(message.payload))
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

    guard
      let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(
        expectedOwnerID: command.ownerID)
    else {
      completeAuthorizedToolExecution(
        command: command,
        executionResult: .failed(
          Self.authorizedToolExecutionError(.ownerChangedDuringExecution)))
      return
    }

    let executionID = UUID()
    let executionTask = Task {
      defer { activeAuthorizedToolExecutionTasks.removeValue(forKey: executionID) }
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
          originatingSessionID: command.sessionID,
          originatingRunId: command.runID,
          originatingAttemptId: command.attemptID,
          toolCapabilityRef: command.capabilityRef,
          chatFirstControlGeneration: command.chatFirstControlGeneration,
          originatingUserText: command.originatingUserText,
          isOnboardingSurface: command.surfaceKind == "onboarding",
          expectedOwnerID: command.ownerID,
          authorizationSnapshot: authorizationSnapshot)
        if !Task.isCancelled,
          RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
        {
          executionResult = .succeeded(result)
        } else {
          return
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
      guard !Task.isCancelled,
        RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
      else { return }
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
    activeAuthorizedToolExecutionTasks[executionID] = executionTask
  }

  private func cancelAuthorizedToolExecutionTasks() {
    activeAuthorizedToolExecutionTasks.values.forEach { $0.cancel() }
  }

  private func cancelAndDrainAuthorizedToolExecutionTasks() async {
    let tasks = Array(activeAuthorizedToolExecutionTasks.values)
    await Self.cancelAndAwaitPhysicalExecutionTasks(tasks)
  }

  /// Shared linearization primitive: cancellation requests revocation, while
  /// awaiting every task proves no non-cooperative physical effect can outlive
  /// the owner transition that is about to expose a replacement account.
  nonisolated static func cancelAndAwaitPhysicalExecutionTasks(
    _ tasks: [Task<Void, Never>]
  ) async {
    tasks.forEach { $0.cancel() }
    for task in tasks { await task.value }
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
    sendJson(
      Self.authorizedToolExecutionResultWireMessage(
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
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(request.authorizationSnapshot) else {
      request.continuation.resume(throwing: BridgeError.authMissing)
      return
    }
    expectedCancelledRequests.remove(requestKey)
    request.continuation.resume(returning: queryResult(from: message))
  }

  private func completeControlRequest(_ message: RuntimeMessage) {
    guard let requestKey = message.requestKey,
      let request = takeActiveControlRequest(requestKey)
    else {
      log("AgentRuntimeProcess: dropping unroutable control tool result")
      return
    }
    let activeOwnerId = currentOwnerId()
    let activeOwnerEpoch = observeDirectControlOwner(activeOwnerId)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(request.authorizationSnapshot),
      Self.isDirectControlResultOwnerCurrent(
        expectedOwnerId: request.expectedOwnerId,
        expectedOwnerEpoch: request.expectedOwnerEpoch,
        resultOwnerId: message.payload["ownerId"] as? String,
        currentOwnerId: activeOwnerId,
        currentOwnerEpoch: activeOwnerEpoch)
    else {
      log("AgentRuntimeProcess: rejecting stale direct control result for owner transition")
      request.continuation.resume(
        throwing: BridgeError.agentError("direct_control_owner_revoked"))
      return
    }
    request.continuation.resume(returning: message.payload["result"] as? String ?? "")
  }

  static func isDirectControlResultOwnerCurrent(
    expectedOwnerId: String,
    expectedOwnerEpoch: UInt64,
    resultOwnerId: String?,
    currentOwnerId: String?,
    currentOwnerEpoch: UInt64
  ) -> Bool {
    guard !expectedOwnerId.isEmpty,
      resultOwnerId == expectedOwnerId,
      currentOwnerId == expectedOwnerId,
      currentOwnerEpoch == expectedOwnerEpoch
    else {
      return false
    }
    return true
  }

  @discardableResult
  private func observeDirectControlOwner(_ ownerId: String?) -> UInt64 {
    if observedDirectControlOwnerId != ownerId {
      directControlOwnerEpoch &+= 1
      observedDirectControlOwnerId = ownerId
    }
    return directControlOwnerEpoch
  }

  private func completeJournalRequest(_ message: RuntimeMessage) {
    guard let requestKey = message.requestKey,
      let request = activeJournalRequests.removeValue(forKey: requestKey)
    else {
      log("AgentRuntimeProcess: dropping unroutable journal result")
      return
    }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(request.authorizationSnapshot) else {
      request.continuation.resume(throwing: BridgeError.authMissing)
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
    let generationBaseTurnSeq =
      message.payload["generationBaseTurnSeq"] as? Int
      ?? turns.map(\.turnSeq).min().map { max(0, $0 - 1) }
      ?? (conversationGeneration > 1 ? highWaterTurnSeq : 0)
    request.continuation.resume(
      returning: JournalOperationResult(
        operation: message.payload["operation"] as? String ?? "",
        conversationId: message.payload["conversationId"] as? String ?? turn?.conversationId ?? turns.first?
          .conversationId ?? "",
        turn: turn,
        turns: turns,
        clearedCount: message.payload["clearedCount"] as? Int ?? 0,
        highWaterTurnSeq: highWaterTurnSeq,
        conversationGeneration: conversationGeneration,
        generationBaseTurnSeq: generationBaseTurnSeq,
        accepted: message.payload["accepted"] as? Bool,
        duplicate: message.payload["duplicate"] as? Bool,
        continuityKey: message.payload["continuityKey"] as? String,
        suppressedByTailQuestion: message.payload["suppressedByTailQuestion"] as? Bool ?? false,
        suppressedByStreamingTail: message.payload["suppressedByStreamingTail"] as? Bool ?? false,
        materializationStoppedByTail: message.payload["materializationStoppedByTail"] as? Bool ?? false,
        materializationReceipts: Self.chatFirstMaterializationReceipts(
          from: message.payload["materializationReceipts"]
        ),
        acknowledgedReceiptCount: message.payload["acknowledgedReceiptCount"] as? Int ?? 0,
        coldStartSequenceTerminalReceipts: Self.chatFirstColdStartSequenceTerminalReceipts(
          from: message.payload["coldStartSequenceTerminalReceipts"]
        )
      ))
  }

  private nonisolated static func chatFirstMaterializationReceipts(
    from payload: Any?
  ) -> [ChatFirstMaterializationReceipt] {
    guard let values = payload as? [[String: Any]] else { return [] }
    return values.compactMap { value in
      guard let intentID = value["intentId"] as? String,
        !intentID.isEmpty,
        let receiptID = value["receiptId"] as? String,
        !receiptID.isEmpty
      else { return nil }
      return ChatFirstMaterializationReceipt(intentID: intentID, receiptID: receiptID)
    }
  }

  private nonisolated static func chatFirstColdStartSequenceTerminalReceipts(
    from payload: Any?
  ) -> [ChatFirstColdStartSequenceTerminalReceipt] {
    guard let values = payload as? [[String: Any]] else { return [] }
    return values.compactMap { value in
      guard let sequenceID = value["sequenceId"] as? String,
        !sequenceID.isEmpty,
        let receiptID = value["receiptId"] as? String,
        !receiptID.isEmpty,
        let rawState = value["terminalState"] as? String,
        let terminalState = ChatFirstColdStartSequenceTerminalReceipt.TerminalState(rawValue: rawState)
      else { return nil }
      return ChatFirstColdStartSequenceTerminalReceipt(
        sequenceID: sequenceID,
        receiptID: receiptID,
        terminalState: terminalState
      )
    }
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

  private func handleChatFirstDeferralDelivery(_ message: RuntimeMessage) {
    guard let request = ChatFirstDeferralDeliveryRequest(payload: message.payload) else {
      sendChatFirstDeferralDeliveryResult(
        requestId: message.requestId,
        clientId: message.clientId,
        ownerID: message.payload["ownerId"] as? String,
        continuityKey: message.payload["continuityKey"] as? String ?? "",
        deliveryGeneration: message.payload["deliveryGeneration"] as? Int ?? 0,
        payloadHash: message.payload["payloadHash"] as? String ?? "",
        ok: false,
        errorCode: "chat_first_deferral_malformed"
      )
      return
    }
    Task { [weak self] in
      do {
        try await APIClient.shared.recordChatFirstDeferral(request)
        await self?.sendChatFirstDeferralDeliveryResult(
          requestId: message.requestId,
          clientId: message.clientId,
          ownerID: request.ownerID,
          continuityKey: request.continuityKey,
          deliveryGeneration: request.deliveryGeneration,
          payloadHash: request.payloadHash,
          ok: true,
          errorCode: nil
        )
      } catch {
        await self?.sendChatFirstDeferralDeliveryResult(
          requestId: message.requestId,
          clientId: message.clientId,
          ownerID: request.ownerID,
          continuityKey: request.continuityKey,
          deliveryGeneration: request.deliveryGeneration,
          payloadHash: request.payloadHash,
          ok: false,
          errorCode: Self.boundedChatFirstDeferralErrorCode(for: error)
        )
      }
    }
  }

  private func sendChatFirstDeferralDeliveryResult(
    requestId: String?,
    clientId: String?,
    ownerID: String?,
    continuityKey: String,
    deliveryGeneration: Int,
    payloadHash: String,
    ok: Bool,
    errorCode: String?
  ) {
    var payload: [String: Any] = [
      "type": "chat_first_deferral_delivery_result",
      "protocolVersion": 2,
      "continuityKey": continuityKey,
      "deliveryGeneration": deliveryGeneration,
      "payloadHash": payloadHash,
      "ok": ok,
    ]
    if let requestId { payload["requestId"] = requestId }
    if let clientId { payload["clientId"] = clientId }
    if let ownerID { payload["ownerId"] = ownerID }
    if let errorCode { payload["errorCode"] = errorCode }
    sendJson(payload)
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
      let controlRequest = takeActiveControlRequest(requestKey)
    {
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(controlRequest.authorizationSnapshot) else {
        controlRequest.continuation.resume(throwing: BridgeError.authMissing)
        return
      }
      log("AgentRuntimeProcess: control tool error (raw): \(raw)")
      controlRequest.continuation.resume(
        throwing: failure.map(BridgeError.agentRuntimeFailure) ?? BridgeError.agentError(raw))
      return
    }
    if let requestKey = message.requestKey,
      let journalRequest = activeJournalRequests.removeValue(forKey: requestKey)
    {
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(journalRequest.authorizationSnapshot) else {
        journalRequest.continuation.resume(throwing: BridgeError.authMissing)
        return
      }
      log("AgentRuntimeProcess: journal operation failed (code-only)")
      journalRequest.continuation.resume(
        throwing: failure.map(BridgeError.agentRuntimeFailure) ?? BridgeError.agentError(raw)
      )
      return
    }
    if let requestKey = message.requestKey,
      let contractRequest = activeKernelContractRequests.removeValue(forKey: requestKey)
    {
      if let authorizationSnapshot = contractRequest.authorizationSnapshot,
        !RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
      {
        contractRequest.continuation.resume(throwing: BridgeError.authMissing)
        return
      }
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
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(request.authorizationSnapshot) else {
      request.continuation.resume(throwing: BridgeError.authMissing)
      return
    }
    let bridgeError = failure.map(BridgeError.agentRuntimeFailure) ?? BridgeError.agentError(raw)
    if !bridgeError.isContextSnapshotProjectionMismatch {
      log("AgentRuntimeProcess: agent error (raw): \(raw)")
    }
    request.continuation.resume(throwing: bridgeError)
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
      terminalStatus: payload["terminalStatus"] as? String,
      failure: AgentRuntimeFailure.parse(from: payload["failure"]),
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
    if bridgeLifecycle.state == .starting {
      // A launch is not a running bridge yet. Preserve the start-failure
      // disposition before unblocking its initializer so ChatProvider can
      // offer retry and diagnostics can record the typed fallback.
      recordBridgeStartFailure(Self.startFailure(for: error))
    } else {
      _ = bridgeLifecycle.reduce(.crash)
    }
    markRuntimeOwnerAuthorityDirty()
    advertisedAgentControlTools.removeAll()
    runtimeAdapterIDs.removeAll()
    negotiatedProtocolVersion = nil
    negotiatedRuntimeVersion = nil
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
    let controlTimeoutTasks = activeControlTimeoutTasks.values
    activeControlTimeoutTasks.removeAll()
    for task in controlTimeoutTasks { task.cancel() }
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
    stdoutBuffer.reset()
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
    let bundleComponent =
      (bundleIdentifier?.isEmpty == false ? bundleIdentifier : "com.omi.desktop-dev")
      ?? "com.omi.desktop-dev"
    return
      homeDirectory
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
    let bundleComponent =
      (bundleIdentifier?.isEmpty == false ? bundleIdentifier : "com.omi.desktop-dev")
      ?? "com.omi.desktop-dev"
    return
      homeDirectory
      .appendingPathComponent("Library")
      .appendingPathComponent("Application Support")
      .appendingPathComponent("Omi")
      .appendingPathComponent("Artifacts")
      .appendingPathComponent(bundleComponent)
      .path
  }

  /// Resource lookup must be optional at this boundary. `Bundle.resourceBundle`
  /// intentionally traps when an app bundle is malformed, but SwiftPM test
  /// executables have no app-style `Contents/Resources` root and must be able to
  /// fall through to the system Node candidates without crashing the process.
  nonisolated static func runtimeResourceExecutableCandidates(
    named resourceName: String,
    bundleURLs: [URL],
    executableURL: URL?
  ) -> [String] {
    let bundleName = "Omi Computer_Omi Computer.bundle"
    var candidates: [String] = []
    var seen = Set<String>()
    func append(_ url: URL) {
      let path = url.standardizedFileURL.path
      if seen.insert(path).inserted { candidates.append(path) }
    }
    for bundleURL in bundleURLs {
      append(
        bundleURL
          .appendingPathComponent("Contents/Resources")
          .appendingPathComponent(bundleName)
          .appendingPathComponent(resourceName))
      append(
        bundleURL
          .appendingPathComponent(bundleName)
          .appendingPathComponent(resourceName))
      append(
        bundleURL.deletingLastPathComponent()
          .appendingPathComponent(bundleName)
          .appendingPathComponent(resourceName))
    }
    if let executableDirectory = executableURL?.deletingLastPathComponent() {
      append(
        executableDirectory
          .appendingPathComponent(bundleName)
          .appendingPathComponent(resourceName))
      append(
        executableDirectory.deletingLastPathComponent()
          .appendingPathComponent(bundleName)
          .appendingPathComponent(resourceName))
    }
    return candidates
  }

  private func findNodeBinary() -> String? {
    let bundleURLs =
      [Bundle.main.bundleURL]
      + Bundle.allBundles.map(\.bundleURL)
      + Bundle.allFrameworks.map(\.bundleURL)
    for bundledNode in Self.runtimeResourceExecutableCandidates(
      named: "node",
      bundleURLs: bundleURLs,
      executableURL: Bundle.main.executableURL
    ) where FileManager.default.isExecutableFile(atPath: bundledNode) {
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
