import GRDB
import XCTest

@testable import Omi_Computer

final class ContextBucketSyncSelectionTests: XCTestCase {
  private let now = Date(timeIntervalSince1970: 1_800_000_000)

  private func migratedQueue() throws -> DatabaseQueue {
    let queue = try DatabaseQueue()
    try queue.write { db in
      try db.create(table: "screenshots") { table in
        table.autoIncrementedPrimaryKey("id")
        table.column("timestamp", .datetime).notNull()
        table.column("appName", .text).notNull()
      }
    }
    var migrator = DatabaseMigrator()
    let defaults = try XCTUnwrap(
      UserDefaults(suiteName: "ContextBucketSyncSelectionTests.\(UUID().uuidString)"))
    ContextBucketSchema.registerMigration(on: &migrator, defaults: defaults, ownerID: "sync-test")
    try migrator.migrate(queue)
    return queue
  }

  private func insertBucket(_ db: Database, id: String, updatedAt: Date) throws {
    try db.execute(
      sql: """
        INSERT INTO context_buckets
          (id, subjectKind, subjectID, displayLabel, notifyWorthiness, visitCount,
           lastVisitedAt, createdAt, updatedAt)
        VALUES (?, 'document', ?, 'Design doc', 0.7, 3, ?, ?, ?)
        """,
      arguments: [id, "subject-\(id)", updatedAt, updatedAt, updatedAt])
  }

  /// `bucket_entries.visitID` is a real foreign key, so an entry needs a visit.
  @discardableResult
  private func insertVisit(_ db: Database, bucketID: String) throws -> Int64 {
    try db.execute(
      sql: """
        INSERT INTO context_visits
          (contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
           normalizedContextKey, referenceHash, startedAt, outcome, createdAt, updatedAt)
        VALUES (1, 1, ?, 'Xcode', 'raw', 'normalized', 'sha256:abc', ?, 'completed', ?, ?)
        """,
      arguments: [bucketID, now, now, now])
    return db.lastInsertedRowID
  }

  private func insertEntry(_ db: Database, id: String, bucketID: String) throws {
    let visitID = try insertVisit(db, bucketID: bucketID)
    try db.execute(
      sql: """
        INSERT INTO bucket_entries
          (id, bucketID, visitID, appName, rawContextKey, normalizedContextKey,
           narrative, evidenceRefsJson, tokenCount, createdAt)
        VALUES (?, ?, ?, 'Xcode', 'raw', 'normalized', 'narrative', '[]', 10, ?)
        """,
      arguments: [id, bucketID, visitID, now])
  }

  private func insertFact(
    _ db: Database,
    id: String,
    bucketID: String,
    validity: String,
    expiresAt: Date? = nil,
    identifiers: String = "[\"parity-pack\"]"
  ) throws {
    try db.execute(
      sql: """
        INSERT INTO bucket_facts
          (id, bucketID, entryID, appName, statement, identifiersJson, evidenceText,
           evidenceRefsJson, validityState, dispositionState, confidence,
           notifyWorthiness, expiresAt, createdAt, updatedAt)
        VALUES (?, ?, 'entry-1', 'Xcode', 'Ship the parity pack', ?, 'quoted screen text',
                '[]', ?, 'none', 0.9, 0.8, ?, ?, ?)
        """,
      arguments: [id, bucketID, identifiers, validity, expiresAt, now, now])
  }

  func testOnlyValidatedFactsAreStagedForPublication() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      try insertBucket(db, id: "bucket-1", updatedAt: now)
      try insertEntry(db, id: "entry-1", bucketID: "bucket-1")
      try insertFact(db, id: "validated", bucketID: "bucket-1", validity: "validated")
      for state in ["proposed", "needs_review", "rejected", "superseded", "expired"] {
        try insertFact(db, id: state, bucketID: "bucket-1", validity: state)
      }
    }

    let facts = try queue.read { db in
      try ContextBucketSyncSelection.facts(in: db, bucketID: "bucket-1", now: now)
    }

    XCTAssertEqual(facts.map(\.factID), ["validated"])
  }

  func testExpiredFactsAreNotStaged() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      try insertBucket(db, id: "bucket-1", updatedAt: now)
      try insertEntry(db, id: "entry-1", bucketID: "bucket-1")
      try insertFact(
        db, id: "expired", bucketID: "bucket-1", validity: "validated",
        expiresAt: now.addingTimeInterval(-60))
      try insertFact(
        db, id: "live", bucketID: "bucket-1", validity: "validated",
        expiresAt: now.addingTimeInterval(60))
    }

    let facts = try queue.read { db in
      try ContextBucketSyncSelection.facts(in: db, bucketID: "bucket-1", now: now)
    }

    XCTAssertEqual(facts.map(\.factID), ["live"])
  }

  func testBucketSelectionWalksForwardFromTheWatermark() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      for index in 0..<5 {
        try insertBucket(
          db, id: "bucket-\(index)", updatedAt: now.addingTimeInterval(Double(index) * 60))
      }
    }

    let buckets = try queue.read { db in try ContextBucketSyncSelection.buckets(in: db, updatedAfter: nil, limit: 3) }

    XCTAssertEqual(buckets.map(\.bucketID), ["bucket-0", "bucket-1", "bucket-2"])
  }

  func testIdentifiersDecodeAndMalformedJSONDegradesToEmpty() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      try insertBucket(db, id: "bucket-1", updatedAt: now)
      try insertEntry(db, id: "entry-1", bucketID: "bucket-1")
      try insertFact(
        db, id: "good", bucketID: "bucket-1", validity: "validated",
        identifiers: "[\"parity-pack\",\"omi\"]")
      try insertFact(
        db, id: "bad", bucketID: "bucket-1", validity: "validated", identifiers: "not json")
    }

    let facts = try queue.read { db in
      try ContextBucketSyncSelection.facts(in: db, bucketID: "bucket-1", now: now)
    }

    let byID = Dictionary(uniqueKeysWithValues: facts.map { ($0.factID, $0.identifiers) })
    XCTAssertEqual(byID["good"], ["parity-pack", "omi"])
    XCTAssertEqual(byID["bad"], [])
  }

  func testStagedFactsCarryNoQuotedScreenText() throws {
    let queue = try migratedQueue()
    try queue.write { db in
      try insertBucket(db, id: "bucket-1", updatedAt: now)
      try insertEntry(db, id: "entry-1", bucketID: "bucket-1")
      try insertFact(db, id: "validated", bucketID: "bucket-1", validity: "validated")
    }

    let staged = try queue.read { db in
      try ContextBucketSyncSelection.facts(in: db, bucketID: "bucket-1", now: now)
    }
    let body = ContextBucketSyncPayload.body(
      deviceID: "macos_abc",
      buckets: try queue.read { db in try ContextBucketSyncSelection.buckets(in: db, updatedAfter: nil) },
      facts: staged)
    let encoded = try XCTUnwrap(String(data: JSONSerialization.data(withJSONObject: body), encoding: .utf8))

    XCTAssertFalse(encoded.contains("quoted screen text"))
    XCTAssertFalse(encoded.contains("narrative"))
    XCTAssertTrue(encoded.contains("Ship the parity pack"))
  }
}
