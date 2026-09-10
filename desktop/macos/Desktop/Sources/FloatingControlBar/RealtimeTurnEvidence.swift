import Foundation
import VoiceTurnDomain

/// Bounded, process-local ownership for evidence extracted during one PTT turn.
/// The kernel journal remains durable truth; this object only keeps a late OCR
/// result attached to the exact owner/turn/continuity identity until that
/// journal write's existing persistence fence completes.
@MainActor
final class RealtimeTurnEvidenceLedger {
  enum CaptureState: Equatable, Sendable {
    case pending
    case unavailable
    case complete
    case partial
  }

  struct Key: Hashable, Sendable {
    let ownerID: String
    let turnID: VoiceTurnID
    let continuityKey: String
  }

  struct Entry: Equatable, Sendable {
    let key: Key
    let surface: AgentSurfaceReference?
    /// Frozen at admission. `screenEvidence` is shared controller state and
    /// may already describe turn B when a late OCR callback for turn A runs.
    let screenDescriptor: RealtimeScreenEvidenceDescriptor?
    var state: CaptureState
    var evidence: ConversationEvidence?
    var journalUserTurnID: String?
    var evidencePersisted: Bool
    var persistenceFailed: Bool
    var terminal: Bool
    var allowsLateEvidence: Bool
    var persistenceFenced: Bool
    let createdAt: Date
  }

  static let maxEntries = 8

  private var entries: [Key: Entry] = [:]

  var count: Int { entries.count }

  #if DEBUG
    /// Hermetic observation seam for native-evidence attach tests. Production
    /// attaches through `FloatingControlBarManager`; tests inject this to count
    /// and order writes without a live kernel journal.
    var testingAttachRealtimeUserEvidence:
      (@MainActor (AgentSurfaceReference, String, String, ConversationEvidence) async -> Bool)?
  #endif

  func begin(
    ownerID: String,
    turnID: VoiceTurnID,
    continuityKey: String,
    surface: AgentSurfaceReference? = nil,
    screenDescriptor: RealtimeScreenEvidenceDescriptor? = nil,
    initialEvidence: ConversationEvidence? = nil,
    createdAt: Date = Date()
  ) -> Key? {
    let owner = ownerID.trimmingCharacters(in: .whitespacesAndNewlines)
    let continuity = continuityKey.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !owner.isEmpty, !continuity.isEmpty else { return nil }
    let key = Key(ownerID: owner, turnID: turnID, continuityKey: continuity)
    if entries[key] == nil {
      pruneIfNeeded()
      guard entries.count < Self.maxEntries else { return nil }
      entries[key] = Entry(
        key: key,
        surface: surface,
        screenDescriptor: screenDescriptor,
        state: .pending,
        evidence: initialEvidence,
        journalUserTurnID: nil,
        evidencePersisted: false,
        persistenceFailed: false,
        terminal: false,
        allowsLateEvidence: false,
        persistenceFenced: false,
        createdAt: createdAt)
    }
    return key
  }

  @discardableResult
  func attachJournalUserTurn(
    key: Key,
    turnID: String
  ) -> Bool {
    guard var entry = entries[key], !turnID.isEmpty else { return false }
    // A cancelled or owner-stale callback cannot invent a producing row after
    // this reservation has already been told no late write is licensed.
    guard !entry.terminal || entry.allowsLateEvidence || entry.journalUserTurnID != nil else {
      return false
    }
    entry.journalUserTurnID = turnID
    entries[key] = entry
    return true
  }

  @discardableResult
  func markEvidencePersisted(key: Key) -> Bool {
    guard var entry = entries[key] else { return false }
    // A pending descriptor is already journal-visible, but the source has not
    // produced a terminal result yet. Keep the obligation alive so the later
    // same-ID replacement can still be appended.
    guard entry.state != .pending else { return false }
    entry.evidencePersisted = true
    entry.persistenceFailed = false
    entries[key] = entry
    retireIfFenced(key: key)
    return true
  }

  /// Records a terminal write failure without pretending the evidence was
  /// durably saved. The obligation remains fenced until the existing journal
  /// lifecycle completes, then it is retired so a broken append cannot fill
  /// the bounded ledger forever.
  @discardableResult
  func markPersistenceFailed(key: Key) -> Bool {
    guard var entry = entries[key] else { return false }
    entry.persistenceFailed = true
    entries[key] = entry
    retireIfFenced(key: key)
    return true
  }

  /// Accept a producer result only for an existing exact key. Callers still
  /// perform the current-owner check before invoking this method; key equality
  /// prevents a stale callback from becoming evidence for turn B.
  @discardableResult
  func resolve(
    key: Key,
    evidence: ConversationEvidence?,
    state: CaptureState
  ) -> Bool {
    guard var entry = entries[key] else { return false }
    // A cancelled turn with no admitted journal row has nowhere safe to attach
    // late OCR. Reject it explicitly so an old callback cannot create a
    // misleading stable-ID update after the user has moved on.
    guard !entry.terminal || entry.journalUserTurnID != nil || entry.allowsLateEvidence else {
      retireIfFenced(key: key)
      return false
    }
    entry.state = state
    entry.evidence = evidence
    entry.evidencePersisted = false
    entry.persistenceFailed = false
    entries[key] = entry
    return true
  }

  func entry(for key: Key) -> Entry? {
    entries[key]
  }

  func key(turnID: VoiceTurnID, continuityKey: String) -> Key? {
    entries.keys.first { $0.turnID == turnID && $0.continuityKey == continuityKey }
  }

  func evidence(for key: Key) -> ConversationEvidence? {
    entries[key]?.evidence
  }

  @discardableResult
  func markTerminal(key: Key, allowsLateEvidence: Bool = false) -> Bool {
    guard var entry = entries[key] else { return false }
    entry.terminal = true
    entry.allowsLateEvidence = allowsLateEvidence
    entries[key] = entry
    retireIfFenced(key: key)
    return true
  }

  /// The native terminal boundary for a reserved source. In-flight writes and
  /// admitted producing rows keep the obligation until their persistence fence;
  /// every other terminal fences immediately so cancelled/too-short/non-hub
  /// reservations cannot fill the bounded ledger.
  @discardableResult
  func finishTerminal(key: Key, allowsLateEvidence: Bool) -> Bool {
    guard markTerminal(key: key, allowsLateEvidence: allowsLateEvidence) else { return false }
    guard
      RealtimeTurnEvidenceTerminalPolicy.shouldFenceAtTerminal(
        allowsLateEvidence: allowsLateEvidence)
    else { return true }
    return markPersistenceFence(key: key)
  }

  /// Called after the existing `RealtimeTurnPersistenceLedger` receipt is
  /// consumed. Evidence survives ordinary reducer cleanup until this point.
  @discardableResult
  func markPersistenceFence(key: Key) -> Bool {
    guard var entry = entries[key] else { return false }
    entry.persistenceFenced = true
    entries[key] = entry
    retireIfFenced(key: key)
    return true
  }

  /// Owner transitions revoke the key immediately. This is the only path that
  /// may discard a pending entry before its persistence fence; a callback from
  /// owner A then has no ledger key capable of touching owner B.
  @discardableResult
  func revoke(ownerID: String) -> Int {
    let keys = entries.keys.filter { $0.ownerID == ownerID }
    for key in keys { entries.removeValue(forKey: key) }
    return keys.count
  }

  /// Owner transitions are a global fence: while the previous owner is being
  /// quiesced, no evidence obligation can safely survive into the replacement
  /// owner. This is intentionally separate from bounded pruning so pending
  /// entries cannot consume all slots after repeated sign-in transitions.
  @discardableResult
  func revokeAll() -> Int {
    let removed = entries.count
    entries.removeAll()
    return removed
  }

  private func retireIfFenced(key: Key) {
    guard let entry = entries[key], entry.persistenceFenced else { return }
    // A pending capture is still allowed to finish after the journal fence and
    // will be removed by resolve. Completed/unavailable results can retire now.
    let terminalWithoutRow =
      entry.terminal
      && !entry.allowsLateEvidence
      && entry.journalUserTurnID == nil
    guard entry.state != .pending || terminalWithoutRow,
      entry.evidencePersisted || entry.persistenceFailed || terminalWithoutRow
    else { return }
    entries.removeValue(forKey: key)
  }

  private func pruneIfNeeded() {
    guard entries.count >= Self.maxEntries else { return }
    let removable = entries.values
      .filter { $0.persistenceFenced && $0.state != .pending }
      .sorted { $0.createdAt < $1.createdAt }
    guard let oldest = removable.first else { return }
    entries.removeValue(forKey: oldest.key)
  }
}

/// Native evidence retirement at a voice-turn terminal. Late OCR is only kept
/// when a journal write is still allowed to finish; otherwise the reservation
/// must release its ledger slot at this boundary.
enum RealtimeTurnEvidenceTerminalPolicy {
  /// Success alone is not a license. A non-hub turn with no producing row and
  /// no in-flight write must release its slot rather than leak until prune.
  static func allowsLateEvidence(
    persistPending: Bool,
    producingRowAdmitted: Bool
  ) -> Bool {
    persistPending || producingRowAdmitted
  }

  static func shouldFenceAtTerminal(allowsLateEvidence: Bool) -> Bool {
    !allowsLateEvidence
  }

  /// Apply the native terminal policy to an existing reservation using the
  /// persistence ledgers `voiceTurnDidTerminate` already consults.
  @discardableResult
  @MainActor
  static func finish(
    ledger: RealtimeTurnEvidenceLedger,
    key: RealtimeTurnEvidenceLedger.Key,
    persistPending: Bool
  ) -> Bool {
    let producingRowAdmitted = ledger.entry(for: key)?.journalUserTurnID != nil
    return ledger.finishTerminal(
      key: key,
      allowsLateEvidence: allowsLateEvidence(
        persistPending: persistPending,
        producingRowAdmitted: producingRowAdmitted))
  }

  /// The allowed write settled as a rejection: drop the reservation so a later
  /// cancelled callback cannot attach a row that was never admitted.
  @discardableResult
  @MainActor
  static func retireRejectedWrite(
    ledger: RealtimeTurnEvidenceLedger,
    key: RealtimeTurnEvidenceLedger.Key
  ) -> Bool {
    ledger.finishTerminal(key: key, allowsLateEvidence: false)
  }

  /// Journal-receipt terminal for a reserved native source. An accepted write
  /// only fences so a still-pending capture can finish. A rejected or missing
  /// receipt retires unlicensed late capture; an already-admitted producing
  /// row is preserved by `retireRejectedWrite`.
  @discardableResult
  @MainActor
  static func applyJournalReceipt(
    ledger: RealtimeTurnEvidenceLedger,
    key: RealtimeTurnEvidenceLedger.Key,
    accepted: Bool
  ) -> Bool {
    if accepted {
      return ledger.markPersistenceFence(key: key)
    }
    return retireRejectedWrite(ledger: ledger, key: key)
  }
}
