import Foundation

/// Silent hub tool for Interject classification. The verb travels here, not
/// on the speech channel. The tool result is opaque so a speech model cannot
/// read it aloud.
enum InterjectHubFeedbackTool {
  static let opaqueResult = #"{"ok":true}"#

  /// Local, flag-gated write through the single mutation owner. Invalid verb,
  /// missing card identity, and flag-off are all no-ops — no store, no analytics.
  @MainActor
  static func recordIfAuthorized(
    verbRaw: String?,
    isEnabled: Bool = InterjectFeature.isEnabled,
    identity: SuggestionAssistantTelemetry.NotificationIdentity? = FloatingControlBarManager.shared
      .recentNotchCardFeedbackIdentity(),
    store: InterjectSuggestionFeedbackStore = .shared,
    emitAnalytics: Bool = true
  ) async {
    guard isEnabled,
      let verbRaw,
      let verb = InterjectFeedbackVerb(rawValue: verbRaw),
      let identity
    else { return }
    await InterjectSuggestionFeedbackMutation.record(
      evaluationID: identity.evaluationID,
      suggestionID: identity.suggestionID,
      verb: verb,
      store: store,
      emitAnalytics: emitAnalytics
    )
  }
}

extension RealtimeHubController {
  /// Local Interject classification — same placement as
  /// `report_screen_observation`, before kernel-authorized tools.
  func handleInterjectFeedbackReport(
    source: RealtimeHubSession,
    callId: String,
    arguments: [String: Any],
    expectedTurnEpoch: Int
  ) {
    let verbRaw = arguments["verb"] as? String
    Task { await InterjectHubFeedbackTool.recordIfAuthorized(verbRaw: verbRaw) }
    sendToolResultIfCurrent(
      source: source,
      callId: callId,
      name: HubTool.recordInterjectFeedback.rawValue,
      output: InterjectHubFeedbackTool.opaqueResult,
      expectedTurnEpoch: expectedTurnEpoch)
  }
}
