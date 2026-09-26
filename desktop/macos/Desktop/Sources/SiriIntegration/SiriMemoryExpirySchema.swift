@preconcurrency import GRDB

enum SiriMemoryExpirySchema {
  static func registerMigration(on migrator: inout DatabaseMigrator) {
    migrator.registerMigration("addSiriMemoryExpiry") { db in
      guard try db.columns(in: "memories").contains(where: { $0.name == "expiresAt" }) == false else { return }
      try db.alter(table: "memories") { table in
        table.add(column: "expiresAt", .datetime)
      }
    }
    // Existing rows have no authoritative lock/visibility proof. Nullable
    // columns keep them out of Siri until the next server refresh fills them.
    migrator.registerMigration("addSiriEligibilityState") { db in
      if try !db.columns(in: "memories").contains(where: { $0.name == "isLocked" }) {
        try db.alter(table: "memories") { $0.add(column: "isLocked", .boolean) }
      }
      if try !db.columns(in: "action_items").contains(where: { $0.name == "isLocked" }) {
        try db.alter(table: "action_items") { $0.add(column: "isLocked", .boolean) }
      }
      if try !db.columns(in: "transcription_sessions").contains(where: { $0.name == "visibility" }) {
        try db.alter(table: "transcription_sessions") { $0.add(column: "visibility", .text) }
      }
    }
  }
}
