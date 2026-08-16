import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

final class ContextBucketStoreCompactionTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "context-bucket-compaction")
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testSixthShortEntryIsCompactedIntoFrozenContextAndLeavesFiveEntryTail() async throws {
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    let (pool, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let database = try XCTUnwrap(pool, "database should be initialized")

    try await database.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_buckets
            (id, subjectKind, subjectID, createdAt, updatedAt)
          VALUES ('bucket', 'context', 'short-history', ?, ?)
          """,
        arguments: [now, now])
      try db.execute(
        sql: """
          INSERT INTO context_visits
            (id, contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
             normalizedContextKey, referenceHash, startedAt, endedAt, outcome, createdAt, updatedAt)
          VALUES (1, 1, ?, 'bucket', 'Test App', 'raw', 'normalized', 'reference', ?, ?, 'completed', ?, ?)
          """,
        arguments: [poolEpoch, now, now, now, now])
    }

    let fence = ContextVisitFence(
      visitID: 1,
      contextGeneration: 1,
      poolEpoch: poolEpoch,
      bucketID: "bucket",
      startedAt: now)
    for index in 0..<6 {
      _ = try await ContextBucketStore.shared.writeExtraction(
        BucketExtraction(narrative: "short-\(index)", facts: []),
        for: fence,
        appName: "Test App",
        rawContextKey: "raw",
        normalizedContextKey: "normalized",
        now: now.addingTimeInterval(TimeInterval(index)))
    }

    let snapshot = try await database.read { db in
      try XCTUnwrap(ContextBucketStore.snapshot(in: db, bucketID: "bucket", now: now))
    }
    let entries = try await database.read { db in
      try Row.fetchAll(
        db,
        sql: "SELECT id, narrative, isCompacted FROM bucket_entries WHERE bucketID = ? ORDER BY createdAt ASC",
        arguments: ["bucket"])
    }

    XCTAssertEqual(entries.count, 6)
    let oldestID = try XCTUnwrap(entries.first?["id"] as String?)
    XCTAssertEqual(entries.first?["narrative"] as String?, "short-0")
    XCTAssertEqual(entries.first?["isCompacted"] as Bool?, true)
    XCTAssertEqual(entries.dropFirst().filter { ($0["isCompacted"] as Bool?) == false }.count, 5)
    XCTAssertEqual(snapshot.tail.count, 5)
    for index in 1...5 {
      XCTAssertTrue(snapshot.tail[index - 1].hasSuffix(" short-\(index)"))
    }

    // Six published versions, one constant header: nothing that changes per
    // visit may be written above the frozen segment, or the director's cache
    // prefix is invalidated before it can ever be reused.
    XCTAssertEqual(snapshot.header, ContextBucketPromptAssembler.stableHeader)
    XCTAssertFalse(snapshot.header.contains(where: \.isNumber))

    let frozen = try XCTUnwrap(String(data: snapshot.frozenRankedSegment, encoding: .utf8))
    XCTAssertTrue(
      frozen.contains("- entry:\(oldestID) short-0\n"),
      "the oldest short entry must survive in frozen context")
  }
}
