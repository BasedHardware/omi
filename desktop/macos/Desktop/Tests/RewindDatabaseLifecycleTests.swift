import XCTest

@testable import Omi_Computer

final class RewindDatabaseLifecycleTests: XCTestCase {

  func testCloseClearsRunningFlag() async throws {
    let testUserId = "rewind-db-lifecycle-\(UUID().uuidString)"
    let userDir = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
    defer { try? FileManager.default.removeItem(at: userDir) }

    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    let runningFlag = userDir.appendingPathComponent(".omi_running")
    XCTAssertTrue(FileManager.default.fileExists(atPath: runningFlag.path))

    await RewindDatabase.shared.close()

    XCTAssertFalse(FileManager.default.fileExists(atPath: runningFlag.path))
    RewindDatabase.currentUserId = nil
  }

  func testPoolGenerationAdvancesAcrossReopen() async throws {
    let testUserId = "rewind-db-pool-generation-\(UUID().uuidString)"
    let userDir = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
    defer { try? FileManager.default.removeItem(at: userDir) }

    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    let first = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    XCTAssertNotNil(first.pool)

    await RewindDatabase.shared.close()
    let closedGeneration = await RewindDatabase.shared.poolGeneration()
    XCTAssertGreaterThan(
      closedGeneration,
      first.generation,
      "closing the database must invalidate cached storage pools"
    )

    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    let reopened = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    XCTAssertNotNil(reopened.pool)
    XCTAssertGreaterThan(
      reopened.generation,
      closedGeneration,
      "reopening the database must invalidate caches independently from close()"
    )

    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = nil
  }

  /// Regression for the stale indexer cache: after the database self-recovers by
  /// closing its pool, the indexer must reopen it on the next frame instead of
  /// trusting its own cached `isInitialized` flag and emitting repeated
  /// `databaseNotInitialized` errors until the 6-hourly cleanup retries.
  func testIndexerReopensDatabaseAfterSelfRecoveryClose() async throws {
    let testUserId = "rewind-indexer-reopen-\(UUID().uuidString)"
    let userDir = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
    defer { try? FileManager.default.removeItem(at: userDir) }

    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    await RewindIndexer.shared.reset()

    // First initialization: indexer + database both ready.
    let firstReady = await RewindIndexer.shared.ensureInitialized()
    XCTAssertTrue(firstReady)
    let dbReadyAfterInit = await RewindDatabase.shared.isInitialized
    XCTAssertTrue(dbReadyAfterInit)

    // Simulate self-recovery: repeated I/O errors close the pool.
    await RewindDatabase.shared.close()
    let dbReadyAfterClose = await RewindDatabase.shared.isInitialized
    XCTAssertFalse(dbReadyAfterClose)

    // The indexer's cached flag is now stale. It must reconcile against the
    // authoritative database readiness and reopen the pool.
    let reopened = await RewindIndexer.shared.ensureInitialized()
    XCTAssertTrue(reopened, "indexer must reinitialize after the database self-recovers")
    let dbReadyAfterReopen = await RewindDatabase.shared.isInitialized
    XCTAssertTrue(
      dbReadyAfterReopen,
      "stale indexer cache must reopen the closed database instead of leaving it closed"
    )

    await RewindIndexer.shared.reset()
    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = nil
  }
}
