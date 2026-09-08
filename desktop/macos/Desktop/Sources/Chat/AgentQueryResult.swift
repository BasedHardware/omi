import Foundation

/// The terminal payload of one agent query, including the served-model
/// attribution (`modelsUsed`) observed on the run's completions.
extension AgentBridge {

  struct QueryResult {
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
    /// Served model identities observed on this run's completions (from the
    /// provider response stream), deduplicated by the adapter. Empty when the
    /// runtime predates the field or the run produced no completion.
    let modelsUsed: [String]
    let artifacts: [AgentArtifactProjection]
    let completionDeltaArtifacts: [AgentArtifactProjection]
    let jitCostStatus: String?
    let jitEstimatedCostUsd: Double?
    let jitProviderAttempts: Int?
    let jitReceiptAttemptIDs: [String]

    init(
      text: String,
      costUsd: Double,
      omiSessionId: String,
      runId: String,
      attemptId: String,
      adapterSessionId: String?,
      terminalStatus: String?,
      failure: AgentRuntimeFailure? = nil,
      inputTokens: Int,
      outputTokens: Int,
      cacheReadTokens: Int,
      cacheWriteTokens: Int,
      modelsUsed: [String] = [],
      artifacts: [AgentArtifactProjection] = [],
      completionDeltaArtifacts: [AgentArtifactProjection] = [],
      jitCostStatus: String? = nil,
      jitEstimatedCostUsd: Double? = nil,
      jitProviderAttempts: Int? = nil,
      jitReceiptAttemptIDs: [String] = []
    ) {
      self.text = text
      self.costUsd = costUsd
      self.omiSessionId = omiSessionId
      self.runId = runId
      self.attemptId = attemptId
      self.adapterSessionId = adapterSessionId
      self.terminalStatus = AgentQueryTerminalStatus(wireValue: terminalStatus)
      self.failure = failure
      self.inputTokens = inputTokens
      self.outputTokens = outputTokens
      self.cacheReadTokens = cacheReadTokens
      self.cacheWriteTokens = cacheWriteTokens
      self.modelsUsed = modelsUsed
      self.artifacts = artifacts
      self.completionDeltaArtifacts = completionDeltaArtifacts
      self.jitCostStatus = jitCostStatus
      self.jitEstimatedCostUsd = jitEstimatedCostUsd
      self.jitProviderAttempts = jitProviderAttempts
      self.jitReceiptAttemptIDs = jitReceiptAttemptIDs
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

}

extension AgentRuntimeProcess {

  func queryResult(from message: RuntimeMessage) -> AgentBridge.QueryResult {
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
      modelsUsed: payload["modelsUsed"] as? [String] ?? [],
      artifacts: AgentArtifactProjection.parseList(
        fromJSONArray: payload["artifacts"] as? [[String: Any]] ?? []
      ),
      completionDeltaArtifacts: AgentArtifactProjection.parseList(
        fromJSONArray: payload["completionDeltaArtifacts"] as? [[String: Any]] ?? []
      ),
      jitCostStatus: payload["jitCostStatus"] as? String,
      jitEstimatedCostUsd: payload["jitEstimatedCostUsd"] as? Double,
      jitProviderAttempts: payload["jitProviderAttempts"] as? Int,
      jitReceiptAttemptIDs: payload["jitReceiptAttemptIDs"] as? [String] ?? []
    )
  }
}
