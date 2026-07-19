import Foundation

/// `@preconcurrency` boundary mirroring `AgentArtifactProjectionLoading`. It lets
/// the non-Sendable `[String: Any]` tool/context payloads cross into the
/// `AgentBridge` actor without Sendable conformance, which `[String: Any]` can
/// never satisfy. Each call site forwards an already-copied local value.
@preconcurrency protocol TaskChatRuntimeControlBridge {
  func controlTool(
    name: String,
    input: [String: Any],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> String

  func updateContextSource(
    sessionId: String,
    surfaceKind: String,
    source: AgentContextSource,
    sourceRevision: String,
    outcome: AgentContextSourceOutcome,
    capturedAtMs: Int,
    expiresAtMs: Int?,
    payload: [String: Any],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> AgentContextSourceUpdateReceipt

  #if DEBUG
    func debugAutomationControlTool(
      name: String,
      input: [String: Any],
      ownerId: String
    ) async throws -> String
  #endif
}

extension AgentBridge: @preconcurrency TaskChatRuntimeControlBridge {}
/// `@unchecked Sendable` carrier for the non-Sendable `[String: Any]` tool
/// payloads that must cross from `@MainActor` `TaskChatRuntime` into the
/// `AgentBridge` actor. The box is unwrapped inside the actor (same isolation),
/// so the dictionary never actually races across a boundary.
struct TaskToolInputBox: @unchecked Sendable {
  let value: [String: Any]
  init(_ value: [String: Any]) { self.value = value }
}

extension AgentBridge {
  /// Sendable entry point: accept the boxed payload so the non-Sendable
  /// `[String: Any]` does not itself cross the actor boundary.
  func controlTool(
    name: String,
    input box: TaskToolInputBox,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> String {
    try await controlTool(name: name, input: box.value, authorizationSnapshot: authorizationSnapshot)
  }

  #if DEBUG
    func debugAutomationControlTool(
      name: String,
      input box: TaskToolInputBox,
      ownerId: String
    ) async throws -> String {
      try await debugAutomationControlTool(name: name, input: box.value, ownerId: ownerId)
    }
  #endif
}

/// Shared agent bridge for task-backed workstream surfaces. Session identity and
/// execution truth live in the kernel; this bridge is transport only.
@MainActor
enum TaskChatRuntime {
  struct QueryRouting: Equatable, Sendable {
    let adapterId: String
    let modelProfile: String?
    let workingDirectory: String
    let runMode: String
  }

  private static var agentBridge: AgentBridge?
  private static var activeWorkstreamId: String?

  static func attachJournalEvents(
    workstreamId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    wake: @escaping @Sendable @MainActor () -> Void
  ) async throws -> UUID {
    try requireCurrent(authorizationSnapshot)
    let bridge = try await sharedBridge()
    try requireCurrent(authorizationSnapshot)
    await KernelJournalEventHub.shared.attach(bridge: bridge)
    try requireCurrent(authorizationSnapshot)
    return KernelJournalEventHub.shared.subscribe(
      surface: .workstream(workstreamId: workstreamId),
      wake: wake
    )
  }

  static func listJournalTurns(
    workstreamId: String,
    ownerID: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    afterTurnSeq: Int,
    limit: Int = 100
  ) async throws -> AgentRuntimeProcess.JournalOperationResult {
    try requireCurrent(authorizationSnapshot, expectedOwnerID: ownerID)
    let bridge = try await sharedBridge()
    try requireCurrent(authorizationSnapshot, expectedOwnerID: ownerID)
    return try await bridge.listJournalTurns(
      surface: .workstream(workstreamId: workstreamId),
      ownerID: ownerID,
      afterTurnSeq: afterTurnSeq,
      limit: limit,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  static func recordJournalExchange(
    workstreamId: String,
    ownerID: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    turns: [KernelJournalTurnWrite]
  ) async throws -> AgentRuntimeProcess.JournalOperationResult {
    try requireCurrent(authorizationSnapshot, expectedOwnerID: ownerID)
    let bridge = try await sharedBridge()
    try requireCurrent(authorizationSnapshot, expectedOwnerID: ownerID)
    return try await bridge.recordJournalExchange(
      surface: .workstream(workstreamId: workstreamId),
      ownerID: ownerID,
      turns: turns,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  static func recordJournalMessage(
    workstreamId: String,
    ownerID: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    message: ChatMessage,
    status: KernelJournalTurnStatus,
    continuityKey: String? = nil
  ) async throws -> KernelJournalTurn {
    try requireCurrent(authorizationSnapshot, expectedOwnerID: ownerID)
    let bridge = try await sharedBridge()
    try requireCurrent(authorizationSnapshot, expectedOwnerID: ownerID)
    return try await bridge.recordJournalTurn(
      surface: .workstream(workstreamId: workstreamId),
      ownerID: ownerID,
      turn: message.journalWrite(
        origin: "workstream",
        status: status,
        continuityKey: continuityKey,
        messageSource: "workstream"
      ),
      authorizationSnapshot: authorizationSnapshot
    )
  }

  static func updateJournalMessage(
    workstreamId: String,
    ownerID: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    message: ChatMessage,
    status: KernelJournalTurnStatus? = nil
  ) async throws -> KernelJournalTurn {
    try requireCurrent(authorizationSnapshot, expectedOwnerID: ownerID)
    let bridge = try await sharedBridge()
    try requireCurrent(authorizationSnapshot, expectedOwnerID: ownerID)
    return try await bridge.updateJournalTurn(
      surface: .workstream(workstreamId: workstreamId),
      ownerID: ownerID,
      update: message.journalUpdate(status: status),
      authorizationSnapshot: authorizationSnapshot
    )
  }

  /// Atomically projects the final assistant payload onto the exact canonical
  /// run attempt. The kernel validates run + attempt ownership and derives the
  /// terminal journal status; Swift cannot choose it.
  static func terminalizeJournalMessage(
    workstreamId: String,
    ownerID: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    message: ChatMessage,
    producingRunId: String,
    producingAttemptId: String
  ) async throws -> KernelJournalTurn {
    try requireCurrent(authorizationSnapshot, expectedOwnerID: ownerID)
    let bridge = try await sharedBridge()
    try requireCurrent(authorizationSnapshot, expectedOwnerID: ownerID)
    return try await bridge.terminalizeJournalTurn(
      surface: .workstream(workstreamId: workstreamId),
      ownerID: ownerID,
      terminalization: KernelJournalTurnTerminalization(
        turnId: message.id,
        producingRunId: producingRunId,
        producingAttemptId: producingAttemptId,
        disposition: .accept,
        content: message.text,
        contentBlocksJSON: ChatContentBlockCodec.encode(message.contentBlocks) ?? "[]",
        resourcesJSON: ChatResource.encodeResourcesForPersistence(message.displayResources) ?? "[]"
      ),
      authorizationSnapshot: authorizationSnapshot
    )
  }

  static func importLegacyMessages(
    workstreamId: String,
    ownerID: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    messages: [ChatMessage]
  ) async throws {
    guard !messages.isEmpty else { return }
    guard messages.count <= TaskChatLegacyCompatibilityMetadata.pageSize else {
      throw BridgeError.agentError("Legacy task chat import page exceeds compatibility bound")
    }
    for message in messages {
      _ = try await recordJournalMessage(
        workstreamId: workstreamId,
        ownerID: ownerID,
        authorizationSnapshot: authorizationSnapshot,
        message: message,
        status: .completed
      )
    }
  }

  static func query(
    prompt: String,
    workstreamId: String,
    producingTurnId: String,
    workspacePath: String,
    mode: String,
    taskContext: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    onTextDelta: @escaping AgentBridge.TextDeltaHandler,
    onToolActivity: @escaping AgentBridge.ToolActivityHandler,
    onThinkingDelta: @escaping AgentBridge.ThinkingDeltaHandler,
    onToolResultDisplay: @escaping AgentBridge.ToolResultDisplayHandler,
    onAuthRequired: @escaping AgentBridge.AuthRequiredHandler,
    onAuthSuccess: @escaping AgentBridge.AuthSuccessHandler
  ) async throws -> AgentBridge.QueryResult {
    try requireCurrent(authorizationSnapshot)
    let bridge = try await sharedBridge()
    try requireCurrent(authorizationSnapshot)
    if activeWorkstreamId != nil {
      throw BridgeError.requestAlreadyActive
    }
    activeWorkstreamId = workstreamId
    defer {
      if activeWorkstreamId == workstreamId {
        activeWorkstreamId = nil
      }
    }
    let surface = AgentSurfaceReference.workstream(workstreamId: workstreamId)
    let bridgePreference = UserDefaults.standard.string(forKey: .chatBridgeMode)
    let routing = try queryRouting(
      bridgePreference: bridgePreference,
      runMode: mode,
      workspacePath: workspacePath
    )
    let creationProfile = AgentSessionCreationProfile(
      adapterId: routing.adapterId,
      modelProfile: routing.modelProfile,
      workingDirectory: routing.workingDirectory
    )
    let session = try await bridge.resolveSurfaceSession(
      surface,
      creationProfile: creationProfile,
      authorizationSnapshot: authorizationSnapshot
    )
    try requireCurrent(authorizationSnapshot)
    var snapshot = try await bridge.getContextSnapshot(
      sessionId: session.sessionId,
      surfaceKind: surface.surfaceKind,
      authorizationSnapshot: authorizationSnapshot
    )
    let contextInputs: [(AgentContextSource, AgentContextSourceOutcome, [String: Any])] = [
      (
        .workspace,
        workspacePath.isEmpty ? .empty : .available,
        workspacePath.isEmpty ? [:] : ["workingDirectory": workspacePath]
      ),
      (
        .surface,
        taskContext?.isEmpty == false ? .available : .empty,
        taskContext?.isEmpty == false ? ["taskContext": taskContext!] : [:]
      ),
    ]
    for (source, outcome, payload) in contextInputs {
      let revision = try AgentContextRevision.make(source: source, payload: payload, outcome: outcome)
      guard snapshot.sourceRevision(for: source) != revision else { continue }
      _ = try await (bridge as any TaskChatRuntimeControlBridge).updateContextSource(
        sessionId: session.sessionId,
        surfaceKind: surface.surfaceKind,
        source: source,
        sourceRevision: revision,
        outcome: outcome,
        capturedAtMs: Int(Date().timeIntervalSince1970 * 1_000),
        expiresAtMs: nil,
        payload: payload,
        authorizationSnapshot: authorizationSnapshot
      )
      try requireCurrent(authorizationSnapshot)
      snapshot = try await bridge.getContextSnapshot(
        sessionId: session.sessionId,
        surfaceKind: surface.surfaceKind,
        authorizationSnapshot: authorizationSnapshot
      )
    }
    await bridge.warmupSession(
      session,
      authorizationSnapshot: authorizationSnapshot
    )
    try requireCurrent(authorizationSnapshot)
    return try await bridge.query(
      prompt: prompt,
      session: session,
      surface: surface,
      mode: routing.runMode,
      producingTurnId: producingTurnId,
      expectedContext: snapshot.freshness,
      authorizationSnapshot: authorizationSnapshot,
      onTextDelta: onTextDelta,
      onToolActivity: onToolActivity,
      onThinkingDelta: onThinkingDelta,
      onToolResultDisplay: onToolResultDisplay,
      onAuthRequired: onAuthRequired,
      onAuthSuccess: onAuthSuccess
    )
  }

  nonisolated static func queryRouting(
    bridgePreference: String?,
    runMode: String,
    workspacePath: String
  ) throws -> QueryRouting {
    let preference = ChatProvider.BridgeMode(rawValue: bridgePreference ?? "piMono") ?? .piMono
    let harness = ChatProvider.harnessMode(for: preference)
    guard let adapterId = AgentRuntimeProcess.adapterId(forHarnessMode: harness) else {
      throw BridgeError.agentError("Unknown AI runtime mode: \(harness)")
    }
    let usesNativeModelChoice = harness == "hermes" || harness == "openclaw"
    return QueryRouting(
      adapterId: adapterId,
      modelProfile: usesNativeModelChoice ? nil : ModelQoS.Claude.chat,
      workingDirectory: workspacePath.isEmpty
        ? AgentRuntimeProcess.defaultArtifactsDirectory()
        : workspacePath,
      runMode: runMode
    )
  }

  static func interrupt(
    workstreamId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
    guard activeWorkstreamId == workstreamId else { return }
    await agentBridge?.interrupt(authorizationSnapshot: authorizationSnapshot)
  }

  static func controlTool(name: String, input: [String: Any]) async throws -> String {
    guard let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else {
      throw LocalMutationAuthorizationError.revoked
    }
    return try await controlTool(
      name: name,
      input: input,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  static func controlTool(
    name: String,
    input: [String: Any],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> String {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      throw LocalMutationAuthorizationError.revoked
    }
    let bridge = try await sharedBridge()
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      throw LocalMutationAuthorizationError.revoked
    }
    return try await bridge.controlTool(
      name: name,
      input: TaskToolInputBox(input),
      authorizationSnapshot: authorizationSnapshot
    )
  }

  private nonisolated static func requireCurrent(
    _ authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    expectedOwnerID: String? = nil
  ) throws {
    if let expectedOwnerID, authorizationSnapshot.ownerID != expectedOwnerID {
      throw LocalMutationAuthorizationError.revoked
    }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      throw LocalMutationAuthorizationError.revoked
    }
  }

  #if DEBUG
    static func debugAutomationControlTool(name: String, input: [String: Any]) async throws -> String {
      let bridge = try await sharedBridge()
      return try await bridge.debugAutomationControlTool(
        name: name, input: TaskToolInputBox(input), ownerId: "scenario-13-automation-owner")
    }

    static func debugImportLegacyTurn(taskId: String) async throws {
      let bridge = try await sharedBridge()
      let message = ChatMessage(
        id: "debug-legacy-task-turn",
        text: "Draft the launch email",
        createdAt: Date(timeIntervalSince1970: 1_783_669_600),
        sender: .user,
        turnOwner: .taskChat(taskId)
      )
      _ = try await bridge.recordJournalTurn(
        surface: .taskChat(taskId: taskId),
        turn: message.journalWrite(
          origin: "task_chat",
          status: .completed,
          messageSource: "task_chat"
        )
      )
    }
  #endif

  private static func sharedBridge() async throws -> AgentBridge {
    if let agentBridge { return agentBridge }

    let mode = UserDefaults.standard.string(forKey: .chatBridgeMode) ?? "piMono"
    let harness = ChatProvider.harnessMode(for: ChatProvider.BridgeMode(rawValue: mode) ?? .piMono)
    let bridge = AgentClient.makeBridge(harnessMode: harness)
    agentBridge = bridge
    log("TaskChatRuntime: shared task-chat bridge initialized")
    return bridge
  }
}
