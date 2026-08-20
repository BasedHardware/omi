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

  static func sendSummary(
    conversationID: String, recipients: [ConversationShareRecipient]
  ) async throws -> [String] {
    try await APIClient.shared.sendConversationSummaryEmail(
      id: conversationID,
      recipientEmails: recipients.map(\.email)
    )
  }
}
