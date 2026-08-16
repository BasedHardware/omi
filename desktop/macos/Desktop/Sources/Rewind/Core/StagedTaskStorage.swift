import Foundation
@preconcurrency import GRDB

struct CanonicalCaptureReceipt: Equatable {
  let candidateID: String
  let status: String
  let taskID: String?
}

/// Single atomic decision for whether a local outbox row may call backend create.
/// Closes the first-writer dual-create window and the dismiss-vs-reuse race in one
/// DB transaction immediately before delivery.
enum CanonicalCaptureDeliveryDecision: Equatable {
  /// Adopted a reusable pending/accepted synced receipt and retired this outbox row.
  case adoptedExistingReceipt(CanonicalCaptureReceipt)
  /// A newer equivalent observation: retired/coalesced into the elected oldest
  /// unsynced delivery leader. Caller must return without backend create.
  case coalescedIntoDeliveryLeader
  /// This row is the sole delivery leader (oldest recent equivalent unsynced, or
  /// no equivalent). Caller proceeds to backend create; on failure/crash the row
  /// remains in the outbox for retry.
  case proceedAsDeliveryLeader
}

enum CanonicalReceiptInvalidationError: Error, Equatable, LocalizedError {
  case ownerMismatch(expected: String, actual: String?)

  var errorDescription: String? {
    switch self {
    case .ownerMismatch(let expected, let actual):
      return
        "Canonical receipt invalidation refused: Rewind owner \(actual ?? "nil") != initiating owner \(expected)"
    }
  }
}

/// Actor-based storage manager for staged tasks awaiting promotion to action_items.
/// Mirrors a subset of ActionItemStorage methods but operates on the staged_tasks table.
actor StagedTaskStorage {
  static let shared = StagedTaskStorage()

  private var _dbQueue: DatabasePool?
  private var _dbGeneration = -1
  private var isInitialized = false

  private init() {}

  func invalidateCache() {
    _dbQueue = nil
    isInitialized = false
  }

  private func ensureInitialized() async throws -> DatabasePool {
    if let db = _dbQueue, await RewindDatabase.shared.poolGeneration() == _dbGeneration {
      return db
    }

    do {
      try await RewindDatabase.shared.initialize()
    } catch {
      log("StagedTaskStorage: Database initialization failed: \(error.localizedDescription)")
      throw error
    }

    let (queue, generation) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let db = queue else {
      throw ActionItemStorageError.databaseNotInitialized
    }

    _dbQueue = db
    _dbGeneration = generation
    isInitialized = true
    return db
  }

  // MARK: - Insert

  @discardableResult
  func insertLocalStagedTask(_ record: StagedTaskRecord) async throws -> StagedTaskRecord {
    let db = try await ensureInitialized()

    var insertRecord = record
    insertRecord.backendSynced = false
    let recordToInsert = insertRecord

    let inserted = try await db.write { database in
      try recordToInsert.inserted(database)
    }

    log("StagedTaskStorage: Inserted staged task (id: \(inserted.id ?? -1))")
    return inserted
  }

  /// Insert with score shift — pushes existing tasks with same or lower score down by 1
  func insertWithScoreShift(_ record: StagedTaskRecord) async throws -> StagedTaskRecord {
    let db = try await ensureInitialized()

    var insertRecord = record
    insertRecord.backendSynced = false
    let recordToInsert = insertRecord

    let inserted = try await db.write { database in
      if let score = recordToInsert.relevanceScore {
        try database.execute(
          sql: """
                UPDATE staged_tasks
                SET relevanceScore = relevanceScore + 1
                WHERE relevanceScore IS NOT NULL AND relevanceScore >= ?
                  AND completed = 0 AND deleted = 0
            """, arguments: [score])
      }
      return try recordToInsert.inserted(database)
    }

    log(
      "StagedTaskStorage: Inserted with score shift (id: \(inserted.id ?? -1), score: \(inserted.relevanceScore ?? -1))"
    )
    return inserted
  }

  // MARK: - Sync

  func markSynced(id: Int64, backendId: String, source: String? = nil) async throws {
    let db = try await ensureInitialized()

    enum MarkSyncedResult {
      case updated
      case mergedDuplicate(existingId: Int64)
    }

    let result: MarkSyncedResult = try await db.write { database in
      guard var record = try StagedTaskRecord.fetchOne(database, key: id) else {
        throw ActionItemStorageError.recordNotFound
      }

      // Sentry has seen UNIQUE constraint failures here when the same backend
      // task already exists locally (for example, from an API refresh racing a
      // local sync retry). Treat that as an idempotent sync completion: keep the
      // canonical backend row and remove the duplicate local row instead of
      // throwing and retrying forever.
      if let existing =
        try StagedTaskRecord
        .filter(Column("backendId") == backendId)
        .filter(Column("id") != id)
        .fetchOne(database),
        let existingId = existing.id
      {
        let now = Date()
        try database.execute(
          sql: """
                UPDATE staged_tasks
                SET backendSynced = 1, updatedAt = ?
                WHERE id = ?
            """,
          arguments: [now, existingId]
        )
        try database.execute(sql: "DELETE FROM staged_tasks WHERE id = ?", arguments: [id])
        return .mergedDuplicate(existingId: existingId)
      }

      record.backendId = backendId
      record.backendSynced = true
      if let source { record.source = source }
      record.updatedAt = Date()
      do {
        try record.update(database)
        return .updated
      } catch let dbError as DatabaseError where dbError.resultCode == .SQLITE_CONSTRAINT {
        // Another local staged row already holds this backendId (duplicate sync, or
        // backend dedup returned an existing task's id). The UNIQUE index on
        // staged_tasks.backendId would otherwise crash the sync-status update.
        // Make it idempotent: drop this freshly-extracted duplicate and keep the
        // existing canonical row that already represents the backend task.
        let existingId =
          try StagedTaskRecord
          .filter(Column("backendId") == backendId)
          .filter(Column("id") != id)
          .fetchOne(database)?
          .id ?? id
        try database.execute(sql: "DELETE FROM staged_tasks WHERE id = ?", arguments: [id])
        return .mergedDuplicate(existingId: existingId)
      }
    }

    switch result {
    case .updated:
      log("StagedTaskStorage: Marked staged task \(id) as synced (backendId: \(backendId))")
    case .mergedDuplicate(let existingId):
      log(
        "StagedTaskStorage: Marked staged task sync idempotent by merging local duplicate \(id) into existing row \(existingId)"
      )
    }
  }

  /// Get unsynced staged tasks for retry
  func getUnsyncedStagedTasks(limit: Int = 50) async throws -> [StagedTaskRecord] {
    let db = try await ensureInitialized()

    return try await db.read { database in
      try StagedTaskRecord
        .filter(Column("backendSynced") == false)
        .filter(Column("deleted") == false)
        .filter(Column("source") == nil || Column("source") != "candidate_outbox")
        .order(Column("createdAt").desc)
        .limit(limit)
        .fetchAll(database)
    }
  }

  func markCanonicalReceipt(id: Int64, candidateID: String, status: String, taskID: String?) async throws {
    let db = try await ensureInitialized()

    enum MarkReceiptResult {
      case updated
      case mergedDuplicate(existingId: Int64)
    }

    let result: MarkReceiptResult = try await db.write { database in
      guard var record = try StagedTaskRecord.fetchOne(database, key: id) else {
        throw ActionItemStorageError.recordNotFound
      }

      // Paraphrase reuse stamps the same candidateID onto a second local outbox
      // row. staged_tasks.backendId is UNIQUE (same as markSynced), so treat an
      // existing receipt row as the canonical identity and retire this duplicate
      // transactionally instead of throwing into a retry loop.
      if let existing =
        try StagedTaskRecord
        .filter(Column("backendId") == candidateID)
        .filter(Column("id") != id)
        .fetchOne(database),
        let existingId = existing.id
      {
        var existingRecord = existing
        var metadata = existingRecord.metadata ?? [:]
        let resolved = Self.resolvedCanonicalReceiptFields(
          existingMetadata: metadata,
          candidateID: candidateID,
          incomingStatus: status,
          incomingTaskID: taskID
        )
        metadata["canonical_candidate_id"] = resolved.candidateID
        metadata["canonical_candidate_status"] = resolved.status
        if let resolvedTaskID = resolved.taskID {
          metadata["canonical_task_id"] = resolvedTaskID
        } else {
          metadata.removeValue(forKey: "canonical_task_id")
        }
        existingRecord.setMetadata(metadata)
        existingRecord.backendSynced = true
        existingRecord.completed = true
        existingRecord.source = "candidate_outbox"
        existingRecord.updatedAt = Date()
        try existingRecord.update(database)
        try database.execute(sql: "DELETE FROM staged_tasks WHERE id = ?", arguments: [id])
        return .mergedDuplicate(existingId: existingId)
      }

      var metadata = record.metadata ?? [:]
      let resolved = Self.resolvedCanonicalReceiptFields(
        existingMetadata: metadata,
        candidateID: candidateID,
        incomingStatus: status,
        incomingTaskID: taskID
      )
      metadata["canonical_candidate_id"] = resolved.candidateID
      metadata["canonical_candidate_status"] = resolved.status
      if let resolvedTaskID = resolved.taskID {
        metadata["canonical_task_id"] = resolvedTaskID
      } else {
        metadata.removeValue(forKey: "canonical_task_id")
      }
      record.setMetadata(metadata)
      record.backendId = candidateID
      record.backendSynced = true
      record.completed = true
      record.source = "candidate_outbox"
      record.updatedAt = Date()
      do {
        try record.update(database)
        return .updated
      } catch let dbError as DatabaseError where dbError.resultCode == .SQLITE_CONSTRAINT {
        guard
          let existingId = try StagedTaskRecord
            .filter(Column("backendId") == candidateID)
            .filter(Column("id") != id)
            .fetchOne(database)?
            .id
        else {
          // Do not turn an unrelated schema/constraint violation into a
          // successful merge that silently deletes the only local outbox row.
          throw dbError
        }
        try database.execute(sql: "DELETE FROM staged_tasks WHERE id = ?", arguments: [id])
        return .mergedDuplicate(existingId: existingId)
      }
    }

    switch result {
    case .updated:
      log("StagedTaskStorage: Marked canonical receipt \(id) (candidateID: \(candidateID))")
    case .mergedDuplicate(let existingId):
      log(
        "StagedTaskStorage: Marked canonical receipt idempotent by merging local duplicate \(id) into existing row \(existingId)"
      )
    }
  }

  /// Atomically decide whether local outbox row `localOutboxID` may deliver a
  /// backend create. One transaction covers:
  /// 1. Adopt a reusable pending/accepted synced receipt and retire this row
  /// 2. Else elect the oldest recent equivalent unsynced outbox row as sole
  ///    delivery leader — older leader proceeds; newer equivalents are
  ///    retired/coalesced without create
  /// 3. Else proceed as leader (no equivalent)
  ///
  /// Rejected/expired synced receipts are never reusable. Source-app / target /
  /// due / polarity fences stay in `ScreenCandidateReconciliation.isEquivalent`.
  /// On leader failure or crash the leader row remains unsynced for retry.
  func resolveCanonicalCaptureDelivery(
    for record: StagedTaskRecord,
    localOutboxID: Int64,
    now: Date = Date()
  ) async throws -> CanonicalCaptureDeliveryDecision {
    let db = try await ensureInitialized()
    let cutoff = now.addingTimeInterval(-ScreenCandidateReconciliation.reuseWindow)

    let decision: CanonicalCaptureDeliveryDecision = try await db.write { database in
      guard let localRow = try StagedTaskRecord.fetchOne(database, key: localOutboxID),
        localRow.deleted == false
      else {
        throw ActionItemStorageError.recordNotFound
      }
      // Equivalence uses the caller's observation (R2). Existence/deleted is
      // checked against the live outbox row so a concurrent discard cannot adopt.
      let probe = record

      let recentSynced =
        try StagedTaskRecord
        .filter(Column("source") == "candidate_outbox")
        .filter(Column("backendSynced") == true)
        .filter(Column("deleted") == false)
        .filter(Column("id") != localOutboxID)
        .filter(Column("createdAt") >= cutoff)
        .order(Column("createdAt").desc)
        .fetchAll(database)

      if let match = recentSynced.first(where: { candidate in
        guard ScreenCandidateReconciliation.isEquivalent(probe, candidate) else { return false }
        guard let status = candidate.metadata?["canonical_candidate_status"] as? String else {
          return false
        }
        return Self.isReusableCanonicalReceiptStatus(status)
      }),
        let metadata = match.metadata,
        let candidateID = metadata["canonical_candidate_id"] as? String,
        let status = metadata["canonical_candidate_status"] as? String,
        Self.isReusableCanonicalReceiptStatus(status)
      {
        // Keep the existing receipt's live status/taskID — never stamp a stale
        // pending onto a row that flipped to rejected/expired mid-flight.
        var existingRecord = match
        var updatedMetadata = metadata
        updatedMetadata["canonical_candidate_id"] = candidateID
        updatedMetadata["canonical_candidate_status"] = status
        if let taskID = metadata["canonical_task_id"] as? String {
          updatedMetadata["canonical_task_id"] = taskID
        } else {
          updatedMetadata.removeValue(forKey: "canonical_task_id")
        }
        existingRecord.setMetadata(updatedMetadata)
        existingRecord.backendId = candidateID
        existingRecord.backendSynced = true
        existingRecord.completed = true
        existingRecord.source = "candidate_outbox"
        existingRecord.updatedAt = Date()
        try existingRecord.update(database)
        try database.execute(sql: "DELETE FROM staged_tasks WHERE id = ?", arguments: [localOutboxID])

        return .adoptedExistingReceipt(
          CanonicalCaptureReceipt(
            candidateID: candidateID,
            status: status,
            taskID: metadata["canonical_task_id"] as? String
          )
        )
      }

      // No reusable synced receipt: elect the oldest recent equivalent unsynced
      // candidate_outbox row as the sole delivery leader.
      let recentUnsynced =
        try StagedTaskRecord
        .filter(Column("source") == "candidate_outbox")
        .filter(Column("backendSynced") == false)
        .filter(Column("deleted") == false)
        .filter(Column("createdAt") >= cutoff)
        .order(Column("createdAt").asc, Column("id").asc)
        .fetchAll(database)

      let equivalentUnsynced = recentUnsynced.filter { candidate in
        guard candidate.id != localOutboxID else { return true }
        return ScreenCandidateReconciliation.isEquivalent(probe, candidate)
      }
      guard let leader = equivalentUnsynced.first, let leaderID = leader.id else {
        return .proceedAsDeliveryLeader
      }

      if leaderID == localOutboxID {
        return .proceedAsDeliveryLeader
      }

      // Newer equivalent: coalesce into the elected leader and refuse create.
      try database.execute(sql: "DELETE FROM staged_tasks WHERE id = ?", arguments: [localOutboxID])
      return .coalescedIntoDeliveryLeader
    }

    switch decision {
    case .adoptedExistingReceipt(let adopted):
      log(
        "StagedTaskStorage: Adopted equivalent canonical receipt \(adopted.candidateID) and retired outbox \(localOutboxID)"
      )
    case .coalescedIntoDeliveryLeader:
      log(
        "StagedTaskStorage: Coalesced outbox \(localOutboxID) into older equivalent delivery leader"
      )
    case .proceedAsDeliveryLeader:
      break
    }
    return decision
  }

  private static func isReusableCanonicalReceiptStatus(_ status: String) -> Bool {
    status == OmiAPI.CandidateStatus.pending.rawValue
      || status == OmiAPI.CandidateStatus.accepted.rawValue
  }

  private static func isTerminalCanonicalReceiptStatus(_ status: String) -> Bool {
    status == OmiAPI.CandidateStatus.rejected.rawValue
      || status == OmiAPI.CandidateStatus.expired.rawValue
  }

  /// Preserve rejected/expired once written — never demote terminal → pending/accepted.
  private static func resolvedCanonicalReceiptFields(
    existingMetadata: [String: Any],
    candidateID: String,
    incomingStatus: String,
    incomingTaskID: String?
  ) -> (candidateID: String, status: String, taskID: String?) {
    let existingStatus = existingMetadata["canonical_candidate_status"] as? String
    let existingTaskID = existingMetadata["canonical_task_id"] as? String
    if let existingStatus, isTerminalCanonicalReceiptStatus(existingStatus) {
      return (candidateID, existingStatus, existingTaskID ?? incomingTaskID)
    }
    return (candidateID, incomingStatus, incomingTaskID)
  }

  /// Mark matching local outbox receipts as rejected (or another terminal status)
  /// so an equivalent observation can create a new Candidate immediately after
  /// Suggested dismiss/reject. Matched by candidate id on `backendId` or
  /// metadata — never by title.
  ///
  /// Returns `true` when at least one matching receipt was terminalized.
  /// Returns `false` on zero match without throwing — callers must retain the
  /// durable pending invalidation so a later create→mark can still be cleaned up.
  ///
  /// Owner-scoped: refuses before `ensureInitialized` and again before/inside the
  /// write when `RewindDatabase.currentUserId` is not `ownerID`, so a mid-flight
  /// retarget cannot terminalize receipts in another account's pool. A closed
  /// stale pool (or any other write failure) throws and is retryable by the caller.
  @discardableResult
  func invalidateCanonicalReceipt(
    candidateID: String,
    ownerID: String,
    status: String = OmiAPI.CandidateStatus.rejected.rawValue
  ) async throws -> Bool {
    try Self.requireRewindOwner(ownerID)
    let db = try await ensureInitialized()
    try Self.requireRewindOwner(ownerID)
    let updatedCount: Int = try await db.write { database in
      try Self.requireRewindOwner(ownerID)
      let candidates =
        try StagedTaskRecord
        .filter(Column("source") == "candidate_outbox")
        .filter(Column("deleted") == false)
        .fetchAll(database)

      var count = 0
      let now = Date()
      for var record in candidates {
        let metadataCandidateID = record.metadata?["canonical_candidate_id"] as? String
        let matches =
          record.backendId == candidateID
          || metadataCandidateID == candidateID
        guard matches else { continue }
        // Re-check immediately before each mutation so a retarget that races the
        // write cannot stamp owner B's rows for an owner-A invalidation.
        try Self.requireRewindOwner(ownerID)
        var metadata = record.metadata ?? [:]
        metadata["canonical_candidate_id"] = candidateID
        metadata["canonical_candidate_status"] = status
        record.setMetadata(metadata)
        record.backendSynced = true
        record.completed = true
        record.updatedAt = now
        try record.update(database)
        count += 1
      }
      return count
    }
    if updatedCount > 0 {
      log(
        "StagedTaskStorage: Invalidated \(updatedCount) canonical receipt(s) for candidate \(candidateID) as \(status)"
      )
    }
    return updatedCount > 0
  }

  private nonisolated static func requireRewindOwner(_ ownerID: String) throws {
    let current = RewindDatabase.currentUserId
    guard current == ownerID else {
      throw CanonicalReceiptInvalidationError.ownerMismatch(expected: ownerID, actual: current)
    }
  }

  func discardCanonicalOutbox(id: Int64) async throws {
    let db = try await ensureInitialized()
    try await db.write { database in
      try database.execute(
        sql: "UPDATE staged_tasks SET completed = 1, deleted = 1, updatedAt = ? WHERE id = ?",
        arguments: [Date(), id]
      )
    }
  }

  enum CanonicalOutboxRejectionOutcome: Equatable {
    case willRetry(rejections: Int)
    case poisoned(rejections: Int)
  }

  /// Records one permanent (validation-class) delivery rejection for an outbox
  /// row. The count is persisted in the row's metadata so it survives restarts.
  /// Once the count reaches `limit`, the row is poisoned: marked deleted so
  /// `getUnsyncedCanonicalOutbox` stops returning it, with a metadata marker
  /// distinguishing this terminal state from a user delete. A permanently
  /// rejected payload can never succeed, so retrying it forever only wedges the
  /// outbox and burns quota on deterministic 4xx responses.
  func recordCanonicalOutboxRejection(
    id: Int64,
    limit: Int = CandidateOutboxRetryPolicy.maxPermanentRejections
  ) async throws -> CanonicalOutboxRejectionOutcome {
    let db = try await ensureInitialized()
    return try await db.write { database in
      guard var record = try StagedTaskRecord.fetchOne(database, key: id) else {
        throw ActionItemStorageError.recordNotFound
      }
      var metadata = record.metadata ?? [:]
      let rejections = ((metadata["outbox_permanent_rejections"] as? Int) ?? 0) + 1
      metadata["outbox_permanent_rejections"] = rejections
      let poisoned = rejections >= limit
      if poisoned {
        metadata["outbox_poisoned"] = true
        record.completed = true
        record.deleted = true
      }
      record.setMetadata(metadata)
      record.updatedAt = Date()
      try record.update(database)
      return poisoned ? .poisoned(rejections: rejections) : .willRetry(rejections: rejections)
    }
  }

  func getUnsyncedCanonicalOutbox(limit: Int? = nil) async throws -> [StagedTaskRecord] {
    let db = try await ensureInitialized()
    return try await db.read { database in
      var request =
        StagedTaskRecord
        .filter(Column("backendSynced") == false)
        .filter(Column("deleted") == false)
        .filter(Column("source") == "candidate_outbox")
        .order(Column("createdAt").asc)
      if let limit {
        request = request.limit(limit)
      }
      return try request.fetchAll(database)
    }
  }

  func getCanonicalCaptureReceipt(id: Int64) async throws -> CanonicalCaptureReceipt? {
    let db = try await ensureInitialized()
    return try await db.read { database in
      guard let record = try StagedTaskRecord.fetchOne(database, key: id),
        record.source == "candidate_outbox",
        record.backendSynced,
        let metadata = record.metadata,
        let candidateID = metadata["canonical_candidate_id"] as? String,
        let status = metadata["canonical_candidate_status"] as? String
      else { return nil }
      return CanonicalCaptureReceipt(
        candidateID: candidateID,
        status: status,
        taskID: metadata["canonical_task_id"] as? String
      )
    }
  }

  /// Find a recently reconciled screen capture that represents the same task.
  /// Canonical create already coalesces exact descriptions, but repeated visual
  /// observations often paraphrase the same request (for example "reply ... to
  /// approve" versus "approve ..."). Reusing its receipt prevents each
  /// paraphrase from becoming another Suggested Candidate.
  func recentEquivalentCanonicalReceipt(
    for record: StagedTaskRecord,
    excludingID: Int64,
    now: Date = Date()
  ) async throws -> CanonicalCaptureReceipt? {
    let db = try await ensureInitialized()
    let cutoff = now.addingTimeInterval(-ScreenCandidateReconciliation.reuseWindow)
    return try await db.read { database in
      let recent =
        try StagedTaskRecord
        .filter(Column("source") == "candidate_outbox")
        .filter(Column("backendSynced") == true)
        .filter(Column("deleted") == false)
        .filter(Column("id") != excludingID)
        .filter(Column("createdAt") >= cutoff)
        .order(Column("createdAt").desc)
        .limit(100)
        .fetchAll(database)

      for candidate in recent where ScreenCandidateReconciliation.isEquivalent(record, candidate) {
        guard let metadata = candidate.metadata,
          let candidateID = metadata["canonical_candidate_id"] as? String,
          let status = metadata["canonical_candidate_status"] as? String,
          Self.isReusableCanonicalReceiptStatus(status)
        else { continue }
        return CanonicalCaptureReceipt(
          candidateID: candidateID,
          status: status,
          taskID: metadata["canonical_task_id"] as? String
        )
      }
      return nil
    }
  }

  /// Pending canonical Candidates are represented locally by completed outbox
  /// rows: `completed` means delivery processing finished, not that the user's
  /// task is complete. Surface their descriptions as already-captured evidence
  /// so extraction does not mistake them for finished work or omit them.
  func getRecentCanonicalCandidateDescriptions(limit: Int = 30) async throws -> [String] {
    let db = try await ensureInitialized()
    return try await db.read { database in
      let records =
        try StagedTaskRecord
        .filter(Column("source") == "candidate_outbox")
        .filter(Column("backendSynced") == true)
        .filter(Column("deleted") == false)
        .order(Column("createdAt").desc)
        .limit(limit * 3)
        .fetchAll(database)

      let descriptions: [String] = records.compactMap { record -> String? in
        guard let status = record.metadata?["canonical_candidate_status"] as? String,
          status == OmiAPI.CandidateStatus.pending.rawValue
            || status == OmiAPI.CandidateStatus.accepted.rawValue
        else { return nil }
        return record.description
      }
      return Array(descriptions.prefix(limit))
    }
  }

  // MARK: - Read

  /// Get all active (non-completed, non-deleted) staged tasks
  func getAllStagedTasks(limit: Int = 10000) async throws -> [TaskActionItem] {
    let db = try await ensureInitialized()

    return try await db.read { database in
      let records =
        try StagedTaskRecord
        .filter(Column("deleted") == false)
        .filter(Column("completed") == false)
        .filter(Column("source") == nil || Column("source") != "candidate_outbox")
        .order(Column("createdAt").desc)
        .limit(limit)
        .fetchAll(database)

      return records.map { $0.toTaskActionItem() }
    }
  }

  /// Get staged tasks ordered by relevance score (best first)
  func getScoredStagedTasks(limit: Int = 100) async throws -> [TaskActionItem] {
    let db = try await ensureInitialized()

    return try await db.read { database in
      let records =
        try StagedTaskRecord
        .filter(Column("deleted") == false)
        .filter(Column("completed") == false)
        .filter(Column("source") == nil || Column("source") != "candidate_outbox")
        .order(sql: "COALESCE(relevanceScore, 999999) ASC")
        .limit(limit)
        .fetchAll(database)

      return records.map { $0.toTaskActionItem() }
    }
  }

  /// Get all scored tasks with backend IDs for syncing scores to backend
  func getAllScoredTasks() async throws -> [(id: String, score: Int)] {
    let db = try await ensureInitialized()

    return try await db.read { database in
      try Row.fetchAll(
        database,
        sql: """
              SELECT backendId, relevanceScore FROM staged_tasks
              WHERE backendId IS NOT NULL AND relevanceScore IS NOT NULL
                AND deleted = 0 AND completed = 0
          """
      ).compactMap { row in
        guard let backendId: String = row["backendId"],
          let score: Int = row["relevanceScore"]
        else { return nil }
        return (id: backendId, score: score)
      }
    }
  }

  // MARK: - Delete

  /// Hard-delete a staged task by backend ID (after promotion)
  func deleteByBackendId(_ backendId: String) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      try database.execute(
        sql: "DELETE FROM staged_tasks WHERE backendId = ?",
        arguments: [backendId]
      )
    }

    log("StagedTaskStorage: Hard-deleted staged task with backendId \(backendId)")
  }

  /// Hard-delete a staged task by local ID
  func deleteById(_ id: Int64) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      try database.execute(
        sql: "DELETE FROM staged_tasks WHERE id = ?",
        arguments: [id]
      )
    }

    log("StagedTaskStorage: Hard-deleted staged task with id \(id)")
  }

  // MARK: - Re-ranking

  /// Apply selective re-ranking from Gemini response
  func applySelectiveReranking(_ reranks: [(backendId: String, newPosition: Int)]) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      let rows = try Row.fetchAll(
        database,
        sql: """
              SELECT id, backendId, relevanceScore
              FROM staged_tasks
              WHERE completed = 0 AND deleted = 0
              ORDER BY COALESCE(relevanceScore, 999999) ASC
          """)

      var orderedIds: [String] = rows.compactMap { $0["backendId"] as? String }
      let rerankedSet = Set(reranks.map { $0.backendId })

      orderedIds.removeAll { rerankedSet.contains($0) }

      let sorted = reranks.sorted { $0.newPosition < $1.newPosition }
      for rerank in sorted {
        let insertIdx = max(0, min(rerank.newPosition - 1, orderedIds.count))
        orderedIds.insert(rerank.backendId, at: insertIdx)
      }

      let now = Date()
      for (index, backendId) in orderedIds.enumerated() {
        try database.execute(
          sql: "UPDATE staged_tasks SET relevanceScore = ?, scoredAt = ?, updatedAt = ? WHERE backendId = ?",
          arguments: [index + 1, now, now, backendId]
        )
      }
    }
  }

  // MARK: - Embedding

  func updateEmbedding(id: Int64, embedding: Data) async throws {
    let db = try await ensureInitialized()

    try await db.write { database in
      try database.execute(
        sql: "UPDATE staged_tasks SET embedding = ? WHERE id = ?",
        arguments: [embedding, id]
      )
    }
  }

  func getAllEmbeddings() async throws -> [(id: Int64, embedding: Data)] {
    let db = try await ensureInitialized()

    return try await db.read { database in
      try Row.fetchAll(
        database,
        sql: """
              SELECT id, embedding FROM staged_tasks
              WHERE embedding IS NOT NULL
                AND completed = 0 AND deleted = 0
                AND (source IS NULL OR source != 'candidate_outbox')
          """
      ).compactMap { row in
        guard let id: Int64 = row["id"],
          let embedding: Data = row["embedding"]
        else { return nil }
        return (id: id, embedding: embedding)
      }
    }
  }

  // MARK: - FTS Search

  func searchFTS(
    query: String,
    limit: Int = 20
  ) async throws -> [(id: Int64, description: String, relevanceScore: Int?)] {
    let db = try await ensureInitialized()
    // Sanitize FTS5 query: strip special characters that could be misinterpreted
    let sanitizedQuery = query.map { $0.isLetter || $0.isNumber || $0 == "*" || $0 == " " ? $0 : Character(" ") }
      .map(String.init).joined()
      .components(separatedBy: .whitespaces).filter { !$0.isEmpty }.joined(separator: " ")
    guard !sanitizedQuery.isEmpty else { return [] }

    return try await db.read { database in
      let sql = """
            SELECT s.id, s.description, s.relevanceScore
            FROM staged_tasks s
            JOIN staged_tasks_fts fts ON fts.rowid = s.id
            WHERE staged_tasks_fts MATCH ?
              AND s.completed = 0 AND s.deleted = 0
            ORDER BY bm25(staged_tasks_fts) ASC LIMIT ?
        """

      return try Row.fetchAll(database, sql: sql, arguments: [sanitizedQuery, limit]).map { row in
        (
          id: row["id"] as Int64,
          description: row["description"] as String,
          relevanceScore: row["relevanceScore"] as Int?
        )
      }
    }
  }

  // MARK: - Single Record Lookup

  /// Get a single staged task by local ID (for vector search fallback)
  func getStagedTask(id: Int64) async throws -> (
    id: Int64, description: String, relevanceScore: Int?, completed: Bool, deleted: Bool
  )? {
    let db = try await ensureInitialized()

    return try await db.read { database in
      guard let record = try StagedTaskRecord.fetchOne(database, key: id),
        !record.completed,
        !record.deleted,
        record.source != "candidate_outbox"
      else {
        return nil
      }
      return (
        id: record.id ?? id, description: record.description, relevanceScore: record.relevanceScore,
        completed: record.completed, deleted: record.deleted
      )
    }
  }

  // MARK: - Missing Embeddings

  /// Get staged tasks missing embeddings (for backfill)
  func getItemsMissingEmbeddings(limit: Int = 100) async throws -> [(id: Int64, description: String)] {
    let db = try await ensureInitialized()

    return try await db.read { database in
      try Row.fetchAll(
        database,
        sql: """
              SELECT id, description FROM staged_tasks
              WHERE embedding IS NULL AND completed = 0 AND deleted = 0
                AND (source IS NULL OR source != 'candidate_outbox')
              ORDER BY createdAt DESC LIMIT ?
          """, arguments: [limit]
      ).map { row in
        (
          id: row["id"] as Int64,
          description: row["description"] as String
        )
      }
    }
  }

  // MARK: - Count

  func countActiveStagedTasks() async throws -> Int {
    let db = try await ensureInitialized()

    return try await db.read { database in
      try Int.fetchOne(
        database,
        sql: """
              SELECT COUNT(*) FROM staged_tasks
              WHERE completed = 0 AND deleted = 0
                AND (source IS NULL OR source != 'candidate_outbox')
          """) ?? 0
    }
  }
}
