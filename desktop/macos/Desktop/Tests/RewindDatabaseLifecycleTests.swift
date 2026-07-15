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

  /// Regression for #9790: after the database self-closes (repeated I/O/corruption
  /// errors close the pool), the indexer's cached `isInitialized` flag went stale and
  /// it never reopened the database until periodic cleanup retried up to 6h later.
  /// The indexer must revalidate against the authoritative database and reopen it.
  func testIndexerReopensDatabaseAfterSelfRecoveryClose() async throws {
    let testUserId = "rewind-indexer-reopen-\(UUID().uuidString)"
    let userDir = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
    defer { try? FileManager.default.removeItem(at: userDir) }

    await RewindDatabase.shared.close()
    await RewindIndexer.shared.reset()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)

    // Prime the indexer so its cached isInitialized flag is true.
    let firstReady = await RewindIndexer.shared.ensureInitialized()
    XCTAssertTrue(firstReady)
    let openedAfterInit = await RewindDatabase.shared.isInitialized
    XCTAssertTrue(openedAfterInit)

    // Simulate the database self-closing after repeated I/O/corruption errors.
    await RewindDatabase.shared.close()
    let closedState = await RewindDatabase.shared.isInitialized
    XCTAssertFalse(closedState)

    // The indexer must notice the authoritative database closed and reopen it,
    // instead of returning a stale "initialized" and emitting databaseNotInitialized.
    let reready = await RewindIndexer.shared.ensureInitialized()
    XCTAssertTrue(reready)
    let reopened = await RewindDatabase.shared.isInitialized
    XCTAssertTrue(reopened, "indexer must reopen a database that closed after it initialized")

    await RewindDatabase.shared.close()
    await RewindIndexer.shared.reset()
    RewindDatabase.currentUserId = nil
  }
}
