@preconcurrency import GRDB

enum SiriMemoryExpirySchema {
  static func registerMigration(on migrator: inout DatabaseMigrator) {
    migrator.registerMigration("addSiriMemoryExpiry") { db in
      guard try db.columns(in: "memories").contains(where: { $0.name == "expiresAt" }) == false else { return }
      try db.alter(table: "memories") { table in
        table.add(column: "expiresAt", .datetime)
      }
    }
  }
}
