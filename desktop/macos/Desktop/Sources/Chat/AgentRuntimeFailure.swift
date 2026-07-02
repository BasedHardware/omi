import Foundation

struct AgentRuntimeFailure: Equatable, Sendable {
  let code: String
  let userMessage: String
  let technicalMessage: String?
  let source: String?
  let adapterId: String?
  let provider: String?
  let retryable: Bool?
  /// Lifecycle phase reported by the Node runtime. `"startup"` is only set at
  /// sites where the runtime can PROVE the adapter never began executing the
  /// prompt (activation gate, adapter registration, session binding — see
  /// agent/src/runtime/failures.ts). Absent for execution-time failures.
  let phase: String?

  /// True when the Node runtime provably tagged this failure as happening
  /// before the adapter began executing the prompt. This is the only failure
  /// class where re-running the same brief on another provider cannot
  /// duplicate side effects.
  var isStartupPhase: Bool { phase == "startup" }

  var displayMessage: String {
    let trimmed = userMessage.trimmingCharacters(in: .whitespacesAndNewlines)
    if !trimmed.isEmpty {
      return trimmed
    }
    return technicalMessage?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty ?? "Agent run failed"
  }

  static func parse(from value: Any?) -> AgentRuntimeFailure? {
    guard let payload = value as? [String: Any],
      let code = payload["code"] as? String
    else {
      return nil
    }

    let userMessage = (payload["userMessage"] as? String)
      ?? (payload["message"] as? String)
      ?? (payload["technicalMessage"] as? String)
      ?? "Agent run failed"

    return AgentRuntimeFailure(
      code: code,
      userMessage: userMessage,
      technicalMessage: payload["technicalMessage"] as? String,
      source: payload["source"] as? String,
      adapterId: payload["adapterId"] as? String,
      provider: payload["provider"] as? String,
      retryable: payload["retryable"] as? Bool,
      phase: payload["phase"] as? String
    )
  }
}

private extension String {
  var nilIfEmpty: String? {
    isEmpty ? nil : self
  }
}
