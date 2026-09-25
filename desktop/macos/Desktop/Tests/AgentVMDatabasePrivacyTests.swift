import GRDB
import XCTest

@testable import Omi_Computer

final class AgentVMDatabasePrivacyTests: XCTestCase {
  func testScreenTablesBlockDatabaseUpload() throws {
    let path = FileManager.default.temporaryDirectory
      .appendingPathComponent("agent-vm-privacy-\(UUID().uuidString).sqlite")
    defer { try? FileManager.default.removeItem(at: path) }

    let queue = try DatabaseQueue(path: path.path)
    try queue.write { db in
      try db.execute(sql: "CREATE TABLE screenshots (id INTEGER PRIMARY KEY, ocrText TEXT)")
      XCTAssertTrue(try RewindDatabase.containsScreenData(in: db))
    }
  }

  func testDatabaseWithoutScreenTablesCanBeUploaded() throws {
    let path = FileManager.default.temporaryDirectory
      .appendingPathComponent("agent-vm-privacy-\(UUID().uuidString).sqlite")
    defer { try? FileManager.default.removeItem(at: path) }

    let queue = try DatabaseQueue(path: path.path)
    try queue.write { db in
      try db.execute(sql: "CREATE TABLE memories (id INTEGER PRIMARY KEY, content TEXT)")
      XCTAssertFalse(try RewindDatabase.containsScreenData(in: db))
    }
  }
}
