import Foundation

enum AgentContextAdmissionRetry {
  static func run<Result>(
    expectedContext: AgentContextFreshness?,
    refresh: () async throws -> AgentContextFreshness,
    attempt: (AgentContextFreshness?) async throws -> Result
  ) async throws -> Result {
    do {
      return try await attempt(expectedContext)
    } catch let error as BridgeError
      where expectedContext != nil && error.isContextSnapshotProjectionMismatch
    {
      log("AgentClient: canonical context advanced before admission; refreshing and retrying once")
      do {
        let refreshedContext = try await refresh()
        let result = try await attempt(refreshedContext)
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "chat_bridge",
          from: "stale_context_snapshot",
          to: "fresh_context_snapshot",
          reason: "local_heal",
          outcome: .recovered
        )
        return result
      } catch {
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "chat_bridge",
          from: "stale_context_snapshot",
          to: "fresh_context_snapshot",
          reason: "local_heal",
          outcome: .exhausted
        )
        throw error
      }
    }
  }
}

/// Unified entry point for agent runtime queries. Owns all `AgentBridge` construction.
enum AgentClient {
  typealias TextDeltaHandler = AgentBridge.TextDeltaHandler
  typealias ToolCallHandler = AgentBridge.ToolCallHandler
  typealias ToolActivityHandler = AgentBridge.ToolActivityHandler
  typealias ThinkingDeltaHandler = AgentBridge.ThinkingDeltaHandler
  typealias ToolResultDisplayHandler = AgentBridge.ToolResultDisplayHandler
  typealias AuthRequiredHandler = AgentBridge.AuthRequiredHandler
  typealias AuthSuccessHandler = AgentBridge.AuthSuccessHandler

  struct QueryResult: Sendable {
    let text: String
    let costUsd: Double
    let omiSessionId: String
    let runId: String
    let attemptId: String
    let adapterSessionId: String?
    let terminalStatus: AgentQueryTerminalStatus
    let failure: AgentRuntimeFailure?
    let inputTokens: Int
    let outputTokens: Int
    let cacheReadTokens: Int
    let cacheWriteTokens: Int
    let artifacts: [AgentArtifactProjection]
    let completionDeltaArtifacts: [AgentArtifactProjection]

    init(_ result: AgentBridge.QueryResult) {
      text = result.text
      costUsd = result.costUsd
      omiSessionId = result.omiSessionId
      runId = result.runId
      attemptId = result.attemptId
      adapterSessionId = result.adapterSessionId
      terminalStatus = result.terminalStatus
      failure = result.failure
      inputTokens = result.inputTokens
      outputTokens = result.outputTokens
      cacheReadTokens = result.cacheReadTokens
      cacheWriteTokens = result.cacheWriteTokens
      artifacts = result.artifacts
      completionDeltaArtifacts = result.completionDeltaArtifacts
    }

    @discardableResult
    func requireSucceeded() throws -> QueryResult {
      switch terminalStatus {
      case .succeeded:
        return self
      case .cancelled:
        throw BridgeError.stopped
      case .failed, .timedOut, .orphaned:
        let raw = failure?.displayMessage ?? (text.isEmpty ? "Agent failed" : text)
        throw failure.map(BridgeError.agentRuntimeFailure) ?? BridgeError.agentError(raw)
      case .invalid:
        throw BridgeError.agentError("Agent returned an invalid terminal status")
      }
    }
  }

  /// Long-lived bridge session for main chat and other streaming surfaces.
  actor Session {
    private var bridge: AgentBridge
    private(set) var harnessMode: String

    init(harnessMode: String) {
      self.harnessMode = harnessMode
      self.bridge = AgentBridge(harnessMode: harnessMode)
    }

    var isAlive: Bool {
      get async { await bridge.isAlive }
    }

    func start() async throws {
      try await bridge.start()
    }

    func restart() async throws {
      try await bridge.restart()
    }

    func prepareForCrashRecovery() async {
      await bridge.prepareForCrashRecovery()
    }

    func stop() async {
      await bridge.stop()
    }

    func stopAndWaitForExit() async {
      await bridge.stopAndWaitForExit()
    }

    func invalidateSurface(_ surface: AgentSurfaceReference) async {
      await bridge.invalidateSurface(surface)
    }

    func setGlobalAuthHandlers(
      onAuthRequired: AuthRequiredHandler?,
      onAuthSuccess: AuthSuccessHandler?
    ) async {
      await bridge.setGlobalAuthHandlers(onAuthRequired: onAuthRequired, onAuthSuccess: onAuthSuccess)
    }

    func setJournalTurnChangedHandler(
      _ handler: @escaping AgentRuntimeProcess.JournalTurnChangedHandler
    ) async {
      await bridge.setJournalTurnChangedHandler(handler)
    }

    func configureDefaultExecutionProfile(
      adapterId: String,
      modelProfile: String?,
      workingDirectory: String,
      expectedPreferenceGeneration: Int? = nil
    ) async throws -> AgentDefaultExecutionProfile {
      try await bridge.configureDefaultExecutionProfile(
        adapterId: adapterId,
        modelProfile: modelProfile,
        workingDirectory: workingDirectory,
        expectedPreferenceGeneration: expectedPreferenceGeneration
      )
    }

    func resolveSurfaceSession(
      _ surface: AgentSurfaceReference,
      title: String? = nil,
      creationProfile: AgentSessionCreationProfile? = nil,
      chatFirstCapability: ChatFirstCapabilityProjection? = nil
    ) async throws -> AgentSurfaceSession {
      try await bridge.resolveSurfaceSession(
        surface,
        title: title,
        creationProfile: creationProfile,
        chatFirstCapability: chatFirstCapability
      )
    }

    func migrateSessionExecutionProfile(
      sessionId: String,
      expectedProfileGeneration: Int,
      adapterId: String,
      modelProfile: String?,
      workingDirectory: String
    ) async throws -> AgentSessionProfileMigration {
      try await bridge.migrateSessionExecutionProfile(
        sessionId: sessionId,
        expectedProfileGeneration: expectedProfileGeneration,
        adapterId: adapterId,
        modelProfile: modelProfile,
        workingDirectory: workingDirectory
      )
    }

    func warmupSession(_ session: AgentSurfaceSession) async {
      await bridge.warmupSession(session)
    }

    func updateContextSource(
      sessionId: String,
      surfaceKind: String,
      source: AgentContextSource,
      sourceRevision: String,
      outcome: AgentContextSourceOutcome,
      capturedAtMs: Int,
      expiresAtMs: Int? = nil,
      payload: RuntimeJSONPayloadBox
    ) async throws -> AgentContextSourceUpdateReceipt {
      try await bridge.updateContextSource(
        sessionId: sessionId,
        surfaceKind: surfaceKind,
        source: source,
        sourceRevision: sourceRevision,
        outcome: outcome,
        capturedAtMs: capturedAtMs,
        expiresAtMs: expiresAtMs,
        payload: payload
      )
    }

    func getContextSnapshot(sessionId: String, surfaceKind: String) async throws -> AgentContextSnapshot {
      try await bridge.getContextSnapshot(sessionId: sessionId, surfaceKind: surfaceKind)
    }

    func recordJournalTurn(
      surface: AgentSurfaceReference,
      ownerID: String? = nil,
      turn: KernelJournalTurnWrite
    ) async throws -> KernelJournalTurn {
      try await bridge.recordJournalTurn(surface: surface, ownerID: ownerID, turn: turn)
    }

    func recordJournalExchange(
      surface: AgentSurfaceReference,
      ownerID: String,
      turns: [KernelJournalTurnWrite]
    ) async throws -> AgentRuntimeProcess.JournalOperationResult {
      try await bridge.recordJournalExchange(
        surface: surface,
        ownerID: ownerID,
        turns: turns
      )
    }

    func recordQuestionInteractionReply(
      surface: AgentSurfaceReference,
      ownerID: String,
      sessionID: String,
      questionID: String,
      optionID: String,
      controlGeneration: Int
    ) async throws -> AgentRuntimeProcess.QuestionInteractionReply {
      try await bridge.recordQuestionInteractionReply(
        surface: surface,
        ownerID: ownerID,
        sessionID: sessionID,
        questionID: questionID,
        optionID: optionID,
        controlGeneration: controlGeneration
      )
    }

    func materializeChatFirstIntents(
      surface: AgentSurfaceReference,
      ownerID: String,
      sessionID: String,
      controlGeneration: Int,
      intents: [ChatFirstPromptIntent]
    ) async throws -> AgentRuntimeProcess.ChatFirstIntentsMaterialization {
      try await bridge.materializeChatFirstIntents(
        surface: surface,
        ownerID: ownerID,
        sessionID: sessionID,
        controlGeneration: controlGeneration,
        intents: intents
      )
    }

    func listChatFirstMaterializationReceipts(
      surface: AgentSurfaceReference,
      ownerID: String,
      sessionID: String,
      controlGeneration: Int
    ) async throws -> ChatFirstPromptReceiptBatch {
      try await bridge.listChatFirstMaterializationReceipts(
        surface: surface,
        ownerID: ownerID,
        sessionID: sessionID,
        controlGeneration: controlGeneration
      )
    }

    @discardableResult
    func acknowledgeChatFirstMaterializationReceipts(
      surface: AgentSurfaceReference,
      ownerID: String,
      sessionID: String,
      controlGeneration: Int,
      receipts: ChatFirstPromptReceiptBatch
    ) async throws -> Int {
      try await bridge.acknowledgeChatFirstMaterializationReceipts(
        surface: surface,
        ownerID: ownerID,
        sessionID: sessionID,
        controlGeneration: controlGeneration,
        receipts: receipts
      )
    }

    func updateJournalTurn(
      surface: AgentSurfaceReference,
      ownerID: String? = nil,
      update: KernelJournalTurnUpdate
    ) async throws -> KernelJournalTurn {
      try await bridge.updateJournalTurn(surface: surface, ownerID: ownerID, update: update)
    }

    func terminalizeJournalTurn(
      surface: AgentSurfaceReference,
      ownerID: String,
      terminalization: KernelJournalTurnTerminalization
    ) async throws -> KernelJournalTurn {
      try await bridge.terminalizeJournalTurn(
        surface: surface,
        ownerID: ownerID,
        terminalization: terminalization
      )
    }

    func listJournalTurns(
      surface: AgentSurfaceReference,
      ownerID: String? = nil,
      afterTurnSeq: Int = 0,
      limit: Int = 100
    ) async throws -> AgentRuntimeProcess.JournalOperationResult {
      try await bridge.listJournalTurns(
        surface: surface,
        ownerID: ownerID,
        afterTurnSeq: afterTurnSeq,
        limit: limit
      )
    }

    func listJournalTurnsForControl(
      surface: AgentSurfaceReference,
      ownerID: String? = nil,
      afterTurnSeq: Int = 0,
      limit: Int = 100
    ) async throws -> AgentRuntimeProcess.JournalOperationResult {
      try await bridge.listJournalTurnsForControl(
        surface: surface,
        ownerID: ownerID,
        afterTurnSeq: afterTurnSeq,
        limit: limit
      )
    }

    func importRemoteJournalTurn(
      surface: AgentSurfaceReference,
      ownerID: String? = nil,
      turn: KernelJournalRemoteTurn
    ) async throws -> KernelJournalTurn {
      try await bridge.importRemoteJournalTurn(surface: surface, ownerID: ownerID, turn: turn)
    }

    func clearJournalTurns(
      surface: AgentSurfaceReference,
      ownerID: String? = nil,
      expectedGeneration: Int? = nil
    ) async throws -> Int {
      try await bridge.clearJournalTurns(
        surface: surface,
        ownerID: ownerID,
        expectedGeneration: expectedGeneration
      )
    }

    func clearJournalTurnsForControl(
      surface: AgentSurfaceReference,
      ownerID: String? = nil,
      expectedGeneration: Int? = nil
    ) async throws -> Int {
      try await bridge.clearJournalTurnsForControl(
        surface: surface,
        ownerID: ownerID,
        expectedGeneration: expectedGeneration
      )
    }

    func testPlaywrightConnection() async throws -> Bool {
      try await bridge.testPlaywrightConnection()
    }

    func interrupt() async {
      await bridge.interrupt()
    }

    func query(
      prompt: String,
      surface: AgentSurfaceReference,
      mode: String? = nil,
      imageData: Data? = nil,
      attachments: [AgentQueryAttachment] = [],
      producingTurnId: String? = nil,
      expectedContext: AgentContextFreshness? = nil,
      reasoningEffort: String? = nil,
      onTextDelta: @escaping TextDeltaHandler,
      onToolActivity: @escaping ToolActivityHandler,
      onThinkingDelta: @escaping ThinkingDeltaHandler = { _ in },
      onToolResultDisplay: @escaping ToolResultDisplayHandler = { _, _, _ in },
      onAuthRequired: @escaping AuthRequiredHandler = { _, _ in },
      onAuthSuccess: @escaping AuthSuccessHandler = {}
    ) async throws -> QueryResult {
      let result = try await bridge.query(
        prompt: prompt,
        surface: surface,
        mode: mode,
        imageData: imageData,
        attachments: attachments,
        producingTurnId: producingTurnId,
        expectedContext: expectedContext,
        reasoningEffort: reasoningEffort,
        onTextDelta: onTextDelta,
        onToolActivity: onToolActivity,
        onThinkingDelta: onThinkingDelta,
        onToolResultDisplay: onToolResultDisplay,
        onAuthRequired: onAuthRequired,
        onAuthSuccess: onAuthSuccess
      )
      return QueryResult(result)
    }

    func query(
      prompt: String,
      session: AgentSurfaceSession,
      surface: AgentSurfaceReference,
      mode: String? = nil,
      imageData: Data? = nil,
      attachments: [AgentQueryAttachment] = [],
      producingTurnId: String? = nil,
      expectedContext: AgentContextFreshness? = nil,
      reasoningEffort: String? = nil,
      onTextDelta: @escaping TextDeltaHandler,
      onToolActivity: @escaping ToolActivityHandler,
      onThinkingDelta: @escaping ThinkingDeltaHandler = { _ in },
      onToolResultDisplay: @escaping ToolResultDisplayHandler = { _, _, _ in },
      onAuthRequired: @escaping AuthRequiredHandler = { _, _ in },
      onAuthSuccess: @escaping AuthSuccessHandler = {}
    ) async throws -> QueryResult {
      let bridge = bridge
      return QueryResult(
        try await AgentContextAdmissionRetry.run(
          expectedContext: expectedContext,
          refresh: {
            try await bridge.getContextSnapshot(
              sessionId: session.sessionId,
              surfaceKind: surface.surfaceKind
            ).freshness
          },
          attempt: { admittedContext in
            try await bridge.query(
              prompt: prompt,
              session: session,
              surface: surface,
              mode: mode,
              imageData: imageData,
              attachments: attachments,
              producingTurnId: producingTurnId,
              expectedContext: admittedContext,
              reasoningEffort: reasoningEffort,
              onTextDelta: onTextDelta,
              onToolActivity: onToolActivity,
              onThinkingDelta: onThinkingDelta,
              onToolResultDisplay: onToolResultDisplay,
              onAuthRequired: onAuthRequired,
              onAuthSuccess: onAuthSuccess
            )
          }
        ))
    }
  }

  static func makeSession(harnessMode: String = "piMono") -> Session {
    Session(harnessMode: harnessMode)
  }

  static func makeBridge(harnessMode: String = "piMono") -> AgentBridge {
    AgentBridge(harnessMode: harnessMode)
  }

  static func run(
    surface: AgentSurfaceReference,
    prompt: String,
    model: String? = nil,
    systemPrompt: String = "You are a helpful assistant.",
    harnessMode: String = "piMono",
    mode: String? = nil,
    cwd: String? = nil,
    onTextDelta: @escaping TextDeltaHandler = { _ in },
    onToolCall _: @escaping ToolCallHandler = { _, _, _ in "" },
    onToolActivity: @escaping ToolActivityHandler = { _, _, _, _ in },
    onThinkingDelta: @escaping ThinkingDeltaHandler = { _ in },
    onToolResultDisplay: @escaping ToolResultDisplayHandler = { _, _, _ in },
    onAuthRequired: @escaping AuthRequiredHandler = { _, _ in },
    onAuthSuccess: @escaping AuthSuccessHandler = {}
  ) async throws -> QueryResult {
    let bridge = AgentClient.makeBridge(harnessMode: harnessMode)
    try await bridge.start()
    do {

      guard let requestedAdapter = AgentRuntimeProcess.adapterId(forHarnessMode: harnessMode) else {
        throw BridgeError.agentError("Unknown AI runtime mode: \(harnessMode)")
      }
      let usesNativeModelChoice = ["hermes", "openclaw"].contains(harnessMode)
      let creationProfile = AgentSessionCreationProfile(
        adapterId: requestedAdapter,
        modelProfile: model ?? (usesNativeModelChoice ? nil : ModelQoS.Claude.chat),
        workingDirectory: cwd?.isEmpty == false ? cwd! : AgentRuntimeProcess.defaultArtifactsDirectory()
      )
      let session = try await bridge.resolveSurfaceSession(
        surface,
        creationProfile: creationProfile
      )
      var snapshot = try await bridge.getContextSnapshot(
        sessionId: session.sessionId,
        surfaceKind: surface.surfaceKind)
      let contextInputs: [(AgentContextSource, AgentContextSourceOutcome, [String: Any])] = [
        (
          .surface,
          systemPrompt.isEmpty ? .empty : .available,
          systemPrompt.isEmpty ? [:] : ["experienceContext": systemPrompt]
        ),
        (
          .workspace,
          cwd?.isEmpty == false ? .available : .empty,
          cwd?.isEmpty == false ? ["workingDirectory": cwd!] : [:]
        ),
      ]
      for (source, outcome, payload) in contextInputs {
        let revision = try AgentContextRevision.make(source: source, payload: payload, outcome: outcome)
        guard snapshot.sourceRevision(for: source) != revision else { continue }
        _ = try await bridge.updateContextSource(
          sessionId: session.sessionId,
          surfaceKind: surface.surfaceKind,
          source: source,
          sourceRevision: revision,
          outcome: outcome,
          capturedAtMs: Int(Date().timeIntervalSince1970 * 1_000),
          payload: RuntimeJSONPayloadBox(payload)
        )
        snapshot = try await bridge.getContextSnapshot(
          sessionId: session.sessionId,
          surfaceKind: surface.surfaceKind)
      }
      await bridge.warmupSession(session)

      let result = try await bridge.query(
        prompt: prompt,
        session: session,
        surface: surface,
        mode: mode,
        expectedContext: snapshot.freshness,
        onTextDelta: onTextDelta,
        onToolActivity: onToolActivity,
        onThinkingDelta: onThinkingDelta,
        onToolResultDisplay: onToolResultDisplay,
        onAuthRequired: onAuthRequired,
        onAuthSuccess: onAuthSuccess
      )
      let output = try QueryResult(result).requireSucceeded()
      await bridge.stop()
      return output
    } catch {
      await bridge.stop()
      throw error
    }
  }
}
