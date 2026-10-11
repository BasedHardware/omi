import GRDB

/// Forward-only retirement. Historical registration names must remain unchanged
/// so installed GRDB databases upgrade without erasing their KEEP data.
enum ProactivityRetirementMigration {
  static let retiredTables = [
    "proactive_deliveries", "proactive_candidates", "bucket_facts", "bucket_entries",
    "bucket_versions", "bucket_workstreams", "context_visits", "context_buckets",
    "context_bucket_migration_meta", "jit_trigger_mirror", "jit_trigger_snapshot_receipts",
    "jit_trigger_wakeup_receipts", "jit_ambient_context_state", "jit_nano_billing_observations",
  ]

  static func registerMigration(on migrator: inout DatabaseMigrator) {
    migrator.registerMigration("retireLegacyProactivity") { db in
      // Task resurfacing owns subject bindings. Rebuild without the old bucket
      // foreign key before dropping its parent; preserve every binding and score.
      if try db.tableExists("subject_bindings") {
        try db.execute(
          sql: """
            CREATE TABLE retained_subject_bindings (
              referenceHash TEXT PRIMARY KEY,
              bucketID TEXT,
              subjectKind TEXT NOT NULL,
              subjectID TEXT NOT NULL,
              workstreamID TEXT,
              confidence DOUBLE NOT NULL,
              source TEXT NOT NULL,
              occurrenceCount INTEGER NOT NULL DEFAULT 1,
              createdAt DATETIME NOT NULL,
              updatedAt DATETIME NOT NULL
            );
            INSERT INTO retained_subject_bindings
            SELECT referenceHash, NULL, subjectKind, subjectID, workstreamID, confidence,
                   source, occurrenceCount, createdAt, updatedAt FROM subject_bindings;
            DROP TABLE subject_bindings;
            ALTER TABLE retained_subject_bindings RENAME TO subject_bindings;
            CREATE INDEX idx_subject_bindings_bucket ON subject_bindings(bucketID);
            """)
      }
      for table in retiredTables {
        try db.execute(sql: "DROP TABLE IF EXISTS \(table)")
      }
    }
  }
}
