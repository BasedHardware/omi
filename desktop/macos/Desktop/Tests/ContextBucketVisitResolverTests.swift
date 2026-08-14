import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

final class ContextBucketVisitResolverTests: XCTestCase {
  func testCompletedNormalizedVisitQualifiesNextVisit() throws {
    let queue = try migratedQueue()
    let appName = "Safari"
    let title = "Project room"
    let normalizedTitle = try XCTUnwrap(ContextTitleNormalizer.normalize(title, appName: appName))
    let normalizedKey = try XCTUnwrap(
      ContextTitleNormalizer.identityKey(appName: appName, windowTitle: title))
    let referenceHash = ContextBucketStore.referenceHash(normalizedKey)
    let firstStartedAt = Date(timeIntervalSince1970: 1_725_000_000)
    let firstEndedAt = firstStartedAt.addingTimeInterval(1)

    try queue.write { db in
      XCTAssertNil(
        try ContextBucketVisitResolver.resolveBucketID(
          in: db,
          referenceHash: referenceHash,
          normalizedTitle: normalizedTitle,
          startedAt: firstStartedAt),
        "the first normalized visit must remain unbucketed")
      XCTAssertEqual(
        try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM context_buckets"),
        0)

      _ = try insertVisit(
        in: db,
        appName: appName,
        windowTitle: title,
        normalizedKey: normalizedKey,
        referenceHash: referenceHash,
        startedAt: firstStartedAt,
        endedAt: firstEndedAt,
        outcome: "completed")

      let secondBucketID = try XCTUnwrap(
        ContextBucketVisitResolver.resolveBucketID(
          in: db,
          referenceHash: referenceHash,
          normalizedTitle: normalizedTitle,
          startedAt: firstEndedAt),
        "a completed visit must qualify the next visit")
      _ = try insertVisit(
        in: db,
        appName: appName,
        windowTitle: title,
        normalizedKey: normalizedKey,
        referenceHash: referenceHash,
        bucketID: secondBucketID,
        startedAt: firstEndedAt,
        outcome: "active")

      XCTAssertEqual(
        try String.fetchOne(
          db,
          sql: "SELECT bucketID FROM context_visits WHERE referenceHash = ? ORDER BY id DESC LIMIT 1",
          arguments: [referenceHash]),
        secondBucketID,
        "a non-ephemeral revisit must not persist a NULL bucket after completion")
    }
  }

  func testDiscardedNormalizedVisitDoesNotQualifyNextVisit() throws {
    let queue = try migratedQueue()
    let appName = "Safari"
    let title = "Project room"
    let normalizedTitle = try XCTUnwrap(ContextTitleNormalizer.normalize(title, appName: appName))
    let normalizedKey = try XCTUnwrap(
      ContextTitleNormalizer.identityKey(appName: appName, windowTitle: title))
    let referenceHash = ContextBucketStore.referenceHash(normalizedKey)
    let firstStartedAt = Date(timeIntervalSince1970: 1_725_000_000)
    let firstEndedAt = firstStartedAt.addingTimeInterval(0.999)

    try queue.write { db in
      XCTAssertNil(
        try ContextBucketVisitResolver.resolveBucketID(
          in: db,
          referenceHash: referenceHash,
          normalizedTitle: normalizedTitle,
          startedAt: firstStartedAt))
      _ = try insertVisit(
        in: db,
        appName: appName,
        windowTitle: title,
        normalizedKey: normalizedKey,
        referenceHash: referenceHash,
        startedAt: firstStartedAt,
        endedAt: firstEndedAt,
        outcome: "discarded")

      XCTAssertNil(
        try ContextBucketVisitResolver.resolveBucketID(
          in: db,
          referenceHash: referenceHash,
          normalizedTitle: normalizedTitle,
          startedAt: firstEndedAt),
        "a discarded visit must not count as a completed visit")
      XCTAssertEqual(
        try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM context_buckets"),
        0)
      XCTAssertEqual(
        try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM subject_bindings"),
        0)
    }
  }

  func testBlankAndNoiseOnlyTitlesRemainEphemeralAndUnbucketed() throws {
    let queue = try migratedQueue()
    let appName = "Safari"
    let titles: [String?] = [nil, "   ", "✳ ◐"]
    let startedAt = Date(timeIntervalSince1970: 1_725_000_000)

    try queue.write { db in
      for (index, title) in titles.enumerated() {
        XCTAssertNil(ContextTitleNormalizer.normalize(title, appName: appName))
        XCTAssertNil(ContextTitleNormalizer.identityKey(appName: appName, windowTitle: title))
        let referenceHash = "ephemeral:test-\(index)"
        XCTAssertNil(
          try ContextBucketVisitResolver.resolveBucketID(
            in: db,
            referenceHash: referenceHash,
            normalizedTitle: nil,
            startedAt: startedAt.addingTimeInterval(Double(index))))
        _ = try insertVisit(
          in: db,
          appName: appName,
          windowTitle: title,
          normalizedKey: nil,
          referenceHash: referenceHash,
          startedAt: startedAt.addingTimeInterval(Double(index)),
          outcome: "active")
      }

      XCTAssertEqual(
        try Int.fetchOne(
          db,
          sql:
            "SELECT COUNT(*) FROM context_visits WHERE bucketID IS NULL AND normalizedContextKey = '' AND referenceHash LIKE 'ephemeral:%'"
        ),
        titles.count)
      XCTAssertEqual(
        try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM context_buckets"),
        0)
      XCTAssertEqual(
        try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM subject_bindings"),
        0)
    }
  }

  func testExplicitRebindAttachesCurrentSubjectBucketNotStalePointer() throws {
    let queue = try migratedQueue()
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    let referenceHash = "sha256:window"
    try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_buckets
            (id, subjectKind, subjectID, workstreamID, createdAt, updatedAt)
          VALUES
            ('bucket-a', 'task', 'task-a', NULL, ?, ?),
            ('bucket-b', 'task', 'task-b', NULL, ?, ?)
          """,
        arguments: [now, now, now, now])
      try db.execute(
        sql: """
          INSERT INTO subject_bindings
            (referenceHash, bucketID, subjectKind, subjectID, confidence, source,
             occurrenceCount, createdAt, updatedAt)
          VALUES (?, 'bucket-a', 'task', 'task-b', 1.0, 'explicit_open', 2, ?, ?)
          """,
        arguments: [referenceHash, now, now])

      let resolved = try ContextBucketVisitResolver.resolveBucketID(
        in: db,
        referenceHash: referenceHash,
        normalizedTitle: "Shared window",
        startedAt: now)
      XCTAssertEqual(resolved, "bucket-b")
      XCTAssertEqual(
        try String.fetchOne(
          db, sql: "SELECT bucketID FROM subject_bindings WHERE referenceHash = ?",
          arguments: [referenceHash]),
        "bucket-b")
    }
  }

  func testActiveVisitKeepsOriginalBucketAfterSubjectRebind() throws {
    let queue = try migratedQueue()
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_buckets
            (id, subjectKind, subjectID, workstreamID, createdAt, updatedAt)
          VALUES
            ('bucket-original', 'context', 'subject-a', NULL, ?, ?),
            ('bucket-new', 'task', 'task-b', NULL, ?, ?)
          """,
        arguments: [now, now, now, now])
      try db.execute(
        sql: """
          INSERT INTO context_visits
            (contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
             normalizedContextKey, referenceHash, startedAt, outcome, createdAt, updatedAt)
          VALUES (7, 11, 'bucket-original', 'Browser', 'Window', 'browser::window',
                  'sha256:window', ?, 'active', ?, ?)
          """,
        arguments: [now, now, now])
      let visitID = db.lastInsertedRowID

      // A later explicit rebind changes the subject binding, not the durable
      // bucket identity captured by this already-active visit.
      try db.execute(
        sql: """
          INSERT INTO subject_bindings
            (referenceHash, bucketID, subjectKind, subjectID, confidence, source,
             occurrenceCount, createdAt, updatedAt)
          VALUES ('sha256:window', 'bucket-new', 'task', 'task-b', 1.0,
                  'explicit_open', 1, ?, ?)
          """,
        arguments: [now, now])

      XCTAssertEqual(
        try ContextBucketVisitResolver.persistedBucketID(
          in: db,
          visitID: visitID,
          contextGeneration: 7,
          poolEpoch: 11),
        "bucket-original")
      XCTAssertNil(
        try ContextBucketVisitResolver.persistedBucketID(
          in: db,
          visitID: visitID,
          contextGeneration: 8,
          poolEpoch: 11))
    }
  }

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
      UserDefaults(suiteName: "ContextBucketVisitResolverTests.\(UUID().uuidString)"))
    ContextBucketSchema.registerMigration(on: &migrator, defaults: defaults, ownerID: "owner")
    try migrator.migrate(queue)
    return queue
  }

  @discardableResult
  private func insertVisit(
    in db: Database,
    appName: String,
    windowTitle: String?,
    normalizedKey: String?,
    referenceHash: String,
    bucketID: String? = nil,
    startedAt: Date,
    endedAt: Date? = nil,
    outcome: String
  ) throws -> Int64 {
    try db.execute(
      sql: """
        INSERT INTO context_visits
          (contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
           normalizedContextKey, referenceHash, startedAt, outcome, endedAt, createdAt, updatedAt)
        VALUES (1, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
      arguments: [
        bucketID, appName, "\(appName)\n\(windowTitle ?? "")", normalizedKey ?? "", referenceHash,
        startedAt, outcome, endedAt, startedAt, endedAt ?? startedAt,
      ])
    return db.lastInsertedRowID
  }
}
