import Foundation
import SwiftUI

@MainActor
final class WhatsAppMessagingProvider: MessagingProvider {
  static let shared = WhatsAppMessagingProvider()

  private init() {}

  let id = "whatsapp"
  let displayName = "WhatsApp"
  let iconSystemName = "message.fill"
  var brandResourceName: String? { nil }

  var isConnected: Bool {
    WhatsAppState.shared.connectionState.isConnected
  }

  func loadThreads() async -> [MessageThread] {
    let threads = await WhatsAppReader.listChats()
    let draftThreadIds = Set(WhatsAppReplyCoordinator.shared.pendingDrafts.map(\.chatJid))
    return threads.map { thread in
      MessageThread(
        id: thread.id,
        providerId: thread.providerId,
        title: thread.title,
        subtitle: thread.subtitle,
        lastMessagePreview: thread.lastMessagePreview,
        lastActivity: thread.lastActivity,
        unreadCount: thread.unreadCount,
        isGroup: thread.isGroup,
        hasPendingDraft: draftThreadIds.contains(thread.id)
      )
    }
  }

  func loadMessages(threadId: String) async -> [MessageItem] {
    await WhatsAppReader.listMessages(chatJid: threadId)
  }

  func pendingDrafts() -> [PendingDraftItem] {
    WhatsAppReplyCoordinator.shared.pendingDrafts.map {
      PendingDraftItem(
        id: $0.id,
        threadId: $0.chatJid,
        text: $0.text,
        incomingText: $0.incomingText,
        createdAt: $0.createdAt
      )
    }
  }

  func sendMessage(threadId: String, text: String) async -> MessageSendResult {
    let result = await ChatToolExecutor.sendWhatsAppMessage(
      to: threadId,
      text: text,
      clientMessageID: "messages-ui:\(UUID().uuidString)"
    )
    guard let status = statusValue(from: result) else {
      return result.hasPrefix("Error:") ? .failed(result) : .sent
    }
    return status == "sent" ? .sent : .failed(errorValue(from: result) ?? result)
  }

  func approveDraft(id: String, editedText: String?) async -> String {
    await WhatsAppReplyCoordinator.shared.approveDraft(id: id, editedText: editedText)
  }

  func dismissDraft(id: String) {
    WhatsAppReplyCoordinator.shared.dismissDraft(id: id)
  }

  func alwaysAutoReply(id: String) async -> String {
    await WhatsAppReplyCoordinator.shared.alwaysAutoReplyAndApproveDraft(id: id)
  }

  func settingsView() -> AnyView {
    AnyView(WhatsAppSettingsSection(highlightedSettingId: .constant(nil)))
  }

  func connectView(onDismiss: @escaping () -> Void) -> AnyView {
    AnyView(WhatsAppConnectView(onDismiss: onDismiss))
  }

  private func statusValue(from jsonString: String) -> String? {
    guard let object = jsonObject(from: jsonString) else { return nil }
    return object["status"] as? String
  }

  private func errorValue(from jsonString: String) -> String? {
    guard let object = jsonObject(from: jsonString) else { return nil }
    return object["error"] as? String
  }

  private func jsonObject(from jsonString: String) -> [String: Any]? {
    guard let data = jsonString.data(using: .utf8) else { return nil }
    return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
  }
}
