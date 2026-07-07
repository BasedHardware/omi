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

  /// Whether the clone can actually *send* on this platform. All three platforms route to a
  /// real send backend now — WhatsApp goes through the local Baileys sidecar once linked
  /// (imported-export contacts are resolved to a number by name or a learned mapping).
  var canSend: Bool { true }

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
    // One-time explicit acknowledgment that WhatsApp autonomous sending rides an unofficial
    // connection (Baileys / Linked Devices) that carries account-flagging risk.
    static let whatsAppAutonomousAcknowledged = "aiCloneWhatsAppAutonomousAcknowledged"
    static let whatsAppPhones = "aiCloneWhatsAppPhoneMap"  // [contactId: phone digits]
    // JSON [KnownContact] — every contact ever registered, so app launch can rebuild
    // listener routing without the AI Clone page being opened.
    static let knownContacts = "aiCloneKnownContacts"
    // Master switch for automatic commitment→Task extraction from incoming messages.
    // Absent → ON (the feature is meant to work out of the box once contacts are trained).
    static let taskCaptureEnabled = "aiCloneTaskCaptureEnabled"
    // Timestamp of the last app-launch "catch up on messages received while closed" sweep,
    // so a quick relaunch doesn't re-scan every known contact's history again.
    static let lastCommitmentBackstop = "aiCloneLastCommitmentBackstop"
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

  /// One-time acknowledgment gate for WhatsApp Autonomous mode (see `setMode`). False until
  /// the user explicitly confirms the unofficial-connection risk dialog.
  @Published private(set) var whatsAppAutonomousAcknowledged: Bool

  /// Learned contactId → phone-number mapping for WhatsApp contacts imported from export
  /// files (whose ids aren't addressable). Populated by name-matched incoming messages and
  /// sidecar name resolution; consulted on every WhatsApp send.
  private(set) var whatsAppPhoneByContactId: [String: String]

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
  /// Per-contact timestamp of the last commitment/task scan, so a burst of incoming texts
  /// triggers at most one history scan per `commitmentScanDebounce` window.
  private var lastCommitmentScanAt: [String: Date] = [:]
  /// Minimum gap between commitment scans for the same contact.
  private let commitmentScanDebounce: TimeInterval = 90
  /// Skip the launch backstop if we already ran one within this window (relaunch guard).
  private let commitmentBackstopCooldown: TimeInterval = 6 * 60 * 60
  /// Cap how many contacts the launch backstop scans, most-active first, to avoid an
  /// LLM storm the moment the app opens.
  private let commitmentBackstopMaxContacts = 8

  /// Whether automatic commitment→Task extraction from incoming messages is on. Defaults to
  /// true; the user can turn it off if it's too noisy.
  var isTaskCaptureEnabled: Bool {
    UserDefaults.standard.object(forKey: Keys.taskCaptureEnabled) as? Bool ?? true
  }

  func setTaskCaptureEnabled(_ enabled: Bool) {
    UserDefaults.standard.set(enabled, forKey: Keys.taskCaptureEnabled)
  }

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

    whatsAppAutonomousAcknowledged = defaults.bool(forKey: Keys.whatsAppAutonomousAcknowledged)
    whatsAppPhoneByContactId =
      (defaults.dictionary(forKey: Keys.whatsAppPhones) as? [String: String]) ?? [:]
  }

  // MARK: - Mode

  func mode(for contactId: String) -> SendMode { modes[contactId] ?? .manual }

  /// Set a contact's send mode. Returns false (and changes nothing) when the WhatsApp
  /// Autonomous acknowledgment gate blocks it — the UI must first show the one-time
  /// unofficial-connection risk confirmation and call `acknowledgeWhatsAppAutonomousRisk()`.
  @discardableResult
  func setMode(_ mode: SendMode, for contactId: String) -> Bool {
    guard
      !Self.requiresWhatsAppAutonomousAcknowledgment(
        mode: mode, contactId: contactId, acknowledged: whatsAppAutonomousAcknowledged)
    else {
      log("AICloneSendModeService: blocked Autonomous for \(contactId) — WhatsApp risk not acknowledged")
      return false
    }
    if mode == .manual {
      modes.removeValue(forKey: contactId)
    } else {
      modes[contactId] = mode
    }
    UserDefaults.standard.set(
      modes.mapValues(\.rawValue), forKey: Keys.modes)
    // A contact that can act on incoming messages needs the listeners running — the
    // launch bootstrap skips them when every contact was Manual at the time.
    if mode != .manual { startListening() }
    return true
  }

  /// The WhatsApp-specific extra safety step: Autonomous mode on a WhatsApp contact requires
  /// a one-time explicit acknowledgment that the connection method is unofficial (Baileys via
  /// Linked Devices) and carries some account-flagging risk. Manual and Draft-Review don't.
  /// Pure and side-effect-free so the gate is unit-testable in isolation.
  nonisolated static func requiresWhatsAppAutonomousAcknowledgment(
    mode: SendMode, contactId: String, acknowledged: Bool
  ) -> Bool {
    mode == .autonomous && AIClonePlatform.of(contactId: contactId) == .whatsapp && !acknowledged
  }

  /// Record the user's explicit acceptance of the WhatsApp-autonomous risk dialog.
  func acknowledgeWhatsAppAutonomousRisk() {
    whatsAppAutonomousAcknowledged = true
    UserDefaults.standard.set(true, forKey: Keys.whatsAppAutonomousAcknowledged)
  }

  // MARK: - Pause switch

  func setPaused(_ paused: Bool) {
    isPaused = paused
    // Unpausing means "go live" — make sure the listeners are actually running.
    if !paused, !activeContacts.isEmpty { startListening() }
  }

  // MARK: - Active-contact registration (drives listeners)

  /// Point the live handlers at the current set of trained contacts. Called by the page with
  /// every contact that has a persona; only Draft-Review / Autonomous contacts actually get
  /// acted on, but registering all trained personas keeps routing simple.
  func updateActiveContacts(_ entries: [(contact: ImportedContact, persona: ContactPersona)]) {
    activeContacts = entries.reduce(into: [:]) { acc, entry in
      acc[entry.contact.id] = entry
    }
    persistKnownContacts(entries.map(\.contact))
  }

  // MARK: - App-launch bootstrap

  /// Lightweight persisted registration (contact metadata only — the persona itself lives
  /// in `AIClonePersonaService`) so launch can rebuild routing without the page.
  private struct KnownContact: Codable {
    let id: String
    let displayName: String
    let messageCount: Int
    let platform: String
  }

  /// Rebuild active-contact routing from persisted personas at app launch and start the
  /// platform listeners when any contact is in Draft-Review/Autonomous — so the clone
  /// works from launch, not only while the AI Clone page happens to be open.
  func bootstrapAtLaunch() {
    Task { @MainActor in
      guard activeContacts.isEmpty else { return }
      let personas = await AIClonePersonaService.shared.allPersonas()
      guard !personas.isEmpty else {
        log("AICloneSendModeService: bootstrap — no trained personas, nothing to do")
        return
      }
      let known = Self.loadKnownContacts()
      let entries = personas.map { id, persona in
        let saved = known[id]
        let contact = ImportedContact(
          id: id,
          displayName: saved?.displayName ?? persona.contactHandle,
          messageCount: saved?.messageCount ?? persona.messageCountUsed,
          platform: saved?.platform ?? AIClonePlatform.of(contactId: id).rawValue)
        return (contact: contact, persona: persona)
      }
      updateActiveContacts(entries)
      let actionable = entries.filter { mode(for: $0.contact.id) != .manual }.count
      // Listeners run when a contact can auto-reply (Draft/Auto) OR when automatic task
      // capture is on — task capture needs the live incoming feed for every known contact,
      // not just the ones in a send mode.
      if actionable > 0 || isTaskCaptureEnabled {
        startListening()
      }
      // Catch up on obligations from messages that landed while the app was closed — the live
      // listener only sees rows added after it starts, so without this a request received
      // overnight would never become a Task. Bounded + cooldown-guarded so relaunches are cheap.
      if isTaskCaptureEnabled {
        runLaunchCommitmentBackstop(contacts: entries.map(\.contact))
      }
      log(
        "AICloneSendModeService: bootstrapped \(entries.count) trained contacts "
          + "(\(actionable) in Draft/Auto, task capture \(isTaskCaptureEnabled ? "on" : "off"))")
    }
  }

  private func persistKnownContacts(_ contacts: [ImportedContact]) {
    guard !contacts.isEmpty else { return }
    // Merge, never shrink: a partial registration (e.g. the harness registering one
    // contact) must not erase names the launch bootstrap depends on.
    var known = Self.loadKnownContacts()
    for contact in contacts {
      known[contact.id] = KnownContact(
        id: contact.id, displayName: contact.displayName,
        messageCount: contact.messageCount, platform: contact.platform)
    }
    if let data = try? JSONEncoder().encode(Array(known.values)) {
      UserDefaults.standard.set(data, forKey: Keys.knownContacts)
    }
  }

  /// Contacts the clone knows about (trained personas / registered), for surfaces like the
  /// Task-settings blocklist. Prefers the live active set, falling back to the persisted
  /// known-contacts store so it works before the AI Clone page has been opened. Sorted by name.
  func knownContactsForSettings() -> [(id: String, displayName: String)] {
    let source: [(id: String, displayName: String)]
    if !activeContacts.isEmpty {
      source = activeContacts.values.map { ($0.contact.id, $0.contact.displayName) }
    } else {
      source = Self.loadKnownContacts().values.map { ($0.id, $0.displayName) }
    }
    return source.sorted {
      $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending
    }
  }

  private static func loadKnownContacts() -> [String: KnownContact] {
    guard let data = UserDefaults.standard.data(forKey: Keys.knownContacts),
      let decoded = try? JSONDecoder().decode([KnownContact].self, from: data)
    else { return [:] }
    return decoded.reduce(into: [:]) { $0[$1.id] = $1 }
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

    // WhatsApp: only if the sidecar session is already linked — never spawns a link flow.
    startWhatsAppListenerIfLinked()
  }

  /// Attach the WhatsApp live listener when a linked session exists. Also called by the
  /// linking UI right after a successful QR scan so listening starts without a page reload.
  func startWhatsAppListenerIfLinked() {
    guard isListening else { return }
    Task {
      // Only resume an existing session; if there's none this is a cheap no-op.
      guard WhatsAppSendService.hasSavedSession() else {
        log("AICloneSendModeService: WhatsApp not linked — skipping live listener")
        return
      }
      _ = await WhatsAppSendService.shared.startLinking()  // spawn + resume saved session
      let state = await WhatsAppSendService.shared.state()
      guard state.isLinked || state == .connecting else {
        log("AICloneSendModeService: WhatsApp session not usable (\(state)) — skipping live listener")
        return
      }
      await WhatsAppSendService.shared.startListening { [weak self] phone, fromMe, text, date, senderName in
        Task { @MainActor in
          self?.handleIncomingWhatsApp(
            phone: phone, fromMe: fromMe, text: text, date: date, senderName: senderName)
        }
      }
    }
  }

  func stopListening() {
    guard isListening else { return }
    isListening = false
    Task { await IMessageSendService.shared.stopListening() }
    Task { await TelegramSendService.shared.stopListening() }
    Task { await WhatsAppSendService.shared.stopListening() }
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

    // De-dupe: the same incoming line shouldn't spawn two drafts (or two scans) if a poll
    // tick repeats.
    let key = "\(id)|\(date.timeIntervalSince1970)|\(text.hashValue)"
    guard !handledIncomingKeys.contains(key) else { return }
    handledIncomingKeys.insert(key)
    if handledIncomingKeys.count > 500 { handledIncomingKeys.removeAll() }

    // Task capture is independent of AI-Clone send mode: even a Manual contact's incoming
    // requests ("can you send me X", "get groceries") should become Tasks. Debounced so a
    // burst of texts triggers one scan.
    maybeExtractCommitments(for: entry.contact)

    let mode = mode(for: id)
    guard mode != .manual else { return }

    switch Self.action(for: mode, isPaused: isPaused) {
    case .ignore:
      return
    case .draft:
      generateDraft(for: entry.contact, persona: entry.persona, incoming: text)
    case .autoSend:
      autoRespond(for: entry.contact, persona: entry.persona, incoming: text)
    }
  }

  // MARK: - Automatic commitment → Task capture

  /// Fire-and-forget: scan this contact's recent history for open obligations the user owes
  /// and create real Tasks for any new ones. Runs regardless of send mode; debounced per
  /// contact so a rapid burst of texts triggers a single scan. All the heavy lifting (LLM
  /// call, confidence filter, dedup, staged-task creation + promotion) lives in
  /// `CommitmentExtractionService` — this only decides *when* to run it.
  func maybeExtractCommitments(for contact: ImportedContact) {
    guard isTaskCaptureEnabled else { return }
    // Respect the per-person blocklist in Task settings — some contacts should never turn
    // their messages into tasks.
    if TaskAssistantSettings.shared.isContactBlocked(contact.id) {
      log("AICloneSendModeService: task capture skipped for blocked contact \(contact.displayName)")
      return
    }
    let now = Date()
    if let last = lastCommitmentScanAt[contact.id], now.timeIntervalSince(last) < commitmentScanDebounce {
      return
    }
    lastCommitmentScanAt[contact.id] = now
    Task {
      do {
        guard
          let messages = try? await AICloneMessageLoader.loadMessages(for: contact, limit: 200),
          messages.count >= 4
        else { return }
        let outcome = try await CommitmentExtractionService.shared.scanAndCreateTasks(
          contact: contact, messages: messages)
        if outcome.created > 0 {
          log(
            "AICloneSendModeService: task capture — \(contact.displayName) created \(outcome.created) task(s)")
        }
      } catch {
        log("AICloneSendModeService: task capture failed for \(contact.id): \(error)")
      }
    }
  }

  /// One-shot launch sweep so obligations from messages received while the app was closed are
  /// still captured (the live poll only sees rows added after it starts). Cooldown-guarded so
  /// frequent relaunches don't re-scan, and capped to the most-active contacts, staggered, to
  /// avoid a burst of LLM calls at launch. Per-contact dedup keeps it from re-creating tasks.
  private func runLaunchCommitmentBackstop(contacts: [ImportedContact]) {
    let defaults = UserDefaults.standard
    let lastRun = defaults.object(forKey: Keys.lastCommitmentBackstop) as? Date
    if let lastRun, Date().timeIntervalSince(lastRun) < commitmentBackstopCooldown {
      log("AICloneSendModeService: launch task-capture backstop skipped (ran recently)")
      return
    }
    defaults.set(Date(), forKey: Keys.lastCommitmentBackstop)

    let ordered = contacts.sorted { $0.messageCount > $1.messageCount }
      .prefix(commitmentBackstopMaxContacts)
    guard !ordered.isEmpty else { return }
    log("AICloneSendModeService: launch task-capture backstop scanning \(ordered.count) contact(s)")
    Task {
      for contact in ordered {
        maybeExtractCommitments(for: contact)
        // Space the scans out — CommitmentExtractionService serializes on one LLM bridge, so
        // this just avoids queueing them all instantly.
        try? await Task.sleep(nanoseconds: 4_000_000_000)
      }
    }
  }

  /// WhatsApp incoming: live events carry a phone number (and often the sender's push-name),
  /// but imported-export contacts are keyed by filename — so resolve to whichever registered
  /// contact this message belongs to, learning the phone mapping for future sends.
  func handleIncomingWhatsApp(
    phone: String, fromMe: Bool, text: String, date: Date, senderName: String?
  ) {
    guard !fromMe else { return }
    let candidates = activeContacts.values
      .filter { AIClonePlatform.of(contactId: $0.contact.id) == .whatsapp }
      .map { (id: $0.contact.id, displayName: $0.contact.displayName) }
    guard
      let contactId = Self.resolveWhatsAppContactId(
        phone: phone, senderName: senderName, activeWhatsAppContacts: candidates,
        phoneMap: whatsAppPhoneByContactId)
    else { return }
    // Remember the number so Draft-Review/Autonomous replies to this contact can send.
    if contactId != "whatsapp:\(phone)" {
      recordWhatsAppPhone(phone, for: contactId)
    }
    handleIncoming(
      platform: .whatsapp, peerKey: String(contactId.dropFirst("whatsapp:".count)),
      fromMe: fromMe, text: text, date: date)
  }

  /// Map a live WhatsApp message (phone + optional push-name) onto a registered contact id.
  /// Precedence: exact `whatsapp:<phone>` id → learned phone mapping → unique
  /// case-insensitive display-name match. Pure for unit testing.
  nonisolated static func resolveWhatsAppContactId(
    phone: String,
    senderName: String?,
    activeWhatsAppContacts: [(id: String, displayName: String)],
    phoneMap: [String: String]
  ) -> String? {
    let direct = "whatsapp:\(phone)"
    if activeWhatsAppContacts.contains(where: { $0.id == direct }) { return direct }
    if let mapped = phoneMap.first(where: { $0.value == phone })?.key,
      activeWhatsAppContacts.contains(where: { $0.id == mapped })
    {
      return mapped
    }
    if let senderName {
      let needle = senderName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
      guard !needle.isEmpty else { return nil }
      let matches = activeWhatsAppContacts.filter {
        $0.displayName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == needle
      }
      if matches.count == 1 { return matches[0].id }
    }
    return nil
  }

  func recordWhatsAppPhone(_ phone: String, for contactId: String) {
    guard whatsAppPhoneByContactId[contactId] != phone else { return }
    whatsAppPhoneByContactId[contactId] = phone
    UserDefaults.standard.set(whatsAppPhoneByContactId, forKey: Keys.whatsAppPhones)
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

  /// Rolling conversation context for a reply. Loading recent history here also rebuilds
  /// the contact's retrieval index when it's cold (personas persist across launches but
  /// indices are in-memory), so app-level replies keep their dynamic few-shot examples.
  /// Returns the last turns oldest-first, dropping the trailing turn when it *is* the
  /// incoming message (live listeners see messages after they land in the local store).
  private func replyContext(for contact: ImportedContact, incoming: String) async
    -> [ConversationTurn]
  {
    guard
      let messages = try? await AICloneMessageLoader.loadMessages(for: contact, limit: 500),
      !messages.isEmpty
    else { return [] }
    await AICloneRetrievalService.shared.ensureIndex(contactId: contact.id, messages: messages)
    // Readers return newest-first; take the newest turns and flip to chronological.
    var turns = messages.prefix(12).reversed().map {
      ConversationTurn(isFromMe: $0.isFromMe, text: $0.text)
    }
    if let last = turns.last, !last.isFromMe,
      last.text.trimmingCharacters(in: .whitespacesAndNewlines)
        == incoming.trimmingCharacters(in: .whitespacesAndNewlines)
    {
      turns.removeLast()
    }
    return turns
  }

  /// Draft-Review: generate a reply and enqueue it for approval. Never sends.
  private func generateDraft(for contact: ImportedContact, persona: ContactPersona, incoming: String)
  {
    Task {
      do {
        let context = await replyContext(for: contact, incoming: incoming)
        let reply = try await AIClonePersonaService.shared.respond(
          as: persona, to: incoming, context: context)
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
  ///
  /// The whole flow is human-paced so the reply reads like the user really handled it:
  /// pause to "read" the message, leave a read receipt where the platform supports one,
  /// think (generation time), then "type" each bubble under a live typing indicator.
  private func autoRespond(for contact: ImportedContact, persona: ContactPersona, incoming: String) {
    guard !isPaused else {
      log("AICloneSendModeService: autonomous paused — enqueuing draft for \(contact.id)")
      generateDraft(for: contact, persona: persona, incoming: incoming)
      return
    }
    Task {
      do {
        try? await Task.sleep(
          nanoseconds: UInt64(AICloneHumanizer.readingDelay(forIncoming: incoming) * 1_000_000_000))
        await markIncomingRead(contactId: contact.id, displayName: contact.displayName)
        let context = await replyContext(for: contact, incoming: incoming)
        let reply = try await AIClonePersonaService.shared.respond(
          as: persona, to: incoming, context: context)
        let text = reply.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        // Re-check the switch right before dispatch — the user may have paused mid-generation.
        guard !isPaused else {
          generateDraft(for: contact, persona: persona, incoming: incoming)
          return
        }
        try await sendBubbles(
          contactId: contact.id, displayName: contact.displayName, text: text, mode: .autonomous,
          humanizedTyping: true)
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
        try await sendBubbles(
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

  /// Send a (possibly multi-bubble) clone reply as separate messages, one per bubble, the
  /// way a real person sends a burst — `respond()` joins bubbles with newlines, and sending
  /// that as one message would land as a single wall of text. A short human-ish pause
  /// separates bubbles. Throws on the first failed bubble (earlier bubbles stay sent).
  ///
  /// `humanizedTyping` (autonomous sends) replaces the fixed pause with a per-bubble
  /// "typing" delay scaled to the bubble's length, refreshing a live typing indicator on
  /// platforms that support one (WhatsApp presence, Telegram chat action).
  func sendBubbles(
    contactId: String, displayName: String, text: String, mode: SendMode,
    humanizedTyping: Bool = false
  ) async throws {
    let bubbles = AICloneReplyPresentation.bubbles(from: text)
    guard !bubbles.isEmpty else { throw IMessageSendError.emptyText }
    for (index, bubble) in bubbles.enumerated() {
      if humanizedTyping {
        await typeLikeAHuman(
          contactId: contactId, displayName: displayName,
          seconds: AICloneHumanizer.typingDelay(forBubble: bubble))
      } else if index > 0 {
        try? await Task.sleep(nanoseconds: UInt64.random(in: 600_000_000...1_400_000_000))
      }
      try await send(contactId: contactId, displayName: displayName, text: bubble, mode: mode)
    }
    if humanizedTyping { await clearTypingIndicator(contactId: contactId, displayName: displayName) }
  }

  // MARK: - Human-pacing helpers (autonomous sends only)

  /// Leave a read receipt where the platform exposes one (WhatsApp "blue ticks"). iMessage
  /// and Telegram have no usable read API here — the pacing alone carries the illusion.
  private func markIncomingRead(contactId: String, displayName: String) async {
    guard AIClonePlatform.of(contactId: contactId) == .whatsapp else { return }
    guard let target = try? await whatsAppSendTarget(contactId: contactId, displayName: displayName)
    else { return }
    await WhatsAppSendService.shared.markRead(to: target)
  }

  /// Hold a "typing…" indicator for `seconds`, re-firing it every few seconds because both
  /// WhatsApp presence and Telegram chat actions auto-expire. Best-effort and non-throwing.
  private func typeLikeAHuman(contactId: String, displayName: String, seconds: TimeInterval) async {
    var remaining = seconds
    while remaining > 0 {
      await showTypingIndicator(contactId: contactId, displayName: displayName)
      let chunk = min(remaining, 4.0)
      try? await Task.sleep(nanoseconds: UInt64(chunk * 1_000_000_000))
      remaining -= chunk
    }
  }

  private func showTypingIndicator(contactId: String, displayName: String) async {
    switch AIClonePlatform.of(contactId: contactId) {
    case .imessage:
      break  // No public typing-indicator API for iMessage.
    case .telegram:
      if let chatId = Int64(String(contactId.dropFirst("telegram:".count))) {
        await TelegramSendService.shared.setTyping(chatId: chatId)
      }
    case .whatsapp:
      if let target = try? await whatsAppSendTarget(contactId: contactId, displayName: displayName) {
        await WhatsAppSendService.shared.setComposing(to: target, true)
      }
    }
  }

  /// WhatsApp keeps showing "typing…" briefly after the last send; explicitly pause it.
  /// Telegram chat actions are cancelled server-side by the send itself.
  private func clearTypingIndicator(contactId: String, displayName: String) async {
    guard AIClonePlatform.of(contactId: contactId) == .whatsapp else { return }
    guard let target = try? await whatsAppSendTarget(contactId: contactId, displayName: displayName)
    else { return }
    await WhatsAppSendService.shared.setComposing(to: target, false)
  }

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
      let target = try await whatsAppSendTarget(contactId: contactId, displayName: displayName)
      try await WhatsAppSendService.shared.send(to: target, text: trimmed)
    }

    recordSent(
      AICloneSentLogEntry(
        contactId: contactId, contactDisplayName: displayName, text: trimmed, mode: mode,
        timestamp: Date()))
  }

  /// Resolve a WhatsApp contact id to something the sidecar can address. Contact ids are
  /// either `whatsapp:<phone/JID>` (live contacts — addressable as-is) or
  /// `whatsapp:<export-filename>` (imported training chats — resolved via the learned phone
  /// mapping, then the linked account's contact list by display name).
  private func whatsAppSendTarget(contactId: String, displayName: String) async throws -> String {
    let raw = String(contactId.dropFirst("whatsapp:".count))
    if let direct = Self.whatsAppDirectTarget(rawId: raw) { return direct }
    if let learned = whatsAppPhoneByContactId[contactId] { return learned }
    if let resolved = await WhatsAppSendService.shared.resolvePhone(forName: displayName) {
      recordWhatsAppPhone(resolved, for: contactId)
      return resolved
    }
    throw WhatsAppSendError.contactNotResolvable(displayName)
  }

  /// A raw WhatsApp contact-id suffix that is directly addressable: a full JID, or a
  /// phone-number-shaped string (digits with optional +, spaces, dashes, parens). Returns
  /// the normalized target, or nil for non-addressable ids (imported export filenames).
  /// Pure for unit testing.
  nonisolated static func whatsAppDirectTarget(rawId: String) -> String? {
    let raw = rawId.trimmingCharacters(in: .whitespacesAndNewlines)
    if raw.hasSuffix("@s.whatsapp.net") { return raw }
    let phoneLike = !raw.isEmpty && raw.allSatisfy { $0.isNumber || "+-() .".contains($0) }
    guard phoneLike else { return nil }
    let digits = raw.filter(\.isNumber)
    return digits.count >= 5 ? digits : nil
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
