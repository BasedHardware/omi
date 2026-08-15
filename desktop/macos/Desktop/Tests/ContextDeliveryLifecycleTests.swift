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
        paywalled: false,
        cooldownSeconds: 3 * 60),
      now: now)

    XCTAssertEqual(result, ContextDeliveryAttempt(id: nil, reason: .cooldown))
  }

  func testDailyBudgetIgnoresInvisibleOutcomesButCountsVisibleSpend() async throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let (database, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let pool = try XCTUnwrap(database)
    let versionID = try await seedBucketAndVisit(in: pool, poolEpoch: poolEpoch, now: now)
    let gate = ContextDeliveryGateInput(
      masterEnabled: true,
      frequencyLevel: 1,
      paywalled: false,
      cooldownSeconds: 0)
    let limit = gate.dailyLimit
    try await pool.write { db in
      for index in 0..<(limit + 2) {
        try db.execute(
          sql: """
            INSERT INTO proactive_deliveries
              (id, visitID, bucketID, bucketVersionID, decisionType, lifecycleState,
               provenanceJson, attemptedAt, expiresAt, createdAt)
            VALUES (?, NULL, 'bucket', ?, 'silence', 'suppressed', '{}', ?, ?, ?)
            """,
          arguments: [
            "silence-\(index)", versionID,
            now.addingTimeInterval(-3_600), now.addingTimeInterval(3_600),
            now.addingTimeInterval(-3_600),
          ])
      }
    }
    let snapshot = ContextBucketSnapshot(
      bucketID: "bucket",
      versionID: versionID,
      version: 1,
      header: "header",
      frozenRankedSegment: Data(),
      tail: [],
      validatedFacts: ["fact:one statement"],
      notifyWorthiness: 1)

    let afterSilences = try await ContextBucketStore.shared.beginDeliveryAttempt(
      fence: ContextVisitFence(
        visitID: 1, contextGeneration: 1, poolEpoch: poolEpoch, bucketID: "bucket",
        startedAt: now),
      snapshot: snapshot, gate: gate, now: now)
    XCTAssertEqual(
      afterSilences.reason, .allowed,
      "silent evaluations never reached the user, so they must not spend the daily budget")

    try await pool.write { db in
      for index in 0..<limit {
        try db.execute(
          sql: """
            INSERT INTO proactive_deliveries
              (id, visitID, bucketID, bucketVersionID, decisionType, lifecycleState,
               provenanceJson, attemptedAt, deliveredAt, expiresAt, createdAt)
            VALUES (?, NULL, 'bucket', ?, 'insight', 'delivered', '{}', ?, ?, ?, ?)
            """,
          arguments: [
            "visible-\(index)", versionID,
            now.addingTimeInterval(-7_200), now.addingTimeInterval(-7_200),
            now.addingTimeInterval(3_600), now.addingTimeInterval(-7_200),
          ])
      }
    }

    let afterVisible = try await ContextBucketStore.shared.beginDeliveryAttempt(
      fence: ContextVisitFence(
        visitID: 2, contextGeneration: 1, poolEpoch: poolEpoch, bucketID: "bucket",
        startedAt: now),
      snapshot: snapshot, gate: gate, now: now)
    XCTAssertEqual(afterVisible, ContextDeliveryAttempt(id: nil, reason: .dailyBudget))
  }

  /// The rehearsal replay of the measured field failure: a 13-second revisit
  /// settles at +8s, the user leaves at +13s, and the in-flight evaluation used
  /// to die at the next active-only guard — quota spent, nothing delivered.
  /// With run-to-completion freshness the departed-but-recent visit still
  /// assembles its snapshot and reserves a delivery attempt.
  func testVisitThatCompletedFiveSecondsAgoStillReservesADeliveryAttempt() async throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let (database, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let pool = try XCTUnwrap(database)
    let versionID = try await seedBucketAndVisit(in: pool, poolEpoch: poolEpoch, now: now)
    try await pool.write { db in
      try db.execute(
        sql: "UPDATE context_visits SET outcome = 'completed', endedAt = ? WHERE id = 1",
        arguments: [now.addingTimeInterval(-5)])
    }
    let fence = ContextVisitFence(
      visitID: 1,
      contextGeneration: 1,
      poolEpoch: poolEpoch,
      bucketID: "bucket",
      startedAt: now.addingTimeInterval(-18))

    let freshness = await ContextBucketStore.shared.fenceFreshness(fence, now: now)
    XCTAssertEqual(
      freshness, ContextVisitFreshness(fresh: true, endedAt: now.addingTimeInterval(-5)))

    let snapshot = await ContextBucketStore.shared.snapshot(for: fence)
    XCTAssertNotNil(
      snapshot, "the snapshot path must resolve a completed visit's bucket, not only an active one")

    let attempt = try await ContextBucketStore.shared.beginDeliveryAttempt(
      fence: fence,
      snapshot: try XCTUnwrap(snapshot),
      gate: allowedGate(),
      now: now)
    XCTAssertEqual(attempt.reason, .allowed)
    XCTAssertNotNil(attempt.id)

    let rowCount = try await pool.read { db in
      try Int.fetchOne(
        db,
        sql: "SELECT COUNT(*) FROM proactive_deliveries WHERE visitID = 1 AND bucketVersionID = ?",
        arguments: [versionID])
    }
    XCTAssertEqual(rowCount, 1, "run-to-completion must create the reservation row")
  }

  func testVisitThatCompletedTwoMinutesAgoIsStaleAtTheNextGuard() async throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let (database, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let pool = try XCTUnwrap(database)
    _ = try await seedBucketAndVisit(in: pool, poolEpoch: poolEpoch, now: now)
    try await pool.write { db in
      try db.execute(
        sql: "UPDATE context_visits SET outcome = 'completed', endedAt = ? WHERE id = 1",
        arguments: [now.addingTimeInterval(-120)])
    }
    let fence = ContextVisitFence(
      visitID: 1,
      contextGeneration: 1,
      poolEpoch: poolEpoch,
      bucketID: "bucket",
      startedAt: now.addingTimeInterval(-133))

    let freshness = await ContextBucketStore.shared.fenceFreshness(fence, now: now)
    XCTAssertEqual(
      freshness, ContextVisitFreshness(fresh: false, endedAt: now.addingTimeInterval(-120)))
  }

  private func allowedGate() -> ContextDeliveryGateInput {
    ContextDeliveryGateInput(
      masterEnabled: true,
      frequencyLevel: 5,
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
