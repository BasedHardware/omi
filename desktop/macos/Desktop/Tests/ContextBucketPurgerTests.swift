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
}
