import Foundation

/// Unified entry point for agent runtime queries. Owns all `AgentBridge` construction.
enum AgentClient {
  typealias TextDeltaHandler = AgentBridge.TextDeltaHandler
  typealias ToolCallHandler = AgentBridge.ToolCallHandler
  typealias ToolActivityHandler = AgentBridge.ToolActivityHandler
  typealias ThinkingDeltaHandler = AgentBridge.ThinkingDeltaHandler
  typealias ToolResultDisplayHandler = AgentBridge.ToolResultDisplayHandler
  typealias AuthRequiredHandler = AgentBridge.AuthRequiredHandler
  typealias AuthSuccessHandler = AgentBridge.AuthSuccessHandler
  typealias WarmupSessionConfig = AgentBridge.WarmupSessionConfig

  struct QueryResult: Sendable {
    let text: String
    let costUsd: Double
    let omiSessionId: String
    let runId: String
    let attemptId: String
    let adapterSessionId: String?
    let terminalStatus: String
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
      inputTokens = result.inputTokens
      outputTokens = result.outputTokens
      cacheReadTokens = result.cacheReadTokens
      cacheWriteTokens = result.cacheWriteTokens
      artifacts = result.artifacts
      completionDeltaArtifacts = result.completionDeltaArtifacts
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

    func replaceHarness(_ harnessMode: String) async {
      await bridge.stop()
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

    func stop() async {
      await bridge.stop()
    }

    func stopAndWaitForExit() async {
      await bridge.stopAndWaitForExit()
    }

    func clearOwnerState() async {
      await bridge.clearOwnerState()
    }

    func clearOwnerSurfaceState(chatId: String = "default") async {
      await bridge.clearOwnerSurfaceState(chatId: chatId)
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

    func setTurnRecordedHandler(_ handler: @escaping AgentRuntimeProcess.TurnRecordedHandler) async {
      await bridge.setTurnRecordedHandler(handler)
    }

    func warmupSession(cwd: String? = nil, sessions: [WarmupSessionConfig]) async {
      await bridge.warmupSession(cwd: cwd, sessions: sessions)
    }

    func importConversationTurns(
      surface: AgentSurfaceReference,
      turns: [(role: String, content: String, createdAtMs: Int?)]
    ) async {
      await bridge.importConversationTurns(surface: surface, turns: turns)
    }

    func recordSurfaceTurn(
      surface: AgentSurfaceReference,
      userText: String,
      assistantText: String,
      origin: String,
      interrupted: Bool = false,
      idempotencyKey: String? = nil
    ) async {
      await bridge.recordSurfaceTurn(
        surface: surface,
        userText: userText,
        assistantText: assistantText,
        origin: origin,
        interrupted: interrupted,
        idempotencyKey: idempotencyKey
      )
    }

    func getVoiceSeedContext(surface: AgentSurfaceReference) async throws -> (conversationId: String, context: String) {
      try await bridge.getVoiceSeedContext(surface: surface)
    }

    func getKernelTurnTail(limit: Int = 8, chatId: String = "default") async throws -> AgentRuntimeProcess.KernelTurnTailResult {
      try await bridge.getKernelTurnTail(limit: limit, chatId: chatId)
    }

    func projectCrossSurfaceTurn(
      surface: AgentSurfaceReference,
      userText: String,
      assistantText: String,
      origin: String,
      idempotencyKey: String? = nil
    ) async {
      await bridge.projectCrossSurfaceTurn(
        surface: surface,
        userText: userText,
        assistantText: assistantText,
        origin: origin,
        idempotencyKey: idempotencyKey
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
      systemPrompt: String,
      surface: AgentSurfaceReference,
      cwd: String? = nil,
      mode: String? = nil,
      model: String? = nil,
      imageData: Data? = nil,
      attachmentMetadataJson: String? = nil,
      surfaceContextJson: String? = nil,
      onTextDelta: @escaping TextDeltaHandler,
      onToolCall: @escaping ToolCallHandler,
      onToolActivity: @escaping ToolActivityHandler,
      onThinkingDelta: @escaping ThinkingDeltaHandler = { _ in },
      onToolResultDisplay: @escaping ToolResultDisplayHandler = { _, _, _ in },
      onAuthRequired: @escaping AuthRequiredHandler = { _, _ in },
      onAuthSuccess: @escaping AuthSuccessHandler = {}
    ) async throws -> QueryResult {
      let result = try await bridge.query(
        prompt: prompt,
        systemPrompt: systemPrompt,
        surface: surface,
        cwd: cwd,
        mode: mode,
        model: model,
        imageData: imageData,
        attachmentMetadataJson: attachmentMetadataJson,
        surfaceContextJson: surfaceContextJson,
        onTextDelta: onTextDelta,
        onToolCall: onToolCall,
        onToolActivity: onToolActivity,
        onThinkingDelta: onThinkingDelta,
        onToolResultDisplay: onToolResultDisplay,
        onAuthRequired: onAuthRequired,
        onAuthSuccess: onAuthSuccess
      )
      return QueryResult(result)
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
    onToolCall: @escaping ToolCallHandler = { _, _, _ in "" },
    onToolActivity: @escaping ToolActivityHandler = { _, _, _, _ in },
    onThinkingDelta: @escaping ThinkingDeltaHandler = { _ in },
    onToolResultDisplay: @escaping ToolResultDisplayHandler = { _, _, _ in },
    onAuthRequired: @escaping AuthRequiredHandler = { _, _ in },
    onAuthSuccess: @escaping AuthSuccessHandler = {}
  ) async throws -> QueryResult {
    let bridge = AgentClient.makeBridge(harnessMode: harnessMode)
    try await bridge.start()
    defer { Task { await bridge.stop() } }

    let result = try await bridge.query(
      prompt: prompt,
      systemPrompt: systemPrompt,
      surface: surface,
      cwd: cwd,
      mode: mode,
      model: model,
      onTextDelta: onTextDelta,
      onToolCall: onToolCall,
      onToolActivity: onToolActivity,
      onThinkingDelta: onThinkingDelta,
      onToolResultDisplay: onToolResultDisplay,
      onAuthRequired: onAuthRequired,
      onAuthSuccess: onAuthSuccess
    )
    return QueryResult(result)
  }
}
