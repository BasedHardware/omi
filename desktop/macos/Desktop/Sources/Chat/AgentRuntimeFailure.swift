import Foundation

enum AgentRuntimeFailureCode: String, CaseIterable, Equatable, Sendable {
  case authentication
  case quotaExceeded = "quota_exceeded"
  case invalidRequest = "invalid_request"
  case timeout
  case transportInterruption = "transport_interruption"
  case adapterUnavailable = "adapter_unavailable"
  case adapterIncompatible = "adapter_incompatible"
  case bridgeStartFailed = "bridge_start_failed"
  case providerSetupNeeded = "provider_setup_needed"
  case malformedOrOversizedToolResult = "malformed_or_oversized_tool_result"
  case cancelled
  case staleOwner = "stale_owner"
  case policyDenied = "policy_denied"
  case unknown
}

struct AgentRuntimeFailure: Equatable, Sendable {
  let code: String
  /// Closed wire classification; `code` remains the detailed diagnostic key.
  let failureCode: AgentRuntimeFailureCode
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

  init(
    code: String,
    failureCode: AgentRuntimeFailureCode = .unknown,
    userMessage: String,
    technicalMessage: String? = nil,
    source: String? = nil,
    adapterId: String? = nil,
    provider: String? = nil,
    retryable: Bool? = nil
  ) {
    self.code = code
    self.failureCode = failureCode
    self.userMessage = userMessage
    self.technicalMessage = technicalMessage
    self.source = source
    self.adapterId = adapterId
    self.provider = provider
    self.retryable = retryable
  }

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

    let userMessage =
      (payload["userMessage"] as? String)
      ?? (payload["message"] as? String)
      ?? (payload["technicalMessage"] as? String)
      ?? "Agent run failed"

    return AgentRuntimeFailure(
      code: code,
      failureCode: (payload["failureCode"] as? String)
        .flatMap(AgentRuntimeFailureCode.init(rawValue:)) ?? .unknown,
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

extension String {
  fileprivate var nilIfEmpty: String? {
    isEmpty ? nil : self
  }
}
