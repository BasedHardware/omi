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

    let timeZone = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
    let recent = await ContextBucketStore.shared.recentDeliveredForBucket(
      bucketID: "bucket", now: now)
    let prompt = ContextProactivityPromptBuilder.directorPrompt(
      snapshot: snapshot(versionID: versionID),
      tasks: [],
      frame: CapturedFrame(jpegData: Data(), appName: "Notes", frameNumber: 1, captureTime: now),
      recentDeliveries: recent,
      timeZone: timeZone)

    XCTAssertEqual(recent.map(\.decisionType), ["resurface", "insight"])
    XCTAssertEqual(
      ContextProactivityPromptBuilder.recentDeliveriesSection(recent, timeZone: timeZone),
      """
      == RECENTLY DELIVERED FOR THIS BUCKET ==
      Do not re-send any of these points, even reworded.
      - resurface (2027-01-15 02:58 EST): Keep the investigation open
      - insight (2027-01-15 02:34 EST): Status changed
      """)
    XCTAssertTrue(
      prompt.hasSuffix(
        """
        == RECENTLY DELIVERED FOR THIS BUCKET ==
        Do not re-send any of these points, even reworded.
        - resurface (2027-01-15 02:58 EST): Keep the investigation open
        - insight (2027-01-15 02:34 EST): Status changed
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
    XCTAssertNil(ContextProactivityPromptBuilder.recentDeliveriesSection(recent))
    XCTAssertFalse(prompt.contains("== RECENTLY DELIVERED FOR THIS BUCKET =="))
  }

  func testAssembledPromptCapsRecentDeliveriesAtPromptCap() async throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let versionID = try await seedBucket(now: now)
    for index in 0..<(ContextBucketRecentDelivery.promptCap + 2) {
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

    XCTAssertEqual(
      recent.map(\.message),
      (0..<ContextBucketRecentDelivery.promptCap).map { "nudge-\($0)" })
    XCTAssertEqual(recent.count, ContextBucketRecentDelivery.promptCap)
    XCTAssertEqual(recent.count, 15, "the enlarged window is what makes the no-repeat rule enforceable")
    XCTAssertTrue(prompt.contains("nudge-14"))
    XCTAssertFalse(prompt.contains("nudge-15"))
    XCTAssertFalse(prompt.contains("nudge-16"))
  }

  func testRecentDeliveriesSurviveExpiryInsideTheLookbackAndDropOutsideIt() async throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let versionID = try await seedBucket(now: now)
    try await seedDelivered(
      id: "expired-but-recent",
      visitID: 1,
      versionID: versionID,
      decisionType: "insight",
      message: "the beta rollout is still incomplete because the legacy PostHog path is live",
      deliveredAt: now.addingTimeInterval(-2 * 60 * 60),
      now: now,
      expiresAt: now.addingTimeInterval(-60))
    try await seedDelivered(
      id: "outside-lookback",
      visitID: 2,
      versionID: versionID,
      decisionType: "insight",
      message: "an older point from yesterday",
      deliveredAt: now.addingTimeInterval(-(ContextBucketRecentDelivery.memoryLookback + 60)),
      now: now,
      expiresAt: now.addingTimeInterval(30 * 24 * 60 * 60))

    let recent = await ContextBucketStore.shared.recentDeliveredForBucket(
      bucketID: "bucket", now: now)
    XCTAssertEqual(
      recent.map(\.message),
      ["the beta rollout is still incomplete because the legacy PostHog path is live"])
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
      for visitID in 1...(ContextBucketRecentDelivery.promptCap + 2) {
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
    now: Date,
    expiresAt: Date? = nil
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
          expiresAt ?? now.addingTimeInterval(30 * 24 * 60 * 60), deliveredAt,
        ])
    }
  }
}
