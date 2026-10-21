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

/// Identity of one reconcile run: the owner key plus a generation that
/// advances every time the scheduler is reset or a different owner starts a
/// run. An attempt captures the token at admission and every terminal report
/// carries it back, so a report from a superseded run — an owner switch reset
/// the scheduler mid-fetch and a new run was admitted — is ignored instead of
/// ending or replacing the live run.
struct MemoryReconcileRunToken: Equatable, Sendable {
  let key: String
  let generation: Int
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
  /// Advances on every `end()`, so a token captured under an earlier
  /// generation never matches the live run even when the same user starts it.
  private(set) var generation = 0

  init(sleeper: Sleeper? = nil) {
    self.sleeper = sleeper ?? MemoryReconcileRetryScheduler.taskSleeper
  }

  /// Whether a delayed retry is currently waiting out its backoff.
  var hasPendingRetry: Bool { pendingTask != nil }

  /// Admit one reconcile attempt for `key`; the returned token names the run
  /// every terminal report must carry back. Nil while another attempt is in
  /// flight or a delayed retry is pending: the reconcile is single-flighted so
  /// concurrent loads cannot double-pull, and a pending retry owns the next
  /// slot instead of being bypassed by an immediate re-pull.
  func beginAttempt(
    key: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) -> MemoryReconcileRunToken? {
    guard !inFlight, pendingTask == nil else { return nil }
    if runKey != key { end() }
    runKey = key
    runAuthorizationSnapshot = authorizationSnapshot
    attempt += 1
    inFlight = true
    return MemoryReconcileRunToken(key: key, generation: generation)
  }

  /// True while `token` still names the live run — same owner key, and no
  /// `end()` since the token was issued. Terminal reports from any other run
  /// are dropped on this check.
  func isCurrentRun(_ token: MemoryReconcileRunToken) -> Bool {
    runKey == token.key && generation == token.generation
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
    guard runKey == key, attempt <= Self.retryDelays.count else { return false }
    inFlight = false
    let delay = Self.retryDelays[attempt - 1]
    log(
      "MemoriesViewModel: Cache reconcile truncated; retrying in \(Int(delay))s (attempt \(attempt + 1) of \(Self.retryDelays.count + 1))"
    )
    let run = MemoryReconcileRunToken(key: key, generation: generation)
    pendingTask?.cancel()
    pendingTask = Task { [weak self] in
      guard let self else { return }
      do {
        try await self.sleeper(delay)
      } catch {
        if self.isCurrentRun(run) { self.end() }
        return
      }
      // A cancellation that landed during the sleep (run ended, owner switch)
      // must never reach the retry.
      guard !Task.isCancelled else {
        if self.isCurrentRun(run) { self.end() }
        return
      }
      // The run this task was scheduled for may have been superseded while the
      // sleep was in flight (owner switch → end() → a new owner admitted); a
      // stale task must not clear the live run's pending retry.
      guard self.isCurrentRun(run) else { return }
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
    generation += 1
  }

  /// Report the active run (an in-flight attempt or a pending retry) through
  /// `report` — with its pre-reset token and attempt count — and then end the
  /// run exactly like `end()`. Used by the owner-switch reset, which must
  /// carry the dying run's `aborted_owner_changed` terminal signal even
  /// though the reset itself invalidates that token: the report fires before
  /// the generation bump, and a later completion from the superseded run is
  /// dropped by the token fence. A run that already terminated (or no run)
  /// reports nothing.
  func abortActiveRun(report: (MemoryReconcileRunToken, Int) -> Void) {
    if inFlight || pendingTask != nil, let key = runKey {
      report(MemoryReconcileRunToken(key: key, generation: generation), max(attempt, 1))
    }
    end()
  }

  static let taskSleeper: Sleeper = { delay in
    try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
  }
}

// MARK: - Reconcile run outcomes

extension MemoriesViewModel {

  /// Users whose reconcile run exhausted its in-launch retries on a truncated
  /// list. Separate from the success latch: nothing was pruned, and the next
  /// launch starts clean.
  static var exhaustedReconcileUserIDsThisLaunch: Set<String> = []

  /// Admission for one reconcile attempt; call at the top of
  /// `reconcileCacheIfNeeded()` after the launch-latch guard. Nil while
  /// another attempt is in flight, a bounded retry is pending, or this user's
  /// run already exhausted its retries this launch. The returned
  /// token names the run and must ride with every terminal report of this
  /// attempt, so a superseded run cannot end or replace the live one.
  func beginReconcileAttempt(userId: String) -> MemoryReconcileRunToken? {
    // An exhausted truncated run already spent this launch's pull budget for
    // the user; later Memories reloads must not start another full run.
    guard !Self.exhaustedReconcileUserIDsThisLaunch.contains(userId) else { return nil }
    return reconcileRetry.beginAttempt(
      key: userId,
      authorizationSnapshot: RuntimeOwnerIdentity.captureAuthorizationSnapshot())
  }

  /// The pull came back truncated, so absence proves nothing this attempt:
  /// schedule the next bounded in-launch retry, or — when the run's attempts
  /// are exhausted — finish the run without pruning and latch the attempt so
  /// the next launch, not the next reload, retries.
  func reconcileAttemptTruncated(run: MemoryReconcileRunToken) {
    // A superseded run's truncated report must neither schedule into the live
    // run's scheduler nor finish the live run.
    guard reconcileRetry.isCurrentRun(run) else { return }
    let scheduled = reconcileRetry.scheduleTruncatedRetry(key: run.key) { [weak self] in
      guard let self else { return }
      // Fencing before every re-entry: the run belongs to the owner that
      // started it, so a switch during the backoff aborts without pulling or
      // pruning. The new owner's own reconcile runs clean.
      guard self.reconcileRetry.isCurrentRun(run) else { return }
      if let snapshot = self.reconcileRetry.runAuthorizationSnapshot,
        RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot)
      {
        await self.reconcileCacheIfNeeded()
      } else {
        log("MemoriesViewModel: Cache reconcile retry aborted because the signed-in owner changed")
        self.finishReconcileRun(run: run, truncated: false, pruned: 0, outcome: .abortedOwnerChanged)
      }
    }
    if scheduled {
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "memories-cache",
        from: "server-page",
        to: "in-launch-retry",
        reason: "list_truncated",
        outcome: .degraded,
        extra: ["attempt": reconcileRetry.attempt + 1])
    } else {
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "memories-cache",
        from: "server-page",
        to: "next-launch",
        reason: "list_truncated",
        outcome: .exhausted,
        extra: ["attempt": max(reconcileRetry.attempt, 1)])
      // "next-launch" is a promise: latch the attempt (not the success) so a
      // later loadMemories() in this process does not spend another full
      // retry budget on a list that stays truncated.
      Self.exhaustedReconcileUserIDsThisLaunch.insert(run.key)
      finishReconcileRun(run: run, truncated: true, pruned: 0, outcome: .truncatedExhausted)
    }
  }

  /// An owner fence tripped mid-run: end it without pruning and without
  /// latching; the new owner's own reconcile must run clean. Ignored when the
  /// report comes from a run an owner switch already superseded.
  func reconcileRunAbortedByOwnerChange(run: MemoryReconcileRunToken) {
    finishReconcileRun(run: run, truncated: false, pruned: 0, outcome: .abortedOwnerChanged)
  }

  /// Owner-switch reset (`resetSessionState`): carry the dying run's
  /// `aborted_owner_changed` terminal signal before the reset invalidates its
  /// token, so a real account switch shows up on the reconcile telemetry
  /// instead of vanishing when the reset drops the run without a report.
  func endRunReportingOwnerChange() {
    reconcileRetry.abortActiveRun { [weak self] run, _ in
      self?.finishReconcileRun(
        run: run, truncated: false, pruned: 0, outcome: .abortedOwnerChanged)
    }
  }

  /// The reconcile threw: no in-launch retry (the policy covers truncation,
  /// not transport errors); unlatched, retried on the next launch as before.
  func reconcileRunFailed(run: MemoryReconcileRunToken) {
    finishReconcileRun(run: run, truncated: false, pruned: 0, outcome: .failed)
  }

  /// Complete pull, prune done, latch set: the terminal success.
  func reconcileRunCompleted(run: MemoryReconcileRunToken, pruned: Int) {
    finishReconcileRun(run: run, truncated: false, pruned: pruned, outcome: .complete)
  }

  private func finishReconcileRun(
    run: MemoryReconcileRunToken,
    truncated: Bool,
    pruned: Int,
    outcome: MemoryReconcileRunOutcome
  ) {
    // Terminal-report fence: an account switch can reset the scheduler while a
    // superseded run's page fetch is still awaiting, and the live run admitted
    // after the switch must survive that late report — no end(), no telemetry,
    // no reset of its attempt counter.
    guard reconcileRetry.isCurrentRun(run) else { return }
    let attempts = max(reconcileRetry.attempt, 1)
    reconcileRetry.end()
    MemoryCacheReconcileTelemetry.runFinished(
      truncated: truncated, pruned: pruned, attempts: attempts, outcome: outcome)
  }
}
