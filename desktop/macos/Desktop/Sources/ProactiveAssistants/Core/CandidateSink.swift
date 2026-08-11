import Foundation
@preconcurrency import GRDB

/// The only coupling between context buckets and the canonical task-candidate
/// system. It deliberately knows nothing about legacy staged tasks.
actor CandidateSink {
  static let shared = CandidateSink()

  func graduateValidatedFacts(deliveryID: String, factIDs: [String]) async {
    let normalizedFactIDs = factIDs.map { $0.hasPrefix("fact:") ? String($0.dropFirst(5)) : $0 }
    guard !normalizedFactIDs.isEmpty else { return }
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return }
    do {
      let rows = try await pool.read { db in
        try Row.fetchAll(
          db,
          sql: """
              SELECT id, statement, evidenceText, confidence FROM bucket_facts
              WHERE validityState = 'validated' AND dispositionState = 'none'
              AND bucketID = (SELECT bucketID FROM proactive_deliveries WHERE id = ?)
              AND id IN (\(normalizedFactIDs.map { _ in "?" }.joined(separator: ",")))
            """,
          arguments: StatementArguments([deliveryID] + normalizedFactIDs))
      }
      guard !rows.isEmpty else { return }
      let control = try await APIClient.shared.getCandidateWorkflowControl()
      guard control.workflowMode == .read, let generation = control.accountGeneration else { return }
      for row in rows {
        let id: String = row["id"]
        let statement: String = row["statement"]
        let evidenceText: String = row["evidenceText"]
        let confidence: Double = row["confidence"]
        let excerptHash = ContextBucketStore.referenceHash(evidenceText)
        let candidate = OmiAPI.CandidateCreate.taskCreate(
          OmiAPI.TaskCreateCandidate(
            captureConfidence: confidence,
            evidenceRefs: [
              OmiAPI.EvidenceRef(
                excerptHash: excerptHash,
                id: "bucket-fact:\(id)",
                kind: .local_screen,
                scope: .device_local,
                version: "context_bucket.v1")
            ],
            ownershipConfidence: confidence,
            proposedAction: "create",
            sourceSurface: "context_bucket",
            subjectKind: "task",
            taskChange: OmiAPI.TaskCreatePayload(description_: statement)))
        _ = try await APIClient.shared.createCanonicalCandidate(
          candidate,
          idempotencyKey: "context-bucket:\(deliveryID):\(id)",
          accountGeneration: generation)
        try await pool.write { db in
          try db.execute(
            sql:
              "UPDATE bucket_facts SET dispositionState = 'candidate_pending', updatedAt = ? WHERE id = ? AND validityState = 'validated'",
            arguments: [Date(), id])
        }
      }
    } catch {
      log("CandidateSink: canonical candidate graduation deferred: \(error.localizedDescription)")
    }
  }
}
