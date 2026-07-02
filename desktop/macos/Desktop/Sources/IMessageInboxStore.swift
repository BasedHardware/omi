import Foundation
import SwiftUI

/// Backing store for the Messages tab: recent iMessage chats with full history.
@MainActor
final class IMessageInboxStore: ObservableObject {
  @Published var chats: [IMessageChat] = []
  @Published var isLoading = false
  @Published var errorMessage: String?
  @Published var permissionNeeded = false
  @Published var selectedChatID: String?
  /// Replies pre-drafted in the background when a new inbound message arrived.
  @Published var preDrafts: [String: String] = [:]

  private var lastLatestMessageID: [String: String] = [:]
  private var baselined = false
  private var watchTask: Task<Void, Never>?

  var selectedChat: IMessageChat? {
    guard let id = selectedChatID else { return nil }
    return chats.first { $0.id == id }
  }

  // MARK: - Real-time watcher

  /// Poll chat.db for new inbound messages; when someone texts, refresh the thread
  /// and immediately pre-draft a reply so it's ready the moment you open the chat.
  func startWatching() {
    guard watchTask == nil else { return }
    watchTask = Task { [weak self] in
      while !Task.isCancelled {
        try? await Task.sleep(nanoseconds: 8_000_000_000)  // 8s
        await self?.poll()
      }
    }
  }

  func stopWatching() {
    watchTask?.cancel()
    watchTask = nil
  }

  private func poll() async {
    guard IMessagePermissionPolicy.fullDiskAccessGranted() else { return }
    guard let loaded = try? await IMessageReaderService.shared.readChats() else { return }
    chats = loaded

    for chat in loaded where chat.awaitingReply {
      let latestID = chat.bubbles.last?.id ?? ""
      let known = lastLatestMessageID[chat.id]
      lastLatestMessageID[chat.id] = latestID
      // Only draft NEW arrivals (after the first baseline pass), so we don't flood
      // the backend for every existing unread thread on launch.
      if baselined, let known, known != latestID {
        preDrafts[chat.id] = nil
        Task { await self.predraft(chat) }
      }
    }
    baselined = true
  }

  private func predraft(_ chat: IMessageChat) async {
    guard
      let draft = try? await APIClient.shared.imessageDraftReply(
        person: chat.personRef, thread: chat.draftContext(), intent: nil)
    else { return }
    preDrafts[chat.id] = draft
  }

  func load() async {
    isLoading = true
    errorMessage = nil
    defer { isLoading = false }

    guard IMessagePermissionPolicy.fullDiskAccessGranted() else {
      permissionNeeded = true
      chats = []
      return
    }
    permissionNeeded = false

    do {
      let loaded = try await IMessageReaderService.shared.readChats()
      chats = loaded
      if selectedChatID == nil {
        selectedChatID = loaded.first?.id
      }
    } catch {
      errorMessage = error.localizedDescription
    }
  }

  /// Optimistically append a just-sent message to the selected chat.
  func appendSent(_ text: String) {
    guard let id = selectedChatID, let idx = chats.firstIndex(where: { $0.id == id }) else { return }
    let chat = chats[idx]
    let bubble = IMessageChatBubble(
      id: UUID().uuidString, text: text, isFromMe: true, date: Date(), senderName: nil)
    chats[idx] = IMessageChat(
      chatGUID: chat.chatGUID, displayName: chat.displayName, isGroup: chat.isGroup,
      personRef: chat.personRef, bubbles: chat.bubbles + [bubble], avatarImageData: chat.avatarImageData)
  }
}
