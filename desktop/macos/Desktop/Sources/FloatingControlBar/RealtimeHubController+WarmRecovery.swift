import Foundation
import OmiSupport
import VoiceTurnDomain

/// Connect-path authorization for a warm realtime session. The plan gate and
/// `ensureWarm` share this so a stored-but-unusable voice key cannot skip the
/// gate and then fall through to a managed mint.
enum RealtimeWarmCredential: Equatable {
  case clientDirect(key: String)
  case unusableBYOK(key: String, fingerprint: String)
  case none
}

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
  ///
  /// Text-lane `APIKeyService.isByokActive` (selected LLM provider enrolled and
  /// fingerprint-matched) is NOT the hub's BYOK test. A basic user can keep
  /// OpenRouter as the text provider, hold `dev_gemini_api_key`, and pick Gemini
  /// as Voice Model: `isByokActive` is false so the subscription decision is
  /// `.planGated`, but `selectedRealtimeBYOKKey(chosenForVoice:)` is non-nil and
  /// the hub connects client-direct at our $0. Warming is governed by that
  /// realtime key: exempt only when this session will actually connect
  /// client-direct. A stored key that `canUseBYOK` rejects falls through to
  /// managed mint on the connect path — the same `resolvedRealtimeWarmCredential`
  /// decision, so a known-bad key is not an exemption.
  func shouldSkipAutomaticManagedWarm() -> Bool {
    if case .clientDirect = resolvedRealtimeWarmCredential() { return false }
    let decision = entitlementDecision()
    let skip = managedPlanGateLatch.shouldSkipAutomaticManagedWork(
      decision: decision,
      now: entitlementNow(),
      ownerID: managedPlanGateOwnerID())
    if decision == .allowManagedProactivity, !managedPlanGateLatch.serverDenied {
      didLogPlanGateSkip = false
    }
    if skip {
      logPlanGateSkipOnce()
      requestEntitlementRefresh()
    }
    return skip
  }

  /// Same key `ensureWarm` will pass to `startSession`. Tests pin the resolver.
  func resolvedRealtimeBYOKKey() -> String? {
    if let realtimeBYOKKeyResolver {
      return realtimeBYOKKeyResolver()
    }
    let provider = effectiveProvider
    return APIKeyService.selectedRealtimeBYOKKey(
      for: provider.byokProvider,
      chosenForVoice: RealtimeHubSettings.shared.isVoiceModelChoice(provider))
  }

  /// Authorization the connect path will make: a stored voice key is not enough.
  /// Known-bad fingerprints (`canUseBYOK` false) are `.unusableBYOK` and mint.
  func resolvedRealtimeWarmCredential() -> RealtimeWarmCredential {
    guard let key = resolvedRealtimeBYOKKey() else { return .none }
    let fingerprint = APIKeyService.byokFingerprint(key)
    if canUseRealtimeBYOK(effectiveProvider.byokProvider, fingerprint) {
      return .clientDirect(key: key)
    }
    return .unusableBYOK(key: key, fingerprint: fingerprint)
  }

  /// Launch / re-entrant `PushToTalkManager.setup`: not a key press, so the plan
  /// gate still applies, but an existing away deferral must not block an entitled
  /// user the way a passive `ensureWarm()` would.
  func prepareAutomaticWarm() {
    clearPresenceWarmDeferral()
    ensureWarm()
  }

  func resetManagedPlanGateForOwnerChange() {
    planGateRetryTask?.cancel()
    planGateRetryTask = nil
    entitlementRefreshGeneration &+= 1
    entitlementRefreshTask?.cancel()
    entitlementRefreshTask = nil
    entitlementRefreshInFlight = false
    managedPlanGateLatch.reset()
    didLogPlanGateSkip = false
  }

  func noteManagedPlanGateFromWarmFailure(_ error: Error) {
    guard ManagedPlanGateHTTP.isPlanGatedWarmFailure(error) else { return }
    managedPlanGateLatch.latchServerDenial(at: entitlementNow(), ownerID: managedPlanGateOwnerID())
    logPlanGateSkipOnce()
    requestEntitlementRefresh()
    scheduleBoundedManagedWarmRetry()
    log("RealtimeHub: server plan_gated — stopping automatic managed re-warm")
  }

  /// One delayed `ensureWarm` after a typed server denial. Without this, the
  /// plan-gated close path tears down and never observes latch expiry.
  func scheduleBoundedManagedWarmRetry() {
    planGateRetryTask?.cancel()
    guard let delay = planGateRetryDelayNanoseconds else {
      planGateRetryTask = nil
      return
    }
    let ownerAtLatch = managedPlanGateOwnerID()
    planGateRetryTask = Task { @MainActor [weak self] in
      if delay > 0 {
        try? await Task.sleep(nanoseconds: delay)
      }
      guard let self, !Task.isCancelled else { return }
      self.planGateRetryTask = nil
      guard self.managedPlanGateOwnerID() == ownerAtLatch else { return }
      self.performScheduledManagedWarmRetry()
    }
  }

  func performScheduledManagedWarmRetry() {
    ensureWarm()
  }

  /// After an expected idle/lifecycle close: skip (plan gated), defer (user
  /// away), or replace the socket. Tests drive this instead of a live WS.
  @discardableResult
  func continueWarmAfterLifecycleClose(
    closeCategory: RealtimeHubCloseCategory?
  ) -> RealtimeProviderCloseRecoveryResult {
    if shouldSkipAutomaticManagedWarm() {
      teardownSession()
      return .deferredPlanGated
    }
    if deferIdleRewarmIfUserAway(closeCategory: closeCategory) {
      return .deferredUserAway
    }
    guard !reconnectPending, hubReconnectStrikes < Self.maxReconnectStrikes else {
      teardownSession()
      return .exhausted
    }
    hubReconnectStrikes += 1
    reconnectPending = true
    replaceSessionAfterDrain(reconnectDelayNanoseconds: lifecycleRewarmDelayNanoseconds)
    return .started
  }

  private func logPlanGateSkipOnce() {
    guard !didLogPlanGateSkip else { return }
    didLogPlanGateSkip = true
    log("RealtimeHub: managed realtime unavailable on this plan; skipping automatic warm")
  }

  private func requestEntitlementRefresh() {
    guard let refreshEntitlement, !entitlementRefreshInFlight else { return }
    entitlementRefreshInFlight = true
    entitlementRefreshGeneration &+= 1
    let generation = entitlementRefreshGeneration
    let ownerAtStart = managedPlanGateOwnerID()
    entitlementRefreshTask = Task { [weak self] in
      await refreshEntitlement()
      await MainActor.run {
        guard let self else { return }
        self.planGateRefreshDidFinish?()
        guard self.entitlementRefreshGeneration == generation else { return }
        self.entitlementRefreshInFlight = false
        self.entitlementRefreshTask = nil
        guard !Task.isCancelled, self.managedPlanGateOwnerID() == ownerAtStart else { return }
        self.completeEntitlementRefresh()
      }
    }
  }

  /// Refresh finished. If the decision is now allow (upgrade, BYOK, or a
  /// newly populated cache), drop a stale skip and re-drive one warm. Does
  /// not call `shouldSkipAutomaticManagedWarm` so it cannot loop a refresh.
  func completeEntitlementRefresh() {
    let decision = entitlementDecision()
    let skip = managedPlanGateLatch.shouldSkipAutomaticManagedWork(
      decision: decision,
      now: entitlementNow(),
      ownerID: managedPlanGateOwnerID())
    guard !skip else { return }
    didLogPlanGateSkip = false
    ensureWarm()
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
