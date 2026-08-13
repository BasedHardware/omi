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
  case purgeFailed
}

/// SQL selection used by deterministic GC. Keeping selection separate from
/// deletion makes the active-visit protection directly testable without
/// invoking the singleton database actor.
enum ContextBucketGarbageCollection {
  static func staleBucketIDs(in db: Database, before cutoff: Date) throws -> [String] {
    try String.fetchAll(
      db,
      sql: """
        SELECT context_buckets.id FROM context_buckets
        WHERE lastVisitedAt IS NOT NULL AND lastVisitedAt < ?
          AND NOT EXISTS (
            SELECT 1 FROM context_visits
            WHERE context_visits.bucketID = context_buckets.id AND outcome = 'active'
          )
        """,
      arguments: [cutoff])
  }

  static func overflowBucketIDs(in db: Database, keeping: Int) throws -> [String] {
    try String.fetchAll(
      db,
      sql: """
        SELECT context_buckets.id FROM context_buckets
        WHERE NOT EXISTS (
          SELECT 1 FROM context_visits
          WHERE context_visits.bucketID = context_buckets.id AND outcome = 'active'
        )
        ORDER BY COALESCE(lastVisitedAt, createdAt) DESC
        LIMIT -1 OFFSET ?
        """,
      arguments: [max(0, keeping)])
  }
}

/// Resolves the durable bucket for a visit identity. Extracted so subject/bucket
/// consistency after explicit rebinding is testable without the singleton store.
enum ContextBucketVisitResolver {
  static func persistedBucketID(
    in db: Database,
    visitID: Int64,
    contextGeneration: Int64,
    poolEpoch: Int
  ) throws -> String? {
    try String.fetchOne(
      db,
      sql: """
        SELECT bucketID FROM context_visits
        WHERE id = ? AND contextGeneration = ? AND poolEpoch = ? AND outcome = 'active'
        """,
      arguments: [visitID, contextGeneration, poolEpoch])
  }

  static func resolveBucketID(
    in db: Database,
    referenceHash: String,
    normalizedTitle: String?,
    startedAt: Date
  ) throws -> String? {
    let binding = try Row.fetchOne(
      db,
      sql: "SELECT * FROM subject_bindings WHERE referenceHash = ?",
      arguments: [referenceHash])
    let subjectKind: String = binding?["subjectKind"] ?? "context"
    let subjectID: String = binding?["subjectID"] ?? referenceHash
    let workstreamID: String? = binding?["workstreamID"]
    let confidence: Double = binding?["confidence"] ?? 0.5
    let source: String = binding?["source"] ?? "repeat_cooccurrence"

    if let existing: String = binding?["bucketID"] {
      let consistent =
        try Bool.fetchOne(
          db,
          sql: """
            SELECT EXISTS(
              SELECT 1 FROM context_buckets
              WHERE id = ? AND subjectKind = ? AND subjectID = ? AND workstreamID IS ?
            )
            """,
          arguments: [existing, subjectKind, subjectID, workstreamID]) ?? false
      if consistent { return existing }
      // Explicit rebinding can leave a stale bucketID pointing at the previous
      // subject. Fall through and re-resolve for the binding's current subject.
    }

    guard normalizedTitle != nil else { return nil }
    // A subject binding (including explicit_open) already owns this identity, so
    // do not require a prior completed visit before attaching the subject bucket.
    if binding == nil {
      let recentCutoff = startedAt.addingTimeInterval(-7 * 24 * 60 * 60)
      let previousVisits =
        try Int.fetchOne(
          db,
          sql:
            "SELECT COUNT(*) FROM context_visits WHERE referenceHash = ? AND outcome = 'completed' AND startedAt >= ?",
          arguments: [referenceHash, recentCutoff]) ?? 0
      guard previousVisits >= 1 else { return nil }
    }

    let id = UUID().uuidString.lowercased()
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
    // Blank/noise-only titles must not share `"app::"` → one referenceHash. Ephemeral
    // hashes keep visit rows unique and skip durable binding/bucket lookup.
    let referenceHash =
      normalizedKey.map(Self.referenceHash) ?? "ephemeral:\(UUID().uuidString.lowercased())"
    let bucketID = try await pool.write { db -> String? in
      guard normalizedKey != nil else { return nil }
      return try ContextBucketVisitResolver.resolveBucketID(
        in: db,
        referenceHash: referenceHash,
        normalizedTitle: normalizedTitle,
        startedAt: startedAt)
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
          contextGeneration, poolEpoch, bucketID, appName, rawKey, normalizedKey ?? "",
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
      let stale = try ContextBucketGarbageCollection.staleBucketIDs(
        in: db, before: now.addingTimeInterval(-30 * 24 * 60 * 60))
      for id in stale {
        try db.execute(sql: "DELETE FROM context_buckets WHERE id = ?", arguments: [id])
      }
      let overflow = try ContextBucketGarbageCollection.overflowBucketIDs(in: db, keeping: 250)
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
          let snapshot = try Self.snapshot(in: db, bucketID: bucketID, now: Date())
        else { return nil }
        return snapshot
      }
    } catch {
      logError("ContextBucketStore: failed to read snapshot", error: error)
      return nil
    }
  }

  static func snapshot(in db: Database, bucketID: String, now: Date = Date()) throws
    -> ContextBucketSnapshot?
  {
    guard
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
            AND (expiresAt IS NULL OR expiresAt > ?)
          ORDER BY createdAt DESC LIMIT 20
        """,
      arguments: [bucketID, now])
    let worthiness =
      try Double.fetchOne(
        db,
        sql: """
          SELECT MAX(notifyWorthiness) FROM bucket_facts
          WHERE bucketID = ? AND validityState = 'validated'
            AND (expiresAt IS NULL OR expiresAt > ?)
          """,
        arguments: [bucketID, now]) ?? 0
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

  func snapshot(for fence: ContextVisitFence) async -> ContextBucketSnapshot? {
    let (pool, generation) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool, generation == fence.poolEpoch, let fenceBucketID = fence.bucketID else { return nil }
    return try? await pool.read { db in
      let persistedBucketID = try ContextBucketVisitResolver.persistedBucketID(
        in: db,
        visitID: fence.visitID,
        contextGeneration: fence.contextGeneration,
        poolEpoch: fence.poolEpoch)
      guard persistedBucketID == fenceBucketID else { return nil }
      return try Self.snapshot(in: db, bucketID: fenceBucketID, now: Date())
    }
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

  func validatedFactIDs(
    _ ids: [String], snapshotFacts: [String], bucketID: String, now: Date = Date()
  ) async -> [String] {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return [] }
    return
      (try? await pool.read { db in
        try Self.validatedFactIDs(
          ids, snapshotFacts: snapshotFacts, bucketID: bucketID, now: now, in: db)
      }) ?? []
  }

  static func validatedFactIDs(
    _ ids: [String],
    snapshotFacts: [String],
    bucketID: String,
    now: Date = Date(),
    in db: Database
  ) throws -> [String] {
    let normalized = ids.map { $0.hasPrefix("fact:") ? String($0.dropFirst(5)) : $0 }
    let snapshotIDs = Set(snapshotFacts.compactMap(Self.snapshotFactID))
    let citedSnapshotIDs = normalized.filter { snapshotIDs.contains($0) }
    guard !citedSnapshotIDs.isEmpty else { return [] }
    var arguments: StatementArguments = [bucketID, now]
    arguments += StatementArguments(citedSnapshotIDs)
    let rows = try String.fetchAll(
      db,
      sql: """
        SELECT id FROM bucket_facts
        WHERE bucketID = ? AND validityState = 'validated'
          AND (expiresAt IS NULL OR expiresAt > ?)
          AND id IN (\(citedSnapshotIDs.map { _ in "?" }.joined(separator: ",")))
        """,
      arguments: arguments)
    let allowed = Set(rows)
    return citedSnapshotIDs.filter { allowed.contains($0) }.map { "fact:\($0)" }
  }

  private static func snapshotFactID(_ fact: String) -> String? {
    guard fact.hasPrefix("fact:") else { return nil }
    let id = fact.dropFirst(5).prefix { !$0.isWhitespace }
    return id.isEmpty ? nil : String(id)
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
