import Foundation
@preconcurrency import GRDB

/// The only coupling between context buckets and the canonical task-candidate
/// system. It deliberately knows nothing about legacy staged tasks.
actor CandidateSink {
  static let shared = CandidateSink()

  private struct GraduationFact: Decodable, FetchableRecord, Sendable {
    let id: String
    let statement: String
    let evidenceText: String
    let confidence: Double
  }

  func graduateValidatedFacts(
    deliveryID: String,
    factIDs: [String],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async {
    let normalizedFactIDs = factIDs.map { $0.hasPrefix("fact:") ? String($0.dropFirst(5)) : $0 }
    guard !normalizedFactIDs.isEmpty else { return }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
    let (pool, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return }
    do {
      let facts = try await pool.read { db in
        try GraduationFact.fetchAll(
          db,
          sql: """
              SELECT id, statement, evidenceText, confidence FROM bucket_facts
              WHERE validityState = 'validated' AND dispositionState = 'none'
              AND bucketID = (SELECT bucketID FROM proactive_deliveries WHERE id = ?)
              AND id IN (\(normalizedFactIDs.map { _ in "?" }.joined(separator: ",")))
            """,
          arguments: StatementArguments([deliveryID] + normalizedFactIDs))
      }
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot), !facts.isEmpty else { return }
      let control = try await APIClient.shared.getCandidateWorkflowControl(
        expectedOwnerId: authorizationSnapshot.ownerID,
        authorizationSnapshot: authorizationSnapshot)
      guard control.workflowMode == .read, let generation = control.accountGeneration else { return }
      for fact in facts {
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
        let excerptHash = ContextBucketStore.referenceHash(fact.evidenceText)
        let candidate = OmiAPI.CandidateCreate.taskCreate(
          OmiAPI.TaskCreateCandidate(
            captureConfidence: fact.confidence,
            evidenceRefs: [
              OmiAPI.EvidenceRef(
                excerptHash: excerptHash,
                id: "bucket-fact:\(fact.id)",
                kind: .local_screen,
                scope: .device_local,
                version: "context_bucket.v1")
            ],
            ownershipConfidence: fact.confidence,
            proposedAction: "create",
            sourceSurface: "context_bucket",
            subjectKind: "task",
            taskChange: OmiAPI.TaskCreatePayload(description_: fact.statement)))
        _ = try await APIClient.shared.createCanonicalCandidate(
          candidate,
          idempotencyKey: "context-bucket:\(deliveryID):\(fact.id)",
          accountGeneration: generation,
          expectedOwnerId: authorizationSnapshot.ownerID,
          authorizationSnapshot: authorizationSnapshot)
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
        let mutationAuthorization = LocalMutationAuthorization {
          RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
        }
        try await mutationAuthorization.withCommitLease {
          let (_, currentPoolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
          guard currentPoolEpoch == poolEpoch else {
            throw ContextBucketStoreError.staleFence
          }
          try await pool.write { db in
            try db.execute(
              sql:
                "UPDATE bucket_facts SET dispositionState = 'candidate_pending', updatedAt = ? WHERE id = ? AND validityState = 'validated'",
              arguments: [Date(), fact.id])
          }
        }
      }
    } catch {
      log("CandidateSink: canonical candidate graduation deferred: \(error.localizedDescription)")
    }
  }
}
