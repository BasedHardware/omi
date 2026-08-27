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
      while !Task.isCancelled {
        try? await Task.sleep(
          nanoseconds: UInt64(RealtimeHubWarmPresencePolicy.presencePollInterval * 1_000_000_000))
        guard let self, !Task.isCancelled else { return }
        guard self.warmDeferredForUserAway else { return }
        if RealtimeHubWarmPresencePolicy.shouldResumeWarming(
          secondsSinceLastUserInput: self.presenceIdleProvider())
        {
          log("RealtimeHub: user input resumed — re-warming deferred hub session")
          self.ensureWarm()
          return
        }
      }
    }
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
