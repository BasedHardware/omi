import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

/// Fast, database-backed lifecycle coverage for the context-director reservation gate.
/// These tests exercise the same actor/store API that runs immediately before the
/// director model request; they intentionally do not invoke a frontier model.
final class ContextDeliveryLifecycleTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "context-delivery-lifecycle")
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testConcurrentBeginAttemptsReserveOneRowAndRejectTheLoserAsDuplicate() async throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let (database, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let pool = try XCTUnwrap(database)
    let versionID = try await seedBucketAndVisit(in: pool, poolEpoch: poolEpoch, now: now)
    let fence = ContextVisitFence(
      visitID: 1,
      contextGeneration: 1,
      poolEpoch: poolEpoch,
      bucketID: "bucket",
      startedAt: now)
    let snapshot = ContextBucketSnapshot(
      bucketID: "bucket",
      versionID: versionID,
      version: 1,
      header: "header",
      frozenRankedSegment: Data(),
      tail: ["entry:one"],
      validatedFacts: ["fact:one statement"],
      notifyWorthiness: 1)
    let gate = allowedGate()

    async let first = ContextBucketStore.shared.beginDeliveryAttempt(
      fence: fence, snapshot: snapshot, gate: gate, now: now)
    async let second = ContextBucketStore.shared.beginDeliveryAttempt(
      fence: fence, snapshot: snapshot, gate: gate, now: now)
    let attempts = try await [first, second]

    XCTAssertEqual(attempts.filter { $0.reason == .allowed }.count, 1)
    XCTAssertEqual(attempts.filter { $0.reason == .duplicate }.count, 1)
    XCTAssertEqual(attempts.compactMap(\.id).count, 1)

    let rowCount = try await pool.read { db in
      try Int.fetchOne(
        db,
        sql: "SELECT COUNT(*) FROM proactive_deliveries WHERE visitID = 1 AND bucketVersionID = ?",
        arguments: [versionID])
    }
    XCTAssertEqual(rowCount, 1, "the duplicate gate must not spend a second director reservation")
  }

  func testDeliveredCooldownRejectsBeforeReservation() async throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let (database, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let pool = try XCTUnwrap(database)
    let versionID = try await seedBucketAndVisit(in: pool, poolEpoch: poolEpoch, now: now)
    try await pool.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_visits
            (id, contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
             normalizedContextKey, referenceHash, startedAt, outcome, createdAt, updatedAt)
          VALUES (2, 1, ?, 'bucket', 'Lifecycle Test', 'raw-2', 'normalized-2', 'reference-2', ?, 'completed', ?, ?)
          """,
        arguments: [poolEpoch, now, now, now])
      try db.execute(
        sql: """
          INSERT INTO proactive_deliveries
            (id, visitID, bucketID, bucketVersionID, decisionType, lifecycleState,
             provenanceJson, attemptedAt, deliveredAt, expiresAt, createdAt)
          VALUES ('already-delivered', 2, 'bucket', ?, 'suggest', 'delivered', '{}', ?, ?, ?, ?)
          """,
        arguments: [
          versionID,
          now.addingTimeInterval(-60),
          now.addingTimeInterval(-30),
          now.addingTimeInterval(30 * 24 * 60 * 60),
          now.addingTimeInterval(-30),
        ])
    }

    let fence = ContextVisitFence(
      visitID: 1,
      contextGeneration: 1,
      poolEpoch: poolEpoch,
      bucketID: "bucket",
      startedAt: now)
    let snapshot = ContextBucketSnapshot(
      bucketID: "bucket",
      versionID: versionID,
      version: 1,
      header: "header",
      frozenRankedSegment: Data(),
      tail: [],
      validatedFacts: ["fact:one statement"],
      notifyWorthiness: 1)

    let result = try await ContextBucketStore.shared.beginDeliveryAttempt(
      fence: fence,
      snapshot: snapshot,
      gate: ContextDeliveryGateInput(
        masterEnabled: true,
        frequencyLevel: 3,
        snoozed: false,
        paywalled: false,
        cooldownSeconds: 10 * 60),
      now: now)

    XCTAssertEqual(result, ContextDeliveryAttempt(id: nil, reason: .cooldown))
    let rowCount = try await pool.read { db in
      try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM proactive_deliveries")
    }
    XCTAssertEqual(rowCount, 1, "cooldown must stop before writing another attempted row")
  }

  func testInFlightAttemptAlsoAnchorsCooldownBeforeAnotherModelReservation() async throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let (database, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let pool = try XCTUnwrap(database)
    let firstVersionID = try await seedBucketAndVisit(in: pool, poolEpoch: poolEpoch, now: now)
    let secondVersionID = try await seedSecondVersion(in: pool, bucketID: "bucket", now: now)
    try await pool.write { db in
      try db.execute(
        sql: """
          INSERT INTO proactive_deliveries
            (id, visitID, bucketID, bucketVersionID, decisionType, lifecycleState,
             provenanceJson, attemptedAt, expiresAt, createdAt)
          VALUES ('in-flight', 1, 'bucket', ?, 'pending', 'attempted', '{}', ?, ?, ?)
          """,
        arguments: [
          firstVersionID,
          now.addingTimeInterval(-30),
          now.addingTimeInterval(30 * 24 * 60 * 60),
          now.addingTimeInterval(-30),
        ])
    }

    let fence = ContextVisitFence(
      visitID: 2,
      contextGeneration: 1,
      poolEpoch: poolEpoch,
      bucketID: "bucket",
      startedAt: now)
    let snapshot = ContextBucketSnapshot(
      bucketID: "bucket",
      versionID: secondVersionID,
      version: 2,
      header: "header",
      frozenRankedSegment: Data(),
      tail: [],
      validatedFacts: ["fact:one statement"],
      notifyWorthiness: 1)

    let result = try await ContextBucketStore.shared.beginDeliveryAttempt(
      fence: fence,
      snapshot: snapshot,
      gate: ContextDeliveryGateInput(
        masterEnabled: true,
        frequencyLevel: 4,
        snoozed: false,
        paywalled: false,
        cooldownSeconds: 3 * 60),
      now: now)

    XCTAssertEqual(result, ContextDeliveryAttempt(id: nil, reason: .cooldown))
  }

  private func allowedGate() -> ContextDeliveryGateInput {
    ContextDeliveryGateInput(
      masterEnabled: true,
      frequencyLevel: 5,
      snoozed: false,
      paywalled: false,
      cooldownSeconds: 0)
  }

  private func seedBucketAndVisit(
    in pool: DatabasePool,
    poolEpoch: Int,
    now: Date
  ) async throws -> Int64 {
    try await pool.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_buckets (id, subjectKind, subjectID, createdAt, updatedAt)
          VALUES ('bucket', 'task', 'lifecycle-test', ?, ?)
          """,
        arguments: [now, now])
      try db.execute(
        sql: """
          INSERT INTO bucket_versions (bucketID, version, header, frozenRankedSegment, createdAt)
          VALUES ('bucket', 1, 'header', ?, ?)
          """,
        arguments: [Data(), now])
      try db.execute(
        sql: """
          INSERT INTO context_visits
            (id, contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
             normalizedContextKey, referenceHash, startedAt, outcome, createdAt, updatedAt)
          VALUES (1, 1, ?, 'bucket', 'Lifecycle Test', 'raw', 'normalized', 'reference', ?, 'active', ?, ?)
          """,
        arguments: [poolEpoch, now, now, now])
      return try Int64.fetchOne(
        db,
        sql: "SELECT id FROM bucket_versions WHERE bucketID = 'bucket' AND version = 1")
        ?? 0
    }
  }

  private func seedSecondVersion(in pool: DatabasePool, bucketID: String, now: Date) async throws -> Int64 {
    try await pool.write { db in
      try db.execute(
        sql: """
          INSERT INTO bucket_versions (bucketID, version, header, frozenRankedSegment, createdAt)
          VALUES (?, 2, 'header-v2', ?, ?)
          """,
        arguments: [bucketID, Data(), now])
      return try Int64.fetchOne(
        db,
        sql: "SELECT id FROM bucket_versions WHERE bucketID = ? AND version = 2",
        arguments: [bucketID])
        ?? 0
    }
  }
}
