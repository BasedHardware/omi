import GRDB
import XCTest

@testable import Omi_Computer

final class RewindDeviceNameTests: XCTestCase {
  private var testUserId = ""
  private var userDir: URL?

  override func setUp() async throws {
    try await super.setUp()
    testUserId = "rewind-device-name-test-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    let appSupport = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first,
      "Application Support directory should be available")
    userDir =
      appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
  }

  override func tearDown() async throws {
    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = nil
    if let userDir { try? FileManager.default.removeItem(at: userDir) }
    try await super.tearDown()
  }

  func testScreenshotsMigrationAddsNullableCaptureProvenanceColumnsAndPersistsValues() async throws {
    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      return XCTFail("database should be initialized")
    }

    let column = try await dbQueue.read { db in
      try Row.fetchOne(
        db, sql: "SELECT type, \"notnull\" FROM pragma_table_info('screenshots') WHERE name = 'deviceName'")
    }
    XCTAssertEqual(column?["type"] as? String, "TEXT")
    XCTAssertEqual(column?["notnull"] as? Int64, 0)

    let clientDeviceColumn = try await dbQueue.read { db in
      try Row.fetchOne(
        db, sql: "SELECT type, \"notnull\" FROM pragma_table_info('screenshots') WHERE name = 'clientDeviceId'")
    }
    XCTAssertEqual(clientDeviceColumn?["type"] as? String, "TEXT")
    XCTAssertEqual(clientDeviceColumn?["notnull"] as? Int64, 0)

    _ = try await RewindDatabase.shared.insertScreenshot(
      Screenshot(
        appName: "MigrationTest",
        isIndexed: true,
        deviceName: "Mac Studio",
        clientDeviceId: "macos_test123"))

    let storedProvenance = try await dbQueue.read { db in
      try Row.fetchOne(
        db,
        sql: "SELECT deviceName, clientDeviceId FROM screenshots WHERE appName = ?",
        arguments: ["MigrationTest"])
    }
    XCTAssertEqual(storedProvenance?["deviceName"] as? String, "Mac Studio")
    XCTAssertEqual(storedProvenance?["clientDeviceId"] as? String, "macos_test123")
  }
}
