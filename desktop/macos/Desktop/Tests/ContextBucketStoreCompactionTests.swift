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

final class ContextBucketQuestionFactTTLTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "context-bucket-question-ttl")
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  /// A stale question fact must not trigger an answer in a later context:
  /// user-authored questions expire `userQuestionFactTTLSeconds` after their
  /// compose moment, so the expiry-filtered fact queries (snapshot, forced
  /// lookup) stop seeing them, while ordinary facts stay live.
  func testUserQuestionFactExpiresAndOrdinaryFactDoesNot() async throws {
    let written = Date().addingTimeInterval(
      -(ContextFactWritePolicy.userQuestionFactTTLSeconds + 60))
    let (pool, poolEpoch) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    let database = try XCTUnwrap(pool, "database should be initialized")

    try await database.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_buckets (id, subjectKind, subjectID, createdAt, updatedAt)
          VALUES ('bucket', 'context', 'question-ttl', ?, ?)
          """,
        arguments: [written, written])
      try db.execute(
        sql: """
          INSERT INTO context_visits
            (id, contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
             normalizedContextKey, referenceHash, startedAt, endedAt, outcome, createdAt, updatedAt)
          VALUES (1, 1, ?, 'bucket', 'Test App', 'raw', 'normalized', 'reference', ?, ?, 'completed', ?, ?)
          """,
        arguments: [poolEpoch, written, written, written, written])
    }
    let fence = ContextVisitFence(
      visitID: 1, contextGeneration: 1, poolEpoch: poolEpoch, bucketID: "bucket",
      startedAt: written)

    _ = try await ContextBucketStore.shared.writeExtraction(
      BucketExtraction(
        narrative: "compose",
        facts: [
          BucketExtraction.Fact(
            statement: "The user is asking david@scalingforever.com: where is the newest Omi build?",
            identifiers: [], evidenceText: "where is the newest Omi build?",
            evidenceRefs: ["visit:1"], confidence: 0.9, notifyWorthiness: 0.9),
          BucketExtraction.Fact(
            statement: "PR #11651 in the BasedHardware/omi repository has been merged.",
            identifiers: [], evidenceText: "PR #11651 merged",
            evidenceRefs: ["visit:1"], confidence: 0.9, notifyWorthiness: 0.7),
        ]),
      for: fence,
      appName: "Test App",
      rawContextKey: "raw",
      normalizedContextKey: "normalized",
      applyWritePolicy: true,
      now: written)

    let rows = try await database.read { db in
      try Row.fetchAll(
        db,
        sql: """
          SELECT statement, expiresAt IS NOT NULL AS hasExpiry,
                 (expiresAt IS NULL OR expiresAt > ?) AS liveNow
          FROM bucket_facts ORDER BY statement
          """,
        arguments: [Date()])
    }
    XCTAssertEqual(rows.count, 2)
    let question = try XCTUnwrap(rows.first { ($0["statement"] as String).hasPrefix("The user is asking") })
    let ordinary = try XCTUnwrap(rows.first { ($0["statement"] as String).hasPrefix("PR #11651") })
    XCTAssertEqual(question["hasExpiry"] as Bool?, true, "question facts carry the TTL")
    XCTAssertEqual(
      question["liveNow"] as Bool?, false,
      "a question older than the TTL is invisible to the expiry-filtered fact queries")
    XCTAssertEqual(ordinary["hasExpiry"] as Bool?, false)
    XCTAssertEqual(ordinary["liveNow"] as Bool?, true)
  }
}
