import Foundation
import SwiftUI

/// Backing store for the Messages tab: recent iMessage chats with full history.
@MainActor
final class IMessageInboxStore: ObservableObject {
  /// App-wide singleton so the incremental watcher (and therefore auto-reply)
  /// keeps running even when the Messages tab isn't on screen — auto-reply must
  /// fire on new inbound messages app-wide, not only while the inbox is open. A
  /// per-view @StateObject would be torn down on navigation, silently killing it
  /// (mirrors WhatsAppInboxStore / TelegramInboxStore).
  static let shared = IMessageInboxStore()

  @Published var chats: [IMessageChat] = []
  @Published var isLoading = false
  @Published var errorMessage: String?
  @Published var permissionNeeded = false
  /// Drafts are generated on-demand when the user opens a chat (not eagerly for
  /// every inbound), so the "Draft ready" pill only appears on chats the user
  /// actually looked at.
  @Published var selectedChatID: String? {
    didSet {
      guard selectedChatID != oldValue, let chat = selectedChat, chat.awaitingReply,
        preDrafts[chat.id] == nil, !autoReplyChats.contains(chat.chatGUID)
      else { return }
      Task { await predraft(chat) }
    }
  }
  /// Replies drafted on-demand when the user opened the chat.
  @Published var preDrafts: [String: String] = [:]
  /// Chats where auto-reply escalated instead of sending: the message needs the user
  /// (can't be answered truthfully, needs their decision, or asks for sensitive info).
  /// Keyed by chat.id; the value is the short user-facing reason. The suggested draft is
  /// kept in `preDrafts` for the composer to pre-fill. Presence here flips the row's
  /// "Draft ready" pill to "Needs you".
  @Published var needsInputReasons: [String: String] = [:]
  /// Tentative calendar holds created when an availability-aware reply accepted a
  /// proposed time. Keyed by chat.id; the Replies inbox surfaces a Confirm/Discard
  /// banner for it. Persists after an auto-sent reply so the user can still discard it.
  @Published var pendingHolds: [String: DraftHold] = [:]
  /// Chat GUIDs the user has opted into automatic replies for. When a new inbound
  /// message arrives in one of these chats, Omi drafts AND sends a reply without
  /// review (sent iMessages can't be unsent — this is strictly opt-in per chat).
  @Published var autoReplyChats: Set<String> = [] {
    didSet { UserDefaults.standard.set(Array(autoReplyChats), forKey: Self.autoReplyDefaultsKey) }
  }
  private static let autoReplyDefaultsKey = "imessageAutoReplyChats"

  init() {
    // Restore per-chat auto-reply opt-ins from the previous session.
    autoReplyChats = Set(UserDefaults.standard.stringArray(forKey: Self.autoReplyDefaultsKey) ?? [])
  }

  func isAutoReplyEnabled(_ chatGUID: String) -> Bool { autoReplyChats.contains(chatGUID) }

  func setAutoReply(_ enabled: Bool, for chatGUID: String) {
    if enabled {
      autoReplyChats.insert(chatGUID)
      // If the chat already has an unanswered inbound message, reply to it now
      // instead of waiting for the contact's next new message — that's what a user
      // expects when they flip the toggle on for a waiting thread.
      if let chat = chats.first(where: { $0.chatGUID == chatGUID }), chat.awaitingReply {
        scheduleAutoReply(chat)
      }
    } else {
      autoReplyChats.remove(chatGUID)
      // Cancel any in-flight draft/send for this chat. A reply whose draft is still
      // being generated must not land after the user toggled auto-reply off — sent
      // iMessages can't be unsent. autoReply() also re-checks membership before send
      // as a second guard against races the cancel can't win.
      autoReplyTasks.removeValue(forKey: chatGUID)?.cancel()
      // Release the once-per-message guard synchronously here too: the cancelled task
      // clears it only asynchronously, so without this a quick toggle off→on for the
      // same still-waiting message would hit the guard and never fire the "reply now".
      lastAutoRepliedInboundID.removeValue(forKey: chatGUID)
    }
  }

  /// Track the auto-reply Task per chat so disabling the toggle can cancel an
  /// in-flight draft+send. A newer request for the same chat supersedes an older one.
  private func scheduleAutoReply(_ chat: IMessageChat) {
    // Idempotency guard: auto-reply to any given inbound message AT MOST once.
    // A watcher burst, the fallback poll, and a fresh refresh can each schedule the
    // same chat; without this, overlapping runs could send the same reply more than
    // once, and sends can't be unsent. Keyed on the latest inbound message id.
    let inboundID = chat.bubbles.last?.id ?? ""
    guard lastAutoRepliedInboundID[chat.chatGUID] != inboundID else { return }
    lastAutoRepliedInboundID[chat.chatGUID] = inboundID
    autoReplyTasks[chat.chatGUID]?.cancel()
    autoReplyTasks[chat.chatGUID] = Task { [weak self] in
      await self?.autoReply(chat, inboundID: inboundID)
      self?.autoReplyTasks[chat.chatGUID] = nil
    }
  }

  /// Latest inbound message id we've already scheduled an auto-reply for, per chat —
  /// so the same incoming message is never auto-replied to twice.
  private var lastAutoRepliedInboundID: [String: String] = [:]
  private var lastLatestMessageID: [String: String] = [:]
  /// In-flight auto-reply tasks keyed by chat GUID, so disabling auto-reply mid-draft
  /// can cancel the pending send.
  private var autoReplyTasks: [String: Task<Void, Never>] = [:]
  private var baselined = false
  private var watchTask: Task<Void, Never>?
  private var dbWatcher: IMessageDBWatcher?
  /// High-water ROWID for incremental gating: we only do a full refresh when a
  /// message newer than this appears. Primed once the baseline is loaded.
  private var lastSeenROWID: Int64 = 0

  var selectedChat: IMessageChat? {
    guard let id = selectedChatID else { return nil }
    return chats.first { $0.id == id }
  }

  // MARK: - Real-time watcher

  /// Event-driven watcher for new inbound messages. Instead of periodically
  /// reloading the whole chat.db, we watch the SQLite files for writes (WAL-mode
  /// writes land in the -wal/-shm sidecars), debounce the burst, then cheaply
  /// query only messages newer than `lastSeenROWID`. A full `readChats()` refresh
  /// (and the resulting pre-draft) runs only when something genuinely new arrived.
  /// A slow fallback timer covers the rare case where a file event is missed.
  func startWatching() {
    guard watchTask == nil else { return }
    startFileWatcher()
    watchTask = Task { [weak self] in
      // Baseline pass (equivalent to the former first poll): full load + record
      // the latest id per chat, then prime the incremental cursor from "now".
      await self?.bootstrap()
      while !Task.isCancelled {
        // Fallback in case a file-system event is missed (e.g. sidecar rotation).
        try? await Task.sleep(nanoseconds: 45_000_000_000)  // 45s
        // Stop the loop once the store is gone, otherwise it keeps waking forever.
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
    let dbPath = IMessagePermissionPolicy.chatDatabaseURL.path
    // WAL-mode writes usually update the -wal/-shm sidecars, so watch all three.
    let paths = [dbPath, dbPath + "-wal", dbPath + "-shm"]
    let watcher = IMessageDBWatcher(paths: paths) { [weak self] in
      // DispatchSource fires on a background queue; hop back to the main actor.
      Task { await self?.syncNewMessages() }
    }
    dbWatcher = watcher
    watcher.start()
  }

  /// One-time baseline: full load (records latest ids for all chats without
  /// pre-drafting) and prime the incremental high-water mark.
  private func bootstrap() async {
    await refresh()
    // Prime the cursor to the current DB max so gating starts from "now".
    // `limit: 1` keeps this cheap — we only need `maxROWID`.
    if let result = try? await IMessageReaderService.shared.newMessages(afterROWID: lastSeenROWID, limit: 1) {
      lastSeenROWID = max(lastSeenROWID, result.maxROWID)
    }
  }

  /// Debounced change handler: cheaply check for messages newer than the
  /// high-water mark and only do a full refresh (+ pre-draft) when something new
  /// actually arrived.
  private func syncNewMessages() async {
    guard IMessagePermissionPolicy.fullDiskAccessGranted() else {
      // Mirror refresh()/load(): reflect revoked Full Disk Access in the UI
      // instead of silently leaving stale chats on screen.
      permissionNeeded = true
      chats = []
      // Force a fresh baseline once access is granted again.
      lastSeenROWID = 0
      return
    }
    permissionNeeded = false
    guard let result = try? await IMessageReaderService.shared.newMessages(afterROWID: lastSeenROWID)
    else { return }
    guard result.maxROWID > lastSeenROWID else { return }  // nothing new
    lastSeenROWID = result.maxROWID
    await refresh()
  }

  private func refresh() async {
    guard IMessagePermissionPolicy.fullDiskAccessGranted() else {
      // Mirror load(): reflect revoked Full Disk Access in the UI instead of
      // silently leaving stale chats on screen.
      permissionNeeded = true
      chats = []
      return
    }
    permissionNeeded = false
    guard let loaded = try? await IMessageReaderService.shared.readChats() else { return }
    chats = loaded

    for chat in loaded {
      let latestID = chat.bubbles.last?.id ?? ""
      let known = lastLatestMessageID[chat.id]
      // Baseline the latest ID for ALL chats so a chat transitioning to
      // awaitingReply on its first inbound message still gets a pre-draft.
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
        if autoReplyChats.contains(chat.chatGUID) {
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

  private func predraft(_ chat: IMessageChat) async {
    // Snapshot the message we're drafting a reply to. If a newer message arrives for
    // this chat during the async call (a racing predraft from selection change / poll),
    // discard this now-stale draft rather than overwriting the fresher one.
    let draftedForID = chat.bubbles.last?.id
    guard
      let resp = try? await APIClient.shared.imessageDraftReply(
        person: chat.personRef, thread: chat.draftContext(), intent: nil, isGroup: chat.isGroup)
    else { return }
    // Don't offer a disambiguation ask as a ready-to-send draft; and when the
    // backend abstained (group message not meant for the user) show no draft.
    guard !resp.ambiguous, !resp.abstain else { return }
    let draft = resp.draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !draft.isEmpty else { return }
    guard chats.first(where: { $0.id == chat.id })?.bubbles.last?.id == draftedForID else { return }
    preDrafts[chat.id] = draft
    pendingHolds[chat.id] = resp.hold
  }

  /// Draft a reply and send it immediately, without review. Only ever called for
  /// 1:1 chats the user explicitly enabled auto-reply on. Sent messages can't be
  /// unsent, so a send failure is logged and the draft is simply dropped (never
  /// silently retried into a duplicate send). Group chats are draft-only (see below).
  private func autoReply(_ chat: IMessageChat, inboundID: String) async {
    // Release the once-per-message guard so a later attempt (e.g. the user
    // re-enables auto-reply for this still-waiting thread) can try again when this
    // attempt did NOT actually send — draft failed, was cancelled, or the backend
    // returned nothing to send. On a real send (or a group predraft) we KEEP the
    // guard so the same inbound message is never replied to twice.
    func allowRetry() {
      if lastAutoRepliedInboundID[chat.chatGUID] == inboundID {
        lastAutoRepliedInboundID[chat.chatGUID] = nil
      }
    }
    guard
      let resp = try? await APIClient.shared.imessageDraftReply(
        person: chat.personRef, thread: chat.draftContext(), intent: nil, isGroup: chat.isGroup)
    else {
      allowRetry()
      return
    }
    // NEVER auto-send when the person is ambiguous — the "draft" is a
    // disambiguation ask, and auto-reply sends without review.
    guard !resp.ambiguous else {
      NSLog("iMessage auto-reply skipped for \(chat.chatGUID): ambiguous contact needs disambiguation")
      allowRetry()
      return
    }
    // Backend abstained (group message not directed at the user) → nothing to send.
    guard !resp.abstain else {
      allowRetry()
      return
    }
    let text = resp.draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty else {
      allowRetry()
      return
    }
    // Final guard: the draft round-trip is async, so re-check that auto-reply is still
    // enabled (and this task wasn't cancelled) BEFORE either publishing a group draft
    // or sending a 1:1. The user may have toggled it off while the draft was being
    // generated — in which case we must neither send nor surface a draft for it.
    guard !Task.isCancelled, autoReplyChats.contains(chat.chatGUID) else {
      NSLog("iMessage auto-reply cancelled for \(chat.chatGUID) before send (toggled off mid-draft)")
      allowRetry()
      return
    }
    // Surface any tentative calendar hold regardless of which path we take below
    // (escalate / group draft / auto-send) so the user can confirm or discard it.
    pendingHolds[chat.id] = resp.hold
    // Escalation: the message needs the user, not an auto-sent reply. Keep the
    // best-guess draft as a SUGGESTION for review, record the reason, and notify —
    // never auto-send. Keep the once-per-inbound guard (this is a terminal outcome like
    // a send) so we don't re-notify on every poll of the same message.
    if resp.needsInput {
      preDrafts[chat.id] = text
      needsInputReasons[chat.id] = resp.needsInputReason ?? ""
      MessagingNeedsInput.notify(
        personName: chat.displayName, reason: resp.needsInputReason, preview: text,
        platform: .imessage, chatID: chat.chatGUID)
      return
    }
    // Groups are DRAFT-ONLY: never auto-send to a group chat (higher blast radius and
    // different send/rollback semantics). Surface the draft for the user to review
    // and send manually instead of sending it automatically.
    if chat.isGroup {
      preDrafts[chat.id] = text
      return
    }
    do {
      try await IMessageSenderService.send(text: text, toChatGUID: chat.chatGUID)
      appendSent(text, to: chat.id)
    } catch {
      // Sent messages can't be unsent and a thrown error doesn't prove the message
      // didn't go out, so we deliberately do NOT release the guard here — never
      // silently retry into a possible duplicate send.
      NSLog("iMessage auto-reply send failed for \(chat.chatGUID): \(error.localizedDescription)")
    }
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
    guard let id = selectedChatID else { return }
    appendSent(text, to: id)
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
        NSLog("iMessage discard hold failed for \(chatID): \(error.localizedDescription)")
      }
    }
  }

  /// Optimistically append a just-sent message to a specific chat (used by
  /// auto-reply, where the target chat may not be the selected one).
  func appendSent(_ text: String, to chatID: String) {
    // The user replied — any escalation for this chat is resolved.
    needsInputReasons[chatID] = nil
    guard let idx = chats.firstIndex(where: { $0.id == chatID }) else { return }
    let chat = chats[idx]
    let bubble = IMessageChatBubble(
      id: UUID().uuidString, text: text, isFromMe: true, date: Date(), senderName: nil)
    chats[idx] = IMessageChat(
      chatGUID: chat.chatGUID, displayName: chat.displayName, isGroup: chat.isGroup,
      personRef: chat.personRef, bubbles: chat.bubbles + [bubble], avatarImageData: chat.avatarImageData)
  }
}

/// Watches the Messages SQLite files (`chat.db` + its `-wal`/`-shm` sidecars) for
/// writes and invokes `onChange` after a short debounce. WAL-mode writes land in
/// the sidecars, so all three are monitored. If a file is checkpointed/rotated
/// away (delete/rename/revoke) the source is re-armed on the new inode.
///
/// All mutable state is confined to `queue`, so DispatchSource callbacks, arming,
/// and teardown never race. `onChange` is invoked on `queue` (a background queue);
/// callers must hop to their own actor.
final class IMessageDBWatcher {
  private let paths: [String]
  private let debounce: TimeInterval
  private let onChange: () -> Void
  private let queue = DispatchQueue(label: "com.omi.imessage.dbwatcher")
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
    // Cancel any live sources so their file descriptors are closed even if stop()
    // was never called. `sources` is confined to `queue` (armed/cancelled there and
    // mutated by the source event handlers), so cancel on `queue` too rather than
    // touching it off-queue and racing an in-flight handler. Capture by value since
    // self is being torn down; the block references neither self nor its stored state.
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
    // fallback timer and the chat.db watcher cover that until it appears.
    guard fd >= 0 else { return }

    let source = DispatchSource.makeFileSystemObjectSource(
      fileDescriptor: fd,
      eventMask: [.write, .extend, .delete, .rename, .revoke, .link],
      queue: queue)
    source.setEventHandler { [weak self] in
      guard let self else { return }
      let flags = source.data
      if flags.contains(.delete) || flags.contains(.rename) || flags.contains(.revoke) {
        // The file was checkpointed/rotated away — drop this source and re-arm on
        // the new inode shortly after.
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
