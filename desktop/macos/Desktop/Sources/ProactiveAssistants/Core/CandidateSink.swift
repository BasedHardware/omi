import Foundation
@preconcurrency import GRDB

/// Bounded outcome of graduating a context-director `task_candidate`. Interactive
/// presentation is allowed only for `.graduated`; every other case is a distinct
/// reason the ledger can record without collapsing them into a generic failure.
enum CandidateGraduationReason: String, Equatable, Sendable {
  case graduated
  case noFactIDs = "no_fact_ids"
  case ownerChanged = "owner_changed"
  case storeUnavailable = "store_unavailable"
  case workflowNotReadable = "workflow_not_readable"
  case ineligibleDisposition = "ineligible_disposition"
  case stale
}

/// Merges a bounded graduation-failure token into an existing director
/// provenance object so bucket refs survive the failed path.
enum CandidateGraduationProvenance {
  static let failureToken = "candidate_graduation_failed"

  static func mergingFailure(
    into provenanceJSON: String,
    reason: CandidateGraduationReason
  ) -> String {
    var object: [String: Any] = [:]
    if let data = provenanceJSON.data(using: .utf8),
      let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    {
      object = parsed
    }
    object["failure"] = failureToken
    object["graduation_reason"] = reason.rawValue
    guard let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]),
      let json = String(data: data, encoding: .utf8)
    else {
      return
        "{\"failure\":\"\(failureToken)\",\"graduation_reason\":\"\(reason.rawValue)\"}"
    }
    return json
  }
}

/// Presentation gate for context-director task candidates. Interactive
/// notifications must not become user-visible until graduation has produced
/// (or confirmed) a durable canonical candidate.
enum CandidateSinkDeliveryGate {
  static func mayPresentInteractively(
    decisionType: String,
    graduation: CandidateGraduationReason
  ) -> Bool {
    guard decisionType == "task_candidate" else { return true }
    return graduation == .graduated
  }

  static func hasCompleteValidatedFactSet(requestedIDs: [String], fetchedIDs: [String]) -> Bool {
    let requested = Set(requestedIDs.map { $0.hasPrefix("fact:") ? String($0.dropFirst(5)) : $0 })
    return !requested.isEmpty && requested == Set(fetchedIDs)
  }

  static func isGraduationEligibleDisposition(_ dispositionState: String) -> Bool {
    dispositionState == "none" || dispositionState == "candidate_pending"
  }

  static func canonicalCandidateIdempotencyKey(factID: String) -> String {
    "context-bucket:\(factID)"
  }
}

/// The only coupling between context buckets and the canonical task-candidate
/// system. It deliberately knows nothing about legacy staged tasks.
actor CandidateSink {
  static let shared = CandidateSink()

  struct GraduationFact: Decodable, FetchableRecord, Sendable {
    let id: String
    let statement: String
    let evidenceText: String
    let confidence: Double
    let dispositionState: String
  }

  static func graduationFacts(
    in db: Database, deliveryID: String, factIDs: [String], now: Date = Date()
  ) throws -> [GraduationFact] {
    var arguments: StatementArguments = [now, deliveryID]
    arguments += StatementArguments(factIDs)
    return try GraduationFact.fetchAll(
      db,
      sql: """
          SELECT id, statement, evidenceText, confidence, dispositionState FROM bucket_facts
          WHERE validityState = 'validated'
          AND (expiresAt IS NULL OR expiresAt > ?)
          AND dispositionState IN ('none', 'candidate_pending')
          AND bucketID = (SELECT bucketID FROM proactive_deliveries WHERE id = ?)
          AND id IN (\(factIDs.map { _ in "?" }.joined(separator: ",")))
        """,
      arguments: arguments)
  }

  /// Creates durable canonical candidates for validated facts. Callers that
  /// surface an interactive `task_candidate` notification must await this
  /// *before* presentation so a tap cannot race an empty candidate store.
  @discardableResult
  func graduateValidatedFacts(
    deliveryID: String,
    factIDs: [String],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    now: Date = Date()
  ) async -> CandidateGraduationReason {
    let normalizedFactIDs = Array(
      Set(factIDs.map { $0.hasPrefix("fact:") ? String($0.dropFirst(5)) : $0 })
    ).sorted()
    guard !normalizedFactIDs.isEmpty else { return .noFactIDs }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      return .ownerChanged
    }
    let (pool, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return .storeUnavailable }
    do {
      let facts = try await pool.read { db in
        try Self.graduationFacts(
          in: db, deliveryID: deliveryID, factIDs: normalizedFactIDs, now: now)
      }
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
        return .ownerChanged
      }
      guard
        CandidateSinkDeliveryGate.hasCompleteValidatedFactSet(
          requestedIDs: normalizedFactIDs,
          fetchedIDs: facts.map(\.id))
      else {
        return .stale
      }
      let needsCreate = facts.contains { $0.dispositionState == "none" }
      var generation: Int?
      if needsCreate {
        let control = try await APIClient.shared.getCandidateWorkflowControl(
          expectedOwnerId: authorizationSnapshot.ownerID,
          authorizationSnapshot: authorizationSnapshot)
        guard control.workflowMode == .read, let accountGeneration = control.accountGeneration else {
          return .workflowNotReadable
        }
        generation = accountGeneration
      }
      for fact in facts {
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
          return .ownerChanged
        }
        guard CandidateSinkDeliveryGate.isGraduationEligibleDisposition(fact.dispositionState) else {
          return .ineligibleDisposition
        }
        if fact.dispositionState == "none" {
          guard let accountGeneration = generation else { return .workflowNotReadable }
          let stillFresh = try await pool.read { db in
            try Self.graduationFacts(
              in: db, deliveryID: deliveryID, factIDs: [fact.id], now: now
            ).count == 1
          }
          guard stillFresh else { return .stale }
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
            idempotencyKey: CandidateSinkDeliveryGate.canonicalCandidateIdempotencyKey(factID: fact.id),
            accountGeneration: accountGeneration,
            expectedOwnerId: authorizationSnapshot.ownerID,
            authorizationSnapshot: authorizationSnapshot)
          guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
            return .ownerChanged
          }
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
                  "UPDATE bucket_facts SET dispositionState = 'candidate_pending', updatedAt = ? WHERE id = ? AND validityState = 'validated' AND dispositionState = 'none' AND (expiresAt IS NULL OR expiresAt > ?)",
                arguments: [now, fact.id, now])
              guard db.changesCount == 1 else { throw ContextBucketStoreError.staleFence }
            }
          }
        }
      }
      return .graduated
    } catch {
      log("CandidateSink: canonical candidate graduation deferred: \(error.localizedDescription)")
      if case .databaseUnavailable = error as? ContextBucketStoreError {
        return .storeUnavailable
      }
      return .stale
    }
  }
}
