extension AgentRuntimeProcess.RuntimeMessage {
  /// Closed routing taxonomy for messages received from the JSONL runtime.
  /// Kept beside the protocol boundary instead of growing the process owner.
  enum Kind: Equatable {
    case initMessage
    case textDelta
    case thinkingDelta
    case toolUse
    case authorizedToolExecution
    case toolActivity
    case turnActivity
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
    case chatFirstHarnessExecutorResult
    case ownerRuntimeRevoked
    case unknown(String)
  }
}
