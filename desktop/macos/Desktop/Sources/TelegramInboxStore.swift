import Foundation
import SwiftUI

/// Backing store for the Telegram tab: recent chats, pre-drafts, and the per-chat
/// auto-reply opt-ins. Driven by `new_message` events from the on-device MTProto
/// helper (via TelegramClientService) instead of a local DB watcher.
@MainActor
final class TelegramInboxStore: ObservableObject {
  enum ConnectionState: Equatable {
    case needsTelegramDesktop  // no local tdata to bootstrap from
    case disconnected  // tdata present, not yet connected
    case needsPasscode  // Telegram Desktop Local Passcode required
    case connecting
    case connected
    case error(String)
  }

  @Published var chats: [TelegramChat] = []
  @Published var connection: ConnectionState = .disconnected
  @Published var selectedChatID: String?
  /// Replies pre-drafted in the background when a new inbound message arrived.
  @Published var preDrafts: [String: String] = [:]
  /// Chat ids the user opted into automatic replies for. When a new inbound
  /// message arrives in one of these chats, Omi drafts AND sends without review
  /// (sent Telegram messages can't be unsent — strictly opt-in per chat).
  @Published var autoReplyChats: Set<String> = [] {
    didSet { UserDefaults.standard.set(Array(autoReplyChats), forKey: Self.autoReplyDefaultsKey) }
  }
  private static let autoReplyDefaultsKey = "telegramAutoReplyChats"

  private var lastLatestMessageID: [String: String] = [:]
  private var started = false

  init() {
    autoReplyChats = Set(UserDefaults.standard.stringArray(forKey: Self.autoReplyDefaultsKey) ?? [])
    if !TelegramClientService.telegramDesktopPresent() {
      connection = .needsTelegramDesktop
    }
  }

  var selectedChat: TelegramChat? {
    guard let id = selectedChatID else { return nil }
    return chats.first { $0.id == id }
  }

  func isAutoReplyEnabled(_ chatID: String) -> Bool { autoReplyChats.contains(chatID) }

  func setAutoReply(_ enabled: Bool, for chatID: String) {
    if enabled {
      autoReplyChats.insert(chatID)
      // Flip on for a thread already awaiting a reply → reply now, as the user expects.
      if let chat = chats.first(where: { $0.chatID == chatID }), chat.awaitingReply {
        Task { await autoReply(chat) }
      }
    } else {
      autoReplyChats.remove(chatID)
    }
  }

  // MARK: - Lifecycle / connect flow

  /// Start the helper and wire its event stream. Idempotent.
  func start() {
    guard !started else { return }
    started = true
    TelegramClientService.shared.onEvent = { [weak self] event in
      self?.handle(event)
    }
    guard TelegramClientService.shared.start() else {
      connection = .error("Telegram helper is unavailable.")
      return
    }
    // "ready" (emitted by the helper on startup) drives the next step.
  }

  /// User tapped Connect. Bootstrap the session from Telegram Desktop's tdata.
  func connect(passcode: String? = nil) {
    connection = .connecting
    TelegramClientService.shared.bootstrap(passcode: passcode)
  }

  func disconnect() {
    TelegramClientService.shared.shutdown()
    Task { try? await APIClient.shared.telegramDisconnect() }
    connection = .disconnected
    chats = []
    preDrafts = [:]
    lastLatestMessageID = [:]
  }

  private func handle(_ event: TelegramHelperEvent) {
    switch event.event {
    case "ready":
      // Reconnect silently if we already have a session; otherwise wait for Connect.
      if TelegramClientService.hasSession {
        connection = .connecting
        TelegramClientService.shared.connect()
      }
    case "bootstrapped", "connected":
      connection = .connected
      TelegramClientService.shared.startListening()
    case "auth_needed":
      switch event.reason {
      case "passcode_required": connection = .needsPasscode
      default: connection = TelegramClientService.telegramDesktopPresent() ? .disconnected : .needsTelegramDesktop
      }
    case "listening":
      connection = .connected
    case "new_message":
      if let thread = event.thread { Task { await handleThread(thread) } }
    case "sent":
      break  // optimistic append already done at send time
    case "error":
      let msg = event.message ?? "Telegram helper error"
      NSLog("Telegram: %@", msg)
      if event.fatal == true { connection = .error(msg) }
    default:
      break
    }
  }

  // MARK: - Message handling

  private func handleThread(_ t: TelegramHelperThread) async {
    let chat = TelegramChat(helperThread: t)
    upsert(chat)

    // Ingest to the backend for conversation/memory processing (durable-ledger
    // deduped server-side, so re-sends are safe).
    let payload = TelegramChat.ingestPayload(from: t)
    _ = try? await APIClient.shared.telegramIngest(threads: [payload])

    // Only act on a genuinely new latest message per chat.
    let known = lastLatestMessageID[chat.chatID]
    lastLatestMessageID[chat.chatID] = t.latestMessageID
    guard t.awaitingReply, known != t.latestMessageID else { return }

    if autoReplyChats.contains(chat.chatID) {
      await autoReply(chat)
    } else {
      preDrafts[chat.chatID] = nil
      await predraft(chat)
    }
  }

  private func upsert(_ chat: TelegramChat) {
    if let idx = chats.firstIndex(where: { $0.chatID == chat.chatID }) {
      chats[idx] = chat
    } else {
      chats.insert(chat, at: 0)
    }
    chats.sort { $0.lastDate > $1.lastDate }
    if selectedChatID == nil { selectedChatID = chats.first?.chatID }
  }

  private func predraft(_ chat: TelegramChat) async {
    guard
      let resp = try? await APIClient.shared.telegramDraftReply(
        person: chat.personRef, thread: chat.draftContext(), intent: nil)
    else { return }
    guard !resp.ambiguous else { return }  // don't offer a disambiguation ask as a pre-draft
    preDrafts[chat.chatID] = resp.draft
  }

  /// Draft AND send without review. Only ever called for opted-in chats. A send
  /// failure is logged and the draft dropped (never silently retried into a dup).
  private func autoReply(_ chat: TelegramChat) async {
    guard
      let resp = try? await APIClient.shared.telegramDraftReply(
        person: chat.personRef, thread: chat.draftContext(), intent: nil)
    else { return }
    guard !resp.ambiguous else {
      NSLog("Telegram auto-reply skipped for %@: ambiguous contact", chat.chatID)
      return
    }
    let text = resp.draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty else { return }
    TelegramClientService.shared.send(chatID: chat.chatID, text: text)
    appendSent(text, to: chat.chatID)
  }

  /// Send a user-composed (or edited pre-draft) reply for the selected chat.
  func sendManual(_ text: String) {
    guard let chat = selectedChat else { return }
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return }
    TelegramClientService.shared.send(chatID: chat.chatID, text: trimmed)
    appendSent(trimmed, to: chat.chatID)
    preDrafts[chat.chatID] = nil
  }

  /// Generate a pre-draft on demand for the selected chat (compose-bar sparkles).
  func generateDraft() async {
    guard let chat = selectedChat else { return }
    await predraft(chat)
  }

  private func appendSent(_ text: String, to chatID: String) {
    guard let idx = chats.firstIndex(where: { $0.chatID == chatID }) else { return }
    let chat = chats[idx]
    let bubble = TelegramChatBubble(
      id: UUID().uuidString, text: text, isFromMe: true, date: Date(), senderName: nil)
    chats[idx] = TelegramChat(
      chatID: chat.chatID, displayName: chat.displayName, isGroup: chat.isGroup,
      personRef: chat.personRef, bubbles: chat.bubbles + [bubble])
    lastLatestMessageID[chatID] = bubble.id
  }
}
