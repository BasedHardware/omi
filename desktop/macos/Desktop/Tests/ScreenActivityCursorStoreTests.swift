import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

final class ScreenActivityCursorStoreTests: XCTestCase {
  func testUnownedHighLegacyCursorCannotSkipNewOwnersFirstRow() async throws {
    let defaults = try makeIsolatedDefaults()
    defaults.set(900_000, forKey: .screenActivitySyncLegacyCursor)
    let auth = EmbeddingTestAuthorization(ownerID: "synthetic-b")
    let store = ScreenActivityCursorStore(defaults: defaults, authority: auth.source)
    let cursor = try store.load(authorization: auth.snapshot)
    XCTAssertEqual(cursor, 0)
    let db = try DatabaseQueue()
    let ids = try await db.write { db in
      try db.execute(
        sql: """
          CREATE TABLE screenshots (id INTEGER PRIMARY KEY, timestamp DATETIME, appName TEXT, windowTitle TEXT,
            ocrText TEXT, embedding BLOB, deviceName TEXT, clientDeviceId TEXT, screenActivitySyncState INTEGER DEFAULT 0);
          INSERT INTO screenshots (id, timestamp, ocrText) VALUES (1, '1970-01-01 00:20:00.000', 'synthetic OCR');
          """)
      return try ScreenActivitySyncService.fetchLegacySyncRows(
        db: db, afterId: cursor, limit: 100, now: Date(timeIntervalSince1970: 4000)
      ).map { $0["id"] as Int64 }
    }
    XCTAssertEqual(ids, [1])
    let saved = try await store.save(1, authorization: auth.snapshot)
    XCTAssertEqual(saved, 1)
    XCTAssertEqual(
      defaults.integer(forKey: .screenActivitySyncLegacyCursor), 900_000, "unowned storage is never claimed")
  }

  func testOwnerStoresRemainSeparateAndLateVectorCannotRollBackCursor() async throws {
    let defaults = try makeIsolatedDefaults()
    let a = EmbeddingTestAuthorization(ownerID: "synthetic-a")
    let b = EmbeddingTestAuthorization(ownerID: "synthetic-b")
    let storeA = ScreenActivityCursorStore(defaults: defaults, authority: a.source)
    let storeB = ScreenActivityCursorStore(defaults: defaults, authority: b.source)
    _ = try await storeA.save(1000, authorization: a.snapshot)
    XCTAssertEqual(try storeB.load(authorization: b.snapshot), 0)
    _ = try await storeB.save(20, authorization: b.snapshot)
    let older = try await storeB.save(1, authorization: b.snapshot)
    XCTAssertEqual(older, 20)
    XCTAssertEqual(try storeB.load(authorization: b.snapshot), 20)
    XCTAssertEqual(try storeA.load(authorization: a.snapshot), 1000)
  }

  func testSameOwnerReauthenticationRetainsDurableCursorButRejectsOldSessionWrites() async throws {
    let defaults = try makeIsolatedDefaults()
    let auth = EmbeddingTestAuthorization(ownerID: "synthetic-a")
    let original = auth.snapshot
    let store = ScreenActivityCursorStore(defaults: defaults, authority: auth.source)
    _ = try await store.save(50, authorization: original)
    auth.authority.beginTransition()
    XCTAssertThrowsError(try store.load(authorization: original))
    auth.authority.endTransition(ownerID: auth.ownerID)
    do {
      _ = try await store.save(9999, authorization: original)
      XCTFail("old session saved")
    } catch { XCTAssertEqual(error as? LocalMutationAuthorizationError, .revoked) }
    XCTAssertEqual(try store.load(authorization: auth.snapshot), 50)
    _ = try await store.save(60, authorization: auth.snapshot)
    XCTAssertEqual(try store.load(authorization: auth.snapshot), 60)
  }
}
