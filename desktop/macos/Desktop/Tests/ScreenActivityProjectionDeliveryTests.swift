import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

private final class ProjectionDeliveryState: @unchecked Sendable {
  private let lock = NSLock()
  private var allowed = true
  private var current = true
  var cloud: Bool { lock.withLock { allowed } }
  var owner: Bool { lock.withLock { current } }
  func downgrade() { lock.withLock { allowed = false } }
  func revoke() { lock.withLock { current = false } }
}

final class ScreenActivityProjectionDeliveryTests: XCTestCase {
  private func fixture() throws -> DatabaseQueue {
    let queue = try DatabaseQueue()
    try queue.write { db in
      try db.execute(
        sql: """
          CREATE TABLE screenshots (id INTEGER PRIMARY KEY, timestamp DATETIME, appName TEXT, windowTitle TEXT,
            ocrText TEXT, embedding BLOB, deviceName TEXT, clientDeviceId TEXT, screenActivitySyncState INTEGER DEFAULT 0);
          INSERT INTO screenshots (id, timestamp, appName, ocrText) VALUES (1, '1970-01-01 00:20:00.000', 'Fixture', 'synthetic OCR');
          """)
    }
    return queue
  }

  private func deliver(
    _ db: DatabaseQueue, cursor: Int64?, state: ProjectionDeliveryState,
    push: ([[String: Any]]) async -> Bool
  ) async throws -> Int64? {
    try await ScreenActivitySyncService.deliverPeriodicBatch(
      database: db, afterId: cursor, limit: 100,
      now: Date(timeIntervalSince1970: 4000), authorizationIsCurrent: { state.owner },
      cloudAllowed: { state.cloud }, mutation: LocalMutationAuthorization { state.owner }, push: push)
  }

  private func writeVector(_ db: DatabaseQueue) throws {
    let vector = [Float(0.5), Float(-0.25)].withUnsafeBytes { Data($0) }
    try db.write { try $0.execute(sql: "UPDATE screenshots SET embedding = ? WHERE id = 1", arguments: [vector]) }
  }

  func testTextCursorAdvanceThenLateVectorUploadsExactlyOnceOnBothPaths() async throws {
    for lossless in [false, true] {
      let db = try fixture()
      let state = ProjectionDeliveryState()
      var sends = 0
      let cursor = try await deliver(db, cursor: lossless ? nil : 0, state: state) { rows in
        sends += 1
        XCTAssertEqual(rows.count, 1)
        XCTAssertNil(rows[0]["embedding"])
        return true
      }
      XCTAssertEqual(cursor, 1)
      try writeVector(db)
      let vectorCursor = try await deliver(db, cursor: lossless ? nil : cursor, state: state) { rows in
        sends += 1
        XCTAssertEqual(rows[0]["id"] as? Int64, 1)
        XCTAssertEqual(rows[0]["embedding"] as? [Double], [0.5, -0.25])
        return true
      }
      XCTAssertEqual(vectorCursor, 1)
      let terminal = try await deliver(db, cursor: lossless ? nil : vectorCursor, state: state) { _ in
        XCTFail("fully acknowledged vector repeated")
        return false
      }
      XCTAssertNil(terminal)
      XCTAssertEqual(sends, 2)
      let storedState1 = try await db.read {
        try Int.fetchOne($0, sql: "SELECT screenActivitySyncState FROM screenshots")
      }
      XCTAssertEqual(storedState1, 2)
    }
  }

  func testFreeVectorlessDeliveryAndDowngradeRetainProjectionForUpgrade() async throws {
    for lossless in [false, true] {
      let db = try fixture()
      try writeVector(db)
      let free = ProjectionDeliveryState()
      free.downgrade()
      let cursor = try await deliver(db, cursor: lossless ? nil : 0, state: free) { rows in
        XCTAssertNil(rows[0]["embedding"])
        return true
      }
      XCTAssertEqual(cursor, 1)
      let noRepeat = try await deliver(db, cursor: lossless ? nil : cursor, state: free) { _ in
        XCTFail("free text repeated while optional vector waited")
        return false
      }
      XCTAssertNil(noRepeat)
      let paid = ProjectionDeliveryState()
      _ = try await deliver(db, cursor: lossless ? nil : cursor, state: paid) { rows in
        XCTAssertNotNil(rows[0]["embedding"])
        return true
      }
      let storedState2 = try await db.read {
        try Int.fetchOne($0, sql: "SELECT screenActivitySyncState FROM screenshots")
      }
      XCTAssertEqual(storedState2, 2)
    }
  }

  func testDowngradeAfterReadSendsTextAndRetainsLateProjection() async throws {
    let db = try fixture()
    try writeVector(db)
    let checks = EmbedCallCounter()
    let cursor = try await ScreenActivitySyncService.deliverPeriodicBatch(
      database: db, afterId: 0, limit: 100,
      now: Date(timeIntervalSince1970: 4000), authorizationIsCurrent: { true },
      cloudAllowed: {
        checks.add(1)
        return checks.snapshot() == 1
      }, mutation: .unrestricted,
      push: { rows in
        XCTAssertNil(rows[0]["embedding"])
        return true
      })
    XCTAssertEqual(cursor, 1)
    let receipt = try await db.read { try Int.fetchOne($0, sql: "SELECT screenActivitySyncState FROM screenshots") }
    XCTAssertEqual(receipt, 1)
    _ = try await deliver(db, cursor: cursor, state: ProjectionDeliveryState()) { rows in
      XCTAssertNotNil(rows[0]["embedding"])
      return true
    }
    let terminal = try await db.read { try Int.fetchOne($0, sql: "SELECT screenActivitySyncState FROM screenshots") }
    XCTAssertEqual(terminal, 2)
  }

  func testFailedOrOwnerRevokedPushNeverAcknowledgesAndRetryRetainsVector() async throws {
    for revoke in [false, true] {
      let db = try fixture()
      try writeVector(db)
      let state = ProjectionDeliveryState()
      do {
        _ = try await deliver(db, cursor: 0, state: state) { _ in
          if revoke {
            state.revoke()
            return true
          }
          return false
        }
        XCTFail("failed/revoked push acknowledged")
      } catch {}
      let storedState3 = try await db.read {
        try Int.fetchOne($0, sql: "SELECT screenActivitySyncState FROM screenshots")
      }
      XCTAssertEqual(storedState3, 0)
      let retryState = ProjectionDeliveryState()
      _ = try await deliver(db, cursor: 0, state: retryState) { rows in
        XCTAssertNotNil(rows[0]["embedding"])
        return true
      }
      let storedState4 = try await db.read {
        try Int.fetchOne($0, sql: "SELECT screenActivitySyncState FROM screenshots")
      }
      XCTAssertEqual(storedState4, 2)
    }
  }

  func testVectorArrivingDuringTextPushRemainsEligibleAfterAcknowledgement() async throws {
    let db = try fixture()
    let state = ProjectionDeliveryState()
    let cursor = try await deliver(db, cursor: 0, state: state) { rows in
      XCTAssertNil(rows[0]["embedding"])
      do { try writeVector(db) } catch {
        XCTFail("fixture vector write failed: \(error)")
        return false
      }
      return true
    }
    _ = try await deliver(db, cursor: cursor, state: state) { rows in
      XCTAssertNotNil(rows[0]["embedding"])
      return true
    }
    let storedState5 = try await db.read {
      try Int.fetchOne($0, sql: "SELECT screenActivitySyncState FROM screenshots")
    }
    XCTAssertEqual(storedState5, 2)
  }
}
