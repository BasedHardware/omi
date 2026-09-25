import Foundation
@preconcurrency import GRDB

/// Durable page staging for the exhaustive JIT ledger mirror. The active
/// compatibility cache and mirror receipt are never changed until a complete,
/// generation-fenced chain has been validated in one final transaction.
enum KnowledgeLedgerMirrorStagingSchema {
  static func registerMigration(on migrator: inout DatabaseMigrator) {
    migrator.registerMigration("createJITKnowledgeLedgerMirrorStaging") { db in
      try db.create(table: "jit_knowledge_ledger_mirror_staging_epochs") { table in
        table.column("ownerID", .text).primaryKey()
        table.column("accountGeneration", .integer).notNull()
        table.column("sourceGeneration", .integer).notNull()
        table.column("writerEpoch", .integer).notNull()
        table.column("headCommitID", .text).notNull()
        table.column("commitSequence", .integer).notNull()
        table.column("epochID", .text).notNull()
        table.column("expectedCursorHash", .text)
        table.column("expectedCursor", .text)
        table.column("contentRevision", .text).notNull()
        table.column("chainRevision", .text).notNull()
        table.column("scannedCount", .integer).notNull()
        table.column("projectedCount", .integer).notNull()
        table.column("pageCount", .integer).notNull()
        table.column("updatedAt", .datetime).notNull()
      }
      try db.create(table: "jit_knowledge_ledger_mirror_staging_members") { table in
        table.column("ownerID", .text).notNull()
        table.column("epochID", .text).notNull()
        table.column("memoryID", .text).notNull()
        table.column("itemRevision", .integer).notNull()
        table.column("status", .text).notNull()
        table.column("sourceState", .text).notNull()
        table.column("canonicalMemoryID", .text)
        table.column("contentPurged", .boolean).notNull()
        table.column("memoryRecordJSON", .blob)
        table.primaryKey(["ownerID", "memoryID"])
      }
      try db.create(table: "jit_knowledge_ledger_mirror_staging_aliases") { table in
        table.column("ownerID", .text).notNull()
        table.column("epochID", .text).notNull()
        table.column("aliasMemoryID", .text).notNull()
        table.column("canonicalMemoryID", .text).notNull()
        table.column("sourceMemoryID", .text).notNull()
        table.column("reason", .text).notNull()
        table.primaryKey(["ownerID", "aliasMemoryID", "reason"])
      }
      try db.create(table: "jit_knowledge_ledger_mirror_staging_cursors") { table in
        table.column("ownerID", .text).notNull()
        table.column("cursorHash", .text).notNull()
        table.primaryKey(["ownerID", "cursorHash"])
      }
    }
    migrator.registerMigration("addJITKnowledgeLedgerMirrorStagingCursor") { db in
      guard
        try db.columns(in: "jit_knowledge_ledger_mirror_staging_epochs")
          .contains(where: { $0.name == "expectedCursor" }) == false
      else { return }
      try db.alter(table: "jit_knowledge_ledger_mirror_staging_epochs") { table in
        table.add(column: "expectedCursor", .text)
      }
    }
  }
}
