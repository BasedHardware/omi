import Foundation

/// Orchestrates the full commitment lifecycle: extraction from finalized
/// conversations, follow-through detection on new conversations, and
/// overdue marking + notification scheduling.
actor CommitmentService {
  static let shared = CommitmentService()

  private init() {}

  /// Whether the user has opted into commitment analysis of their conversations.
  /// Defaults to false — users must explicitly enable in Settings.
  static var isAnalysisEnabled: Bool {
    UserDefaults.standard.bool(forKey: commitmentsAnalysisEnabledKey)
  }

  // MARK: - Extraction (after conversation is finalized)

  /// Extract commitments from a finalized conversation session.
  /// Skips if already processed (dedup via sourceSessionId or processed_sessions).
  /// Does nothing if the user has not opted into commitment analysis.
  func processSessionIfNeeded(sessionId: Int64) async {
    guard Self.isAnalysisEnabled else { return }

    let alreadyProcessed = await CommitmentStorage.shared.hasProcessedSession(sessionId)
    guard !alreadyProcessed else { return }

    do {
      let segments = try await TranscriptionStorage.shared.getSegments(sessionId: sessionId)
      guard !segments.isEmpty else {
        try? await CommitmentStorage.shared.markSessionProcessed(sessionId)
        return
      }

      let session = try await TranscriptionStorage.shared.getSession(id: sessionId)
      let conversationDate = session?.startedAt ?? Date()
      let conversationId = session?.backendId

      let transcript = segments.map { seg in
        (speaker: seg.speakerLabel ?? "Speaker \(seg.speaker)", text: seg.text)
      }

      let extracted = await CommitmentExtractor.shared.extract(
        from: transcript,
        conversationDate: conversationDate
      )

      for item in extracted {
        let record = CommitmentRecord(
          text: item.text,
          speaker: item.speaker,
          deadline: item.deadline,
          sourceSessionId: sessionId,
          sourceConversationId: conversationId,
          confidence: item.confidence
        )
        if let id = try? await CommitmentStorage.shared.insertCommitment(record) {
          var rec = record
          rec.id = id
          Task { @MainActor in
            CommitmentNotificationScheduler.shared.scheduleReminder(for: rec)
          }
          log("CommitmentService: Extracted commitment [\(id)]: \(item.text)")
        }
      }

      if !extracted.isEmpty {
        log("CommitmentService: Extracted \(extracted.count) commitment(s) from session \(sessionId)")
      } else {
        try? await CommitmentStorage.shared.markSessionProcessed(sessionId)
        log("CommitmentService: No commitments found in session \(sessionId), marked as processed")
      }
    } catch {
      log("CommitmentService: processSessionIfNeeded failed: \(error.localizedDescription)")
    }
  }

  // MARK: - Follow-Through Detection

  /// Check a new conversation for evidence that prior pending commitments
  /// were fulfilled. Does nothing if the user has not opted into commitment analysis.
  func processFollowThrough(sessionId: Int64) async {
    guard Self.isAnalysisEnabled else { return }
    do {
      let pending = try await CommitmentStorage.shared.getPendingCommitments()
      guard !pending.isEmpty else { return }

      let segments = try await TranscriptionStorage.shared.getSegments(sessionId: sessionId)
      guard !segments.isEmpty else { return }

      let transcript = segments.map { seg in
        (speaker: seg.speakerLabel ?? "Speaker \(seg.speaker)", text: seg.text)
      }

      let results = await CommitmentFollowThroughDetector.shared.detect(
        commitments: pending,
        transcript: transcript,
        sessionId: sessionId
      )

      for result in results {
        try? await CommitmentStorage.shared.markFulfilled(
          id: result.commitmentId,
          evidence: result.evidence,
          bySessionId: sessionId
        )
        CommitmentNotificationScheduler.shared.cancelReminder(commitmentId: result.commitmentId)
        log("CommitmentService: Fulfilled commitment [\(result.commitmentId)] — evidence: \(result.evidence ?? "none")")
      }

      if !results.isEmpty {
        log("CommitmentService: Detected \(results.count) fulfilled commitment(s) from session \(sessionId)")
        Task { @MainActor in
          await CommitmentsStore.shared.loadCommitments()
        }
      }
    } catch {
      log("CommitmentService: processFollowThrough failed: \(error.localizedDescription)")
    }
  }

  // MARK: - Overdue Check

  /// Mark pending commitments with passed deadlines as missed, and notify.
  func checkOverdueCommitments() async {
    do {
      let overdue = try await CommitmentStorage.shared.getOverdueCommitments()
      for commitment in overdue {
        try? await CommitmentStorage.shared.markMissed(id: commitment.id ?? 0)
        if let id = commitment.id {
          CommitmentNotificationScheduler.shared.cancelReminder(commitmentId: id)
        }
        CommitmentNotificationScheduler.shared.notifyMissed(commitment)
        log("CommitmentService: Marked missed: \(commitment.text)")
      }

      if !overdue.isEmpty {
        log("CommitmentService: Marked \(overdue.count) commitment(s) as missed")
        Task { @MainActor in
          await CommitmentsStore.shared.loadCommitments()
        }
      }
    } catch {
      log("CommitmentService: checkOverdueCommitments failed: \(error.localizedDescription)")
    }
  }

  // MARK: - Full Process (after conversation finalized)

  /// Run the full pipeline after a conversation is finalized:
  /// 1. Check follow-through on existing commitments
  /// 2. Extract new commitments
  /// 3. Check for newly overdue commitments
  ///
  /// No global guard — different sessions can be processed concurrently.
  /// Per-session dedup is handled by `processSessionIfNeeded` via `hasProcessedSession`.
  func processFinalizedSession(sessionId: Int64) async {
    await processFollowThrough(sessionId: sessionId)
    await processSessionIfNeeded(sessionId: sessionId)
    await checkOverdueCommitments()
  }

  // MARK: - Backfill (scan past conversations)

  /// Scan past conversations for commitments that were never extracted.
  /// Called once on app launch to backfill conversations that predate
  /// the commitment tracker feature. Does nothing if the user has not
  /// opted into commitment analysis.
  func scanPastConversations(limit: Int = 20) async {
    guard Self.isAnalysisEnabled else { return }
    do {
      let sessionIds = try await CommitmentStorage.shared.getUnprocessedCompletedSessionIds(limit: limit)
      guard !sessionIds.isEmpty else { return }

      log("CommitmentService: Scanning \(sessionIds.count) past conversation(s) for commitments")

      for sessionId in sessionIds {
        await processSessionIfNeeded(sessionId: sessionId)
      }

      await checkOverdueCommitments()
    } catch {
      log("CommitmentService: scanPastConversations failed: \(error.localizedDescription)")
    }
  }
}
