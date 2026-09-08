import Foundation
import VoiceTurnDomain

extension RealtimeHubController {
  struct AcceptedSpawnJournalReceipt {
    let ownerID: String
    let receipt: RealtimeSpawnJournalReceipt
  }

  @discardableResult
  func enqueueTurnPersistence(
    idempotencyKey: String,
    retainingReceipt: Bool = false,
    _ operation: @escaping @MainActor () async -> Bool
  ) -> Task<Bool, Never> {
    turnPersistenceLedger.enqueue(
      continuityKey: idempotencyKey,
      retainingReceipt: retainingReceipt,
      operation)
  }

  /// Starts the shared journal stream only after both sides have meaningful text.
  func beginStreamingRealtimeProjectionIfNeeded() {
    let userText = turnTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    let responseText = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !turnIdempotencyKey.isEmpty, !userText.isEmpty, !responseText.isEmpty,
      acceptedSpawnJournalReceiptByContinuityKey[turnIdempotencyKey] == nil,
      VoiceTurnCoordinator.shared.activeTurn?.pendingToolCallIDs.isEmpty == true,
      let ownerID = VoiceTurnCoordinator.shared.activeTurn?.ownerID
    else { return }

    let nativeEvidence: [ConversationEvidence] = {
      guard let turnID = Self.turnID(forVoiceContinuityKey: turnIdempotencyKey),
        let evidence = turnEvidenceLedger.evidence(
          for: RealtimeTurnEvidenceLedger.Key(
            ownerID: ownerID, turnID: turnID, continuityKey: turnIdempotencyKey))
      else { return [] }
      return [evidence]
    }()
    let projection = RealtimeStreamingJournalProjection(
      ownerID: ownerID, continuityKey: turnIdempotencyKey,
      admissionSurface: FloatingControlBarManager.shared.mainChatSurfaceReference(),
      modelsUsed: [sessionProvider?.modelID].compactMap { $0 },
      screenContext: screenContextByContinuityKey[turnIdempotencyKey],
      evidence: nativeEvidence)
    guard
      streamingJournalWriteLedger.begin(
        projection: projection,
        record: { [weak self] projection in
          let accepted = await FloatingControlBarManager.shared.recordStreamingRealtimeExchange(
            projection: projection, userText: userText)
          if accepted, !projection.evidence.isEmpty,
            let self,
            let turnID = Self.turnID(forVoiceContinuityKey: projection.continuityKey)
          {
            let key = RealtimeTurnEvidenceLedger.Key(
              ownerID: projection.ownerID,
              turnID: turnID,
              continuityKey: projection.continuityKey)
            _ = self.turnEvidenceLedger.markEvidencePersisted(key: key)
          } else if !accepted, !projection.evidence.isEmpty,
            let self,
            let turnID = Self.turnID(forVoiceContinuityKey: projection.continuityKey)
          {
            let key = RealtimeTurnEvidenceLedger.Key(
              ownerID: projection.ownerID,
              turnID: turnID,
              continuityKey: projection.continuityKey)
            _ = self.turnEvidenceLedger.markPersistenceFailed(key: key)
          }
          return accepted
        })
    else { return }
    if let turnID = Self.turnID(forVoiceContinuityKey: turnIdempotencyKey) {
      let key = RealtimeTurnEvidenceLedger.Key(
        ownerID: ownerID, turnID: turnID, continuityKey: turnIdempotencyKey)
      _ = turnEvidenceLedger.attachJournalUserTurn(key: key, turnID: projection.userTurnID)
    }
    scheduleStreamingRealtimeProjectionFlush(continuityKey: projection.continuityKey)
  }

  /// Schedules a late native OCR result behind the same record/update tail as
  /// the user and assistant rows. If the first journal stage has not begun,
  /// the evidence is picked up by the projection constructor above instead.
  func enqueueNativeEvidenceUpdate(
    continuityKey: String,
    evidence: ConversationEvidence
  ) {
    guard streamingJournalWriteLedger.contains(continuityKey: continuityKey) else { return }
    streamingJournalWriteLedger.enqueueUpdate(continuityKey: continuityKey) { [weak self] projection in
      let accepted = await FloatingControlBarManager.shared.attachRealtimeUserEvidence(
        surface: projection.admissionSurface,
        ownerID: projection.ownerID,
        userTurnID: projection.userTurnID,
        evidence: evidence)
      if accepted, let self,
        let turnID = Self.turnID(forVoiceContinuityKey: projection.continuityKey)
      {
        let key = RealtimeTurnEvidenceLedger.Key(
          ownerID: projection.ownerID,
          turnID: turnID,
          continuityKey: projection.continuityKey)
        _ = self.turnEvidenceLedger.markEvidencePersisted(key: key)
      } else if !accepted, let self,
        let turnID = Self.turnID(forVoiceContinuityKey: projection.continuityKey)
      {
        let key = RealtimeTurnEvidenceLedger.Key(
          ownerID: projection.ownerID,
          turnID: turnID,
          continuityKey: projection.continuityKey)
        _ = self.turnEvidenceLedger.markPersistenceFailed(key: key)
      }
      return accepted
    }
  }

  /// Completes the evidence side of a non-streaming journal admission. A
  /// provider/spawn fallback can finish the user row while native OCR is still
  /// resolving; re-reading the bounded transient obligation here closes that
  /// race without creating another durable ledger.
  func persistNativeEvidenceAfterJournalAdmission(
    ownerID: String,
    continuityKey: String
  ) async -> Bool {
    guard RuntimeOwnerIdentity.currentOwnerId() == ownerID,
      let turnID = Self.turnID(forVoiceContinuityKey: continuityKey)
    else { return false }
    let key = RealtimeTurnEvidenceLedger.Key(
      ownerID: ownerID, turnID: turnID, continuityKey: continuityKey)
    guard let entry = turnEvidenceLedger.entry(for: key) else { return true }
    guard entry.state != .pending else { return true }
    if entry.evidencePersisted { return true }
    guard let evidence = entry.evidence else { return true }
    let userTurnID =
      entry.journalUserTurnID
      ?? KernelTurnProjection.stableTurnID(continuityKey: continuityKey, role: "user")
    let accepted = await FloatingControlBarManager.shared.attachRealtimeUserEvidence(
      surface: entry.surface ?? FloatingControlBarManager.shared.mainChatSurfaceReference(),
      ownerID: ownerID,
      userTurnID: userTurnID,
      evidence: evidence)
    if accepted {
      _ = turnEvidenceLedger.markEvidencePersisted(key: key)
      _ = turnEvidenceLedger.attachJournalUserTurn(key: key, turnID: userTurnID)
    } else {
      _ = turnEvidenceLedger.markPersistenceFailed(key: key)
    }
    return accepted
  }

  /// Coalesces transcript deltas so audio frames do not each create a revision.
  func scheduleStreamingRealtimeProjectionFlush(continuityKey: String) {
    guard streamingJournalFlushTasks[continuityKey] == nil else { return }
    streamingJournalFlushTasks[continuityKey] = Task { @MainActor [weak self] in
      try? await Task.sleep(nanoseconds: 75_000_000)
      guard let self else { return }
      self.streamingJournalFlushTasks.removeValue(forKey: continuityKey)
      guard self.turnIdempotencyKey == continuityKey else { return }
      self.enqueueStreamingRealtimeProjectionUpdate(
        continuityKey: continuityKey, assistantText: self.assistantText)
    }
  }

  func enqueueStreamingRealtimeProjectionUpdate(continuityKey: String, assistantText: String) {
    let text = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty else { return }
    streamingJournalWriteLedger.enqueueUpdate(continuityKey: continuityKey) { projection in
      await FloatingControlBarManager.shared.updateStreamingRealtimeAssistant(
        projection: projection, assistantText: text)
    }
  }

  /// Completes the same journal pair. Callers retain the final-only fallback
  /// when atomic admission was rejected.
  func finalizeStreamingRealtimeProjection(
    ownerID: String,
    userText: String,
    assistantText: String,
    continuityKey: String,
    assistantStatus: KernelJournalTurnStatus = .completed,
    terminalReason: String? = nil
  ) async -> RealtimeStreamingJournalWriteLedger.FinalizationResult {
    streamingJournalFlushTasks.removeValue(forKey: continuityKey)?.cancel()
    return await streamingJournalWriteLedger.finalize(continuityKey: continuityKey) { projection in
      guard projection.ownerID == ownerID else { return false }
      return await FloatingControlBarManager.shared.completeStreamingRealtimeExchange(
        projection: projection, userText: userText, assistantText: assistantText,
        assistantStatus: assistantStatus, terminalReason: terminalReason)
    }
  }

  func cancelStreamingJournalWrites() {
    let flushTasks = streamingJournalFlushTasks.values
    streamingJournalFlushTasks.removeAll()
    for task in flushTasks { task.cancel() }
    streamingJournalWriteLedger.cancelAll()
  }

  /// Cancels streaming writes for a single continuity key when a canonical
  /// spawn receipt takes over its journal exchange.
  func cancelStreamingJournalWrites(forContinuityKey continuityKey: String) {
    streamingJournalFlushTasks.removeValue(forKey: continuityKey)?.cancel()
    streamingJournalWriteLedger.cancel(continuityKey: continuityKey)
  }

  func awaitTurnPersistenceFence() async {
    while !Task.isCancelled {
      let persistenceGeneration = turnPersistenceLedger.generation
      let streamGeneration = streamingJournalWriteLedger.generation
      await turnPersistenceLedger.awaitPendingObligations()
      await streamingJournalWriteLedger.awaitPendingWrites()
      guard persistenceGeneration == turnPersistenceLedger.generation,
        streamGeneration == streamingJournalWriteLedger.generation
      else { continue }
      return
    }
  }
}
