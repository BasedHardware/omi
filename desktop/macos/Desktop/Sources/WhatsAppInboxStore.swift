import Foundation
import SwiftUI

/// Backing store for the WhatsApp tab: recent chats with their message history.
@MainActor
final class WhatsAppInboxStore: ObservableObject {
  /// App-wide singleton so the incremental watcher (and therefore auto-reply)
  /// keeps running even when the WhatsApp tab isn't on screen. A per-view
  /// @StateObject would be torn down on navigation, silently killing auto-reply.
  static let shared = WhatsAppInboxStore()

  @Published var chats: [WhatsAppChat] = []
  @Published var isLoading = false
  @Published var errorMessage: String?
  @Published var permissionNeeded = false
  /// True when a send couldn't complete because Accessibility/Automation isn't granted
  /// (auto-send needs both to press Return in WhatsApp). Surfaced as a banner so the user
  /// can grant it once; cleared automatically the next time a send succeeds.
  @Published var sendPermissionNeeded = false
  /// Drafts are generated on-demand when the user opens a chat (not eagerly for
  /// every inbound), so the "Draft ready" pill only appears on chats the user
  /// actually looked at.
  @Published var selectedChatID: String? {
    didSet {
      guard selectedChatID != oldValue, let chat = selectedChat, chat.awaitingReply,
        preDrafts[chat.id] == nil, !autoReplyChats.contains(chat.chatID)
      else { return }
      Task { await predraft(chat) }
    }
  }
  /// Replies drafted on-demand when the user opened the chat.
  @Published var preDrafts: [String: String] = [:]
  /// Chats where auto-reply escalated instead of sending: the message needs the user
  /// (can't be answered truthfully, needs their decision, or asks for sensitive info).
  /// Keyed by chat.id; the value is the short user-facing reason. The suggested draft is
  /// kept in `preDrafts` for the composer to pre-fill.
  @Published var needsInputReasons: [String: String] = [:]
  /// Tentative calendar holds created when an availability-aware reply accepted a
  /// proposed time. Keyed by chat.id; the Replies inbox surfaces a Confirm/Discard banner.
  @Published var pendingHolds: [String: DraftHold] = [:]
  /// Chat IDs the user has opted into automatic replies for. When a new inbound
  /// message arrives in one of these chats, Omi drafts AND sends a reply without
  /// review (sent WhatsApp messages can't be unsent — this is strictly opt-in per
  /// chat, and only works for 1:1 chats where an automated send is possible).
  @Published var autoReplyChats: Set<String> = [] {
    didSet { UserDefaults.standard.set(Array(autoReplyChats), forKey: Self.autoReplyDefaultsKey) }
  }
  private static let autoReplyDefaultsKey = "whatsappAutoReplyChats"

  init() {
    // Restore per-chat auto-reply opt-ins from the previous session.
    autoReplyChats = Set(UserDefaults.standard.stringArray(forKey: Self.autoReplyDefaultsKey) ?? [])
  }

  func isAutoReplyEnabled(_ chatID: String) -> Bool { autoReplyChats.contains(chatID) }

  /// Whether the auto-reply toggle is offered for this chat. Shown for ALL chats
  /// (1:1 and groups) so the control is consistent everywhere. 1:1 chats can be
  /// auto-sent via the WhatsApp deep link; groups/opaque chats fall back to
  /// drafting + prefilling WhatsApp for the user to send (see `autoReply`).
  func canAutoReply(_ chatID: String) -> Bool { true }

  /// True only when a drafted reply can be delivered fully automatically (no user
  /// step) — i.e. 1:1 chats with a dialable number.
  func canAutoSend(_ chatID: String) -> Bool {
    if let chat = chats.first(where: { $0.chatID == chatID }), chat.dialablePhone != nil { return true }
    return WhatsAppSenderService.phoneDigits(forChatID: chatID) != nil
  }

  func setAutoReply(_ enabled: Bool, for chatID: String) {
    if enabled {
      autoReplyChats.insert(chatID)
      // If the chat already has an unanswered inbound message, reply to it now
      // instead of waiting for the contact's next new message.
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
  private func scheduleAutoReply(_ chat: WhatsAppChat) {
    autoReplyTasks[chat.chatID]?.cancel()
    autoReplyTasks[chat.chatID] = Task { [weak self] in
      await self?.autoReply(chat)
      self?.autoReplyTasks[chat.chatID] = nil
    }
  }

  private var lastLatestMessageID: [String: String] = [:]
  /// In-flight auto-reply tasks keyed by chat id, so disabling auto-reply mid-draft
  /// can cancel the pending send.
  private var autoReplyTasks: [String: Task<Void, Never>] = [:]
  private var baselined = false
  private var watchTask: Task<Void, Never>?
  private var dbWatcher: WhatsAppDBWatcher?
  /// High-water `Z_PK` for incremental gating: we only do a full refresh when a
  /// message newer than this appears. Primed once the baseline is loaded.
  private var lastSeenZPK: Int64 = 0

  var selectedChat: WhatsAppChat? {
    guard let id = selectedChatID else { return nil }
    return chats.first { $0.id == id }
  }

  // MARK: - Real-time watcher

  /// Event-driven watcher for new inbound messages. Instead of periodically
  /// reloading the whole database, we watch the SQLite files for writes (WAL-mode
  /// writes land in the -wal/-shm sidecars), debounce the burst, then cheaply
  /// query only messages newer than `lastSeenZPK`. A full `readChats()` refresh
  /// (and the resulting pre-draft) runs only when something genuinely new arrived.
  /// A slow fallback timer covers the rare case where a file event is missed.
  func startWatching() {
    guard watchTask == nil else { return }
    startFileWatcher()
    watchTask = Task { [weak self] in
      await self?.bootstrap()
      while !Task.isCancelled {
        try? await Task.sleep(nanoseconds: 45_000_000_000)  // 45s fallback
        guard let self else { break }
        await self.syncNewMessages()
      }
    }
  }

  func stopWatching() {
    watchTask?.cancel()
    watchTask = nil
    dbWatcher?.stop()
    dbWatcher = nil
  }

  deinit {
    watchTask?.cancel()
    dbWatcher?.stop()
  }

  private func startFileWatcher() {
    guard dbWatcher == nil else { return }
    let dbPath = WhatsAppPermissionPolicy.chatDatabaseURL.path
    // WAL-mode writes usually update the -wal/-shm sidecars, so watch all three.
    let paths = [dbPath, dbPath + "-wal", dbPath + "-shm"]
    let watcher = WhatsAppDBWatcher(paths: paths) { [weak self] in
      Task { await self?.syncNewMessages() }
    }
    dbWatcher = watcher
    watcher.start()
  }

  /// One-time baseline: full load (records latest ids for all chats without
  /// pre-drafting) and prime the incremental high-water mark.
  private func bootstrap() async {
    await refresh()
    if let result = try? await WhatsAppReaderService.shared.newMessages(afterZPK: lastSeenZPK, limit: 1) {
      lastSeenZPK = max(lastSeenZPK, result.maxZPK)
    }
    // A persisted auto-reply chat does NOT get setAutoReply's immediate reply on launch,
    // so a message that arrived while Omi was closed (or before permission was granted)
    // would sit unanswered until the contact's NEXT new message — which looks like
    // "auto-reply doesn't work". Reply now to any still-unanswered message in an opted-in
    // chat. Safe: once replied, the chat's last message is outbound so `awaitingReply`
    // flips false and this won't re-fire on the next launch; a failed send stays pending
    // and is retried next launch.
    for chat in chats where autoReplyChats.contains(chat.chatID) && chat.awaitingReply {
      scheduleAutoReply(chat)
    }
  }

  /// Debounced change handler: cheaply check for messages newer than the
  /// high-water mark and only do a full refresh (+ pre-draft) when something new
  /// actually arrived.
  private func syncNewMessages() async {
    guard WhatsAppPermissionPolicy.fullDiskAccessGranted() else {
      permissionNeeded = true
      chats = []
      lastSeenZPK = 0
      return
    }
    permissionNeeded = false
    guard let result = try? await WhatsAppReaderService.shared.newMessages(afterZPK: lastSeenZPK)
    else { return }
    guard result.maxZPK > lastSeenZPK else { return }  // nothing new
    lastSeenZPK = result.maxZPK
    await refresh()
  }

  private func refresh() async {
    guard WhatsAppPermissionPolicy.fullDiskAccessGranted() else {
      permissionNeeded = true
      chats = []
      return
    }
    permissionNeeded = false
    guard let loaded = try? await WhatsAppReaderService.shared.readChats() else { return }
    chats = loaded

    for chat in loaded {
      let latestID = chat.bubbles.last?.id ?? ""
      let known = lastLatestMessageID[chat.id]
      lastLatestMessageID[chat.id] = latestID
      guard chat.awaitingReply else { continue }
      // Only act on NEW arrivals (after the first baseline pass), so we don't flood
      // the backend for every existing unread thread on launch.
      if baselined, let known, known != latestID {
        // A new inbound arrived → any earlier draft is stale regardless of path. Drop
        // it first so an outdated draft can't linger if the fresh attempt abstains,
        // fails, or (for a 1:1) sends instead of drafting.
        preDrafts[chat.id] = nil
        needsInputReasons[chat.id] = nil
        pendingHolds[chat.id] = nil
        if autoReplyChats.contains(chat.chatID) {
          scheduleAutoReply(chat)
        } else {
          // We draft on-demand when the user opens the chat (or right now if open).
          if chat.id == selectedChatID {
            Task { await self.predraft(chat) }
          }
        }
      }
    }
    baselined = true
  }

  private func predraft(_ chat: WhatsAppChat) async {
    // Snapshot the message being replied to; discard if a newer one arrives during the
    // async call so a stale draft can't overwrite the fresher one.
    let draftedForID = chat.bubbles.last?.id
    guard
      let resp = try? await APIClient.shared.whatsappDraftReply(
        person: chat.personRef, thread: chat.draftContext(), intent: nil, isGroup: chat.isGroup)
    else { return }
    // Don't offer a disambiguation ask as a draft; and when the backend abstained
    // (group message not meant for the user) show no draft.
    guard !resp.ambiguous, !resp.abstain else { return }
    let draft = resp.draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !draft.isEmpty else { return }
    guard chats.first(where: { $0.id == chat.id })?.bubbles.last?.id == draftedForID else { return }
    preDrafts[chat.id] = draft
    pendingHolds[chat.id] = resp.hold
  }

  /// Draft a reply and send it immediately, without review. Only ever called for
  /// chats the user explicitly enabled auto-reply on. Sent messages can't be unsent, so
  /// the send is confirmed against WhatsApp's database before being reflected; if it
  /// can't be confirmed, the composed reply is kept as a draft (not silently dropped)
  /// so a possibly-unsent reply isn't lost — except when auto-reply was toggled off
  /// mid-send, where nothing is kept.
  private func autoReply(_ chat: WhatsAppChat) async {
    // Groups are DRAFT-ONLY: never auto-send to a group chat. (In practice WhatsApp
    // group sends already have no dialable number, but guard explicitly so this holds
    // regardless of how the phone is resolved.)
    if chat.isGroup {
      await predraft(chat)
      return
    }
    // Automated send only works for 1:1 chats with a dialable number (from the
    // JID, or — for @lid privacy chats — the session identifier).
    let phone = chat.dialablePhone ?? WhatsAppSenderService.phoneDigits(forChatID: chat.chatID)
    guard let phone else {
      NSLog("WhatsApp auto-reply skipped for \(chat.chatID): automated send unavailable for this chat")
      return
    }
    guard
      let resp = try? await APIClient.shared.whatsappDraftReply(
        person: chat.personRef, thread: chat.draftContext(), intent: nil, isGroup: chat.isGroup)
    else { return }
    guard !resp.ambiguous else {
      NSLog("WhatsApp auto-reply skipped for \(chat.chatID): ambiguous contact needs disambiguation")
      return
    }
    // Backend abstained (group message not directed at the user) → nothing to send.
    guard !resp.abstain else { return }
    let text = resp.draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty else { return }
    // Final guard: the draft round-trip is async, so re-check auto-reply is still on
    // (and this task wasn't cancelled) right before the irreversible send.
    guard !Task.isCancelled, autoReplyChats.contains(chat.chatID) else {
      NSLog("WhatsApp auto-reply cancelled for \(chat.chatID) before send (toggled off mid-draft)")
      return
    }
    // Surface any tentative calendar hold regardless of which path we take below.
    pendingHolds[chat.id] = resp.hold
    // Escalation: the message needs the user, not an auto-sent reply. Keep the
    // best-guess draft as a SUGGESTION for review, record the reason, and notify —
    // never auto-send.
    if resp.needsInput {
      preDrafts[chat.id] = text
      needsInputReasons[chat.id] = resp.needsInputReason ?? ""
      MessagingNeedsInput.notify(
        personName: chat.displayName, reason: resp.needsInputReason, preview: text,
        platform: .whatsapp, chatID: chat.chatID)
      return
    }
    // Auto-reply should reliably SEND on draft. `.notConfirmed` means the recipient
    // guard couldn't verify the target chat and NOTHING was sent (fail-closed) — often a
    // transient miss on an unattended reply (WhatsApp slow to open the chat). Retry once;
    // a fresh prefill usually settles, and because nothing was sent a retry can't
    // duplicate. Any other outcome is terminal (see the catch).
    let maxSendAttempts = 2
    for attempt in 1...maxSendAttempts {
      do {
        try await WhatsAppSenderService.send(text: text, toChatID: chat.chatID, phone: phone)
        // Only reflect the send once WhatsApp's database confirms it (send() throws
        // otherwise), so auto-reply never optimistically shows an unsent message.
        appendSent(text, to: chat.id)
        sendPermissionNeeded = false
        return
      } catch is CancellationError {
        // Auto-reply was toggled off (or the task cancelled) mid-send — nothing was sent
        // and the user opted out, so don't leave a draft behind.
        NSLog("WhatsApp auto-reply cancelled mid-send for \(chat.chatID)")
        return
      } catch WhatsAppSenderError.notConfirmed
      where attempt < maxSendAttempts && !Task.isCancelled && autoReplyChats.contains(chat.chatID) {
        NSLog("WhatsApp auto-reply not confirmed for \(chat.chatID); retrying (attempt \(attempt + 1))")
        continue
      } catch {
        // The send wasn't confirmed after our attempt(s). Either nothing-sent (permission
        // missing, recipient still unverifiable) or `.sendUnconfirmed` (Return fired but no
        // confirming row appeared). Since the confirm window far exceeds WhatsApp's normal
        // persist latency, an unconfirmed result more likely means the reply did NOT go out
        // — so keep it as a draft rather than silently dropping a possibly-unsent reply.
        // Auto-reply never auto-resends a draft, so this can't create an automatic
        // duplicate; it just surfaces the reply for the user to complete. (Mirrors the
        // manual path, which keeps the draft and warns.)
        // If the user opted out mid-send (the recipient-guard poll swallows cancellation
        // and surfaces as .notConfirmed rather than CancellationError), don't leave a
        // draft behind — matches the explicit-cancellation branch.
        guard !Task.isCancelled, autoReplyChats.contains(chat.chatID) else {
          NSLog("WhatsApp auto-reply opted out mid-send for \(chat.chatID); dropping draft")
          return
        }
        if case WhatsAppSenderError.sendUnconfirmed = error {
          NSLog("WhatsApp auto-reply unconfirmed for \(chat.chatID); keeping draft")
        } else {
          NSLog("WhatsApp auto-reply not sent for \(chat.chatID): \(error.localizedDescription)")
        }
        // Surface a one-time "grant permission" banner if that's why it couldn't send.
        if case WhatsAppSenderError.permissionRequired = error { sendPermissionNeeded = true }
        preDrafts[chat.id] = text
        return
      }
    }
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
        NSLog("WhatsApp discard hold failed for \(chatID): \(error.localizedDescription)")
      }
    }
  }

  func load() async {
    isLoading = true
    errorMessage = nil
    defer { isLoading = false }

    guard WhatsAppPermissionPolicy.fullDiskAccessGranted() else {
      permissionNeeded = true
      chats = []
      return
    }
    permissionNeeded = false

    do {
      let loaded = try await WhatsAppReaderService.shared.readChats()
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
    guard let id = selectedChatID else { return }
    appendSent(text, to: id)
  }

  /// Optimistically append a just-sent message to a specific chat (used by
  /// auto-reply, where the target chat may not be the selected one).
  func appendSent(_ text: String, to chatID: String) {
    // The user replied — any escalation for this chat is resolved.
    needsInputReasons[chatID] = nil
    guard let idx = chats.firstIndex(where: { $0.id == chatID }) else { return }
    let chat = chats[idx]
    let bubble = WhatsAppChatBubble(
      id: UUID().uuidString, text: text, isFromMe: true, date: Date(), senderName: nil)
    chats[idx] = WhatsAppChat(
      chatID: chat.chatID, displayName: chat.displayName, isGroup: chat.isGroup,
      personRef: chat.personRef, bubbles: chat.bubbles + [bubble], avatarImageData: chat.avatarImageData,
      dialablePhone: chat.dialablePhone)
  }
}

/// Watches the WhatsApp SQLite files (`ChatStorage.sqlite` + its `-wal`/`-shm`
/// sidecars) for writes and invokes `onChange` after a short debounce. WAL-mode
/// writes land in the sidecars, so all three are monitored. If a file is
/// checkpointed/rotated away (delete/rename/revoke) the source is re-armed on the
/// new inode.
///
/// All mutable state is confined to `queue`, so DispatchSource callbacks, arming,
/// and teardown never race. `onChange` is invoked on `queue` (a background queue);
/// callers must hop to their own actor.
final class WhatsAppDBWatcher {
  private let paths: [String]
  private let debounce: TimeInterval
  private let onChange: () -> Void
  private let queue = DispatchQueue(label: "com.omi.whatsapp.dbwatcher")
  private var sources: [DispatchSourceFileSystemObject] = []
  private var pending: DispatchWorkItem?
  private var stopped = false

  init(paths: [String], debounce: TimeInterval = 1.2, onChange: @escaping () -> Void) {
    self.paths = paths
    self.debounce = debounce
    self.onChange = onChange
  }

  func start() {
    queue.async { [weak self] in
      guard let self, !self.stopped else { return }
      for path in self.paths { self.arm(path) }
    }
  }

  func stop() {
    queue.async { [weak self] in
      guard let self else { return }
      self.stopped = true
      self.pending?.cancel()
      self.pending = nil
      for source in self.sources { source.cancel() }
      self.sources.removeAll()
    }
  }

  deinit {
    // `sources` is confined to `queue`; cancel there too rather than racing an
    // in-flight handler off-queue. Capture by value since self is being torn down.
    let sourcesToCancel = sources
    queue.async {
      for source in sourcesToCancel { source.cancel() }
    }
  }

  /// Must run on `queue`.
  private func arm(_ path: String) {
    guard !stopped else { return }
    let fd = open(path, O_EVTONLY)
    // A sidecar may not exist yet (e.g. `-wal` before the first WAL write); the
    // fallback timer and the main DB watcher cover that until it appears.
    guard fd >= 0 else { return }

    let source = DispatchSource.makeFileSystemObjectSource(
      fileDescriptor: fd,
      eventMask: [.write, .extend, .delete, .rename, .revoke, .link],
      queue: queue)
    source.setEventHandler { [weak self] in
      guard let self else { return }
      let flags = source.data
      if flags.contains(.delete) || flags.contains(.rename) || flags.contains(.revoke) {
        source.cancel()
        self.sources.removeAll { $0 === source }
        self.queue.asyncAfter(deadline: .now() + 0.2) { [weak self] in self?.arm(path) }
      }
      self.scheduleFire()
    }
    source.setCancelHandler { close(fd) }
    sources.append(source)
    source.resume()
  }

  /// Must run on `queue`.
  private func scheduleFire() {
    guard !stopped else { return }
    pending?.cancel()
    let work = DispatchWorkItem { [weak self] in self?.onChange() }
    pending = work
    queue.asyncAfter(deadline: .now() + debounce, execute: work)
  }
}
