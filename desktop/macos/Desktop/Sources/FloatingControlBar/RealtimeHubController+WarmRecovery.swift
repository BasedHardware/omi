import Foundation
import OmiSupport
import VoiceTurnDomain

/// Recovery for the two *expected* warm-session lifecycle closes: provider
/// idle teardowns (presence-gated re-warm) and provider session rotation.
extension RealtimeHubController {
  // MARK: - Presence-gated warming

  /// A normal idle teardown with the user away from the machine does not
  /// re-warm: each unconditional re-warm re-bills the full session context
  /// (~18.5k tokens measured) around the clock, per running app — the loop
  /// that exhausted the shared Gemini quota fleet-wide. Returns true when the
  /// re-warm was deferred; the caller records the close resolution.
  func deferIdleRewarmIfUserAway(closeCategory: RealtimeHubCloseCategory?) -> Bool {
    guard closeCategory == .expectedIdleTeardown,
      !RealtimeHubWarmPresencePolicy.shouldRewarmAfterIdleTeardown(
        secondsSinceLastUserInput: presenceIdleProvider())
    else { return false }
    log("RealtimeHub: user away — deferring hub re-warm until input activity returns")
    teardownSession()
    deferRewarmWhileUserAway()
    return true
  }

  /// Idle teardown fired while the user is away: stop the re-warm loop and
  /// poll for returned input. Any explicit `ensureWarm()` (PTT-down, settings
  /// change) also clears the deferral immediately, so this can never make a
  /// present user wait.
  func deferRewarmWhileUserAway() {
    warmDeferredForUserAway = true
    presenceRewarmTask?.cancel()
    presenceRewarmTask = Task { @MainActor [weak self] in
      var previousSampleAt = Date()
      while !Task.isCancelled {
        try? await Task.sleep(
          nanoseconds: UInt64(RealtimeHubWarmPresencePolicy.presencePollInterval * 1_000_000_000))
        guard let self, !Task.isCancelled else { return }
        let now = Date()
        let elapsed = now.timeIntervalSince(previousSampleAt)
        previousSampleAt = now
        if self.presencePollTick(elapsedSincePreviousSample: elapsed) { return }
      }
    }
  }

  /// One presence-poll tick. Returns true when polling should stop — either
  /// warming resumed or the deferral is gone. The freshness window is the
  /// MEASURED gap since the previous sample plus slack, so a poll delayed by
  /// the scheduler still accepts input that arrived anywhere in the gap
  /// (a fixed sub-gap window would miss a brief return permanently).
  @discardableResult
  func presencePollTick(elapsedSincePreviousSample: TimeInterval) -> Bool {
    guard warmDeferredForUserAway else { return true }
    guard
      RealtimeHubWarmPresencePolicy.shouldResumeWarming(
        secondsSinceLastUserInput: presenceIdleProvider(),
        freshnessWindow: max(
          RealtimeHubWarmPresencePolicy.presencePollInterval,
          elapsedSincePreviousSample) + RealtimeHubWarmPresencePolicy.presencePollSlack)
    else { return false }
    log("RealtimeHub: user input resumed — re-warming deferred hub session")
    // Presence return is not a key press. Clear the away deferral so a later
    // PTT is not stuck, then keep-warm (plan-gated accounts skip the mint).
    clearPresenceWarmDeferral()
    ensureWarm()
    return true
  }

  /// Skip idle/reconnect/launch mint when the cached decision is `.planGated`
  /// or after a typed server `plan_gated`. User-initiated PTT still attempts.
  /// Same latch as LiveNotes `shouldSkipManagedAINotes`.
  func shouldSkipAutomaticManagedWarm() -> Bool {
    let decision = entitlementDecision()
    let skip = managedPlanGateLatch.shouldSkipAutomaticManagedWork(
      decision: decision,
      now: entitlementNow())
    if decision == .allowManagedProactivity, !managedPlanGateLatch.serverDenied {
      didLogPlanGateSkip = false
    }
    if skip {
      logPlanGateSkipOnce()
      requestEntitlementRefresh()
    }
    return skip
  }

  func noteManagedPlanGateFromWarmFailure(_ error: Error) {
    guard ManagedPlanGateHTTP.isPlanGatedWarmFailure(error) else { return }
    managedPlanGateLatch.latchServerDenial(at: entitlementNow())
    logPlanGateSkipOnce()
    requestEntitlementRefresh()
    log("RealtimeHub: server plan_gated — stopping automatic managed re-warm")
  }

  private func logPlanGateSkipOnce() {
    guard !didLogPlanGateSkip else { return }
    didLogPlanGateSkip = true
    log("RealtimeHub: managed realtime unavailable on this plan; skipping automatic warm")
  }

  private func requestEntitlementRefresh() {
    guard let refreshEntitlement, !entitlementRefreshInFlight else { return }
    entitlementRefreshInFlight = true
    Task { [weak self] in
      await refreshEntitlement()
      await MainActor.run {
        self?.entitlementRefreshInFlight = false
      }
    }
  }

  /// Gate on every `ensureWarm` entry. A path carrying direct user intent
  /// (PTT press, automation) always clears an away deferral. Passive
  /// lifecycle callers (mint completions, owner-change recovery, barge-in
  /// cleanup) keep it unless the HID sample shows the user actually returned
  /// — otherwise background churn would silently defeat the quota gate.
  func admitWarmRequest(userInitiated: Bool) -> Bool {
    guard warmDeferredForUserAway else { return true }
    guard
      userInitiated
        || RealtimeHubWarmPresencePolicy.shouldResumeWarming(
          secondsSinceLastUserInput: presenceIdleProvider())
    else {
      log("RealtimeHub: passive warm request skipped — deferred while user away")
      return false
    }
    clearPresenceWarmDeferral()
    return true
  }

  func clearPresenceWarmDeferral() {
    guard warmDeferredForUserAway || presenceRewarmTask != nil else { return }
    warmDeferredForUserAway = false
    presenceRewarmTask?.cancel()
    presenceRewarmTask = nil
  }

  // MARK: - Expected session rotation

  /// OpenAI limits realtime sessions to sixty minutes. Rotation is a normal
  /// transport lifecycle event: keep the provider choice, replace the retired
  /// socket immediately, and let the reducer terminalize an interrupted turn.
  func recoverFromExpectedSessionRotation(
    _ plan: RealtimeHubSessionRotationPlan,
    activeTurn: VoiceTurn?
  ) {
    if plan == .terminateActiveTurnAndRewarm {
      terminateActiveHubTurn(activeTurn)
    }
    hubReconnectStrikes = 0
    reconnectPending = true
    replaceSessionAfterDrain()
  }
}
