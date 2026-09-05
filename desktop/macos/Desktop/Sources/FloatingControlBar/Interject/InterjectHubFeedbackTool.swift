import Foundation

/// Silent hub tool for Interject classification. The verb travels here, not
/// on the speech channel. The tool result is opaque so a speech model cannot
/// read it aloud.
enum InterjectHubFeedbackTool {
  static let opaqueResult = #"{"ok":true}"#

  /// Card identity captured when the tool call is admitted (synchronous with
  /// the hub event). The async write must not blindly re-read mutable UI
  /// state: it rechecks the live recent card against this snapshot, so an
  /// owner or card change between admission and the write can never classify
  /// the wrong card.
  struct AdmittedFeedback: Sendable {
    let identity: SuggestionAssistantTelemetry.NotificationIdentity
  }

  /// Admission: capture the current card identity synchronously with the hub
  /// event. Flag-off or no current card admits nothing.
  @MainActor
  static func admit(
    isEnabled: Bool = InterjectFeature.isEnabled,
    identity: SuggestionAssistantTelemetry.NotificationIdentity? = FloatingControlBarManager.shared
      .recentNotchCardFeedbackIdentity()
  ) -> AdmittedFeedback? {
    guard isEnabled, let identity else { return nil }
    return AdmittedFeedback(identity: identity)
  }

  /// Write the admitted classification through the single mutation owner.
  /// Owner/turn fence: immediately before the mutation the live recent card
  /// must still match the admitted snapshot. Invalid verb, missing admission,
  /// and a replaced card are all no-ops — no store, no analytics.
  @MainActor
  static func recordIfAdmitted(
    _ admitted: AdmittedFeedback?,
    verbRaw: String?,
    currentIdentity: SuggestionAssistantTelemetry.NotificationIdentity? = FloatingControlBarManager.shared
      .recentNotchCardFeedbackIdentity(),
    store: InterjectSuggestionFeedbackStore = .shared,
    emitAnalytics: Bool = true
  ) async {
    guard let admitted,
      let verbRaw,
      let verb = InterjectFeedbackVerb(rawValue: verbRaw),
      let currentIdentity,
      currentIdentity == admitted.identity
    else { return }
    _ = await InterjectSuggestionFeedbackMutation.record(
      evaluationID: admitted.identity.evaluationID,
      suggestionID: admitted.identity.suggestionID,
      verb: verb,
      store: store,
      emitAnalytics: emitAnalytics
    )
  }
}

extension RealtimeHubController {
  /// Local Interject classification — same placement as
  /// `report_screen_observation`, before kernel-authorized tools. The card
  /// identity is captured at admission; the async write rechecks the live
  /// card against that snapshot before mutating.
  func handleInterjectFeedbackReport(
    source: RealtimeHubSession,
    callId: String,
    arguments: [String: Any],
    expectedTurnEpoch: Int
  ) {
    let verbRaw = arguments["verb"] as? String
    let admitted = InterjectHubFeedbackTool.admit()
    Task {
      await InterjectHubFeedbackTool.recordIfAdmitted(admitted, verbRaw: verbRaw)
    }
    sendToolResultIfCurrent(
      source: source,
      callId: callId,
      name: HubTool.recordInterjectFeedback.rawValue,
      output: InterjectHubFeedbackTool.opaqueResult,
      expectedTurnEpoch: expectedTurnEpoch)
  }
}
