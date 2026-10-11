import Foundation

/// How one failed finalization attempt affects a session's retry schedule.
enum FinalizationFailureClass: String, Equatable, Sendable {
  /// No usable network path. The attempt says nothing about the session, so it never spends retry budget.
  case offline
  /// A failure that can succeed later unchanged: 5xx, throttling, timeouts, auth refresh, local state.
  case transient
  /// The backend rejected the request itself (4xx other than auth/throttle). The session stays
  /// retryable, at the slowest cadence, because a backend fix or deploy can make the same bytes succeed.
  case permanent

  static func classify(_ error: Error) -> FinalizationFailureClass {
    if let urlError = error as? URLError {
      switch urlError.code {
      case .notConnectedToInternet, .networkConnectionLost, .cannotFindHost, .cannotConnectToHost,
        .dnsLookupFailed:
        return .offline
      default:
        return .transient
      }
    }
    if case APIError.httpError(let statusCode, _) = error,
      (400...499).contains(statusCode),
      !transientClientStatusCodes.contains(statusCode)
    {
      return .permanent
    }
    return .transient
  }

  /// 4xx responses that describe the caller's moment rather than the payload.
  private static let transientClientStatusCodes: Set<Int> = [401, 408, 425, 429]
}

/// Retry schedule for the canonical conversation finalizer.
///
/// `.localSegments` sessions hold the only copy of an on-device transcript, and the backend dedups
/// `/v1/conversations/from-segments` by `client_conversation_id`, so they retry without a budget at a
/// capped cadence. Cloud reconciliation keeps its bounded budget plus local fallback.
enum FinalizationRetryPolicy {
  static let maxBackoffSeconds: TimeInterval = 60 * 60

  /// `lastError` prefix that persists a `.permanent` classification across launches.
  static let permanentFailurePrefix = "permanent_rejection: "

  /// 1, 2, 4, 8, 16, 32 minutes, then hourly. A permanent rejection waits the full hour.
  static func backoffSeconds(retryCount: Int, permanentFailure: Bool) -> TimeInterval {
    guard !permanentFailure else { return maxBackoffSeconds }
    let exponent = Double(min(max(retryCount, 0), 6))
    return min(pow(2.0, exponent) * 60.0, maxBackoffSeconds)
  }
}
