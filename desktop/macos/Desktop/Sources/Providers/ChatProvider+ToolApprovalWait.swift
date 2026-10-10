import Foundation

extension ChatProvider {
  /// True while a device tool approval card for this turn's kernel session is
  /// waiting on the person. The turn's stall detector pauses for it: a card
  /// that is up is the person's turn, not a stalled tool, so neither the
  /// "taking longer than usual" banner nor the 90 s no-progress abort may
  /// fire while it waits. Keyed by the session the turn itself resolved, so
  /// the main chat, the agent pill and a workstream thread each see their own
  /// card. The composer's stop button still cancels the run.
  static func hasPendingToolApproval(
    sessionId: String?, approvals: DesktopToolApprovalStore = .shared
  ) -> Bool {
    approvals.approvals(forSessionId: sessionId).contains { $0.state.isPending }
  }
}
