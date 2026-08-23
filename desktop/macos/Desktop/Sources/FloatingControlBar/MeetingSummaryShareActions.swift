import AppKit

/// The meeting summary share card's two actions, factored out of the SwiftUI
/// card so the automation bridge exercises the identical implementation the
/// buttons call (copy mints the link and writes the pasteboard; send emails
/// the backend-validated recipients).
@MainActor
enum MeetingSummaryShareActions {
  static func copyLink(conversationID: String) async -> ConversationShareLinkFeedback {
    await ConversationShareLinkAction.run(
      mintLink: { try await APIClient.shared.getConversationShareLink(id: conversationID) },
      copyToPasteboard: { link in
        NSPasteboard.general.clearContents()
        return NSPasteboard.general.setString(link, forType: .string)
      }
    )
  }

  /// Open the conversation detail for this meeting's summary: summon the main
  /// window, land on Conversations, and drive the same pending-open request the
  /// established conversation-open path consumes.
  static func openSummary(conversationID: String) {
    AppDelegate.summonWindowTarget()?.openMainAppWindow()
    postOpenSignals(conversationID: conversationID)
  }

  /// Window-independent half of `openSummary`, separated so a hermetic test can
  /// assert the navigation contract without AppKit window state.
  static func postOpenSignals(conversationID: String) {
    NotificationCenter.default.post(
      name: .navigateToSidebarItem,
      object: nil,
      userInfo: ["rawValue": SidebarNavItem.conversations.rawValue]
    )
    ConversationDetailAutomationState.shared.requestOpen(
      conversationId: conversationID,
      showTranscript: false
    )
    NotificationCenter.default.post(name: .desktopAutomationOpenConversationRequested, object: nil)
  }

  /// Email these notes to the addresses the owner typed (detection only
  /// prefilled the field, so the address is theirs, not ours).
  static func sendSummary(
    conversationID: String, recipientEmails: [String]
  ) async throws -> [String] {
    try await APIClient.shared.sendConversationSummaryEmail(
      id: conversationID,
      recipientEmails: recipientEmails
    )
  }
}
