import Foundation
import VoiceTurnDomain

extension RealtimeHubController {
  func acceptsTurnEvent(
    _ identity: RealtimeHubEventIdentity?,
    source: RealtimeHubSession
  ) -> Bool {
    guard isCurrentSession(source), let identity else { return false }
    guard VoiceTurnCoordinator.shared.requireCurrentOwner(for: identity.turnID) != nil else {
      log("RealtimeHub: dropping provider event after authenticated owner changed")
      return false
    }
    switch RealtimeHubEventOwnership.admission(
      identity,
      activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
      activeResponseID: voiceResponseID
    ) {
    case .accept:
      return true
    case .dropStaleTurn:
      log(
        "RealtimeHub: dropping stale provider event turn=\(identity.turnID) "
          + "response=\(identity.responseID)")
      return false
    case .rejectCurrentTurnResponse:
      // A live session speaking for the current logical turn with the wrong
      // response identity is a broken handoff, not an old-turn callback. Fail
      // immediately so PTT never waits for the provider-no-response deadline.
      log(
        "RealtimeHub: rejecting current-turn provider response identity turn=\(identity.turnID) "
          + "response=\(identity.responseID)")
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "realtime_hub",
        from: sessionProvider?.rawValue ?? "unbound",
        to: "none",
        reason: "response_identity_mismatch",
        outcome: .exhausted,
        extra: ["user_visible": true])
      source.cancelActiveResponse()
      VoiceTurnCoordinator.shared.publish(
        .finish(turnID: identity.turnID, reason: .providerFailed))
      exitVoiceUI(clearResponseGlow: true)
      return false
    }
  }
}
