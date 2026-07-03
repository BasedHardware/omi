import Foundation
import SwiftUI

/// Backing store for the Telegram tab: recent chats, pre-drafts, and the per-chat
/// auto-reply opt-ins. Driven by `new_message` events from the on-device MTProto
/// helper (via TelegramClientService) instead of a local DB watcher.
@MainActor
final class TelegramInboxStore: ObservableObject {
  /// Shared across the app so navigating away from / back to the Telegram tab keeps
  /// the same connection, backfilled chats, and helper event subscription (the
  /// helper is a singleton whose backfill runs once — a per-view store would miss it).
  static let shared = TelegramInboxStore()

  enum ConnectionState: Equatable {
    case disconnected  // not connected — show phone entry (or Telegram Desktop option)
    case needsPasscode  // Telegram Desktop Local Passcode required (tdata path)
    case codeSent  // phone-login: waiting for the SMS/app login code
    case passwordRequired  // phone-login: 2FA password needed
    case connecting
    case connected
    case error(String)
  }

  @Published var chats: [TelegramChat] = []
  @Published var connection: ConnectionState = .disconnected
  /// Drafts are generated on-demand when the user opens a chat (not eagerly for
  /// every inbound), so the "Draft ready" pill only appears on chats the user
  /// actually looked at.
  @Published var selectedChatID: String? {
    didSet {
      guard selectedChatID != oldValue, let chat = selectedChat, chat.awaitingReply,
        preDrafts[chat.chatID] == nil, !autoReplyChats.contains(chat.chatID)
      else { return }
      Task { await predraft(chat) }
    }
  }
  /// Replies drafted on-demand when the user opened the chat.
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
    // Default: .disconnected — phone-code login works regardless of whether
    // Telegram Desktop tdata exists (native macOS Telegram has none).
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
    // Drive the initial connect directly rather than waiting for the helper's
    // one-shot "ready": the helper is a shared singleton, so a prior view's store
    // may have already consumed "ready". Commands are queued to the helper's stdin
    // and processed once it's up, so sending connect now is safe on cold start too.
    if TelegramClientService.hasSession {
      connection = .connecting
      TelegramClientService.shared.connect()
    }
  }

  /// Phone-code login step 1: request a login code for this phone number.
  func sendCode(phone: String) {
    connection = .connecting
    TelegramClientService.shared.sendCode(phone: phone)
  }

  /// Phone-code login step 2: submit the code Telegram sent.
  func submitCode(_ code: String) {
    connection = .connecting
    TelegramClientService.shared.signIn(code: code)
  }

  /// Phone-code login step 3 (only if 2FA is on): submit the account password.
  func submitPassword(_ password: String) {
    connection = .connecting
    TelegramClientService.shared.signInPassword(password)
  }

  /// Telegram Desktop path: bootstrap the session from local tdata (no login code).
  func connectViaDesktop(passcode: String? = nil) {
    connection = .connecting
    TelegramClientService.shared.bootstrap(passcode: passcode)
  }

  /// Whether the Telegram Desktop tdata path is available (offer it as an option).
  var telegramDesktopAvailable: Bool { TelegramClientService.telegramDesktopPresent() }

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
      // Cold start: if a session exists, connect. (start() also drives this for the
      // singleton-already-running case; connect is safe to receive more than once.)
      if TelegramClientService.hasSession, connection != .connected, connection != .connecting {
        connection = .connecting
        TelegramClientService.shared.connect()
      }
    case "bootstrapped", "connected":
      connection = .connected
      TelegramClientService.shared.startListening()
    case "code_sent":
      connection = .codeSent
    case "password_required":
      connection = .passwordRequired
    case "auth_needed":
      switch event.reason {
      case "passcode_required": connection = .needsPasscode
      default: connection = .disconnected
      }
    case "listening":
      connection = .connected
    case "new_message":
      if let thread = event.thread { Task { await handleThread(thread) } }
    case "backfill":
      // Existing chat loaded on connect: show it + learn its history, but do NOT
      // auto-draft/reply to old threads (only genuinely new arrivals do that).
      if let thread = event.thread { Task { await handleBackfill(thread) } }
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

  /// A chat loaded during connect backfill: populate the inbox and ingest its
  /// history (so Omi learns per-person voice), but seed the high-water mark so we
  /// never auto-draft/reply to these already-existing threads.
  private func handleBackfill(_ t: TelegramHelperThread) async {
    let chat = TelegramChat(helperThread: t)
    upsert(chat)
    lastLatestMessageID[chat.chatID] = t.latestMessageID
    let payload = TelegramChat.ingestPayload(from: t)
    _ = try? await APIClient.shared.telegramIngest(threads: [payload])
  }

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
      // A new inbound arrived → any earlier draft is stale. Drop it; we draft
      // on-demand when the user opens the chat (or right now if it's already open).
      preDrafts[chat.chatID] = nil
      if chat.chatID == selectedChatID {
        await predraft(chat)
      }
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
        person: chat.personRef, thread: chat.draftContext(), intent: nil, isGroup: chat.isGroup)
    else { return }
    // Don't offer a disambiguation ask as a draft; and when the backend abstained
    // (group message not meant for the user) show no draft.
    guard !resp.ambiguous, !resp.abstain else { return }
    let draft = resp.draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !draft.isEmpty else { return }
    preDrafts[chat.chatID] = draft
  }

  /// Draft AND send without review. Only ever called for opted-in chats. A send
  /// failure is logged and the draft dropped (never silently retried into a dup).
  private func autoReply(_ chat: TelegramChat) async {
    guard
      let resp = try? await APIClient.shared.telegramDraftReply(
        person: chat.personRef, thread: chat.draftContext(), intent: nil, isGroup: chat.isGroup)
    else { return }
    guard !resp.ambiguous else {
      NSLog("Telegram auto-reply skipped for %@: ambiguous contact", chat.chatID)
      return
    }
    // Backend abstained (group message not directed at the user) → nothing to send.
    guard !resp.abstain else { return }
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
      personRef: chat.personRef, bubbles: chat.bubbles + [bubble],
      avatarImageData: chat.avatarImageData)
    lastLatestMessageID[chatID] = bubble.id
  }
}
