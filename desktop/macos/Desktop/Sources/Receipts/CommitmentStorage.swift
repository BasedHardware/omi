import Foundation
import GRDB

/// Actor-based storage for commitments. Local-only MVP — no backend sync.
/// Mirrors the ActionItemStorage / TranscriptionStorage pattern.
actor CommitmentStorage {
  static let shared = CommitmentStorage()

  private var _dbQueue: DatabasePool?
  private var isInitialized = false

  private init() {}

  func invalidateCache() {
    _dbQueue = nil
    isInitialized = false
  }

  private func ensureInitialized() async throws -> DatabasePool {
    if let db = _dbQueue { return db }

    do {
      try await RewindDatabase.shared.initialize()
    } catch {
      log("CommitmentStorage: Database initialization failed: \(error.localizedDescription)")
      throw error
    }

    guard let db = await RewindDatabase.shared.getDatabaseQueue() else {
      throw CommitmentStorageError.databaseNotInitialized
    }

    _dbQueue = db
    isInitialized = true
    return db
  }

  // MARK: - Insert

  @discardableResult
  func insertCommitment(_ record: CommitmentRecord) async throws -> Int64 {
    let db = try await ensureInitialized()
    var rec = record
    rec.updatedAt = Date()
    let captured = rec
    let inserted = try await db.write { database in
      try captured.inserted(database)
    }
    return inserted.id!
  }

  // MARK: - Queries

  func getCommitments(
    status: CommitmentStatus? = nil,
    limit: Int = 200,
    offset: Int = 0
  ) async throws -> [CommitmentRecord] {
    let db = try await ensureInitialized()
    return try await db.read { database in
      var query = CommitmentRecord.all()
      if let status = status {
        query = query.filter(Column("status") == status.rawValue)
      }
      return try query
        .order(Column("deadline").ascNullsLast, Column("createdAt").desc)
        .limit(limit, offset: offset)
        .fetchAll(database)
    }
  }

  func getPendingCommitments() async throws -> [CommitmentRecord] {
    try await getCommitments(status: .pending, limit: 500)
  }

  func getOverdueCommitments() async throws -> [CommitmentRecord] {
    let db = try await ensureInitialized()
    let now = Date()
    return try await db.read { database in
      try CommitmentRecord
        .filter(Column("status") == CommitmentStatus.pending.rawValue)
        .filter(Column("deadline") != nil)
        .filter(Column("deadline") < now)
        .order(Column("deadline").asc)
        .fetchAll(database)
    }
  }

  func getCommitment(byId id: Int64) async throws -> CommitmentRecord? {
    let db = try await ensureInitialized()
    return try await db.read { database in
      try CommitmentRecord.fetchOne(
        database,
        key: id
      )
    }
  }

  func getCommitmentCount() async -> Int {
    guard let db = try? await ensureInitialized() else { return 0 }
    return (try? await db.read { database in
      try CommitmentRecord
        .filter(Column("status") == CommitmentStatus.pending.rawValue)
        .fetchCount(database)
    }) ?? 0
  }

  // MARK: - Updates

  func markFulfilled(
    id: Int64,
    evidence: String?,
    bySessionId: Int64?
  ) async throws {
    let db = try await ensureInitialized()
    try await db.write { database in
      guard var record = try CommitmentRecord.fetchOne(database, key: id) else {
        throw CommitmentStorageError.recordNotFound
      }
      record.status = CommitmentStatus.fulfilled.rawValue
      record.fulfilledAt = Date()
      record.fulfilledByEvidence = evidence
      record.fulfilledBySessionId = bySessionId
      record.updatedAt = Date()
      try record.update(database)
    }
  }

  func markMissed(id: Int64) async throws {
    let db = try await ensureInitialized()
    try await db.write { database in
      guard var record = try CommitmentRecord.fetchOne(database, key: id) else {
        throw CommitmentStorageError.recordNotFound
      }
      record.status = CommitmentStatus.missed.rawValue
      record.updatedAt = Date()
      try record.update(database)
    }
  }

  func updateDeadline(id: Int64, deadline: Date?) async throws {
    let db = try await ensureInitialized()
    try await db.write { database in
      guard var record = try CommitmentRecord.fetchOne(database, key: id) else {
        throw CommitmentStorageError.recordNotFound
      }
      record.deadline = deadline
      record.updatedAt = Date()
      try record.update(database)
    }
  }

  func updateStatus(id: Int64, status: CommitmentStatus) async throws {
    let db = try await ensureInitialized()
    try await db.write { database in
      guard var record = try CommitmentRecord.fetchOne(database, key: id) else {
        throw CommitmentStorageError.recordNotFound
      }
      record.status = status.rawValue
      if status == .fulfilled && record.fulfilledAt == nil {
        record.fulfilledAt = Date()
      }
      record.updatedAt = Date()
      try record.update(database)
    }
  }

  // MARK: - Delete

  func deleteCommitment(id: Int64) async throws {
    let db = try await ensureInitialized()
    try await db.write { database in
      _ = try CommitmentRecord.deleteOne(database, key: id)
    }
  }

  // MARK: - Session dedup

  /// True if a session has already been processed (either commitments found or none found).
  func hasProcessedSession(_ sessionId: Int64) async -> Bool {
    guard let db = try? await ensureInitialized() else { return false }
    return (try? await db.read { database in
      let hasCommitments = try CommitmentRecord
        .filter(Column("sourceSessionId") == sessionId)
        .fetchCount(database) > 0
      guard !hasCommitments else { return true }
      return try ProcessedSessionRecord
        .filter(Column("sessionId") == sessionId)
        .fetchCount(database) > 0
    }) ?? false
  }

  /// Mark a session as processed (no commitments found), so it won't be re-scanned.
  /// Idempotent — safe to call multiple times for the same session (INSERT OR IGNORE
  /// on the unique sessionId column). Retries, duplicate completion hooks, and
  /// overlapping backfill/finalization paths must not turn "already processed" into an error.
  func markSessionProcessed(_ sessionId: Int64) async throws {
    let db = try await ensureInitialized()
    _ = try await db.write { database in
      try database.execute(
        sql: """
          INSERT OR IGNORE INTO processed_sessions (sessionId, processedAt)
          VALUES (?, ?)
          """,
        arguments: [sessionId, Date()]
      )
    }
  }

  /// Get IDs of completed, synced sessions that have neither commitments extracted
  /// nor a processed-session marker. Used for the "scan past conversations" backfill.
  func getUnprocessedCompletedSessionIds(limit: Int = 20) async throws -> [Int64] {
    let db = try await ensureInitialized()
    return try await db.read { database in
      try Int64.fetchAll(
        database,
        sql: """
          SELECT s.id FROM transcription_sessions s
          WHERE s.backendSynced = 1
            AND s.deleted = 0
            AND s.discarded = 0
            AND s.id NOT IN (
              SELECT DISTINCT sourceSessionId FROM commitments
              WHERE sourceSessionId IS NOT NULL
            )
            AND s.id NOT IN (
              SELECT DISTINCT sessionId FROM processed_sessions
            )
          ORDER BY s.startedAt DESC
          LIMIT ?
          """,
        arguments: [limit]
      )
    }
  }
}
