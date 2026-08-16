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
    "bucket_workstreams",
    "proactive_candidates",
    "subject_bindings",
    "proactive_deliveries",
    "context_bucket_migration_meta",
  ]

  private struct LegacyBinding: Codable {
    let referenceHash: String
    let subjectKind: String
    let subjectID: String
    let workstreamID: String?
    let updatedAt: Date
  }

  private struct LegacyBindingsLoad {
    let present: Bool
    let bindings: [LegacyBinding]
  }

  static func registerMigration(
    on migrator: inout DatabaseMigrator,
    defaults: UserDefaults,
    ownerID: String,
    fallbackOwnerID: String? = nil
  ) {
    let effectiveOwnerID = effectiveLegacyOwnerID(ownerID)
    let primary = loadLegacyBindings(defaults: defaults, ownerID: effectiveOwnerID)
    let fallback = fallbackOwnerID.map { effectiveLegacyOwnerID($0) }
    let sourceOwnerID: String?
    let legacyBindings: [LegacyBinding]
    if primary.present {
      sourceOwnerID = primary.bindings.isEmpty ? nil : effectiveOwnerID
      legacyBindings = primary.bindings
    } else if let fallback, fallback != effectiveOwnerID {
      let fallbackLoad = loadLegacyBindings(defaults: defaults, ownerID: fallback)
      sourceOwnerID = fallbackLoad.bindings.isEmpty ? nil : fallback
      legacyBindings = fallbackLoad.bindings
    } else {
      sourceOwnerID = nil
      legacyBindings = []
    }
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
      try db.execute(
        sql: """
          INSERT OR REPLACE INTO context_bucket_migration_meta
            (migrationName, ownerID, sourceOwnerID, importedCount, createdAt)
          VALUES (?, ?, ?, ?, ?)
          """,
        arguments: [migrationName, effectiveOwnerID, sourceOwnerID, legacyBindings.count, Date()])
    }
    migrator.registerMigration("addContextVisitHandles") { db in
      try db.alter(table: "context_visits") { table in
        table.add(column: "primaryHandleType", .text)
        table.add(column: "primaryHandleValue", .text)
        table.add(column: "handlesJson", .text)
        table.add(column: "bundleID", .text)
      }
      try db.create(
        index: "idx_context_visits_handle",
        on: "context_visits",
        columns: ["primaryHandleType", "primaryHandleValue"])
    }
    migrator.registerMigration("addBucketFactWorkstreamTag") { db in
      try db.alter(table: "bucket_facts") { table in
        // Sanitized workstream label proposed by the extraction model, nil when
        // it abstained or the proposal failed sanitization. Facts written before
        // this column exist as nil and simply never pool.
        table.add(column: "workstreamTag", .text)
      }
      try db.create(
        index: "idx_bucket_facts_workstream",
        on: "bucket_facts",
        columns: ["workstreamTag", "createdAt"])
    }
    // Durable bucket-level workstream assignments and pre-written notification
    // candidates. The dormant `bucket_facts.workstreamTag` column is left
    // untouched: new labels accumulate here so they can be reused across visits.
    migrator.registerMigration("addWorkstreamAssignmentsAndCandidates") { db in
      try db.create(table: "bucket_workstreams") { table in
        table.primaryKey("id", .text)
        table.column("bucketID", .text).notNull().references("context_buckets", onDelete: .cascade)
        table.column("tag", .text).notNull()
        table.column("source", .text).notNull().defaults(to: "reconciler")
        table.column("assignedAt", .datetime).notNull()
        table.uniqueKey(["bucketID", "tag"])
      }
      try db.create(
        index: "idx_bucket_workstreams_tag",
        on: "bucket_workstreams",
        columns: ["tag", "assignedAt"])
      try db.create(table: "proactive_candidates") { table in
        table.primaryKey("id", .text)
        table.column("bucketID", .text).notNull().references("context_buckets", onDelete: .cascade)
        table.column("workstreamTag", .text)
        table.column("message", .text).notNull()
        table.column("groundingFactIDsJson", .text).notNull()
        table.column("triggerNote", .text).notNull()
        table.column("state", .text).notNull().defaults(to: "armed")
        table.column("createdAt", .datetime).notNull()
        table.column("expiresAt", .datetime).notNull()
        table.column("consumedAt", .datetime)
        table.check(sql: "state IN ('armed','consumed','expired')")
      }
      try db.create(
        index: "idx_proactive_candidates_lookup",
        on: "proactive_candidates",
        columns: ["bucketID", "state", "expiresAt"])
      try db.create(
        index: "idx_proactive_candidates_workstream",
        on: "proactive_candidates",
        columns: ["workstreamTag", "state", "expiresAt"])
    }
    // Terminal candidate rows (consumed or expired) are never read again once
    // past their expiry; without cleanup they accumulate for the lifetime of
    // the database. The lookup/workstream indexes above lead with bucketID or
    // workstreamTag, neither useful for a table-wide retention sweep, so this
    // index leads with state instead.
    migrator.registerMigration("addProactiveCandidatesRetentionIndex") { db in
      try db.create(
        index: "idx_proactive_candidates_retention",
        on: "proactive_candidates",
        columns: ["state", "expiresAt"])
    }
  }

  static func removeMigratedLegacyDefaults(
    afterMigrating queue: DatabaseWriter,
    defaults: UserDefaults,
    ownerID: String
  ) throws {
    let migration: (importedCount: Int, sourceOwnerID: String?)? = try queue.read { db in
      guard try db.tableExists("context_bucket_migration_meta") else { return nil }
      guard
        let row = try Row.fetchOne(
          db,
          sql: """
            SELECT importedCount, sourceOwnerID FROM context_bucket_migration_meta
            WHERE migrationName = ? AND ownerID = ?
            """,
          arguments: [migrationName, effectiveLegacyOwnerID(ownerID)])
      else { return nil }
      return (row["importedCount"] as Int? ?? 0, row["sourceOwnerID"] as String?)
    }
    // A table existing only proves that a previous version created the schema;
    // it does not prove that this owner's legacy source was consumed.  Keep the
    // defaults key for late/rollback writers when no import was recorded.
    guard let migration, migration.importedCount > 0, let sourceOwnerID = migration.sourceOwnerID else {
      return
    }
    defaults.removeObject(
      forKey: .taskContextSubjectMatches(
        ownerHash: legacyOwnerHash(sourceOwnerID)))
  }

  @discardableResult
  static func deleteExpiredDeliveries(in db: Database, now: Date) throws -> Int {
    try db.execute(
      sql: "DELETE FROM proactive_deliveries WHERE expiresAt <= ?",
      arguments: [now])
    return db.changesCount
  }

  /// Terminal `proactive_candidates` rows (consumed, expired, or simply past
  /// their `expiresAt`) never get read again — without this they accumulate
  /// indefinitely whenever the reconciler feature is on.
  @discardableResult
  static func deleteExpiredProactiveCandidates(in db: Database, now: Date) throws -> Int {
    try db.execute(
      sql: "DELETE FROM proactive_candidates WHERE state <> 'armed' OR expiresAt <= ?",
      arguments: [now])
    return db.changesCount
  }

  /// Test/migration fixture helper retained for callers that need to seed the
  /// pre-context-buckets defaults entry. Production reads/removes use the
  /// typed `ScopedDefaultsKey` directly below so the storage namespace cannot
  /// drift from the live legacy matcher.
  static func legacyDefaultsKey(ownerID: String) -> ScopedDefaultsKey {
    .taskContextSubjectMatches(ownerHash: legacyOwnerHash(effectiveLegacyOwnerID(ownerID)))
  }

  /// The legacy matcher names the signed-out owner `signed-out`; Rewind's
  /// anonymous database directory is still named `anonymous`.  Keep storage
  /// paths unchanged while using the same owner namespace for migration keys.
  static func effectiveLegacyOwnerID(_ ownerID: String) -> String {
    ownerID == "anonymous" ? "signed-out" : ownerID
  }

  private static func legacyOwnerHash(_ ownerID: String) -> String {
    SHA256.hash(data: Data(ownerID.utf8))
      .map { String(format: "%02x", $0) }
      .joined()
      .prefix(24)
      .description
  }

  private static func loadLegacyBindings(defaults: UserDefaults, ownerID: String) -> LegacyBindingsLoad {
    guard
      let data = defaults.data(
        forKey: .taskContextSubjectMatches(ownerHash: legacyOwnerHash(ownerID)))
    else { return LegacyBindingsLoad(present: false, bindings: []) }
    let decoded = (try? JSONDecoder().decode([LegacyBinding].self, from: data)) ?? []
    return LegacyBindingsLoad(present: true, bindings: decoded)
  }

  private static func createTables(in db: Database) throws {
    try db.create(table: "context_bucket_migration_meta") { table in
      table.primaryKey("migrationName", .text)
      table.column("ownerID", .text).notNull()
      table.column("sourceOwnerID", .text)
      table.column("importedCount", .integer).notNull()
      table.column("createdAt", .datetime).notNull()
    }

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
