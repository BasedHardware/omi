import CryptoKit
import Foundation
@preconcurrency import GRDB

struct ContextVisitFence: Equatable, Sendable {
  let visitID: Int64
  let contextGeneration: Int64
  let poolEpoch: Int
  let bucketID: String?
  let startedAt: Date
}

struct ContextBucketSnapshot: Equatable, Sendable {
  let bucketID: String
  let versionID: Int64
  let version: Int
  let header: String
  let frozenRankedSegment: Data
  let tail: [String]
  let validatedFacts: [String]
  let notifyWorthiness: Double
}

enum ContextBucketStoreError: Error {
  case databaseUnavailable
  case staleFence
}

actor ContextBucketStore {
  static let shared = ContextBucketStore()

  private init() {}

  func startVisit(
    appName: String,
    windowTitle: String?,
    contextGeneration: Int64,
    startedAt: Date = Date()
  ) async throws -> ContextVisitFence {
    let (pool, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw ContextBucketStoreError.databaseUnavailable }
    let normalizedTitle = ContextTitleNormalizer.normalize(windowTitle, appName: appName)
    let normalizedKey = ContextTitleNormalizer.identityKey(appName: appName, windowTitle: windowTitle)
    let rawKey = "\(appName)\n\(windowTitle ?? "")"
    let referenceHash = Self.referenceHash(normalizedKey)
    let bucketID = try await pool.write { db -> String? in
      let binding = try Row.fetchOne(
        db,
        sql: "SELECT * FROM subject_bindings WHERE referenceHash = ?",
        arguments: [referenceHash])
      let existing: String? = binding?["bucketID"]
      if let existing { return existing }
      guard normalizedTitle != nil else { return nil }
      let recentCutoff = startedAt.addingTimeInterval(-7 * 24 * 60 * 60)
      let previousVisits =
        try Int.fetchOne(
          db,
          sql:
            "SELECT COUNT(*) FROM context_visits WHERE referenceHash = ? AND outcome = 'completed' AND startedAt >= ?",
          arguments: [referenceHash, recentCutoff]) ?? 0
      guard previousVisits >= 1 else { return nil }
      let id = UUID().uuidString.lowercased()
      let subjectKind: String = binding?["subjectKind"] ?? "context"
      let subjectID: String = binding?["subjectID"] ?? referenceHash
      let workstreamID: String? = binding?["workstreamID"]
      let confidence: Double = binding?["confidence"] ?? 0.5
      let source: String = binding?["source"] ?? "repeat_cooccurrence"
      let existingSubjectBucket = try String.fetchOne(
        db,
        sql: """
          SELECT id FROM context_buckets
          WHERE subjectKind = ? AND subjectID = ? AND workstreamID IS ?
          LIMIT 1
          """,
        arguments: [subjectKind, subjectID, workstreamID])
      let resolvedBucketID = existingSubjectBucket ?? id
      if existingSubjectBucket == nil {
        try db.execute(
          sql: """
            INSERT INTO context_buckets
              (id, subjectKind, subjectID, workstreamID, displayLabel, visitCount,
               lastVisitedAt, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, NULL, 0, ?, ?, ?)
            """,
          arguments: [resolvedBucketID, subjectKind, subjectID, workstreamID, startedAt, startedAt, startedAt])
      }
      try db.execute(
        sql: """
          INSERT INTO subject_bindings
            (referenceHash, bucketID, subjectKind, subjectID, confidence, source,
             occurrenceCount, createdAt, updatedAt)
          VALUES (?, ?, ?, ?, ?, ?, 2, ?, ?)
          ON CONFLICT(referenceHash) DO UPDATE SET
            bucketID = excluded.bucketID,
            occurrenceCount = subject_bindings.occurrenceCount + 1,
            updatedAt = excluded.updatedAt
          """,
        arguments: [
          referenceHash, resolvedBucketID, subjectKind, subjectID, confidence, source, startedAt, startedAt,
        ])
      return resolvedBucketID
    }
    let visitID = try await pool.write { db -> Int64 in
      try db.execute(
        sql: """
          INSERT INTO context_visits
            (contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
             normalizedContextKey, referenceHash, startedAt, outcome, createdAt, updatedAt)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
          """,
        arguments: [
          contextGeneration, poolEpoch, bucketID, appName, rawKey, normalizedKey,
          referenceHash, startedAt, startedAt, startedAt,
        ])
      return db.lastInsertedRowID
    }
    return ContextVisitFence(
      visitID: visitID,
      contextGeneration: contextGeneration,
      poolEpoch: poolEpoch,
      bucketID: bucketID,
      startedAt: startedAt)
  }

  func finalizeVisit(
    _ fence: ContextVisitFence,
    outcome: String = "completed",
    exitReason: String,
    lastScreenshotID: Int64?,
    endedAt: Date = Date()
  ) async throws {
    let pool = try await pool(for: fence)
    try await pool.write { db in
      try db.execute(
        sql: """
          UPDATE context_visits
          SET outcome = ?, exitReason = ?, endedAt = ?, lastScreenshotID = ?, updatedAt = ?
          WHERE id = ? AND contextGeneration = ? AND poolEpoch = ? AND outcome = 'active'
          """,
        arguments: [
          outcome, exitReason, endedAt, lastScreenshotID, endedAt, fence.visitID,
          fence.contextGeneration, fence.poolEpoch,
        ])
      guard db.changesCount == 1 else { throw ContextBucketStoreError.staleFence }
      if outcome == "completed", let bucketID = fence.bucketID {
        try db.execute(
          sql: """
            UPDATE context_buckets
            SET visitCount = visitCount + 1, lastVisitedAt = ?, updatedAt = ?
            WHERE id = ?
            """,
          arguments: [endedAt, endedAt, bucketID])
      }
    }
  }

  @discardableResult
  func reconcileInterruptedVisits(now: Date = Date()) async throws -> Int {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw ContextBucketStoreError.databaseUnavailable }
    return try await pool.write { db in
      try db.execute(
        sql: """
          UPDATE context_visits
          SET outcome = 'interrupted', exitReason = 'startup_reconcile', endedAt = ?, updatedAt = ?
          WHERE outcome = 'active'
          """,
        arguments: [now, now])
      return db.changesCount
    }
  }

  func runDeterministicGC(now: Date = Date()) async throws {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw ContextBucketStoreError.databaseUnavailable }
    try await pool.write { db in
      _ = try ContextBucketSchema.deleteExpiredDeliveries(in: db, now: now)
      try db.execute(
        sql: "DELETE FROM bucket_facts WHERE expiresAt IS NOT NULL AND expiresAt <= ?",
        arguments: [now])
      try db.execute(
        sql: "DELETE FROM context_buckets WHERE lastVisitedAt IS NOT NULL AND lastVisitedAt < ?",
        arguments: [now.addingTimeInterval(-30 * 24 * 60 * 60)])
      let overflow = try String.fetchAll(
        db,
        sql: """
            SELECT id FROM context_buckets ORDER BY COALESCE(lastVisitedAt, createdAt) DESC
            LIMIT -1 OFFSET 250
          """)
      for id in overflow {
        try db.execute(sql: "DELETE FROM context_buckets WHERE id = ?", arguments: [id])
      }
    }
  }

  func fenceIsValid(_ fence: ContextVisitFence) async -> Bool {
    do {
      let pool = try await pool(for: fence)
      return try await pool.read { db in
        try Bool.fetchOne(
          db,
          sql: """
            SELECT EXISTS(
              SELECT 1 FROM context_visits
              WHERE id = ? AND contextGeneration = ? AND poolEpoch = ?
                AND outcome IN ('active', 'completed')
            )
            """,
          arguments: [fence.visitID, fence.contextGeneration, fence.poolEpoch]) ?? false
      }
    } catch {
      return false
    }
  }

  func markVisitSettled(_ fence: ContextVisitFence, at date: Date = Date()) async throws {
    let pool = try await pool(for: fence)
    try await pool.write { db in
      try db.execute(
        sql: """
          UPDATE context_visits SET settledAt = COALESCE(settledAt, ?), updatedAt = ?
          WHERE id = ? AND contextGeneration = ? AND poolEpoch = ? AND outcome = 'active'
          """,
        arguments: [date, date, fence.visitID, fence.contextGeneration, fence.poolEpoch])
      guard db.changesCount == 1 else { throw ContextBucketStoreError.staleFence }
    }
  }

  func snapshot(forNormalizedKey key: String) async -> ContextBucketSnapshot? {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return nil }
    do {
      return try await pool.read { db in
        guard
          let bucketID: String = try String.fetchOne(
            db,
            sql: """
                SELECT bucketID FROM subject_bindings
                WHERE referenceHash = ? AND bucketID IS NOT NULL
              """,
            arguments: [Self.referenceHash(key)]),
          let version = try Row.fetchOne(
            db,
            sql: """
                SELECT id, version, header, frozenRankedSegment
                FROM bucket_versions WHERE bucketID = ? ORDER BY version DESC LIMIT 1
              """,
            arguments: [bucketID])
        else { return nil }
        let tail = try String.fetchAll(
          db,
          sql: """
            SELECT 'entry:' || id || ' ' || narrative FROM bucket_entries
              WHERE bucketID = ? AND isCompacted = 0 ORDER BY createdAt DESC LIMIT 5
            """,
          arguments: [bucketID]
        ).reversed()
        let facts = try String.fetchAll(
          db,
          sql: """
            SELECT 'fact:' || id || ' ' || statement ||
              ' [evidence: ' || evidenceText || '; refs: ' || evidenceRefsJson || ']'
            FROM bucket_facts
              WHERE bucketID = ? AND validityState = 'validated'
              ORDER BY createdAt DESC LIMIT 20
            """,
          arguments: [bucketID])
        let worthiness =
          try Double.fetchOne(
            db, sql: "SELECT notifyWorthiness FROM context_buckets WHERE id = ?", arguments: [bucketID]) ?? 0
        return ContextBucketSnapshot(
          bucketID: bucketID,
          versionID: version["id"],
          version: version["version"],
          header: version["header"],
          frozenRankedSegment: version["frozenRankedSegment"],
          tail: Array(tail),
          validatedFacts: facts,
          notifyWorthiness: worthiness)
      }
    } catch {
      logError("ContextBucketStore: failed to read snapshot", error: error)
      return nil
    }
  }

  func snapshot(for fence: ContextVisitFence) async -> ContextBucketSnapshot? {
    let (pool, generation) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool, generation == fence.poolEpoch else { return nil }
    guard
      let key = try? await pool.read({ db in
        try String.fetchOne(
          db,
          sql: "SELECT normalizedContextKey FROM context_visits WHERE id = ? AND contextGeneration = ?",
          arguments: [fence.visitID, fence.contextGeneration])
      })
    else { return nil }
    return await snapshot(forNormalizedKey: key)
  }

  func validatedEntryRefs(_ refs: [String], bucketID: String) async -> [String] {
    let normalized = refs.map { $0.hasPrefix("entry:") ? String($0.dropFirst(6)) : $0 }
    guard !normalized.isEmpty else { return [] }
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return [] }
    let rows =
      (try? await pool.read { db in
        try String.fetchAll(
          db,
          sql:
            "SELECT id FROM bucket_entries WHERE bucketID = ? AND id IN (\(normalized.map { _ in "?" }.joined(separator: ",")))",
          arguments: StatementArguments([bucketID] + normalized))
      }) ?? []
    let allowed = Set(rows)
    return normalized.filter { allowed.contains($0) }.map { "entry:\($0)" }
  }

  private func pool(for fence: ContextVisitFence) async throws -> DatabasePool {
    let (pool, generation) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool, generation == fence.poolEpoch else { throw ContextBucketStoreError.staleFence }
    return pool
  }

  static func referenceHash(_ normalizedKey: String) -> String {
    let digest = SHA256.hash(data: Data(normalizedKey.utf8))
      .map { String(format: "%02x", $0) }.joined()
    return "sha256:\(digest)"
  }
}
