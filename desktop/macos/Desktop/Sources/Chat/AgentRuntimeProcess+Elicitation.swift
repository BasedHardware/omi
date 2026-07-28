import Foundation

extension AgentRuntimeProcess {
  typealias ElicitationPendingHandler = @Sendable (PendingElicitation) -> Void
  typealias ElicitationResolvedHandler = @Sendable (String) -> Void

  func setElicitationHandlers(
    pending: ElicitationPendingHandler?,
    resolved: ElicitationResolvedHandler?
  ) {
    elicitationPendingHandler = pending
    elicitationResolvedHandler = resolved
  }

  /// Project a pending or retired elicitation to the surface.
  ///
  /// Owner-fenced like every other owner-scoped projection: a message for an
  /// owner that is no longer authorized is dropped rather than rendered, so
  /// signing out cannot leave another user's question on screen.
  func handleElicitationMessage(_ message: RuntimeMessage) {
    guard messageOwnerIsCurrentlyAuthorized(message) else { return }
    let decoded =
      message.kind == .elicitationPending
      ? ElicitationWire.decodePending(message.payload)
      : ElicitationWire.decodeResolved(message.payload)
    switch decoded {
    case .pending(let elicitation): elicitationPendingHandler?(elicitation)
    case .resolved(let dispatchID): elicitationResolvedHandler?(dispatchID)
    case nil: log("AgentRuntimeProcess: dropping malformed elicitation message")
    }
  }

}
