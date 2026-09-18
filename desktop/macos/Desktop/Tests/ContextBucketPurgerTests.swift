import GRDB
import XCTest

@testable import Omi_Computer

final class ContextBucketPurgerTests: XCTestCase {
  func testPurgeDeletesExcludedAppAcrossCaptureAndBucketTables() throws {
    let db = try DatabaseQueue()
    try db.write { database in
      try database.create(table: "screenshots") { table in
        table.autoIncrementedPrimaryKey("id")
        table.column("timestamp", .datetime).notNull()
        table.column("appName", .text).notNull()
      }
      try database.create(table: "observations") { table in
        table.autoIncrementedPrimaryKey("id")
        table.column("appName", .text).notNull()
      }
    }
    var migrator = DatabaseMigrator()
    ContextBucketSchema.registerMigration(on: &migrator, defaults: .standard, ownerID: "purge-test")
    try migrator.migrate(db)
    try db.write { database in
      for app in ["Secret", "Keep"] {
        try database.execute(
          sql: "INSERT INTO screenshots (timestamp, appName) VALUES (?, ?)", arguments: [Date(), app])
        try database.execute(sql: "INSERT INTO observations (appName) VALUES (?)", arguments: [app])
      }
      XCTAssertEqual(try ContextBucketPurger.delete(appName: "Secret", in: database), [])
    }
    try db.read { database in
      XCTAssertEqual(try String.fetchAll(database, sql: "SELECT appName FROM screenshots"), ["Keep"])
      XCTAssertEqual(try String.fetchAll(database, sql: "SELECT appName FROM observations"), ["Keep"])
    }
  }

  func testPurgeInvalidatesVisitsAndRemovesFrozenBytesForAffectedBuckets() throws {
    let db = try DatabaseQueue()
    try db.write { database in
      try database.create(table: "screenshots") { table in
        table.autoIncrementedPrimaryKey("id")
        table.column("timestamp", .datetime).notNull()
        table.column("appName", .text).notNull()
        table.column("imagePath", .text)
        table.column("videoChunkPath", .text)
      }
    }
    var migrator = DatabaseMigrator()
    ContextBucketSchema.registerMigration(on: &migrator, defaults: .standard, ownerID: "purge-frozen")
    try migrator.migrate(db)

    let now = Date(timeIntervalSince1970: 1_725_000_000)
    try db.write { database in
      try database.execute(
        sql: """
          INSERT INTO context_buckets
            (id, subjectKind, subjectID, createdAt, updatedAt)
          VALUES ('bucket', 'task', 'task-1', ?, ?)
          """,
        arguments: [now, now])
      try database.execute(
        sql: """
          INSERT INTO context_visits
            (id, contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
             normalizedContextKey, referenceHash, startedAt, outcome, createdAt, updatedAt)
          VALUES (1, 1, 1, 'bucket', 'Secret', 'raw', 'normalized', 'hash', ?, 'completed', ?, ?)
          """,
        arguments: [now, now, now])
      try database.execute(
        sql: """
          INSERT INTO context_visits
            (id, contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
             normalizedContextKey, referenceHash, startedAt, outcome, createdAt, updatedAt)
          VALUES (2, 1, 1, 'bucket', 'Keep', 'raw', 'normalized', 'hash-2', ?, 'active', ?, ?)
          """,
        arguments: [now, now, now])
      try database.execute(
        sql: """
          INSERT INTO bucket_entries
            (id, bucketID, visitID, appName, rawContextKey, normalizedContextKey,
             narrative, evidenceRefsJson, tokenCount, isCompacted, createdAt)
          VALUES ('secret-entry', 'bucket', 1, 'Secret', 'raw', 'normalized',
                  'excluded narrative', '[]', 2, 1, ?),
                 ('keep-entry', 'bucket', 2, 'Keep', 'raw', 'normalized',
                  'surviving narrative', '[]', 2, 1, ?)
          """,
        arguments: [now, now])
      try database.execute(
        sql:
          "INSERT INTO bucket_versions (bucketID, version, header, frozenRankedSegment, createdAt) VALUES ('bucket', 1, 'header', ?, ?)",
        arguments: [Data("- excluded narrative\n".utf8), now])
      try database.execute(
        sql:
          "INSERT INTO proactive_deliveries (id, bucketID, decisionType, lifecycleState, provenanceJson, attemptedAt, expiresAt, createdAt) VALUES ('delivery', 'bucket', 'suggest', 'delivered', ?, ?, ?, ?)",
        arguments: ["{\"excluded narrative\":true}", now, now.addingTimeInterval(60), now])
      try database.execute(
        sql: """
          INSERT INTO proactive_candidates
            (id, bucketID, message, groundingFactIDsJson, triggerNote, state, createdAt, expiresAt)
          VALUES ('candidate', 'bucket', 'excluded narrative still needs review', '[]',
                  'when relevant', 'armed', ?, ?)
          """,
        arguments: [now, now.addingTimeInterval(12 * 60 * 60)])

      let result = try ContextBucketPurger.deleteWithArtifacts(
        appName: "Secret", in: database, now: now)
      XCTAssertEqual(result.affectedBucketIDs, ["bucket"])
      XCTAssertEqual(try Int.fetchOne(database, sql: "SELECT COUNT(*) FROM context_visits WHERE appName = 'Secret'"), 0)
      XCTAssertEqual(try Int.fetchOne(database, sql: "SELECT COUNT(*) FROM context_visits WHERE appName = 'Keep'"), 1)
      XCTAssertEqual(try Int.fetchOne(database, sql: "SELECT COUNT(*) FROM bucket_versions"), 0)
      XCTAssertEqual(try Int.fetchOne(database, sql: "SELECT COUNT(*) FROM proactive_deliveries"), 0)
      XCTAssertEqual(try Int.fetchOne(database, sql: "SELECT COUNT(*) FROM proactive_candidates"), 0)
      XCTAssertEqual(
        try String.fetchAll(database, sql: "SELECT narrative FROM bucket_entries"), ["surviving narrative"])
      XCTAssertEqual(
        try Bool.fetchOne(database, sql: "SELECT isCompacted FROM bucket_entries WHERE id = 'keep-entry'"), false)
    }
  }

  func testArtifactsIncludeSharedVideoChunkAndLegacyImagePath() throws {
    let db = try DatabaseQueue()
    try db.write { database in
      try database.create(table: "screenshots") { table in
        table.autoIncrementedPrimaryKey("id")
        table.column("timestamp", .datetime).notNull()
        table.column("appName", .text).notNull()
        table.column("imagePath", .text)
        table.column("videoChunkPath", .text)
      }
    }
    var migrator = DatabaseMigrator()
    ContextBucketSchema.registerMigration(on: &migrator, defaults: .standard, ownerID: "purge-shared")
    try migrator.migrate(db)
    try db.write { database in
      let now = Date(timeIntervalSince1970: 1_725_000_000)
      try database.execute(
        sql:
          "INSERT INTO screenshots (timestamp, appName, imagePath, videoChunkPath) VALUES (?, 'Secret', 'secret.jpg', 'day/chunk.mp4'), (?, 'Keep', NULL, 'day/chunk.mp4')",
        arguments: [now, now])
      let result = try ContextBucketPurger.artifacts(appName: "Secret", in: database)
      XCTAssertEqual(result.imagePaths, ["secret.jpg"])
      XCTAssertEqual(result.videoChunkPaths, ["day/chunk.mp4"])
      let deleted = try ContextBucketPurger.deleteWithArtifacts(appName: "Secret", in: database)
      XCTAssertEqual(deleted.videoChunkPaths, ["day/chunk.mp4"])
      XCTAssertEqual(
        try Int.fetchOne(
          database, sql: "SELECT COUNT(*) FROM screenshots WHERE videoChunkPath = 'day/chunk.mp4'"),
        0,
        "No screenshot row may reference a privacy-deleted shared chunk")
    }
  }

  func testPurgeRecomputesVisitCountAndLastVisitedAtFromSurvivingVisits() throws {
    let db = try DatabaseQueue()
    try db.write { database in
      try database.create(table: "screenshots") { table in
        table.autoIncrementedPrimaryKey("id")
        table.column("timestamp", .datetime).notNull()
        table.column("appName", .text).notNull()
      }
    }
    var migrator = DatabaseMigrator()
    ContextBucketSchema.registerMigration(on: &migrator, defaults: .standard, ownerID: "purge-visits")
    try migrator.migrate(db)

    let secretEnded = Date(timeIntervalSince1970: 1_725_000_100)
    let keepEnded = Date(timeIntervalSince1970: 1_725_000_200)
    let now = Date(timeIntervalSince1970: 1_725_000_300)
    try db.write { database in
      try database.execute(
        sql: """
          INSERT INTO context_buckets
            (id, subjectKind, subjectID, visitCount, lastVisitedAt, createdAt, updatedAt)
          VALUES ('bucket', 'task', 'task-1', 2, ?, ?, ?)
          """,
        arguments: [secretEnded, secretEnded, secretEnded])
      try database.execute(
        sql: """
          INSERT INTO context_visits
            (id, contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
             normalizedContextKey, referenceHash, startedAt, endedAt, outcome, createdAt, updatedAt)
          VALUES
            (1, 1, 1, 'bucket', 'Secret', 'raw', 'normalized', 'hash', ?, ?, 'completed', ?, ?),
            (2, 1, 1, 'bucket', 'Keep', 'raw', 'normalized', 'hash-2', ?, ?, 'completed', ?, ?)
          """,
        arguments: [
          secretEnded, secretEnded, secretEnded, secretEnded,
          keepEnded, keepEnded, keepEnded, keepEnded,
        ])
      try database.execute(
        sql: """
          INSERT INTO bucket_entries
            (id, bucketID, visitID, appName, rawContextKey, normalizedContextKey,
             narrative, evidenceRefsJson, tokenCount, createdAt)
          VALUES ('secret-entry', 'bucket', 1, 'Secret', 'raw', 'normalized',
                  'excluded', '[]', 1, ?)
          """,
        arguments: [secretEnded])

      _ = try ContextBucketPurger.deleteWithArtifacts(appName: "Secret", in: database, now: now)
      let row = try Row.fetchOne(
        database, sql: "SELECT visitCount, lastVisitedAt FROM context_buckets WHERE id = 'bucket'")
      XCTAssertEqual(row?["visitCount"] as Int?, 1)
      XCTAssertEqual(row?["lastVisitedAt"] as Date?, keepEnded)
    }
  }

  func testPurgeClearsVisitStatsWhenNoCompletedVisitsRemain() throws {
    let db = try DatabaseQueue()
    try db.write { database in
      try database.create(table: "screenshots") { table in
        table.autoIncrementedPrimaryKey("id")
        table.column("timestamp", .datetime).notNull()
        table.column("appName", .text).notNull()
      }
    }
    var migrator = DatabaseMigrator()
    ContextBucketSchema.registerMigration(on: &migrator, defaults: .standard, ownerID: "purge-empty-visits")
    try migrator.migrate(db)

    let ended = Date(timeIntervalSince1970: 1_725_000_100)
    let now = Date(timeIntervalSince1970: 1_725_000_300)
    try db.write { database in
      try database.execute(
        sql: """
          INSERT INTO context_buckets
            (id, subjectKind, subjectID, visitCount, lastVisitedAt, createdAt, updatedAt)
          VALUES ('bucket', 'task', 'task-1', 1, ?, ?, ?)
          """,
        arguments: [ended, ended, ended])
      try database.execute(
        sql: """
          INSERT INTO context_visits
            (id, contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
             normalizedContextKey, referenceHash, startedAt, endedAt, outcome, createdAt, updatedAt)
          VALUES (1, 1, 1, 'bucket', 'Secret', 'raw', 'normalized', 'hash', ?, ?, 'completed', ?, ?)
          """,
        arguments: [ended, ended, ended, ended])
      try database.execute(
        sql: """
          INSERT INTO bucket_entries
            (id, bucketID, visitID, appName, rawContextKey, normalizedContextKey,
             narrative, evidenceRefsJson, tokenCount, createdAt)
          VALUES ('secret-entry', 'bucket', 1, 'Secret', 'raw', 'normalized',
                  'excluded', '[]', 1, ?)
          """,
        arguments: [ended])

      _ = try ContextBucketPurger.deleteWithArtifacts(appName: "Secret", in: database, now: now)
      let row = try Row.fetchOne(
        database, sql: "SELECT visitCount, lastVisitedAt FROM context_buckets WHERE id = 'bucket'")
      XCTAssertEqual(row?["visitCount"] as Int?, 0)
      XCTAssertNil(row?["lastVisitedAt"] as Date?)
    }
  }

  func testDeterministicGCExcludesBucketsWithActiveVisits() throws {
    let db = try DatabaseQueue()
    try db.write { database in
      try database.create(table: "screenshots") { table in
        table.autoIncrementedPrimaryKey("id")
        table.column("timestamp", .datetime).notNull()
        table.column("appName", .text).notNull()
      }
    }
    var migrator = DatabaseMigrator()
    ContextBucketSchema.registerMigration(on: &migrator, defaults: .standard, ownerID: "gc-active")
    try migrator.migrate(db)

    let old = Date(timeIntervalSince1970: 1_600_000_000)
    try db.write { database in
      try database.execute(
        sql: """
          INSERT INTO context_buckets
            (id, subjectKind, subjectID, lastVisitedAt, createdAt, updatedAt)
          VALUES ('active-bucket', 'task', 'task-active', ?, ?, ?)
          """,
        arguments: [old, old, old])
      try database.execute(
        sql: """
          INSERT INTO context_visits
            (contextGeneration, poolEpoch, bucketID, appName, rawContextKey,
             normalizedContextKey, referenceHash, startedAt, outcome, createdAt, updatedAt)
          VALUES (1, 1, 'active-bucket', 'Keep', 'raw', 'normalized', 'hash', ?, 'active', ?, ?)
          """,
        arguments: [old, old, old])

      let cutoff = old.addingTimeInterval(30 * 24 * 60 * 60)
      XCTAssertEqual(
        try ContextBucketGarbageCollection.staleBucketIDs(in: database, before: cutoff), [])
      XCTAssertEqual(
        try ContextBucketGarbageCollection.overflowBucketIDs(in: database, keeping: 0), [])
    }
  }
}
