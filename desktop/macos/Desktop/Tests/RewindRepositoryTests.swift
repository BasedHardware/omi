import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

private actor RewindRepositoryPoolSourceHarness {
  private var current: RewindDatabasePoolSnapshot
  private var initializationCount = 0
  private var initializationError: Error?

  init(pool: DatabasePool?, generation: Int) {
    current = RewindDatabasePoolSnapshot(pool: pool, generation: generation)
  }

  func initialize() throws {
    initializationCount += 1
    if let initializationError { throw initializationError }
  }

  func snapshot() -> RewindDatabasePoolSnapshot {
    current
  }

  func replacePool(with pool: DatabasePool?, generation: Int) {
    current = RewindDatabasePoolSnapshot(pool: pool, generation: generation)
  }

  func failInitialization(with error: Error?) {
    initializationError = error
  }

  func initializeCalls() -> Int {
    initializationCount
  }
}

private struct RewindRepositoryTestError: Error {}

final class RewindRepositoryTests: XCTestCase {
  func testPoolCacheRevalidatesGenerationAndExplicitInvalidation() async throws {
    let firstPool = try makeDatabasePool(name: "first")
    let secondPool = try makeDatabasePool(name: "second")
    defer {
      try? firstPool.close()
      try? secondPool.close()
    }

    let harness = RewindRepositoryPoolSourceHarness(pool: firstPool, generation: 1)
    let repository = RewindRepository(
      owner: "RewindRepositoryTests",
      source: source(for: harness)
    )

    let first = try await repository.databasePool()
    XCTAssertTrue(first === firstPool)
    let callsAfterFirstOpen = await harness.initializeCalls()
    XCTAssertEqual(callsAfterFirstOpen, 1)

    let cached = try await repository.databasePool()
    XCTAssertTrue(cached === firstPool)
    let callsAfterCachedOpen = await harness.initializeCalls()
    XCTAssertEqual(callsAfterCachedOpen, 1)

    await harness.replacePool(with: secondPool, generation: 2)
    let replaced = try await repository.databasePool()
    XCTAssertTrue(replaced === secondPool)
    let callsAfterGenerationChange = await harness.initializeCalls()
    XCTAssertEqual(callsAfterGenerationChange, 2)

    await repository.invalidate()
    let reopened = try await repository.databasePool()
    XCTAssertTrue(reopened === secondPool)
    let callsAfterInvalidation = await harness.initializeCalls()
    XCTAssertEqual(callsAfterInvalidation, 3)
  }

  func testGenerationChangeNeverFallsBackToStalePoolWhenReopenFails() async throws {
    let firstPool = try makeDatabasePool(name: "stale")
    let secondPool = try makeDatabasePool(name: "replacement")
    defer {
      try? firstPool.close()
      try? secondPool.close()
    }

    let harness = RewindRepositoryPoolSourceHarness(pool: firstPool, generation: 1)
    let repository = RewindRepository(
      owner: "RewindRepositoryTests",
      source: source(for: harness)
    )
    let initial = try await repository.databasePool()
    XCTAssertTrue(initial === firstPool)

    await harness.replacePool(with: secondPool, generation: 2)
    await harness.failInitialization(with: RewindRepositoryTestError())

    do {
      _ = try await repository.databasePool()
      XCTFail("a failed reopen must not return the stale pool")
    } catch is RewindRepositoryTestError {
      // Expected.
    }

    await harness.failInitialization(with: nil)
    let recovered = try await repository.databasePool()
    XCTAssertTrue(recovered === secondPool)
  }

  func testInjectedPoolStaysLocalUntilInvalidatedThenUsesSharedSource() async throws {
    let injectedPool = try makeDatabasePool(name: "injected")
    let sharedPool = try makeDatabasePool(name: "shared")
    defer {
      try? injectedPool.close()
      try? sharedPool.close()
    }

    let harness = RewindRepositoryPoolSourceHarness(pool: sharedPool, generation: 4)
    let repository = RewindRepository(
      owner: "RewindRepositoryTests",
      source: source(for: harness),
      initialPool: injectedPool
    )

    let initial = try await repository.databasePool()
    XCTAssertTrue(initial === injectedPool)
    let callsBeforeInvalidation = await harness.initializeCalls()
    XCTAssertEqual(callsBeforeInvalidation, 0)

    await repository.invalidate()
    let reopened = try await repository.databasePool()
    XCTAssertTrue(reopened === sharedPool)
    let callsAfterInvalidation = await harness.initializeCalls()
    XCTAssertEqual(callsAfterInvalidation, 1)
  }

  func testParameterizedFTSRepairRebuildsOnlyItsProjection() async throws {
    let pool = try makeDatabasePool(name: "fts")
    defer { try? pool.close() }

    let definition = RewindFTSDefinition(
      virtualTable: "documents_fts",
      contentTable: "documents",
      indexedColumns: ["title", "body"]
    )
    try await pool.write { database in
      try database.execute(
        sql: "CREATE TABLE documents (id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL)")
      try definition.install(in: database, populateExistingRows: false)
      try database.execute(
        sql: "INSERT INTO documents (title, body) VALUES (?, ?)",
        arguments: ["Durable title", "repair keeps the source row"])
      try database.execute(sql: "DROP TABLE documents_fts")
    }

    let repository = RewindRepository(owner: "RewindRepositoryTests")
    try await repository.repairFTS(definition, in: pool, reason: "test")

    let matches = try await pool.read { database in
      try String.fetchAll(
        database,
        sql: """
          SELECT documents.title
          FROM documents_fts
          JOIN documents ON documents_fts.rowid = documents.id
          WHERE documents_fts MATCH 'repair'
          """)
    }
    XCTAssertEqual(matches, ["Durable title"])

    let repairable = DatabaseError(
      resultCode: .SQLITE_ERROR,
      message: "no such table: documents_fts")
    let unrelated = DatabaseError(
      resultCode: .SQLITE_ERROR,
      message: "no such table: another_projection")
    XCTAssertTrue(definition.matchesRepairableError(repairable))
    XCTAssertFalse(definition.matchesRepairableError(unrelated))
  }

  private func source(for harness: RewindRepositoryPoolSourceHarness) -> RewindDatabasePoolSource {
    RewindDatabasePoolSource(
      initialize: {
        try await harness.initialize()
      },
      snapshot: {
        await harness.snapshot()
      }
    )
  }

  private func makeDatabasePool(name: String) throws -> DatabasePool {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("rewind-repository-tests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    addTeardownBlock {
      try? FileManager.default.removeItem(at: directory)
    }
    return try DatabasePool(path: directory.appendingPathComponent("\(name).sqlite").path)
  }
}
