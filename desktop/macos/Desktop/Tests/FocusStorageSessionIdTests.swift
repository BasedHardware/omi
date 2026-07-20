import XCTest

@testable import Omi_Computer

/// Regression coverage for `FocusStorage.sessionId(forSqliteRowId:)`.
///
/// A freshly-detected focus session used to be inserted in memory with a random
/// UUID id, unrelated to its SQLite `focus_sessions` rowid. `deleteSession`
/// routes a numeric id to the SQLite delete and only removes a UUID-id, not-yet-
/// synced session in memory — so the SQLite row survived and the session
/// resurrected on the next `loadFromSQLite`. When the rowid is known, the
/// in-memory id must be that rowid (as a string) so the delete reaches SQLite.
final class FocusStorageSessionIdTests: XCTestCase {
  func testRowIdBecomesNumericStringThatRoutesToSqliteDelete() {
    let id = FocusStorage.sessionId(forSqliteRowId: 42)
    XCTAssertEqual(id, "42")
    XCTAssertNotNil(
      Int64(id),
      "A rowid-derived id must parse as Int64 so deleteSession removes the SQLite row")
  }

  func testMissingRowIdFallsBackToUUID() {
    let id = FocusStorage.sessionId(forSqliteRowId: nil)
    XCTAssertNil(Int64(id), "A UUID fallback id must not masquerade as a SQLite rowid")
    XCTAssertNotNil(UUID(uuidString: id), "Fallback id must be a valid UUID string")
  }
}
