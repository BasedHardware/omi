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

  /// Non-production manager-harness facts. These describe ownership and
  /// admission only; they deliberately omit turn IDs, context payload, and
  /// provider text so a failed physical-path probe is diagnosable without
  /// exposing user content.
  func automationPTTInputDiagnostics() -> [String: String] {
    let requirement = voiceSessionContext(for: currentOwnerScope)
    let preparation: String
    if reconnectAudioBuffer != nil {
      preparation = "buffered"
    } else if admittedInputTurnID != nil {
      preparation = "admitted"
    } else {
      preparation = "none"
    }
    return [
      "ptt_admission": pttAdmission == .immediate ? "immediate" : "capture_and_buffer",
      "ptt_input_preparation": preparation,
      "ptt_rebind_attempts": "\(reconnectAudioBuffer?.rebindAttempts ?? 0)",
      "ptt_binding_matches_requirement":
        (requirement.isResolved && requirement.snapshotFreshnessIdentity == sessionVoiceContextFreshnessIdentity)
        ? "true" : "false",
      "ptt_handoff_pending": pendingSessionRefreshReason ?? "none",
    ]
  }
}
