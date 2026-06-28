import Foundation
import SwiftUI

@MainActor
final class WhatsAppMessagingProvider: MessagingProvider {
  static let shared = WhatsAppMessagingProvider()

  private init() {}
  private var backfilledThreadIds: Set<String> = []
  private var threadAliases: [String: String] = [:]
  private var draftThreadAliases: [String: String] = [:]

  let id = "whatsapp"
  let displayName = "WhatsApp"
  let iconSystemName = "message.fill"
  var connectorBrand: ConnectorBrand? { .whatsapp }

  var isConnected: Bool {
    WhatsAppState.shared.connectionState.isConnected
  }

  func loadThreads() async -> [MessageThread] {
    let threads = await WhatsAppReader.listChats()
    let pendingDrafts = WhatsAppReplyCoordinator.shared.pendingDrafts
    threadAliases = [:]
    draftThreadAliases = draftAliases(for: pendingDrafts, in: threads)
    let draftThreadIds = Set(pendingDrafts.map { canonicalThreadId(for: $0) })
    let mappedThreads = mergeAliasedThreads(threads, draftThreadIds: draftThreadIds)
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
        let threadId = canonicalThreadId(for: draft)
        return MessageThread(
          id: threadId,
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
    draftThreadAliases[draft.chatJid] ?? threadAliases[draft.chatJid] ?? draft.chatJid
  }

  private func draftAliases(for drafts: [WhatsAppDraft], in threads: [MessageThread]) -> [String: String] {
    var aliases: [String: String] = [:]

    for draft in drafts where draft.chatJid.contains("@lid") {
      if let match = canonicalAliasMatchedThreadId(for: draft, in: threads)
        ?? phoneMatchedThreadId(for: draft, in: threads)
      {
        aliases[draft.chatJid] = match
        rememberAliasContact(for: draft, canonicalThreadId: match, threads: threads)
      }
    }

    return aliases
  }

  private func mergeAliasedThreads(_ threads: [MessageThread], draftThreadIds: Set<String>) -> [MessageThread] {
    let sortedThreads = threads.sorted { lhs, rhs in
      if isLinkedDeviceThread(lhs.id) != isLinkedDeviceThread(rhs.id) {
        return !isLinkedDeviceThread(lhs.id)
      }
      return (lhs.lastActivity ?? .distantPast) > (rhs.lastActivity ?? .distantPast)
    }
    return sortedThreads.reduce(into: [String: MessageThread]()) { partial, thread in
      let threadId = threadAliases[thread.id] ?? thread.id
      let candidate = MessageThread(
        id: threadId,
        providerId: thread.providerId,
        title: thread.title,
        subtitle: thread.subtitle,
        lastMessagePreview: thread.lastMessagePreview,
        lastActivity: thread.lastActivity,
        unreadCount: thread.unreadCount,
        isGroup: thread.isGroup,
        hasPendingDraft: draftThreadIds.contains(threadId)
      )
      guard let existing = partial[threadId] else {
        partial[threadId] = candidate
        return
      }
      partial[threadId] = mergeThread(existing, with: candidate, hasPendingDraft: draftThreadIds.contains(threadId))
    }
    .values
    .sorted { ($0.lastActivity ?? .distantPast) > ($1.lastActivity ?? .distantPast) }
  }

  private func mergeThread(_ existing: MessageThread, with candidate: MessageThread, hasPendingDraft: Bool) -> MessageThread {
    let candidateIsNewer = (candidate.lastActivity ?? .distantPast) > (existing.lastActivity ?? .distantPast)
    return MessageThread(
      id: existing.id,
      providerId: existing.providerId,
      title: existing.title,
      subtitle: existing.subtitle,
      lastMessagePreview: candidateIsNewer ? (candidate.lastMessagePreview ?? existing.lastMessagePreview) : existing.lastMessagePreview,
      lastActivity: candidateIsNewer ? (candidate.lastActivity ?? existing.lastActivity) : existing.lastActivity,
      unreadCount: max(existing.unreadCount, candidate.unreadCount),
      isGroup: existing.isGroup,
      hasPendingDraft: existing.hasPendingDraft || candidate.hasPendingDraft || hasPendingDraft
    )
  }

  private func phoneMatchedThreadId(for draft: WhatsAppDraft, in threads: [MessageThread]) -> String? {
    let digits = WhatsAppContactResolver.shared.phoneDigits(for: draft.chatJid)
      ?? WhatsAppContactResolver.shared.phoneDigits(for: draft.senderJid)
    guard let digits else { return nil }
    return uniquePhoneMatchedThreadId(digits: digits, in: threads, excluding: draft.chatJid)
  }

  private func uniquePhoneMatchedThreadId(digits: String, in threads: [MessageThread], excluding excludedThreadId: String) -> String? {
    let matches = threads.filter { thread in
      guard !thread.isGroup, thread.id != excludedThreadId, !isLinkedDeviceThread(thread.id) else { return false }
      return WhatsAppContactResolver.shared.phoneDigits(for: thread.id) == digits
    }
    return matches.count == 1 ? matches[0].id : nil
  }

  private func canonicalAliasMatchedThreadId(for draft: WhatsAppDraft, in threads: [MessageThread]) -> String? {
    let candidates = [
      WhatsAppContactResolver.shared.canonicalJid(for: draft.chatJid),
      WhatsAppContactResolver.shared.canonicalJid(for: draft.senderJid),
    ]
    let matches = Set(candidates.compactMap { canonical -> String? in
      guard canonical != draft.chatJid, canonical != draft.senderJid else { return nil }
      return threads.first { thread in
        thread.id.lowercased() == canonical && !isLinkedDeviceThread(thread.id)
      }?.id
    })
    return matches.count == 1 ? matches.first : nil
  }

  private func rememberAliasContact(for draft: WhatsAppDraft, canonicalThreadId: String, threads: [MessageThread]) {
    guard let thread = threads.first(where: { $0.id == canonicalThreadId }) else { return }
    WhatsAppContactResolver.shared.remember(jid: draft.chatJid, contactName: thread.title)
    WhatsAppContactResolver.shared.remember(jid: draft.senderJid, contactName: thread.title)
    WhatsAppContactResolver.shared.rememberAlias(jid: draft.chatJid, canonicalJid: canonicalThreadId)
    WhatsAppContactResolver.shared.rememberAlias(jid: draft.senderJid, canonicalJid: canonicalThreadId)
  }

  private func isLinkedDeviceThread(_ threadId: String) -> Bool {
    threadId.lowercased().contains("@lid")
  }
}
