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

  func testSyncPayloadIncludesDeviceNameWhenPresent() throws {
    let payload = try payloadRow(deviceName: "Mac Studio", clientDeviceId: "macos_test123")

    XCTAssertEqual(payload["deviceName"] as? String, "Mac Studio")
    XCTAssertEqual(payload["clientDeviceId"] as? String, "macos_test123")
    XCTAssertEqual(payload["appName"] as? String, "Safari")
    XCTAssertEqual(payload["windowTitle"] as? String, "GitHub")
    XCTAssertEqual(payload["ocrText"] as? String, "review thread")
    XCTAssertEqual(payload["embedding"] as? [Double], [1.25, -2.5])
  }

  func testSyncPayloadOmitsDeviceNameWhenUnknown() throws {
    let payload = try payloadRow(deviceName: nil, clientDeviceId: nil)

    XCTAssertNil(payload["deviceName"])
    XCTAssertNil(payload["clientDeviceId"])
  }

  private func payloadRow(deviceName: String?, clientDeviceId: String?) throws -> [String: Any] {
    let dbQueue = try DatabaseQueue()
    let embedding = [Float(1.25), Float(-2.5)].withUnsafeBytes { Data($0) }

    return try dbQueue.write { db in
      try db.create(table: "sync_rows", temporary: true) { t in
        t.autoIncrementedPrimaryKey("id")
        t.column("timestamp", .text)
        t.column("appName", .text)
        t.column("windowTitle", .text)
        t.column("ocrText", .text)
        t.column("embedding", .blob)
        t.column("deviceName", .text)
        t.column("clientDeviceId", .text)
      }

      try db.execute(
        sql: """
          INSERT INTO sync_rows (timestamp, appName, windowTitle, ocrText, embedding, deviceName, clientDeviceId)
          VALUES (?, ?, ?, ?, ?, ?, ?)
          """,
        arguments: ["2026-06-26T20:00:00Z", "Safari", "GitHub", "review thread", embedding, deviceName, clientDeviceId])

      guard
        let row = try Row.fetchOne(
          db,
          sql:
            "SELECT id, timestamp, appName, windowTitle, ocrText, embedding, deviceName, clientDeviceId FROM sync_rows"
        )
      else {
        throw RewindDeviceNameTestError.missingRow
      }
      guard let payload = ScreenActivitySyncService.payloadRow(from: row) else {
        throw RewindDeviceNameTestError.missingPayload
      }
      return payload
    }
  }
}

private enum RewindDeviceNameTestError: Error {
  case missingPayload
  case missingRow
}
