import Foundation

/// Unified entry point for one-shot agent queries from reader services, onboarding helpers, and task chat.
enum AgentClient {
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
    }
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
    onTextDelta: @escaping AgentBridge.TextDeltaHandler = { _ in },
    onToolCall: @escaping AgentBridge.ToolCallHandler = { _, _, _ in "" },
    onToolActivity: @escaping AgentBridge.ToolActivityHandler = { _, _, _, _ in },
    onThinkingDelta: @escaping AgentBridge.ThinkingDeltaHandler = { _ in },
    onToolResultDisplay: @escaping AgentBridge.ToolResultDisplayHandler = { _, _, _ in },
    onAuthRequired: @escaping AgentBridge.AuthRequiredHandler = { _, _ in },
    onAuthSuccess: @escaping AgentBridge.AuthSuccessHandler = {}
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
