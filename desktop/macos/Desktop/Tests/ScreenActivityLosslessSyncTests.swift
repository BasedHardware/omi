import GRDB
import XCTest

@testable import Omi_Computer

final class ScreenActivityLosslessSyncTests: XCTestCase {
  func testMigrationPreservesPopulatedLegacyRowsAndStartsThemPending() throws {
    let queue = try makeLegacyQueue()
    try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO screenshots (timestamp, appName, windowTitle, ocrText, embedding, deviceName, clientDeviceId)
          VALUES (?, ?, ?, ?, NULL, ?, ?)
          """,
        arguments: [
          Date(timeIntervalSince1970: 1_700_000_000), "SyntheticApp", "SyntheticWindow", "legacy text", "Test Mac",
          "test-device",
        ])

      try RewindDatabase.installScreenActivitySyncStateSchema(db)

      let row = try XCTUnwrap(Row.fetchOne(db, sql: "SELECT * FROM screenshots"))
      XCTAssertEqual(row["appName"] as? String, "SyntheticApp")
      XCTAssertEqual(row["ocrText"] as? String, "legacy text")
      XCTAssertEqual(row["screenActivitySyncState"] as? Int64, Int64(ScreenActivitySyncState.pending.rawValue))
      XCTAssertEqual(
        try String.fetchOne(
          db,
          sql: "SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'idx_screenshots_screen_activity_sync'"),
        "idx_screenshots_screen_activity_sync")
    }
  }

  func testRowUnreadyAtFirstSweepIsDeliveredAfterOCRAndEmbeddingCanFollowLater() throws {
    let queue = try makeLegacyQueue()
    let cutoff = Date(timeIntervalSince1970: 1_700_001_000)
    try queue.write { db in
      try RewindDatabase.installScreenActivitySyncStateSchema(db)
      try db.execute(
        sql: """
          INSERT INTO screenshots (timestamp, appName, windowTitle, ocrText)
          VALUES (?, ?, ?, NULL)
          """,
        arguments: [Date(timeIntervalSince1970: 1_700_000_000), "SyntheticApp", "SyntheticWindow"])

      try ScreenActivitySyncService.compactClosedBuckets(db: db, now: cutoff, slack: 0)
      XCTAssertTrue(
        try ScreenActivitySyncService.fetchSyncCandidates(db: db, limit: 100, now: cutoff, slack: 0, embeddingGrace: 0)
          .isEmpty)

      try db.execute(sql: "UPDATE screenshots SET ocrText = ? WHERE id = 1", arguments: ["OCR arrived later"])
      let textCandidates = try ScreenActivitySyncService.fetchSyncCandidates(
        db: db, limit: 100, now: cutoff, slack: 0, embeddingGrace: 0)
      XCTAssertEqual(textCandidates.map(\.id), [1])
      XCTAssertFalse(textCandidates[0].hasEmbedding)
      try ScreenActivitySyncService.markCandidatesSynced(db: db, candidates: textCandidates)
      XCTAssertEqual(
        try Int.fetchOne(db, sql: "SELECT screenActivitySyncState FROM screenshots WHERE id = 1"),
        ScreenActivitySyncState.textSynced.rawValue)

      let embedding = [Float(0.25), Float(-0.5)].withUnsafeBytes { Data($0) }
      try db.execute(sql: "UPDATE screenshots SET embedding = ? WHERE id = 1", arguments: [embedding])
      let vectorCandidates = try ScreenActivitySyncService.fetchSyncCandidates(
        db: db, limit: 100, now: cutoff, slack: 0, embeddingGrace: 0)
      XCTAssertEqual(vectorCandidates.map(\.id), [1])
      XCTAssertTrue(vectorCandidates[0].hasEmbedding)
      try ScreenActivitySyncService.markCandidatesSynced(db: db, candidates: vectorCandidates)
      XCTAssertEqual(
        try Int.fetchOne(db, sql: "SELECT screenActivitySyncState FROM screenshots WHERE id = 1"),
        ScreenActivitySyncState.fullySynced.rawValue)
    }
  }

  /// The defect this pins: eligibility must be per *bucket*, not per row.
  ///
  /// With a per-row `timestamp <= now - slack` test, the early rows of a bucket become eligible
  /// while its later rows do not, so the bucket is ranked twice and ships two winners. Replayed
  /// over 7,346 real OCR-bearing rows that shipped 5,517 rows where bucket-aligned ranking ships
  /// 3,842 — 44% more than intended, which is most of the compaction saving.
  func testAPartiallyAgedBucketIsNotRankedUntilTheWholeBucketHasClosed() throws {
    let queue = try makeLegacyQueue()
    // 1_700_000_100 is bucket-aligned (divisible by 300), so both rows land in the bucket
    // [1_700_000_100, 1_700_000_400): an early row and a late row.
    let bucketStart = Date(timeIntervalSince1970: 1_700_000_100)
    try queue.write { db in
      try RewindDatabase.installScreenActivitySyncStateSchema(db)
      for (offset, text) in [(10.0, "early row"), (290.0, "the late row has the longest text")] {
        try db.execute(
          sql: "INSERT INTO screenshots (timestamp, appName, windowTitle, ocrText) VALUES (?, ?, ?, ?)",
          arguments: [bucketStart.addingTimeInterval(offset), "SyntheticApp", "SyntheticWindow", text])
      }

      // A sliding per-row cutoff would call the early row ready here and ship it alone.
      let midway = bucketStart.addingTimeInterval(60)
      try ScreenActivitySyncService.compactClosedBuckets(db: db, now: midway, slack: 0)
      XCTAssertTrue(
        try ScreenActivitySyncService.fetchSyncCandidates(
          db: db, limit: 100, now: midway, slack: 0, embeddingGrace: 0
        ).isEmpty,
        "an open bucket must ship nothing")

      // Once the bucket has closed, it is ranked exactly once and the longest row wins.
      let afterClose = bucketStart.addingTimeInterval(301)
      try ScreenActivitySyncService.compactClosedBuckets(db: db, now: afterClose, slack: 0)
      let candidates = try ScreenActivitySyncService.fetchSyncCandidates(
        db: db, limit: 100, now: afterClose, slack: 0, embeddingGrace: 0)
      XCTAssertEqual(candidates.map(\.id), [2], "the longest row wins, and it wins alone")
      try ScreenActivitySyncService.markCandidatesSynced(db: db, candidates: candidates)

      // And the bucket does not produce a second winner on any later sweep.
      let later = bucketStart.addingTimeInterval(3_600)
      try ScreenActivitySyncService.compactClosedBuckets(db: db, now: later, slack: 0)
      XCTAssertTrue(
        try ScreenActivitySyncService.fetchSyncCandidates(
          db: db, limit: 100, now: later, slack: 0, embeddingGrace: 0
        ).isEmpty,
        "a closed bucket must not ship again")
    }
  }

  /// A row whose vector is still pending must not ship text-only and then ship again unchanged:
  /// the second push is a byte-identical Firestore document write plus a full index rewrite.
  func testARowWaitsForItsEmbeddingRatherThanShippingTwice() throws {
    let queue = try makeLegacyQueue()
    let bucketStart = Date(timeIntervalSince1970: 1_700_000_000)
    try queue.write { db in
      try RewindDatabase.installScreenActivitySyncStateSchema(db)
      try db.execute(
        sql: "INSERT INTO screenshots (timestamp, appName, windowTitle, ocrText) VALUES (?, ?, ?, ?)",
        arguments: [bucketStart, "SyntheticApp", "SyntheticWindow", "awaiting its vector"])

      // Bucket closed, but the grace period for the embedding has not expired.
      let justClosed = bucketStart.addingTimeInterval(301)
      XCTAssertTrue(
        try ScreenActivitySyncService.fetchSyncCandidates(
          db: db, limit: 100, now: justClosed, slack: 0, embeddingGrace: 900
        ).isEmpty,
        "must wait for the vector rather than shipping text-only")

      // The vector lands: one push, straight to fullySynced.
      let embedding = [Float(0.25), Float(-0.5)].withUnsafeBytes { Data($0) }
      try db.execute(sql: "UPDATE screenshots SET embedding = ? WHERE id = 1", arguments: [embedding])
      let candidates = try ScreenActivitySyncService.fetchSyncCandidates(
        db: db, limit: 100, now: justClosed, slack: 0, embeddingGrace: 900)
      XCTAssertEqual(candidates.map(\.id), [1])
      XCTAssertTrue(candidates[0].hasEmbedding)
      try ScreenActivitySyncService.markCandidatesSynced(db: db, candidates: candidates)
      XCTAssertEqual(
        try Int.fetchOne(db, sql: "SELECT screenActivitySyncState FROM screenshots WHERE id = 1"),
        ScreenActivitySyncState.fullySynced.rawValue,
        "one push, not two")
    }
  }

  /// Losslessness still wins if the vector never arrives: the grace period is a delay, not a gate.
  func testARowWithoutAnEmbeddingStillShipsOnceTheGraceExpires() throws {
    let queue = try makeLegacyQueue()
    let bucketStart = Date(timeIntervalSince1970: 1_700_000_000)
    try queue.write { db in
      try RewindDatabase.installScreenActivitySyncStateSchema(db)
      try db.execute(
        sql: "INSERT INTO screenshots (timestamp, appName, windowTitle, ocrText) VALUES (?, ?, ?, ?)",
        arguments: [bucketStart, "SyntheticApp", "SyntheticWindow", "never embedded"])

      let afterGrace = bucketStart.addingTimeInterval(1_500)
      let candidates = try ScreenActivitySyncService.fetchSyncCandidates(
        db: db, limit: 100, now: afterGrace, slack: 0, embeddingGrace: 900)
      XCTAssertEqual(candidates.map(\.id), [1])
      XCTAssertFalse(candidates[0].hasEmbedding)
    }
  }

  func testCompactionKeepsLongestOCRTextPerAppWindowAndFiveMinuteBucket() throws {
    let queue = try makeLegacyQueue()
    let base = Date(timeIntervalSince1970: 1_700_000_000)
    let cutoff = base.addingTimeInterval(1_000)
    try queue.write { db in
      try RewindDatabase.installScreenActivitySyncStateSchema(db)
      for (offset, text) in [(0.0, "short"), (30.0, "the longest synthetic OCR text"), (60.0, "medium text")] {
        try db.execute(
          sql: "INSERT INTO screenshots (timestamp, appName, windowTitle, ocrText) VALUES (?, ?, ?, ?)",
          arguments: [base.addingTimeInterval(offset), "SyntheticApp", "SyntheticWindow", text])
      }
      try db.execute(
        sql: "INSERT INTO screenshots (timestamp, appName, windowTitle, ocrText) VALUES (?, ?, ?, ?)",
        arguments: [base.addingTimeInterval(330), "SyntheticApp", "SyntheticWindow", "next bucket"])

      try ScreenActivitySyncService.compactClosedBuckets(db: db, now: cutoff, slack: 0)
      let candidates = try ScreenActivitySyncService.fetchSyncCandidates(
        db: db, limit: 100, now: cutoff, slack: 0, embeddingGrace: 0)

      XCTAssertEqual(candidates.map(\.id), [2, 4])
      XCTAssertEqual(
        try Int.fetchAll(
          db,
          sql: "SELECT id FROM screenshots WHERE screenActivitySyncState = ? ORDER BY id",
          arguments: [ScreenActivitySyncState.compacted.rawValue]),
        [1, 3])
    }
  }

  func testPayloadCanonicalizesISOFallbackTimestamp() throws {
    let queue = try makeLegacyQueue()
    try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO screenshots (timestamp, appName, windowTitle, ocrText)
          VALUES (?, ?, ?, ?)
          """,
        arguments: ["2026-08-18T19:00:00.123Z", "SyntheticApp", "SyntheticWindow", "synthetic OCR"])
      let row = try XCTUnwrap(Row.fetchOne(db, sql: "SELECT * FROM screenshots"))
      let payload = try XCTUnwrap(ScreenActivitySyncService.payloadRow(from: row))
      XCTAssertEqual(payload["timestamp"] as? String, "2026-08-18 19:00:00.123")
    }
  }

  private func makeLegacyQueue() throws -> DatabaseQueue {
    let queue = try DatabaseQueue()
    try queue.write { db in
      try db.create(table: "screenshots") { table in
        table.autoIncrementedPrimaryKey("id")
        table.column("timestamp", .datetime).notNull()
        table.column("appName", .text).notNull()
        table.column("windowTitle", .text)
        table.column("ocrText", .text)
        table.column("embedding", .blob)
        table.column("deviceName", .text)
        table.column("clientDeviceId", .text)
      }
    }
    return queue
  }
}

final class ScreenshotEmbeddingBackfillRecoveryTests: XCTestCase {
  private var testUserID = ""
  private var userDirectory: URL?

  override func setUp() async throws {
    try await super.setUp()
    testUserID = "screen-backfill-recovery-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await RewindDatabase.shared.configure(userId: testUserID)
    try await RewindDatabase.shared.initialize()

    let appSupport = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first)
    userDirectory =
      appSupport.appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserID, isDirectory: true)
  }

  override func tearDown() async throws {
    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = nil
    if let userDirectory { try? FileManager.default.removeItem(at: userDirectory) }
    try await super.tearDown()
  }

  func testCompletedZeroProgressBackfillRearmsWhenCompactedWinnerIsMissing() async throws {
    _ = try await RewindDatabase.shared.insertScreenshot(
      Screenshot(
        timestamp: Date(timeIntervalSince1970: 1_700_000_000),
        appName: "SyntheticApp",
        windowTitle: "SyntheticWindow",
        ocrText: "synthetic OCR text long enough to require an embedding",
        isIndexed: true))
    let databasePool = await RewindDatabase.shared.getDatabaseQueue()
    let pool = try XCTUnwrap(databasePool)
    try await pool.write { db in
      try db.execute(
        sql: """
          UPDATE migration_status
          SET completed = 1, processedCount = 0, completedAt = datetime('now')
          WHERE name = 'screenshot_embedding_backfill'
          """)
    }

    let rearmed = try await RewindDatabase.shared.rearmScreenshotEmbeddingBackfillIfNeeded(
      olderThan: Date(timeIntervalSince1970: 1_700_001_000))
    let status = try await RewindDatabase.shared.getScreenshotEmbeddingBackfillStatus()
    let winners = try await RewindDatabase.shared.getCompactedScreenshotsMissingEmbeddings(
      limit: 100, olderThan: Date(timeIntervalSince1970: 1_700_001_000))

    XCTAssertTrue(rearmed)
    XCTAssertFalse(status.completed)
    XCTAssertEqual(status.processedCount, 0)
    XCTAssertEqual(winners.count, 1)
  }
}
