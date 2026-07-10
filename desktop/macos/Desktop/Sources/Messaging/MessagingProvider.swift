import SwiftUI

@MainActor
protocol MessagingProvider: AnyObject {
  var id: String { get }
  var displayName: String { get }
  var iconSystemName: String { get }
  var connectorBrand: ConnectorBrand? { get }

  var isConnected: Bool { get }

  func loadThreads() async -> [MessageThread]
  func loadMessages(threadId: String) async -> [MessageItem]
  func pendingDrafts() -> [PendingDraftItem]

  func sendMessage(threadId: String, text: String) async -> MessageSendResult
  func approveDraft(id: String, editedText: String?) async -> String
  func dismissDraft(id: String)
  func alwaysAutoReply(id: String) async -> String

  func settingsView() -> AnyView
  func connectView(onDismiss: @escaping () -> Void) -> AnyView
}
