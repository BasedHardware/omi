import GRDB
import XCTest

@testable import Omi_Computer

final class ContextBucketRecentDeliveryTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "recent-delivery-prompt")
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testAssembledPromptIncludesRecentDeliveriesFromTheLedger() async throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let versionID = try await seedBucket(now: now)
    try await seedDelivered(
      id: "first",
      visitID: 1,
      versionID: versionID,
      decisionType: "resurface",
      message: "Keep the investigation open",
      deliveredAt: now.addingTimeInterval(-65),
      now: now)
    try await seedDelivered(
      id: "second",
      visitID: 2,
      versionID: versionID,
      decisionType: "insight",
      message: "Status changed",
      deliveredAt: now.addingTimeInterval(-26 * 60),
      now: now)

    let recent = await ContextBucketStore.shared.recentDeliveredForBucket(
      bucketID: "bucket", now: now)
    let prompt = ContextProactivityPromptBuilder.directorPrompt(
      snapshot: snapshot(versionID: versionID),
      tasks: [],
      frame: CapturedFrame(jpegData: Data(), appName: "Notes", frameNumber: 1, captureTime: now),
      recentDeliveries: recent)

    XCTAssertEqual(recent.map(\.decisionType), ["resurface", "insight"])
    XCTAssertEqual(
      ContextProactivityPromptBuilder.recentDeliveriesSection(recent, now: now),
      """
      == RECENTLY DELIVERED FOR THIS BUCKET ==
      - resurface (1m ago): Keep the investigation open
      - insight (26m ago): Status changed
      """)
    XCTAssertTrue(
      prompt.hasSuffix(
        """
        == RECENTLY DELIVERED FOR THIS BUCKET ==
        - resurface (1m ago): Keep the investigation open
        - insight (26m ago): Status changed
        """))
  }

  func testAssembledPromptOmitsRecentSectionWhenLedgerHasNone() async throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let versionID = try await seedBucket(now: now)
    let recent = await ContextBucketStore.shared.recentDeliveredForBucket(
      bucketID: "bucket", now: now)
    let prompt = ContextProactivityPromptBuilder.directorPrompt(
      snapshot: snapshot(versionID: versionID),
      tasks: [],
      frame: CapturedFrame(jpegData: Data(), appName: "Notes", frameNumber: 1, captureTime: now),
      recentDeliveries: recent)

    XCTAssertEqual(recent, [])
    XCTAssertNil(ContextProactivityPromptBuilder.recentDeliveriesSection(recent, now: now))
    XCTAssertFalse(prompt.contains("== RECENTLY DELIVERED FOR THIS BUCKET =="))
  }

  func testAssembledPromptCapsRecentDeliveriesAtThree() async throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let versionID = try await seedBucket(now: now)
    for index in 0..<5 {
      try await seedDelivered(
        id: "nudge-\(index)",
        visitID: Int64(index + 1),
        versionID: versionID,
        decisionType: "resurface",
        message: "nudge-\(index)",
        deliveredAt: now.addingTimeInterval(TimeInterval(-60 * (index + 1))),
        now: now)
    }

    let recent = await ContextBucketStore.shared.recentDeliveredForBucket(
      bucketID: "bucket", now: now)
    let prompt = ContextProactivityPromptBuilder.directorPrompt(
      snapshot: snapshot(versionID: versionID),
      tasks: [],
      frame: CapturedFrame(jpegData: Data(), appName: "Notes", frameNumber: 1, captureTime: now),
      recentDeliveries: recent)

    XCTAssertEqual(recent.map(\.message), ["nudge-0", "nudge-1", "nudge-2"])
    XCTAssertEqual(recent.count, ContextBucketRecentDelivery.promptCap)
    XCTAssertEqual(
      ContextProactivityPromptBuilder.recentDeliveriesSection(recent, now: now),
      """
      == RECENTLY DELIVERED FOR THIS BUCKET ==
      - resurface (1m ago): nudge-0
      - resurface (2m ago): nudge-1
      - resurface (3m ago): nudge-2
      """)
    XCTAssertFalse(prompt.contains("nudge-3"))
    XCTAssertFalse(prompt.contains("nudge-4"))
  }

  private func snapshot(versionID: Int64) -> ContextBucketSnapshot {
    ContextBucketSnapshot(
      bucketID: "bucket",
      versionID: versionID,
      version: 1,
      header: "header",
      frozenRankedSegment: Data(),
      tail: [],
      validatedFacts: ["fact"],
      notifyWorthiness: 1)
  }

  private func seedBucket(now: Date) async throws -> Int64 {
    let (database, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let pool = try XCTUnwrap(database)
    return try await pool.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_buckets (id, subjectKind, subjectID, createdAt, updatedAt)
          VALUES ('bucket', 'task', 'recent-delivery', ?, ?)
          """,
        arguments: [now, now])
      try db.execute(
        sql: """
          INSERT INTO bucket_versions (bucketID, version, header, frozenRankedSegment, createdAt)
          VALUES ('bucket', 1, 'header', ?, ?)
          """,
        arguments: [Data(), now])
      for visitID in 1...5 {
        try db.execute(
          sql: """
            INSERT INTO context_visits
              (id, contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
               normalizedContextKey, referenceHash, startedAt, outcome, createdAt, updatedAt)
            VALUES (?, 1, ?, 'bucket', 'Notes', ?, ?, ?, ?, 'completed', ?, ?)
            """,
          arguments: [
            visitID, poolEpoch, "raw-\(visitID)", "normalized-\(visitID)", "ref-\(visitID)", now, now,
            now,
          ])
      }
      return try Int64.fetchOne(
        db,
        sql: "SELECT id FROM bucket_versions WHERE bucketID = 'bucket' AND version = 1")
        ?? 0
    }
  }

  private func seedDelivered(
    id: String,
    visitID: Int64,
    versionID: Int64,
    decisionType: String,
    message: String,
    deliveredAt: Date,
    now: Date
  ) async throws {
    let (database, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let pool = try XCTUnwrap(database)
    try await pool.write { db in
      try db.execute(
        sql: """
          INSERT INTO proactive_deliveries
            (id, visitID, bucketID, bucketVersionID, decisionType, lifecycleState,
             provenanceJson, message, attemptedAt, deliveredAt, expiresAt, createdAt)
          VALUES (?, ?, 'bucket', ?, ?, 'delivered', '{}', ?, ?, ?, ?, ?)
          """,
        arguments: [
          id, visitID, versionID, decisionType, message, deliveredAt, deliveredAt,
          now.addingTimeInterval(30 * 24 * 60 * 60), deliveredAt,
        ])
    }
  }
}
