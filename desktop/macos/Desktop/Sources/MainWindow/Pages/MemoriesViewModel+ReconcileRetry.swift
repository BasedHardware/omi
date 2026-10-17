import Foundation

/// Terminal outcome of one cache-reconcile run, as reported to PostHog.
enum MemoryReconcileRunOutcome: String {
  case complete
  case truncatedExhausted = "truncated_exhausted"
  case abortedOwnerChanged = "aborted_owner_changed"
  case failed
}

/// First product signal for the reconcile's prune path. Mirrors the light
/// `SearchAnalytics` mechanism (closed event name, property builder, one
/// PostHog call) so no new pipeline is introduced. Counts and booleans only.
@MainActor
enum MemoryCacheReconcileTelemetry {
  static let eventName = "Memories Cache Reconcile"

  /// Test observation at the same boundary as the PostHog call; nil in
  /// production. Mirrors the AnalyticsManager search-telemetry seam.
  static var captureForTests: (@MainActor (String, [String: Any]) -> Void)?

  static func runFinishedProperties(
    truncated: Bool,
    pruned: Int,
    attempts: Int,
    outcome: MemoryReconcileRunOutcome
  ) -> [String: Any] {
    ["truncated": truncated, "pruned": pruned, "attempts": attempts, "outcome": outcome.rawValue]
  }

  /// One event per reconcile run, fired when the run reaches a terminal
  /// outcome. `attempts` is the 1-based attempt number the run ended on, so a
  /// run that succeeded on its first scheduled retry reports `attempts: 2`.
  static func runFinished(
    truncated: Bool,
    pruned: Int,
    attempts: Int,
    outcome: MemoryReconcileRunOutcome
  ) {
    let properties = runFinishedProperties(
      truncated: truncated, pruned: pruned, attempts: attempts, outcome: outcome)
    captureForTests?(eventName, properties)
    PostHogManager.shared.track(eventName, properties: properties)
  }
}

/// Runs the bounded in-launch retry for a truncated cache reconcile, one run
/// at a time. Shaped like `MemoryDeleteRetryScheduler`: a small keyed
/// scheduler with an injected sleeper so tests drive the backoff
/// deterministically, cancellable when the run ends or the owner changes.
///
/// The retry re-enters `reconcileCacheIfNeeded()` itself, so every guard —
/// launch latch, fresh cursor, owner fencing before each sync and the prune —
/// runs again on every attempt exactly as it did on the first pull. The
/// scheduler only owns attempt admission and the delay between attempts.
@MainActor
final class MemoryReconcileRetryScheduler {
  typealias Sleeper = @Sendable (TimeInterval) async throws -> Void

  /// Monotonic backoff after a truncated pull: the first retry waits 30s, the
  /// second 60s, the third 120s. No jitter — the delays are the contract.
  static let retryDelays: [TimeInterval] = [30, 60, 120]

  private let sleeper: Sleeper
  /// The delayed retry that ends the current run's backoff window.
  private var pendingTask: Task<Void, Never>?
  /// True while an admitted attempt is executing (between `beginAttempt` and
  /// its terminal report). Guards the reconcile's single-flight admission.
  private var inFlight = false
  /// 1-based attempt number of the current run.
  private(set) var attempt = 0
  /// The user the current run reconciles; a different user's reconcile starts
  /// a fresh run rather than inheriting the previous counters.
  private(set) var runKey: String?
  /// Owner captured when the run's first attempt began. Every retry re-checks
  /// it before re-entering, so a run can never pull or prune for an owner it
  /// was not started by — even when the switch happens during the backoff.
  private(set) var runAuthorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?

  init(sleeper: Sleeper? = nil) {
    self.sleeper = sleeper ?? MemoryReconcileRetryScheduler.taskSleeper
  }

  /// Whether a delayed retry is currently waiting out its backoff.
  var hasPendingRetry: Bool { pendingTask != nil }

  /// Admit one reconcile attempt for `key`. False while another attempt is in
  /// flight or a delayed retry is pending: the reconcile is single-flighted so
  /// concurrent loads cannot double-pull, and a pending retry owns the next
  /// slot instead of being bypassed by an immediate re-pull.
  func beginAttempt(
    key: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) -> Bool {
    guard !inFlight, pendingTask == nil else { return false }
    if runKey != key { end() }
    runKey = key
    runAuthorizationSnapshot = authorizationSnapshot
    attempt += 1
    inFlight = true
    return true
  }

  /// A truncated pull ended the current attempt. Schedules the next bounded
  /// retry (which re-enters the reconcile with every guard re-run) and returns
  /// true; returns false when the run's attempts are exhausted, leaving the
  /// caller to finish the run (reporting the final attempt count) unlatched so
  /// the next launch retries.
  func scheduleTruncatedRetry(
    key: String,
    retry: @escaping @MainActor () async -> Void
  ) -> Bool {
    inFlight = false
    guard runKey == key, attempt <= Self.retryDelays.count else { return false }
    let delay = Self.retryDelays[attempt - 1]
    log(
      "MemoriesViewModel: Cache reconcile truncated; retrying in \(Int(delay))s (attempt \(attempt + 1) of \(Self.retryDelays.count + 1))"
    )
    pendingTask?.cancel()
    pendingTask = Task { [weak self] in
      guard let self else { return }
      do {
        try await self.sleeper(delay)
      } catch {
        self.end()
        return
      }
      // A cancellation that landed during the sleep (run ended, owner switch)
      // must never reach the retry.
      guard !Task.isCancelled else {
        self.end()
        return
      }
      self.pendingTask = nil
      await retry()
    }
    return true
  }

  /// End the current run: cancel any pending retry and reset the counters so
  /// the next admitted attempt starts a fresh run.
  func end() {
    pendingTask?.cancel()
    pendingTask = nil
    inFlight = false
    attempt = 0
    runKey = nil
    runAuthorizationSnapshot = nil
  }

  static let taskSleeper: Sleeper = { delay in
    try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
  }
}

// MARK: - Reconcile run outcomes

extension MemoriesViewModel {

  /// Admission for one reconcile attempt; call at the top of
  /// `reconcileCacheIfNeeded()` after the launch-latch guard. False while
  /// another attempt is in flight or a bounded retry is pending.
  func beginReconcileAttempt(userId: String) -> Bool {
    reconcileRetry.beginAttempt(
      key: userId,
      authorizationSnapshot: RuntimeOwnerIdentity.captureAuthorizationSnapshot())
  }

  /// The pull came back truncated, so absence proves nothing this attempt:
  /// schedule the next bounded in-launch retry, or — when the run's attempts
  /// are exhausted — finish the run unlatched so the next launch retries,
  /// exactly as a truncated reconcile used to.
  func reconcileAttemptTruncated(userId: String) {
    let scheduled = reconcileRetry.scheduleTruncatedRetry(key: userId) { [weak self] in
      guard let self else { return }
      // Fencing before every re-entry: the run belongs to the owner that
      // started it, so a switch during the backoff aborts without pulling or
      // pruning. The new owner's own reconcile runs clean.
      if let snapshot = self.reconcileRetry.runAuthorizationSnapshot,
        RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot)
      {
        await self.reconcileCacheIfNeeded()
      } else {
        log("MemoriesViewModel: Cache reconcile retry aborted because the signed-in owner changed")
        self.finishReconcileRun(truncated: false, pruned: 0, outcome: .abortedOwnerChanged)
      }
    }
    if !scheduled {
      finishReconcileRun(truncated: true, pruned: 0, outcome: .truncatedExhausted)
    }
  }

  /// An owner fence tripped mid-run: end it without pruning and without
  /// latching; the new owner's own reconcile must run clean.
  func reconcileRunAbortedByOwnerChange() {
    finishReconcileRun(truncated: false, pruned: 0, outcome: .abortedOwnerChanged)
  }

  /// The reconcile threw: no in-launch retry (the policy covers truncation,
  /// not transport errors); unlatched, retried on the next launch as before.
  func reconcileRunFailed() {
    finishReconcileRun(truncated: false, pruned: 0, outcome: .failed)
  }

  /// Complete pull, prune done, latch set: the terminal success.
  func reconcileRunCompleted(pruned: Int) {
    finishReconcileRun(truncated: false, pruned: pruned, outcome: .complete)
  }

  private func finishReconcileRun(
    truncated: Bool,
    pruned: Int,
    outcome: MemoryReconcileRunOutcome
  ) {
    let attempts = max(reconcileRetry.attempt, 1)
    reconcileRetry.end()
    MemoryCacheReconcileTelemetry.runFinished(
      truncated: truncated, pruned: pruned, attempts: attempts, outcome: outcome)
  }
}
