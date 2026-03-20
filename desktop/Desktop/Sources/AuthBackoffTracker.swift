import Foundation

/// Tracks consecutive auth failures and provides exponential backoff for polling operations.
/// When API calls return 401/Unauthorized, callers report the failure here. Subsequent polls
/// check `shouldSkipRequest()` to avoid flooding logs with repeated auth errors.
/// Resets automatically on any successful auth call.
@MainActor
final class AuthBackoffTracker {
    static let shared = AuthBackoffTracker()
    private init() {}

    private var consecutiveFailures = 0
    private var lastFailureTime: Date?

    /// Backoff intervals: 5s, 15s, 30s, 60s (cap)
    private let backoffIntervals: [TimeInterval] = [5, 15, 30, 60]

    /// Whether a polling request should be skipped due to recent auth failures.
    /// Returns true if we're in a backoff period.
    func shouldSkipRequest() -> Bool {
        guard consecutiveFailures > 0, let lastFailure = lastFailureTime else {
            return false
        }
        let index = min(consecutiveFailures - 1, backoffIntervals.count - 1)
        let backoff = backoffIntervals[index]
        let elapsed = Date().timeIntervalSince(lastFailure)
        return elapsed < backoff
    }

    /// Report an auth failure (401/Unauthorized). Increments the backoff counter.
    func reportAuthFailure() {
        consecutiveFailures += 1
        lastFailureTime = Date()
        if consecutiveFailures == 1 {
            log("AuthBackoff: first auth failure, backing off")
        }
    }

    /// Report a successful auth call. Resets the backoff counter.
    func reportSuccess() {
        if consecutiveFailures > 0 {
            log("AuthBackoff: auth recovered after \(consecutiveFailures) failure(s)")
        }
        consecutiveFailures = 0
        lastFailureTime = nil
    }

    /// Current consecutive failure count (for diagnostics).
    var failureCount: Int { consecutiveFailures }
}
