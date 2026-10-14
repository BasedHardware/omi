import Foundation

/// Classifies a failed server memory delete and bounds its deferred retry.
///
/// The backend's account-wide destructive-operation gate answers a concurrent
/// delete with 409 `account_gate_busy` plus a `Retry-After` header. That answer
/// means "try again shortly", not "the delete is impossible" — but the old
/// failure path restored the row on any error, so every delete during a
/// retention-cleanup window visibly resurrected seconds after the user
/// confirmed it.
enum MemoryDeleteRecovery {
  /// Matches `ACCOUNT_GATE_BUSY_DETAIL` in `backend/utils/other/account_gate_http.py`.
  static let gateBusyDetail = "account_gate_busy"
  static let minRetryDelay: TimeInterval = 5
  static let maxRetryDelay: TimeInterval = 300
  /// Used when the server sent no usable `Retry-After`.
  static let defaultRetryDelay: TimeInterval = 30

  /// The bounded retry delay for a gate-busy delete failure, or nil when the
  /// failure is not retryable and the caller must restore the row.
  static func retryDelay(for error: Error) -> TimeInterval? {
    switch error {
    case APIError.memoryDeleteGateBusy(let retryAfterSeconds):
      return clamp(retryAfterSeconds)
    case APIError.httpError(let statusCode, let detail)
    where statusCode == 409 && detail == gateBusyDetail:
      return clamp(nil)
    default:
      return nil
    }
  }

  /// Clamp the server's hint to a sane backoff window: long enough to let the
  /// gate clear, short enough that a stuck gate cannot hold a pending delete
  /// hostage for the rest of the session.
  static func clamp(_ seconds: Int?) -> TimeInterval {
    guard let seconds, seconds > 0 else { return defaultRetryDelay }
    return min(max(TimeInterval(seconds), minRetryDelay), maxRetryDelay)
  }
}

/// Runs the single deferred retry for a gate-busy delete.
///
/// Holds at most one pending retry: a new schedule replaces (cancels) the
/// previous one, so repeated failures cannot accumulate tasks. The task holds
/// the scheduler weakly and the scheduler cancels its task on deinit, so a
/// deallocated view model cannot fire a late retry into a fresh instance.
/// The sleeper is injected so tests drive the delay deterministically.
@MainActor
final class MemoryDeleteRetryScheduler {
  typealias Sleeper = @Sendable (TimeInterval) async throws -> Void

  private let sleeper: Sleeper
  private var task: Task<Void, Never>?

  /// Delay of the currently pending retry, or nil when none is scheduled.
  private(set) var pendingDelay: TimeInterval?

  /// How many deferred retries have actually run.
  private(set) var retryCount = 0

  init(sleeper: Sleeper? = nil) {
    self.sleeper = sleeper ?? MemoryDeleteRetryScheduler.taskSleeper
  }

  /// Schedule one deferred `retry`. A pending retry is cancelled first; when
  /// the sleeper throws (cancellation) the retry is dropped without running.
  func schedule(after delay: TimeInterval, retry: @escaping @MainActor () async -> Void) {
    task?.cancel()
    pendingDelay = delay
    task = Task { [weak self] in
      guard let self else { return }
      do {
        try await self.sleeper(delay)
      } catch {
        self.pendingDelay = nil
        return
      }
      guard !Task.isCancelled else {
        self.pendingDelay = nil
        return
      }
      self.pendingDelay = nil
      self.retryCount += 1
      await retry()
    }
  }

  func cancel() {
    task?.cancel()
    task = nil
    pendingDelay = nil
  }

  deinit {
    task?.cancel()
  }

  static let taskSleeper: Sleeper = { delay in
    try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
  }
}
