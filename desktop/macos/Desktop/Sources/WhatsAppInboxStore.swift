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
        Task { await autoReply(chat) }
      }
    } else {
      autoReplyChats.remove(chatID)
    }
  }

  private var lastLatestMessageID: [String: String] = [:]
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
        if autoReplyChats.contains(chat.chatID) {
          Task { await self.autoReply(chat) }
        } else {
          // A new inbound arrived → any earlier draft is stale. Drop it; we draft
          // on-demand when the user opens the chat (or right now if it's already open).
          preDrafts[chat.id] = nil
          if chat.id == selectedChatID {
            Task { await self.predraft(chat) }
          }
        }
      }
    }
    baselined = true
  }

  private func predraft(_ chat: WhatsAppChat) async {
    guard
      let resp = try? await APIClient.shared.whatsappDraftReply(
        person: chat.personRef, thread: chat.draftContext(), intent: nil, isGroup: chat.isGroup)
    else { return }
    // Don't offer a disambiguation ask as a draft; and when the backend abstained
    // (group message not meant for the user) show no draft.
    guard !resp.ambiguous, !resp.abstain else { return }
    let draft = resp.draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !draft.isEmpty else { return }
    preDrafts[chat.id] = draft
  }

  /// Draft a reply and send it immediately, without review. Only ever called for
  /// chats the user explicitly enabled auto-reply on. Sent messages can't be
  /// unsent, so a send failure is logged and the draft is simply dropped.
  private func autoReply(_ chat: WhatsAppChat) async {
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
    do {
      try WhatsAppSenderService.send(text: text, toChatID: chat.chatID, phone: phone)
      appendSent(text, to: chat.id)
    } catch {
      NSLog("WhatsApp auto-reply send failed for \(chat.chatID): \(error.localizedDescription)")
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
    for source in sources { source.cancel() }
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
