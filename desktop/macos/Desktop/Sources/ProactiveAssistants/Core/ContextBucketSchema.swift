import CryptoKit
import Foundation
@preconcurrency import GRDB

enum ContextBucketSchema {
  static let migrationName = "createContextBucketsAndProactivityLedger"
  static let tableNames: Set<String> = [
    "context_visits",
    "context_buckets",
    "bucket_versions",
    "bucket_entries",
    "bucket_facts",
    "subject_bindings",
    "proactive_deliveries",
  ]

  private struct LegacyBinding: Codable {
    let referenceHash: String
    let subjectKind: String
    let subjectID: String
    let workstreamID: String?
    let updatedAt: Date
  }

  static func registerMigration(
    on migrator: inout DatabaseMigrator,
    defaults: UserDefaults,
    ownerID: String
  ) {
    let legacyBindings = loadLegacyBindings(defaults: defaults, ownerID: ownerID)
    migrator.registerMigration(migrationName) { db in
      try createTables(in: db)
      for binding in legacyBindings {
        try db.execute(
          sql: """
            INSERT INTO subject_bindings
              (referenceHash, subjectKind, subjectID, workstreamID, confidence, source,
               occurrenceCount, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, 1.0, 'legacy_explicit_open', 1, ?, ?)
            ON CONFLICT(referenceHash) DO UPDATE SET
              subjectKind = excluded.subjectKind,
              subjectID = excluded.subjectID,
              workstreamID = excluded.workstreamID,
              confidence = excluded.confidence,
              source = excluded.source,
              updatedAt = excluded.updatedAt
            """,
          arguments: [
            binding.referenceHash,
            binding.subjectKind,
            binding.subjectID,
            binding.workstreamID,
            binding.updatedAt,
            binding.updatedAt,
          ])
      }
    }
  }

  static func removeMigratedLegacyDefaults(
    afterMigrating queue: DatabaseWriter,
    defaults: UserDefaults,
    ownerID: String
  ) throws {
    let migrationApplied = try queue.read { db in
      try db.tableExists("subject_bindings")
    }
    guard migrationApplied else { return }
    defaults.removeObject(forKey: legacyDefaultsKey(ownerID: ownerID))
  }

  @discardableResult
  static func deleteExpiredDeliveries(in db: Database, now: Date) throws -> Int {
    try db.execute(
      sql: "DELETE FROM proactive_deliveries WHERE expiresAt <= ?",
      arguments: [now])
    return db.changesCount
  }

  static func legacyDefaultsKey(ownerID: String) -> String {
    let digest = SHA256.hash(data: Data(ownerID.utf8))
      .map { String(format: "%02x", $0) }
      .joined()
    return "taskContextSubjectMatches.v1.\(digest.prefix(24))"
  }

  private static func loadLegacyBindings(defaults: UserDefaults, ownerID: String) -> [LegacyBinding] {
    guard let data = defaults.data(forKey: legacyDefaultsKey(ownerID: ownerID)),
      let decoded = try? JSONDecoder().decode([LegacyBinding].self, from: data)
    else { return [] }
    return decoded
  }

  private static func createTables(in db: Database) throws {
    try db.create(table: "context_buckets") { table in
      table.primaryKey("id", .text)
      table.column("subjectKind", .text).notNull()
      table.column("subjectID", .text).notNull()
      table.column("workstreamID", .text)
      table.column("displayLabel", .text)
      table.column("notifyWorthiness", .double).notNull().defaults(to: 0)
      table.column("visitCount", .integer).notNull().defaults(to: 0)
      table.column("lastVisitedAt", .datetime)
      table.column("createdAt", .datetime).notNull()
      table.column("updatedAt", .datetime).notNull()
      table.uniqueKey(["subjectKind", "subjectID", "workstreamID"])
    }

    try db.create(table: "context_visits") { table in
      table.autoIncrementedPrimaryKey("id")
      table.column("contextGeneration", .integer).notNull()
      table.column("poolEpoch", .integer).notNull()
      table.column("bucketID", .text).references("context_buckets", onDelete: .setNull)
      table.column("appName", .text).notNull()
      table.column("rawContextKey", .text).notNull()
      table.column("normalizedContextKey", .text).notNull()
      table.column("referenceHash", .text).notNull()
      table.column("startedAt", .datetime).notNull()
      table.column("settledAt", .datetime)
      table.column("endedAt", .datetime)
      table.column("outcome", .text).notNull().defaults(to: "active")
      table.column("exitReason", .text)
      table.column("lastScreenshotID", .integer).references("screenshots", onDelete: .setNull)
      table.column("createdAt", .datetime).notNull()
      table.column("updatedAt", .datetime).notNull()
      table.check(sql: "outcome IN ('active', 'completed', 'interrupted', 'discarded')")
    }

    try db.create(table: "bucket_versions") { table in
      table.autoIncrementedPrimaryKey("id")
      table.column("bucketID", .text).notNull().references("context_buckets", onDelete: .cascade)
      table.column("version", .integer).notNull()
      table.column("header", .text).notNull()
      table.column("frozenRankedSegment", .blob).notNull()
      table.column("rankedTokenCount", .integer).notNull().defaults(to: 0)
      table.column("createdAt", .datetime).notNull()
      table.uniqueKey(["bucketID", "version"])
    }

    try db.create(table: "bucket_entries") { table in
      table.primaryKey("id", .text)
      table.column("bucketID", .text).notNull().references("context_buckets", onDelete: .cascade)
      table.column("visitID", .integer).notNull().references("context_visits", onDelete: .cascade)
      table.column("bucketVersionID", .integer).references("bucket_versions", onDelete: .setNull)
      table.column("appName", .text).notNull()
      table.column("rawContextKey", .text).notNull()
      table.column("normalizedContextKey", .text).notNull()
      table.column("narrative", .text).notNull()
      table.column("evidenceRefsJson", .text).notNull()
      table.column("tokenCount", .integer).notNull()
      table.column("isCompacted", .boolean).notNull().defaults(to: false)
      table.column("createdAt", .datetime).notNull()
    }

    try db.create(table: "bucket_facts") { table in
      table.primaryKey("id", .text)
      table.column("bucketID", .text).notNull().references("context_buckets", onDelete: .cascade)
      table.column("entryID", .text).notNull().references("bucket_entries", onDelete: .cascade)
      table.column("appName", .text).notNull()
      table.column("statement", .text).notNull()
      table.column("identifiersJson", .text).notNull()
      table.column("evidenceText", .text).notNull()
      table.column("evidenceRefsJson", .text).notNull()
      table.column("validityState", .text).notNull().defaults(to: "proposed")
      table.column("dispositionState", .text).notNull().defaults(to: "none")
      table.column("confidence", .double).notNull()
      table.column("notifyWorthiness", .double).notNull().defaults(to: 0)
      table.column("expiresAt", .datetime)
      table.column("createdAt", .datetime).notNull()
      table.column("updatedAt", .datetime).notNull()
      table.check(
        sql:
          "validityState IN ('proposed', 'validated', 'rejected', 'superseded', 'expired', 'needs_review')"
      )
      table.check(
        sql:
          "dispositionState IN ('none', 'candidate_pending', 'task_created', 'update_proposed')"
      )
    }

    try db.create(table: "subject_bindings") { table in
      table.primaryKey("referenceHash", .text)
      table.column("bucketID", .text).references("context_buckets", onDelete: .setNull)
      table.column("subjectKind", .text).notNull()
      table.column("subjectID", .text).notNull()
      table.column("workstreamID", .text)
      table.column("confidence", .double).notNull()
      table.column("source", .text).notNull()
      table.column("occurrenceCount", .integer).notNull().defaults(to: 1)
      table.column("createdAt", .datetime).notNull()
      table.column("updatedAt", .datetime).notNull()
    }

    try db.create(table: "proactive_deliveries") { table in
      table.primaryKey("id", .text)
      table.column("visitID", .integer).references("context_visits", onDelete: .setNull)
      table.column("bucketID", .text).references("context_buckets", onDelete: .setNull)
      table.column("bucketVersionID", .integer).references("bucket_versions", onDelete: .setNull)
      table.column("decisionType", .text).notNull()
      table.column("lifecycleState", .text).notNull()
      table.column("provenanceJson", .text).notNull()
      table.column("message", .text)
      table.column("attemptedAt", .datetime).notNull()
      table.column("modelCompletedAt", .datetime)
      table.column("policyApprovedAt", .datetime)
      table.column("deliveredAt", .datetime)
      table.column("expiresAt", .datetime).notNull()
      table.column("createdAt", .datetime).notNull()
      table.check(
        sql:
          "lifecycleState IN ('attempted', 'model_completed', 'policy_approved', 'delivered', 'suppressed', 'failed')"
      )
    }

    try db.create(index: "idx_context_visits_context", on: "context_visits", columns: ["normalizedContextKey"])
    try db.execute(
      sql: """
        CREATE UNIQUE INDEX idx_context_buckets_subject
        ON context_buckets(subjectKind, subjectID, COALESCE(workstreamID, ''))
        """)
    try db.create(index: "idx_context_visits_open", on: "context_visits", columns: ["outcome", "endedAt"])
    try db.create(index: "idx_bucket_versions_latest", on: "bucket_versions", columns: ["bucketID", "version"])
    try db.create(index: "idx_bucket_entries_tail", on: "bucket_entries", columns: ["bucketID", "createdAt"])
    try db.create(index: "idx_bucket_entries_app", on: "bucket_entries", columns: ["appName"])
    try db.create(index: "idx_bucket_facts_valid", on: "bucket_facts", columns: ["bucketID", "validityState"])
    try db.create(index: "idx_bucket_facts_app", on: "bucket_facts", columns: ["appName"])
    try db.create(index: "idx_subject_bindings_bucket", on: "subject_bindings", columns: ["bucketID"])
    try db.create(index: "idx_proactive_deliveries_budget", on: "proactive_deliveries", columns: ["deliveredAt"])
    try db.create(index: "idx_proactive_deliveries_expiry", on: "proactive_deliveries", columns: ["expiresAt"])
    try db.create(
      index: "idx_proactive_deliveries_dedup",
      on: "proactive_deliveries",
      columns: ["visitID", "bucketVersionID"],
      unique: true)
  }
}
