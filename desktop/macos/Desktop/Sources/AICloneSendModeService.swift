import Foundation

// MARK: - Send mode

/// How the AI Clone handles an incoming message from a given contact.
enum SendMode: String, Codable, CaseIterable, Sendable {
  /// The clone never acts on its own. You send manually from the Preview Chat, which now
  /// dispatches through the real platform send service. This is the default for every contact.
  case manual
  /// A new incoming message generates a suggested reply that lands in a pending-approval
  /// queue. Nothing is sent until you Approve (optionally after editing).
  case draftReview
  /// A new incoming message is answered and sent automatically — but only while the global
  /// kill switch (`isPaused`) is OFF. Guarded hard because it messages real people unattended.
  case autonomous

  var label: String {
    switch self {
    case .manual: return "Manual"
    case .draftReview: return "Draft"
    case .autonomous: return "Auto"
    }
  }

  var fullLabel: String {
    switch self {
    case .manual: return "Manual"
    case .draftReview: return "Draft-Review"
    case .autonomous: return "Autonomous"
    }
  }
}

// MARK: - Platform routing

/// Which concrete send/listen backend a contact id maps to. iMessage contact ids are the
/// raw handle (unprefixed); Telegram/WhatsApp ids carry a `platform:` prefix.
enum AIClonePlatform: String, Sendable {
  case imessage
  case telegram
  case whatsapp

  /// Whether the clone can actually *send* on this platform. WhatsApp is import-only for
  /// training (its contact id is an export filename, not an addressable number).
  var canSend: Bool { self != .whatsapp }

  static func of(contactId: String) -> AIClonePlatform {
    if contactId.hasPrefix("telegram:") { return .telegram }
    if contactId.hasPrefix("whatsapp:") { return .whatsapp }
    return .imessage
  }
}

// MARK: - Persisted records

/// One entry in the "Recent Sent Messages" log.
struct AICloneSentLogEntry: Codable, Identifiable, Sendable {
  let id: UUID
  let contactId: String
  let contactDisplayName: String
  let text: String
  let mode: SendMode
  let timestamp: Date

  init(
    id: UUID = UUID(), contactId: String, contactDisplayName: String, text: String,
    mode: SendMode, timestamp: Date
  ) {
    self.id = id
    self.contactId = contactId
    self.contactDisplayName = contactDisplayName
    self.text = text
    self.mode = mode
    self.timestamp = timestamp
  }
}

/// A reply the clone generated in Draft-Review mode, awaiting the user's decision.
struct AIClonePendingDraft: Identifiable, Sendable, Equatable {
  let id: UUID
  let contactId: String
  let contactDisplayName: String
  let incomingText: String
  var draftText: String
  let createdAt: Date

  init(
    id: UUID = UUID(), contactId: String, contactDisplayName: String, incomingText: String,
    draftText: String, createdAt: Date
  ) {
    self.id = id
    self.contactId = contactId
    self.contactDisplayName = contactDisplayName
    self.incomingText = incomingText
    self.draftText = draftText
    self.createdAt = createdAt
  }
}

// MARK: - Service

/// The single coordinator that turns trained personas into an actual send experience:
/// per-contact `SendMode`, the global autonomous kill switch, the pending-draft queue, the
/// sent-message log, and the live listeners that drive Draft-Review / Autonomous.
///
/// MainActor-isolated and `ObservableObject` so the AI Clone page binds directly to it.
/// Persistence is UserDefaults (small, per-user, local — matches the rest of the feature).
@MainActor
final class AICloneSendModeService: ObservableObject {
  static let shared = AICloneSendModeService()

  // MARK: Persistence keys
  private enum Keys {
    static let modes = "aiCloneSendModes"  // [contactId: SendMode.rawValue]
    static let isPaused = "aiCloneAutonomousPaused"
    static let sentLog = "aiCloneSentLog"
  }

  /// How many sent entries we keep. The log is a convenience surface, not an audit store.
  private static let maxSentLogEntries = 200

  // MARK: Published state

  /// Global kill switch for Autonomous sending. Defaults to TRUE (paused) — automated
  /// sending to real people must be an explicit, deliberate opt-in.
  @Published var isPaused: Bool {
    didSet { UserDefaults.standard.set(isPaused, forKey: Keys.isPaused) }
  }

  /// Per-contact send mode. Absent → `.manual`.
  @Published private(set) var modes: [String: SendMode]

  /// Drafts awaiting Approve/Edit/Reject, newest first.
  @Published private(set) var pendingDrafts: [AIClonePendingDraft] = []

  /// Recently sent messages, newest first.
  @Published private(set) var sentLog: [AICloneSentLogEntry]

  // MARK: Listener wiring

  /// Contacts + personas the page has registered for live handling. Keyed by contact id.
  private var activeContacts: [String: (contact: ImportedContact, persona: ContactPersona)] = [:]
  private var isListening = false
  /// De-dupes generation for the same incoming message across rapid duplicate poll ticks.
  private var handledIncomingKeys: Set<String> = []

  private init() {
    let defaults = UserDefaults.standard
    // Default paused = true. `object(forKey:)` is nil on first launch → paused.
    if defaults.object(forKey: Keys.isPaused) == nil {
      isPaused = true
    } else {
      isPaused = defaults.bool(forKey: Keys.isPaused)
    }

    if let raw = defaults.dictionary(forKey: Keys.modes) as? [String: String] {
      modes = raw.reduce(into: [:]) { acc, kv in
        if let mode = SendMode(rawValue: kv.value) { acc[kv.key] = mode }
      }
    } else {
      modes = [:]
    }

    if let data = defaults.data(forKey: Keys.sentLog),
      let decoded = try? JSONDecoder().decode([AICloneSentLogEntry].self, from: data)
    {
      sentLog = decoded
    } else {
      sentLog = []
    }
  }

  // MARK: - Mode

  func mode(for contactId: String) -> SendMode { modes[contactId] ?? .manual }

  func setMode(_ mode: SendMode, for contactId: String) {
    if mode == .manual {
      modes.removeValue(forKey: contactId)
    } else {
      modes[contactId] = mode
    }
    UserDefaults.standard.set(
      modes.mapValues(\.rawValue), forKey: Keys.modes)
  }

  // MARK: - Pause switch

  func setPaused(_ paused: Bool) { isPaused = paused }

  // MARK: - Active-contact registration (drives listeners)

  /// Point the live handlers at the current set of trained contacts. Called by the page with
  /// every contact that has a persona; only Draft-Review / Autonomous contacts actually get
  /// acted on, but registering all trained personas keeps routing simple.
  func updateActiveContacts(_ entries: [(contact: ImportedContact, persona: ContactPersona)]) {
    activeContacts = entries.reduce(into: [:]) { acc, entry in
      acc[entry.contact.id] = entry
    }
  }

  // MARK: - Listening lifecycle

  /// Start platform listeners for any platform that has at least one registered contact and
  /// is actually available (Telegram logged in; iMessage reachable). Safe to call repeatedly.
  ///
  /// Note: starting listeners is inert with respect to *sending* — nothing is auto-sent
  /// unless a contact is Autonomous AND `isPaused == false`. Draft-Review only enqueues.
  func startListening() {
    guard !isListening else { return }
    isListening = true

    // iMessage: always safe to tail chat.db locally.
    Task {
      await IMessageSendService.shared.startListening { [weak self] handle, fromMe, text, date in
        Task { @MainActor in
          self?.handleIncoming(
            platform: .imessage, peerKey: handle, fromMe: fromMe, text: text, date: date)
        }
      }
    }

    // Telegram: only if a ready session exists — otherwise skip silently (no failure banner).
    Task {
      let state = await TelegramSendService.shared.state()
      guard case .ready = state else {
        log("AICloneSendModeService: Telegram not ready (\(state)) — skipping live listener")
        return
      }
      await TelegramSendService.shared.startListening { [weak self] chatId, fromMe, text, date in
        Task { @MainActor in
          self?.handleIncoming(
            platform: .telegram, peerKey: String(chatId), fromMe: fromMe, text: text, date: date)
        }
      }
    }
  }

  func stopListening() {
    guard isListening else { return }
    isListening = false
    Task { await IMessageSendService.shared.stopListening() }
    Task { await TelegramSendService.shared.stopListening() }
    handledIncomingKeys.removeAll()
  }

  // MARK: - Incoming handling

  /// Map a platform + peer key back to the AI Clone contact id.
  private func contactId(platform: AIClonePlatform, peerKey: String) -> String {
    switch platform {
    case .imessage: return peerKey
    case .telegram: return "telegram:\(peerKey)"
    case .whatsapp: return "whatsapp:\(peerKey)"
    }
  }

  /// Called for every message the listeners see. We only act on *incoming* messages
  /// (`fromMe == false`) for contacts we have a persona for and that aren't in Manual mode.
  func handleIncoming(
    platform: AIClonePlatform, peerKey: String, fromMe: Bool, text: String, date: Date
  ) {
    guard !fromMe else { return }
    let id = contactId(platform: platform, peerKey: peerKey)
    guard let entry = activeContacts[id] else { return }
    let mode = mode(for: id)
    guard mode != .manual else { return }

    // De-dupe: the same incoming line shouldn't spawn two drafts if a poll tick repeats.
    let key = "\(id)|\(date.timeIntervalSince1970)|\(text.hashValue)"
    guard !handledIncomingKeys.contains(key) else { return }
    handledIncomingKeys.insert(key)
    if handledIncomingKeys.count > 500 { handledIncomingKeys.removeAll() }

    switch Self.action(for: mode, isPaused: isPaused) {
    case .ignore:
      return
    case .draft:
      generateDraft(for: entry.contact, persona: entry.persona, incoming: text)
    case .autoSend:
      autoRespond(for: entry.contact, persona: entry.persona, incoming: text)
    }
  }

  /// What an incoming message should trigger, given the contact's mode and the global kill
  /// switch. Pure and side-effect-free so the safety-critical rule — Autonomous NEVER sends
  /// while paused — is unit-testable in isolation.
  enum IncomingAction: Equatable { case ignore, draft, autoSend }

  nonisolated static func action(for mode: SendMode, isPaused: Bool) -> IncomingAction {
    switch mode {
    case .manual: return .ignore
    case .draftReview: return .draft
    case .autonomous: return isPaused ? .draft : .autoSend
    }
  }

  /// Draft-Review: generate a reply and enqueue it for approval. Never sends.
  private func generateDraft(for contact: ImportedContact, persona: ContactPersona, incoming: String)
  {
    Task {
      do {
        let reply = try await AIClonePersonaService.shared.respond(as: persona, to: incoming)
        let text = reply.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        pendingDrafts.insert(
          AIClonePendingDraft(
            contactId: contact.id, contactDisplayName: contact.displayName,
            incomingText: incoming, draftText: text, createdAt: Date()),
          at: 0)
      } catch {
        log("AICloneSendModeService: draft generation failed for \(contact.id): \(error)")
      }
    }
  }

  /// Autonomous: generate and send automatically — HARD-GATED on `!isPaused`. If paused (the
  /// default), this degrades to enqueuing a draft so nothing is ever sent unattended.
  private func autoRespond(for contact: ImportedContact, persona: ContactPersona, incoming: String) {
    guard !isPaused else {
      log("AICloneSendModeService: autonomous paused — enqueuing draft for \(contact.id)")
      generateDraft(for: contact, persona: persona, incoming: incoming)
      return
    }
    Task {
      do {
        let reply = try await AIClonePersonaService.shared.respond(as: persona, to: incoming)
        let text = reply.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        // Re-check the switch right before dispatch — the user may have paused mid-generation.
        guard !isPaused else {
          generateDraft(for: contact, persona: persona, incoming: incoming)
          return
        }
        try await send(contactId: contact.id, displayName: contact.displayName, text: text, mode: .autonomous)
      } catch {
        log("AICloneSendModeService: autonomous send failed for \(contact.id): \(error)")
      }
    }
  }

  // MARK: - Pending-draft actions

  /// Approve a pending draft (optionally with an edited body), sending it for real.
  func approveDraft(_ draft: AIClonePendingDraft, editedText: String? = nil) {
    let text = (editedText ?? draft.draftText).trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty else { return }
    removeDraft(draft.id)
    Task {
      do {
        try await send(
          contactId: draft.contactId, displayName: draft.contactDisplayName, text: text,
          mode: .draftReview)
      } catch {
        log("AICloneSendModeService: approved-draft send failed for \(draft.contactId): \(error)")
      }
    }
  }

  func rejectDraft(_ draft: AIClonePendingDraft) { removeDraft(draft.id) }

  func updateDraftText(_ id: UUID, to text: String) {
    guard let idx = pendingDrafts.firstIndex(where: { $0.id == id }) else { return }
    pendingDrafts[idx].draftText = text
  }

  private func removeDraft(_ id: UUID) {
    pendingDrafts.removeAll { $0.id == id }
  }

  // MARK: - Sending (unified)

  /// Route a send to the correct platform backend and, on success, log it. Throws on failure
  /// so callers (manual UI) can surface it; autonomous/draft callers log and swallow.
  func send(contactId: String, displayName: String, text: String, mode: SendMode) async throws {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { throw IMessageSendError.emptyText }

    let platform = AIClonePlatform.of(contactId: contactId)
    switch platform {
    case .imessage:
      try await IMessageSendService.shared.send(toHandle: contactId, text: trimmed)
    case .telegram:
      let raw = String(contactId.dropFirst("telegram:".count))
      guard let chatId = Int64(raw) else {
        throw IMessageSendError.sendScriptFailed("invalid Telegram chat id in \(contactId)")
      }
      try await TelegramSendService.shared.sendMessage(chatId: chatId, text: trimmed)
    case .whatsapp:
      throw IMessageSendError.sendScriptFailed("Sending to WhatsApp isn't supported yet.")
    }

    recordSent(
      AICloneSentLogEntry(
        contactId: contactId, contactDisplayName: displayName, text: trimmed, mode: mode,
        timestamp: Date()))
  }

  // MARK: - Sent log

  private func recordSent(_ entry: AICloneSentLogEntry) {
    sentLog.insert(entry, at: 0)
    if sentLog.count > Self.maxSentLogEntries {
      sentLog = Array(sentLog.prefix(Self.maxSentLogEntries))
    }
    persistSentLog()
  }

  /// Read method for the sent log (the published `sentLog` is the live source; this mirrors
  /// the "with a read method" requirement and returns an immutable snapshot).
  func recentSent(limit: Int = 50) -> [AICloneSentLogEntry] {
    Array(sentLog.prefix(limit))
  }

  func clearSentLog() {
    sentLog = []
    persistSentLog()
  }

  private func persistSentLog() {
    if let data = try? JSONEncoder().encode(sentLog) {
      UserDefaults.standard.set(data, forKey: Keys.sentLog)
    }
  }
}
