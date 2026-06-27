import Foundation
import SwiftUI

@MainActor
final class WhatsAppMessagingProvider: MessagingProvider {
  static let shared = WhatsAppMessagingProvider()

  private init() {}
  private var backfilledThreadIds: Set<String> = []
  private var draftThreadAliases: [String: String] = [:]

  let id = "whatsapp"
  let displayName = "WhatsApp"
  let iconSystemName = "message.fill"
  var brandResourceName: String? { nil }

  var isConnected: Bool {
    WhatsAppState.shared.connectionState.isConnected
  }

  func loadThreads() async -> [MessageThread] {
    let threads = await WhatsAppReader.listChats()
    let pendingDrafts = WhatsAppReplyCoordinator.shared.pendingDrafts
    draftThreadAliases = draftAliases(for: pendingDrafts, in: threads)
    let draftThreadIds = Set(pendingDrafts.map { canonicalThreadId(for: $0) })
    let mappedThreads = threads.map { thread in
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
    let existingThreadIds = Set(mappedThreads.map(\.id))
    let draftOnlyThreads = pendingDrafts
      .filter { !existingThreadIds.contains(canonicalThreadId(for: $0)) }
      .reduce(into: [String: WhatsAppDraft]()) { partial, draft in
        let threadId = canonicalThreadId(for: draft)
        if let existing = partial[threadId], existing.createdAt >= draft.createdAt {
          return
        }
        partial[threadId] = draft
      }
      .values
      .map { draft in
        MessageThread(
          id: draft.chatJid,
          providerId: id,
          title: WhatsAppContactResolver.shared.displayName(for: draft.senderJid, fallback: draft.senderName),
          subtitle: WhatsAppContactResolver.shared.detailLabel(for: draft.senderJid),
          lastMessagePreview: draft.incomingText,
          lastActivity: draft.createdAt,
          unreadCount: 0,
          isGroup: draft.chatJid.contains("@g.us"),
          hasPendingDraft: true
        )
      }
    return (mappedThreads + draftOnlyThreads)
      .sorted { ($0.lastActivity ?? .distantPast) > ($1.lastActivity ?? .distantPast) }
  }

  func loadMessages(threadId: String) async -> [MessageItem] {
    if !backfilledThreadIds.contains(threadId) {
      await WhatsAppReader.backfillRecentMessages(chatJid: threadId)
      backfilledThreadIds.insert(threadId)
    }
    return await WhatsAppReader.listMessages(chatJid: threadId)
  }

  func pendingDrafts() -> [PendingDraftItem] {
    WhatsAppReplyCoordinator.shared.pendingDrafts.map {
      PendingDraftItem(
        id: $0.id,
        threadId: canonicalThreadId(for: $0),
        text: WhatsAppReplyCoordinator.visibleReplyText(from: $0.text),
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
    AnyView(WhatsAppSettingsSection(highlightedSettingId: .constant(nil), includePendingDrafts: false))
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

  private func canonicalThreadId(for draft: WhatsAppDraft) -> String {
    draftThreadAliases[draft.chatJid] ?? draft.chatJid
  }

  private func draftAliases(for drafts: [WhatsAppDraft], in threads: [MessageThread]) -> [String: String] {
    var aliases: [String: String] = [:]
    let visibleThreadIds = Set(threads.map(\.id))

    for draft in drafts where draft.chatJid.contains("@lid") && !visibleThreadIds.contains(draft.chatJid) {
      if let match = nameMatchedThreadId(for: draft, in: threads) {
        aliases[draft.chatJid] = match
        rememberAliasContact(for: draft, canonicalThreadId: match, threads: threads)
        continue
      }
      if let match = previewMatchedThreadId(for: draft, in: threads) {
        aliases[draft.chatJid] = match
        rememberAliasContact(for: draft, canonicalThreadId: match, threads: threads)
      }
    }

    return aliases
  }

  private func nameMatchedThreadId(for draft: WhatsAppDraft, in threads: [MessageThread]) -> String? {
    let draftName = normalizedName(
      WhatsAppContactResolver.shared.displayName(for: draft.senderJid, fallback: draft.senderName)
    )
    guard !draftName.isEmpty else { return nil }

    let matches = threads.filter { thread in
      guard !thread.isGroup else { return false }
      let threadTitle = normalizedName(thread.title)
      return threadTitle == draftName
    }
    return matches.count == 1 ? matches[0].id : nil
  }

  private func previewMatchedThreadId(for draft: WhatsAppDraft, in threads: [MessageThread]) -> String? {
    let draftText = normalizedMessageText(draft.incomingText)
    guard !draftText.isEmpty else { return nil }

    let matches = threads.filter { thread in
      guard !thread.isGroup else { return false }
      return normalizedMessageText(thread.lastMessagePreview ?? "") == draftText
    }
    return matches.count == 1 ? matches[0].id : nil
  }

  private func normalizedName(_ value: String) -> String {
    value
      .lowercased()
      .components(separatedBy: CharacterSet.alphanumerics.inverted)
      .filter { !$0.isEmpty }
      .joined(separator: " ")
  }

  private func normalizedMessageText(_ value: String) -> String {
    value
      .lowercased()
      .trimmingCharacters(in: .whitespacesAndNewlines)
      .components(separatedBy: .whitespacesAndNewlines)
      .filter { !$0.isEmpty }
      .joined(separator: " ")
  }

  private func rememberAliasContact(for draft: WhatsAppDraft, canonicalThreadId: String, threads: [MessageThread]) {
    guard let thread = threads.first(where: { $0.id == canonicalThreadId }) else { return }
    WhatsAppContactResolver.shared.remember(jid: draft.chatJid, contactName: thread.title)
    WhatsAppContactResolver.shared.remember(jid: draft.senderJid, contactName: thread.title)
  }
}
