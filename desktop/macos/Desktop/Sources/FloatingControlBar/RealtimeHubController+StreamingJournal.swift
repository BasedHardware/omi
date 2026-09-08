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

    let projection = RealtimeStreamingJournalProjection(
      ownerID: ownerID, continuityKey: turnIdempotencyKey,
      admissionSurface: FloatingControlBarManager.shared.mainChatSurfaceReference(),
      modelsUsed: [sessionProvider?.modelID].compactMap { $0 },
      screenContext: screenContextByContinuityKey[turnIdempotencyKey])
    guard
      streamingJournalWriteLedger.begin(
        projection: projection,
        record: { projection in
          await FloatingControlBarManager.shared.recordStreamingRealtimeExchange(
            projection: projection, userText: userText)
        })
    else { return }
    scheduleStreamingRealtimeProjectionFlush(continuityKey: projection.continuityKey)
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
