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

/// Runs the deferred retry for a gate-busy delete, one slot per memory id.
///
/// Deleting a second memory during a first memory's retry window must not
/// cancel the first memory's only server delete, so pending retries are keyed
/// by memory id: a new `schedule` for id X replaces (cancels) only X's
/// previous retry. Pending retries are bounded (`maxPendingRetries`, evicting
/// the oldest first) so a pathological loop cannot accumulate unbounded work.
/// The task holds the scheduler weakly and the scheduler cancels its tasks on
/// deinit, so a deallocated view model cannot fire a late retry into a fresh
/// instance. The sleeper is injected so tests drive the delay deterministically.
@MainActor
final class MemoryDeleteRetryScheduler {
  typealias Sleeper = @Sendable (TimeInterval) async throws -> Void

  /// Bound on concurrently pending retries. Eviction is FIFO: the oldest
  /// pending retry is cancelled first, which leaves its row soft-deleted —
  /// exactly the state a still-busy gate already produces.
  static let maxPendingRetries = 8

  private let sleeper: Sleeper
  private var tasks: [String: Task<Void, Never>] = [:]
  /// Pending ids in schedule order, for FIFO eviction and `pendingDelay`.
  private var pendingIDs: [String] = []
  private var pendingDelays: [String: TimeInterval] = [:]

  /// Delay of the most recently scheduled pending retry, or nil when none is
  /// scheduled.
  var pendingDelay: TimeInterval? {
    pendingIDs.last.flatMap { pendingDelays[$0] }
  }

  /// How many deferred retries have actually run, across all memory ids.
  private(set) var retryCount = 0

  init(sleeper: Sleeper? = nil) {
    self.sleeper = sleeper ?? MemoryDeleteRetryScheduler.taskSleeper
  }

  /// Schedule one deferred `retry` for `memoryID`. A pending retry for the
  /// same memory is cancelled first; retries pending for other memories are
  /// left alone. When the sleeper throws (cancellation) the retry is dropped
  /// without running.
  func schedule(
    after delay: TimeInterval,
    memoryID: String,
    retry: @escaping @MainActor () async -> Void
  ) {
    cancel(memoryID: memoryID)
    if pendingIDs.count >= Self.maxPendingRetries, let oldest = pendingIDs.first {
      cancel(memoryID: oldest)
    }
    pendingIDs.append(memoryID)
    pendingDelays[memoryID] = delay
    tasks[memoryID] = Task { [weak self] in
      guard let self else { return }
      do {
        try await self.sleeper(delay)
      } catch {
        self.finishPending(memoryID: memoryID)
        return
      }
      // A cancellation that landed during the sleep (undo, session reset, or
      // replacement by a newer schedule) must never reach the delete.
      guard !Task.isCancelled else {
        self.finishPending(memoryID: memoryID)
        return
      }
      self.finishPending(memoryID: memoryID)
      self.retryCount += 1
      await retry()
    }
  }

  /// Cancel `memoryID`'s pending retry only; other ids' retries survive.
  func cancel(memoryID: String) {
    tasks.removeValue(forKey: memoryID)?.cancel()
    finishPending(memoryID: memoryID)
  }

  /// Cancel every pending retry (sign-out / owner switch).
  func cancelAll() {
    for task in tasks.values {
      task.cancel()
    }
    tasks.removeAll()
    pendingIDs.removeAll()
    pendingDelays.removeAll()
  }

  /// Whether `memoryID` still has a retry waiting to fire.
  func hasPendingRetry(for memoryID: String) -> Bool {
    tasks[memoryID] != nil
  }

  /// How many retries are currently pending.
  var pendingCount: Int { pendingIDs.count }

  private func finishPending(memoryID: String) {
    tasks.removeValue(forKey: memoryID)
    pendingIDs.removeAll { $0 == memoryID }
    pendingDelays.removeValue(forKey: memoryID)
  }

  deinit {
    for task in tasks.values {
      task.cancel()
    }
  }

  static let taskSleeper: Sleeper = { delay in
    try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
  }
}
