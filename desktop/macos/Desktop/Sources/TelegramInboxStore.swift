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
  /// Chats where auto-reply escalated instead of sending: the message needs the user
  /// (can't be answered truthfully, needs their decision, or asks for sensitive info).
  /// Keyed by chatID; the value is the short user-facing reason. The suggested draft is
  /// kept in `preDrafts` for the composer to pre-fill.
  @Published var needsInputReasons: [String: String] = [:]
  /// Tentative calendar holds created when an availability-aware reply accepted a
  /// proposed time. Keyed by chatID; the Replies inbox surfaces a Confirm/Discard banner.
  @Published var pendingHolds: [String: DraftHold] = [:]
  /// Chat ids the user opted into automatic replies for. When a new inbound
  /// message arrives in one of these chats, Omi drafts AND sends without review
  /// (sent Telegram messages can't be unsent — strictly opt-in per chat).
  @Published var autoReplyChats: Set<String> = [] {
    didSet { UserDefaults.standard.set(Array(autoReplyChats), forKey: Self.autoReplyDefaultsKey) }
  }
  private static let autoReplyDefaultsKey = "telegramAutoReplyChats"

  private var lastLatestMessageID: [String: String] = [:]
  /// In-flight auto-reply tasks keyed by chat id, so disabling auto-reply mid-draft
  /// can cancel the pending send.
  private var autoReplyTasks: [String: Task<Void, Never>] = [:]
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
        scheduleAutoReply(chat)
      }
    } else {
      autoReplyChats.remove(chatID)
      // Cancel any in-flight draft/send so a reply can't land after the toggle is off.
      autoReplyTasks.removeValue(forKey: chatID)?.cancel()
    }
  }

  /// Track the auto-reply Task per chat so disabling the toggle can cancel an
  /// in-flight draft+send. A newer request for the same chat supersedes an older one.
  private func scheduleAutoReply(_ chat: TelegramChat) {
    autoReplyTasks[chat.chatID]?.cancel()
    autoReplyTasks[chat.chatID] = Task { [weak self] in
      await self?.autoReply(chat)
      self?.autoReplyTasks[chat.chatID] = nil
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
      // start() fails closed when the helper binary is missing or no shippable
      // Omi-registered API credentials are configured (see TelegramClientService).
      connection = .error("Telegram isn't available in this build yet.")
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

  /// Manual resync: reconnect the on-device helper and resume listening. Used by the
  /// "refresh" button when the listener has gone idle and new messages have stopped
  /// arriving. Relaunches the helper if it died, then re-issues connect + startListening
  /// (both are safe to receive more than once — the helper re-subscribes idempotently).
  func refresh() {
    guard TelegramClientService.shared.start() else {
      connection = .error("Telegram isn't available in this build yet.")
      return
    }
    guard TelegramClientService.hasSession else { return }
    connection = .connecting
    TelegramClientService.shared.connect()
    TelegramClientService.shared.startListening()
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
    needsInputReasons = [:]
    pendingHolds = [:]
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
    // Retain-and-retry ingest, independent of any UI flow (backfill has none).
    Task { [weak self] in await self?.ingestThread(payload) }
  }

  private func handleThread(_ t: TelegramHelperThread) async {
    let chat = TelegramChat(helperThread: t)
    upsert(chat)

    // Ingest to the backend for conversation/memory processing (durable-ledger
    // deduped server-side, so re-sends are safe). Runs as an independent retrying
    // task so a slow/failed ingest never delays the reply flow below.
    let payload = TelegramChat.ingestPayload(from: t)
    Task { [weak self] in await self?.ingestThread(payload) }

    // Only act on a genuinely new latest message per chat.
    let known = lastLatestMessageID[chat.chatID]
    lastLatestMessageID[chat.chatID] = t.latestMessageID
    guard t.awaitingReply, known != t.latestMessageID else { return }

    // A new inbound arrived → any earlier draft is stale regardless of path. Drop it
    // first so an outdated draft can't linger if the fresh attempt abstains or fails.
    preDrafts[chat.chatID] = nil
    needsInputReasons[chat.chatID] = nil
    pendingHolds[chat.chatID] = nil
    if autoReplyChats.contains(chat.chatID) {
      scheduleAutoReply(chat)
    } else {
      // We draft on-demand when the user opens the chat (or right now if open).
      if chat.chatID == selectedChatID {
        await predraft(chat)
      }
    }
  }

  /// Ingest a thread payload, retrying on a thrown error or a partial-persist
  /// (`allPersisted == false`) response. Telegram events/backfills are the only source
  /// of these normalized payloads, so a fire-once ingest silently loses messages on a
  /// transient backend failure. This is a best-effort in-memory retry — bounded backoff
  /// (~15s total), not a durable queue: it does NOT survive app quit or an outage longer
  /// than the backoff budget. Re-sends are safe (the backend dedups every message via its
  /// durable ledger); a persistent on-disk outbox would be the follow-up for full
  /// at-least-once delivery.
  private func ingestThread(_ payload: TelegramThreadPayload) async {
    let maxAttempts = 5
    for attempt in 0..<maxAttempts {
      // nil → the call threw (transient/offline); false → backend released some
      // windows without storing them; true → fully durable, nothing to retry.
      let allPersisted = (try? await APIClient.shared.telegramIngest(threads: [payload]))?.allPersisted
      if allPersisted == true { return }
      if attempt + 1 < maxAttempts {
        try? await Task.sleep(nanoseconds: UInt64(1 << attempt) * 1_000_000_000)  // 1, 2, 4, 8s
      }
    }
    NSLog("Telegram ingest: gave up after %d attempts; some messages may be unstored", maxAttempts)
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
    // Snapshot the message being replied to; discard if a newer one arrives during the
    // async call (racing predraft from selection-change didSet vs handleThread).
    let draftedForID = chat.bubbles.last?.id
    guard
      let resp = try? await APIClient.shared.telegramDraftReply(
        person: chat.personRef, thread: chat.draftContext(), intent: nil, isGroup: chat.isGroup)
    else { return }
    // Don't offer a disambiguation ask as a draft; and when the backend abstained
    // (group message not meant for the user) show no draft.
    guard !resp.ambiguous, !resp.abstain else { return }
    let draft = resp.draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !draft.isEmpty else { return }
    guard chats.first(where: { $0.chatID == chat.chatID })?.bubbles.last?.id == draftedForID else { return }
    preDrafts[chat.chatID] = draft
    pendingHolds[chat.chatID] = resp.hold
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
    // Final guard: the draft round-trip is async, so re-check auto-reply is still on
    // (and this task wasn't cancelled) BEFORE publishing a group draft or sending a
    // 1:1 — a toggled-off auto-reply must neither send nor surface a draft.
    guard !Task.isCancelled, autoReplyChats.contains(chat.chatID) else {
      NSLog("Telegram auto-reply cancelled for %@ before send (toggled off mid-draft)", chat.chatID)
      return
    }
    // Surface any tentative calendar hold regardless of which path we take below.
    pendingHolds[chat.chatID] = resp.hold
    // Escalation: the message needs the user, not an auto-sent reply. Keep the
    // best-guess draft as a SUGGESTION for review, record the reason, and notify —
    // never auto-send.
    if resp.needsInput {
      preDrafts[chat.chatID] = text
      needsInputReasons[chat.chatID] = resp.needsInputReason ?? ""
      MessagingNeedsInput.notify(
        personName: chat.displayName, reason: resp.needsInputReason, preview: text,
        platform: .telegram, chatID: chat.chatID)
      return
    }
    // Groups are DRAFT-ONLY: never auto-send to a group chat. Surface the draft for
    // the user to review and send manually instead.
    if chat.isGroup {
      preDrafts[chat.chatID] = text
      return
    }
    // Only reflect the send once the command actually reached a live helper — a
    // dead helper / failed stdin write must not leave a phantom "sent" bubble.
    // Keep the draft on failure so the reply isn't silently lost (mirrors WhatsApp,
    // which confirms against its DB, and iMessage, which drops the optimistic append).
    if TelegramClientService.shared.sendConfirmed(chatID: chat.chatID, text: text) {
      appendSent(text, to: chat.chatID)
    } else {
      NSLog("Telegram auto-reply send failed for %@ (helper unavailable); keeping draft", chat.chatID)
      preDrafts[chat.chatID] = text
    }
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

  /// Confirm (keep) or discard a tentative calendar hold surfaced in the Replies inbox.
  /// Confirm just dismisses the banner; discard also deletes the event on the backend.
  func resolveHold(chatID: String, discard: Bool) {
    guard let hold = pendingHolds[chatID] else { return }
    pendingHolds[chatID] = nil
    guard discard else { return }
    Task {
      do {
        try await APIClient.shared.discardCalendarHold(eventID: hold.eventID)
      } catch {
        NSLog("Telegram discard hold failed for %@: %@", chatID, error.localizedDescription)
      }
    }
  }

  private func appendSent(_ text: String, to chatID: String) {
    // The user replied — any escalation for this chat is resolved.
    needsInputReasons[chatID] = nil
    guard let idx = chats.firstIndex(where: { $0.chatID == chatID }) else { return }
    let chat = chats[idx]
    let bubble = TelegramChatBubble(
      id: UUID().uuidString, text: text, isFromMe: true, date: Date(), senderName: nil)
    chats[idx] = TelegramChat(
      chatID: chat.chatID, displayName: chat.displayName, isGroup: chat.isGroup,
      personRef: chat.personRef, bubbles: chat.bubbles + [bubble],
      avatarImageData: chat.avatarImageData)
    // NOTE: do not overwrite lastLatestMessageID here. That key dedups *inbound*
    // messages in handleThread (`known != t.latestMessageID`); stamping it with our
    // outgoing bubble's UUID would let a re-emitted snapshot of the same inbound
    // message pass the guard and trigger a duplicate auto-reply. WhatsApp's
    // appendSent deliberately leaves the key untouched for the same reason.
  }
}
