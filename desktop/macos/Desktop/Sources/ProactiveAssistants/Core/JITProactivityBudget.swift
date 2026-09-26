import Foundation

/// Time values used by JIT are deliberately separated by meaning.  A capture
/// time describes the evidence; an evaluation time describes when the policy
/// made its decision.  Neither value is allowed to masquerade as the other.
struct JITProactivityTemporalContext: Equatable, Sendable {
  let capturedAt: Date?
  let evaluatedAt: Date?
  let timezoneIdentifier: String?

  var timeZone: TimeZone? {
    guard let timezoneIdentifier else { return nil }
    return TimeZone(identifier: timezoneIdentifier)
  }

  /// Prompt text is bounded, content-free metadata.  If capture time is
  /// unavailable, the model is told to avoid temporal claims while retaining
  /// the rest of the proactive decision surface.
  func promptSection() -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    var lines = ["Trusted temporal context:"]
    if let capturedAt {
      lines.append("  Evidence captured at (UTC): \(formatter.string(from: capturedAt))")
    } else {
      lines.append("  Evidence capture time: unavailable")
    }
    if let evaluatedAt {
      lines.append("  Evaluated at (UTC): \(formatter.string(from: evaluatedAt))")
    } else {
      lines.append("  Evaluation time: unavailable")
    }
    if let timezoneIdentifier, timeZone != nil {
      lines.append("  Authoritative user timezone: \(timezoneIdentifier)")
    } else {
      lines.append("  Authoritative user timezone: unavailable")
    }
    lines.append("  Do not make a time-specific claim when the required timestamp or timezone is unavailable.")
    return lines.joined(separator: "\n")
  }
}

/// Qualification-only limits for the cheaper JIT full-agent route.  Normal
/// chat never receives this value; its global route policy remains unchanged.
/// The server advertises the same contract version before the client attaches
/// this payload to a request.
struct JITProactivityAgentBudget: Equatable, Sendable {
  static let cloudQAContractVersion = "jit-cloud-qa-v1"
  static let cloudQA = (
    maxProviderAttempts: 3, maxOutputTokensPerAttempt: 2_048,
    maxNormalizedInputTokensPerAttempt: 32_768,
    maxEstimatedSpendMicroUSD: 50_000
  )

  let contractVersion: String
  let executionID: String
  let maxProviderAttempts: Int
  let maxOutputTokensPerAttempt: Int
  let maxNormalizedInputTokensPerAttempt: Int
  let maxEstimatedSpendMicroUSD: Int

  init?(contractVersion: String?, executionID: String) {
    guard contractVersion == Self.cloudQAContractVersion,
      JITProactivityReservation.isIdentifier(executionID)
    else { return nil }
    self.contractVersion = Self.cloudQAContractVersion
    self.executionID = executionID
    self.maxProviderAttempts = Self.cloudQA.maxProviderAttempts
    self.maxOutputTokensPerAttempt = Self.cloudQA.maxOutputTokensPerAttempt
    self.maxNormalizedInputTokensPerAttempt = Self.cloudQA.maxNormalizedInputTokensPerAttempt
    self.maxEstimatedSpendMicroUSD = Self.cloudQA.maxEstimatedSpendMicroUSD
  }

  var wireDictionary: [String: Any] {
    [
      "contractVersion": contractVersion,
      "executionID": executionID,
      "maxProviderAttempts": maxProviderAttempts,
      "maxOutputTokensPerAttempt": maxOutputTokensPerAttempt,
      "maxNormalizedInputTokensPerAttempt": maxNormalizedInputTokensPerAttempt,
      "maxEstimatedSpendMicroUSD": maxEstimatedSpendMicroUSD,
    ]
  }
}
