import XCTest

@testable import Omi_Computer

/// Stranded local-only rows need a bounded fate.
///
/// The extraction durability pipeline inserts locally before the backend
/// create; when that create fails (e.g. an expired auth refresh), the row
/// stays `backendId NULL, backendSynced false` forever because nothing
/// retries `getUnsyncedMemories()`. It keeps counting in cache-first surfaces
/// with no delete affordance. The purge tombstones only rows older than the
/// bound — younger rows keep their retry window — and never touches rows the
/// reconcile owns (those with a backendId).
@MainActor
final class MemoryStaleLocalOnlyPurgeTests: XCTestCase {
  private var userDir: URL?
  private var authSnapshot: RewindStorageTestIsolation.AuthSnapshot?

  override func setUp() async throws {
    authSnapshot = RewindStorageTestIsolation.captureAuthSnapshot()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memory-stale-local-only-purge")
    userDir = fixture.userDir
    RewindStorageTestIsolation.signInForTests(userId: fixture.testUserId)
  }

  override func tearDown() async throws {
    if let authSnapshot {
      RewindStorageTestIsolation.restoreAuthSnapshot(authSnapshot)
    }
    if let userDir {
      await RewindStorageTestIsolation.tearDown(userDir: userDir)
    }
  }

  private func daysAgo(_ days: Double) -> Date {
    Date(timeIntervalSinceNow: -86_400 * days)
  }

  /// `insertLocalMemory` always writes `backendSynced false`; a backendId is
  /// attached here only to prove the purge scopes on it, not on the sync flag.
  private func insertRow(
    content: String,
    createdAt: Date,
    backendId: String? = nil
  ) async throws -> Int64 {
    let record = MemoryRecord(
      backendId: backendId,
      content: content,
      createdAt: createdAt,
      updatedAt: createdAt)
    let inserted = try await MemoryStorage.shared.insertLocalMemory(record)
    return try XCTUnwrap(inserted.id, "inserted row must have an id")
  }

  private func deletedFlag(rowId: Int64) async throws -> Bool? {
    try await MemoryStorage.shared.getMemory(id: rowId)?.deleted
  }

  func testPurgeRemovesOnlyLocalOnlyRowsOlderThanTheBound() async throws {
    let staleRow = try await insertRow(content: "stale stranded", createdAt: daysAgo(45))
    let freshRow = try await insertRow(content: "fresh stranded", createdAt: daysAgo(1))
    let backendIdRow = try await insertRow(
      content: "old but server-backed", createdAt: daysAgo(45), backendId: "backend-1")
    let tombstonedRow = try await insertRow(content: "already tombstoned", createdAt: daysAgo(45))
    try await MemoryStorage.shared.deleteMemory(id: tombstonedRow)

    let purged = try await MemoryStorage.shared.purgeStaleLocalOnlyMemories(olderThan: 30)

    XCTAssertEqual(purged, 1, "only the stale local-only row is purged")
    let staleDeleted = try await deletedFlag(rowId: staleRow)
    XCTAssertEqual(staleDeleted, true, "the stale local-only row is tombstoned")
    let freshDeleted = try await deletedFlag(rowId: freshRow)
    XCTAssertEqual(freshDeleted, false, "a young local-only row keeps its retry window")
    let backendIdDeleted = try await deletedFlag(rowId: backendIdRow)
    XCTAssertEqual(
      backendIdDeleted, false, "rows with a backendId belong to the reconcile, never this purge")
    let tombstonedDeleted = try await deletedFlag(rowId: tombstonedRow)
    XCTAssertEqual(
      tombstonedDeleted, true, "an already-tombstoned row is not counted or touched")
  }

  func testPurgeBoundaryIsExclusiveAtTheCutoff() async throws {
    let now = Date()
    let exactlyAtBound = try await insertRow(
      content: "exactly 30 days old", createdAt: now.addingTimeInterval(-86_400 * 30))
    let justOver = try await insertRow(
      content: "31 days old", createdAt: now.addingTimeInterval(-86_400 * 31))

    let purged = try await MemoryStorage.shared.purgeStaleLocalOnlyMemories(olderThan: 30, now: now)

    XCTAssertEqual(purged, 1)
    let atBoundDeleted = try await deletedFlag(rowId: exactlyAtBound)
    XCTAssertEqual(atBoundDeleted, false)
    let justOverDeleted = try await deletedFlag(rowId: justOver)
    XCTAssertEqual(justOverDeleted, true)
  }

  /// The purge runs next to the reconcile, once per launch per user: a second
  /// call in the same launch must be a no-op even when new stale rows exist.
  func testPurgeIfNeededRunsOncePerLaunchPerUser() async throws {
    await MemoriesViewModel().purgeStaleLocalOnlyMemoriesIfNeeded()

    _ = try await insertRow(content: "stale after first purge", createdAt: daysAgo(45))
    await MemoriesViewModel().purgeStaleLocalOnlyMemoriesIfNeeded()

    let unsynced = try await MemoryStorage.shared.getUnsyncedMemories()
    XCTAssertEqual(
      unsynced.count, 1, "the second same-launch purge must not run against the latched user")
  }
}
