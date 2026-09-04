import Foundation

/// Rebuilds hub decisions from kernel-owned continuity facts after relaunch.
/// Hub maps die with the process; stable turn IDs already in the kernel journal
/// (or its typed voice-context snapshot) are the durable ownership signal.
enum RealtimeHubContinuityRestore {
  static func kernelOwnsExchange(
    continuityKey: String,
    kernelTurnIDs: Set<String>
  ) -> Bool {
    guard !continuityKey.isEmpty else { return false }
    return !kernelTurnIDs.isDisjoint(
      with: KernelTurnProjection.stableTurnIDs(continuityKey: continuityKey))
  }
}

/// Selects the sole journal owner after realtime `spawn_agent` admission. The
/// spawn RPC atomically records the canonical exchange; provider turn_done may
/// refresh that projection, but it must never submit a second mutation for the
/// same continuity identity. After relaunch, `kernelOwnsExchange` restores that
/// same authority when hub-local spawn-receipt maps are empty.
@MainActor
enum RealtimeTurnJournalAuthority {
  static func persist(
    turnOwnerID: String,
    acceptedSpawnOwnerID: String?,
    kernelOwnsExchange: Bool = false,
    refreshAcceptedSpawn: @escaping @MainActor () async -> Bool,
    recordProviderExchange: @escaping @MainActor () async -> Bool
  ) async -> Bool {
    if acceptedSpawnOwnerID == turnOwnerID || kernelOwnsExchange {
      return await refreshAcceptedSpawn()
    }
    return await recordProviderExchange()
  }
}

/// A single kernel write is an obligation of one stable continuity key.  The
/// controller may have several turns in flight while a barge-in replaces a
/// physical session, so completion of B must never supersede A's receipt.
struct RealtimeTurnPersistenceReceipt: Equatable {
  let continuityKey: String
  let accepted: Bool
}

/// The two stable journal IDs for an in-flight realtime turn. This is deliberately
/// only an in-memory write coordinator: the kernel journal remains the transcript
/// authority, including after process restart.
struct RealtimeStreamingJournalProjection: Equatable {
  let ownerID: String
  let continuityKey: String
  let userTurnID: String
  let assistantTurnID: String
  /// Pinned at admission so a mid-stream chat switch cannot redirect deltas
  /// or finalization to a different conversation surface.
  let admissionSurface: AgentSurfaceReference
  /// Concrete model id of the realtime session answering this turn (e.g.
  /// "gemini-3.1-flash-live-preview"), pinned at admission for the journaled
  /// exchange's Response Context attribution.
  let modelsUsed: [String]
  /// Accepted screen observation for this turn, journaled on the user row (see MessageMetadata).
  let screenContext: String?

  init(
    ownerID: String, continuityKey: String, admissionSurface: AgentSurfaceReference,
    modelsUsed: [String] = [], screenContext: String? = nil
  ) {
    self.ownerID = ownerID
    self.continuityKey = continuityKey
    self.admissionSurface = admissionSurface
    self.modelsUsed = modelsUsed
    self.screenContext = screenContext
    userTurnID = KernelTurnProjection.stableTurnID(continuityKey: continuityKey, role: "user")
    assistantTurnID = KernelTurnProjection.stableTurnID(continuityKey: continuityKey, role: "assistant")
  }

  func userMessage(text: String) -> ChatMessage {
    var message = ChatMessage(
      id: userTurnID,
      clientTurnId: continuityKey,
      text: text,
      sender: .user
    )
    if let screenContext, !screenContext.isEmpty {
      message.metadata = MessageMetadata(screenContext: screenContext)
    }
    return message
  }

  func assistantMessage(text: String, isStreaming: Bool) -> ChatMessage {
    var message = ChatMessage(
      id: assistantTurnID,
      clientTurnId: continuityKey,
      text: text,
      sender: .ai,
      isStreaming: isStreaming
    )
    if !modelsUsed.isEmpty {
      message.metadata = MessageMetadata(adapterId: "realtime", modelsUsed: modelsUsed)
    }
    return message
  }
}

/// Serializes journal writes for one or more realtime turns without retaining
/// transcript content locally. A barge-in can finalize turn A while turn B is
/// already recording, so each continuity key owns an independent write tail.
@MainActor
final class RealtimeStreamingJournalWriteLedger {
  enum FinalizationResult: Equatable {
    case absent
    case recordRejected
    case completed(Bool)
  }

  private struct Entry {
    let id: UUID
    let projection: RealtimeStreamingJournalProjection
    let recordTask: Task<Bool, Never>
    var tail: Task<Bool, Never>
  }

  private var entries: [String: Entry] = [:]
  private(set) var generation: UInt64 = 0

  var hasActiveProjections: Bool {
    !entries.isEmpty
  }

  func contains(continuityKey: String) -> Bool {
    entries[continuityKey] != nil
  }

  @discardableResult
  func begin(
    projection: RealtimeStreamingJournalProjection,
    record: @escaping @MainActor (RealtimeStreamingJournalProjection) async -> Bool
  ) -> Bool {
    guard entries[projection.continuityKey] == nil else { return false }
    generation &+= 1
    let recordTask = Task { @MainActor in
      await record(projection)
    }
    entries[projection.continuityKey] = Entry(
      id: UUID(),
      projection: projection,
      recordTask: recordTask,
      tail: recordTask
    )
    return true
  }

  func enqueueUpdate(
    continuityKey: String,
    update: @escaping @MainActor (RealtimeStreamingJournalProjection) async -> Bool
  ) {
    guard var entry = entries[continuityKey] else { return }
    let previous = entry.tail
    let recordTask = entry.recordTask
    let projection = entry.projection
    let task = Task { @MainActor in
      guard await recordTask.value else { return false }
      _ = await previous.value
      return await update(projection)
    }
    entry.tail = task
    entries[continuityKey] = entry
  }

  func finalize(
    continuityKey: String,
    complete: @escaping @MainActor (RealtimeStreamingJournalProjection) async -> Bool
  ) async -> FinalizationResult {
    guard var entry = entries[continuityKey] else { return .absent }
    let recordTask = entry.recordTask
    let previous = entry.tail
    let projection = entry.projection
    let entryID = entry.id
    let task = Task { @MainActor in
      guard await recordTask.value else { return false }
      _ = await previous.value
      return await complete(projection)
    }
    entry.tail = task
    entries[continuityKey] = entry

    let recorded = await recordTask.value
    let completed = await task.value
    if entries[continuityKey]?.id == entryID {
      entries.removeValue(forKey: continuityKey)
    }
    generation &+= 1
    return recorded ? .completed(completed) : .recordRejected
  }

  func awaitPendingWrites() async {
    let tails = entries.values.map(\.tail)
    for task in tails {
      _ = await task.value
    }
  }

  func cancelAll() {
    let tasks = entries.values.flatMap { [$0.recordTask, $0.tail] }
    entries.removeAll()
    generation &+= 1
    for task in tasks { task.cancel() }
  }

  /// Cancels a single continuity key's projection so a later canonical receipt
  /// (e.g. an accepted spawn_agent) can take over without competing writes.
  func cancel(continuityKey: String) {
    guard let entry = entries.removeValue(forKey: continuityKey) else { return }
    generation &+= 1
    entry.recordTask.cancel()
    entry.tail.cancel()
  }
}

@MainActor
final class RealtimeTurnPersistenceLedger {
  private struct Obligation {
    let id: UUID
    let task: Task<Bool, Never>
    var retainingReceipt: Bool
  }

  private var obligations: [String: Obligation] = [:]
  private var receipts: [String: RealtimeTurnPersistenceReceipt] = [:]
  private(set) var generation: UInt64 = 0

  var pendingContinuityKeys: Set<String> {
    Set(obligations.keys)
  }

  /// Idempotent and widen-never-narrow: a continuity key already in flight
  /// returns its existing task unchanged rather than starting a second kernel
  /// write. But retention is a live property of that obligation, not a value
  /// frozen into the first caller's closure — a later call that additionally
  /// needs a receipt (`retainingReceipt: true`) widens the same obligation in
  /// place, and the completion below re-reads the current flag instead of the
  /// value captured at creation, so the widening call is never lost to the
  /// first caller's capture.
  @discardableResult
  func enqueue(
    continuityKey: String,
    retainingReceipt: Bool,
    _ operation: @escaping @MainActor () async -> Bool
  ) -> Task<Bool, Never> {
    if var existing = obligations[continuityKey] {
      if retainingReceipt, !existing.retainingReceipt {
        existing.retainingReceipt = true
        obligations[continuityKey] = existing
      }
      return existing.task
    }

    receipts.removeValue(forKey: continuityKey)
    generation &+= 1
    let obligationID = UUID()
    let task = Task { @MainActor [weak self] in
      let accepted = await operation()
      guard let self,
        self.obligations[continuityKey]?.id == obligationID
      else {
        // The kernel result remains truthful to this caller even if an owner
        // transition or a newer obligation has retired this local ledger entry.
        return accepted
      }
      // Re-read retention live rather than the value this closure captured at
      // creation, so a widening `enqueue(retainingReceipt: true)` observed
      // after this task started still gets its receipt.
      let shouldRetain = self.obligations[continuityKey]?.retainingReceipt ?? retainingReceipt
      self.obligations.removeValue(forKey: continuityKey)
      // An external authority (e.g. an atomically-accepted spawn) may have
      // already recorded this key's receipt while this obligation was still
      // pending via `recordAcceptedReceipt`. That acceptance stays
      // authoritative — this obligation's own completion must never overwrite it.
      if shouldRetain, self.receipts[continuityKey] == nil {
        self.receipts[continuityKey] = RealtimeTurnPersistenceReceipt(
          continuityKey: continuityKey,
          accepted: accepted)
      }
      return accepted
    }
    obligations[continuityKey] = Obligation(
      id: obligationID, task: task, retainingReceipt: retainingReceipt)
    return task
  }

  /// Awaits the exact obligation for this logical turn and consumes only its
  /// receipt.  A concurrent B write cannot alter A's outcome.
  func consumeReceipt(for continuityKey: String) async -> RealtimeTurnPersistenceReceipt? {
    if let obligation = obligations[continuityKey] {
      _ = await obligation.task.value
    }
    return receipts.removeValue(forKey: continuityKey)
  }

  func receipt(for continuityKey: String) -> RealtimeTurnPersistenceReceipt? {
    receipts[continuityKey]
  }

  /// Use only for a kernel mutation that was atomically accepted by a different
  /// authority (currently `spawn_agent`).  It gives that exact continuity key a
  /// finalization receipt without inventing a second provider-exchange write.
  /// Idempotent: recording the same key's acceptance twice (e.g. a duplicate
  /// external acceptance callback) writes the same `accepted: true` payload
  /// both times, so it is safe to call more than once without an assertion.
  func recordAcceptedReceipt(for continuityKey: String) {
    receipts[continuityKey] = RealtimeTurnPersistenceReceipt(
      continuityKey: continuityKey,
      accepted: true)
  }

  /// Repeatedly observes pending obligations because a new turn may enqueue a
  /// write while an earlier write is suspended.  It never serializes unrelated
  /// continuity keys.
  func awaitPendingObligations() async {
    while !Task.isCancelled {
      let pending = obligations.values.map(\.task)
      guard !pending.isEmpty else { return }
      for task in pending {
        _ = await task.value
      }
    }
  }

  /// Chains one follow-up write after the in-flight obligation for the same
  /// continuity key, taking over that key's obligation slot so
  /// `awaitPendingObligations` — the next voice turn's context fence — still
  /// observes the follow-up before the journal settles. The follow-up runs
  /// only after the original write's kernel result is known; a plain `enqueue`
  /// would drop it entirely while the original is still in flight.
  ///
  /// When the original obligation already completed before this call, its
  /// retained receipt (if any) is final and must survive the follow-up: a
  /// later `consumeReceipt` still reports the original write's acceptance.
  /// The follow-up therefore runs as a fresh non-retaining obligation that
  /// never touches the receipt slot — unlike `enqueue`, which clears a key's
  /// receipt when it starts a superseding write.
  @discardableResult
  func enqueueFollowUp(
    continuityKey: String,
    _ followUp: @escaping @MainActor () async -> Bool
  ) -> Task<Bool, Never> {
    guard let existing = obligations[continuityKey] else {
      generation &+= 1
      let followUpID = UUID()
      let task = Task { @MainActor [weak self] in
        let accepted = await followUp()
        guard let self, self.obligations[continuityKey]?.id == followUpID else {
          return accepted
        }
        self.obligations.removeValue(forKey: continuityKey)
        return accepted
      }
      obligations[continuityKey] = Obligation(
        id: followUpID, task: task, retainingReceipt: false)
      return task
    }
    let previous = existing.task
    let retention = existing.retainingReceipt
    let followUpID = UUID()
    generation &+= 1
    let task = Task { @MainActor [weak self] in
      let originalAccepted = await previous.value
      guard let self, self.obligations[continuityKey]?.id == followUpID else {
        return originalAccepted
      }
      // The original write's epilogue no longer owns this slot, so its receipt
      // semantics survive here: retention still reflects the original write's
      // kernel result, never the follow-up's revision of an accepted row.
      if retention, self.receipts[continuityKey] == nil {
        self.receipts[continuityKey] = RealtimeTurnPersistenceReceipt(
          continuityKey: continuityKey,
          accepted: originalAccepted)
      }
      let accepted = await followUp()
      if self.obligations[continuityKey]?.id == followUpID {
        self.obligations.removeValue(forKey: continuityKey)
      }
      return accepted
    }
    obligations[continuityKey] = Obligation(
      id: followUpID, task: task, retainingReceipt: retention)
    return task
  }

  /// Owner replacement revokes every local waiter.  An ignored cancellation can
  /// still complete its kernel RPC, but its old obligation is forbidden from
  /// removing or writing over any newer key's state.
  func cancelAll() {
    let pending = obligations.values.map(\.task)
    obligations.removeAll()
    receipts.removeAll()
    generation &+= 1
    for task in pending { task.cancel() }
  }
}

struct InterruptedTurnPayload: Equatable {
  let ownerID: String
  let userText: String
  let assistantText: String
  let idempotencyKey: String
  /// A successful `spawn_agent` call has already committed this turn's exchange
  /// to the kernel. Capture that authority before a barge-in clears transport state.
  let acceptedSpawnOwnerID: String?
  /// Whether the turn's full-answer playback had drained by capture time. A
  /// barge-in after a fully spoken reply must journal that reply as delivered,
  /// not as a cut-off failure the model later tries to re-deliver.
  let answerDelivered: Bool

  init(
    ownerID: String,
    userText: String,
    assistantText: String,
    idempotencyKey: String,
    acceptedSpawnOwnerID: String? = nil,
    answerDelivered: Bool = false
  ) {
    self.ownerID = ownerID
    self.userText = userText
    self.assistantText = assistantText
    self.idempotencyKey = idempotencyKey
    self.acceptedSpawnOwnerID = acceptedSpawnOwnerID
    self.answerDelivered = answerDelivered
  }

  /// User-visible chat text for a PTT-barged reply: keep streamed partial text only.
  static func visibleAssistantText(partialAssistantText: String) -> String {
    partialAssistantText.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}

/// The assistant row a voice turn's funnel sealed `.completed` at
/// provider-response-finish, before the reducer's playback fence resolved.
/// Consumed by the reducer's terminal: when the answer never reached the user,
/// the sealed row is revised through the payload-free terminal-revision update
/// (`VoiceJournalSealedRowRevisionPolicy`) — its content and canonical
/// metadata stay exactly as sealed. Journal-write bookkeeping only — the
/// reducer remains the lifecycle owner (INV-VOICE-1), and the kernel journal
/// stays the one transcript authority (INV-CHAT-1).
struct SealedCompletedVoiceJournalRow {
  let ownerID: String
  let surface: AgentSurfaceReference
}

/// Resolves and records the visible portion of a provider-failed turn before
/// terminal cleanup clears its transcript. The provider callback invokes this
/// policy before sending the terminal reducer event, which makes the ordering
/// deterministic and directly testable without a live socket.
enum RealtimeProviderFailureContinuity {
  /// Installs the journal fence before provider teardown can terminalize the
  /// turn. Transcript resolution may suspend, but the next context refresh can
  /// already observe and await this exact continuity obligation.
  @MainActor
  static func registerCapturedTurn(
    in ledger: RealtimeTurnPersistenceLedger,
    continuityKey: String,
    capturedTurnTask: Task<InterruptedTurnPayload?, Never>,
    record: @escaping @MainActor (InterruptedTurnPayload) async -> Bool
  ) -> Task<Bool, Never> {
    ledger.enqueue(continuityKey: continuityKey, retainingReceipt: true) {
      await persistCapturedTurn(
        resolve: { await capturedTurnTask.value },
        record: record)
    }
  }

  @MainActor static func persistCapturedTurn(
    resolve: () async -> InterruptedTurnPayload?,
    record: (InterruptedTurnPayload) async -> Bool
  ) async -> Bool {
    guard let interruptedTurn = await resolve() else { return true }
    return await record(interruptedTurn)
  }
}

struct RealtimeHubTranscriptResolution: Equatable {
  let userText: String
  let providerLanguage: String?
  let localTranscript: String?
  let localLanguage: String?
  let usedLocalTranscript: Bool
}

enum RealtimeHubTranscriptPolicy {
  static func resolve(
    providerText: String,
    preferredLanguages: [String],
    localTranscript: String?,
    localLanguage: String?
  ) -> RealtimeHubTranscriptResolution {
    let provider = providerText.trimmingCharacters(in: .whitespacesAndNewlines)
    let local = localTranscript?.trimmingCharacters(in: .whitespacesAndNewlines)
    let providerLanguage =
      provider.isEmpty
      ? nil : PTTLanguageIdentifier.dominantLanguage(of: provider, hints: [])
    let providerMismatches =
      !provider.isEmpty && !preferredLanguages.isEmpty
      && (providerLanguage.map { !preferredLanguages.contains($0) } ?? false)
    let localMatchesPreference =
      preferredLanguages.isEmpty
      || localLanguage.map(preferredLanguages.contains) == true
    let shouldUseLocal =
      (provider.isEmpty || providerMismatches)
      && local?.isEmpty == false && localMatchesPreference

    return RealtimeHubTranscriptResolution(
      userText: shouldUseLocal ? local! : provider,
      providerLanguage: providerLanguage,
      localTranscript: local,
      localLanguage: localLanguage,
      usedLocalTranscript: shouldUseLocal)
  }
}
