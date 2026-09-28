import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

/// Corruption recovery for the Rewind database (closed issue #12145, "Preparing your data…").
///
/// `sqlite3 .recover` prints the whole database as SQL. It used to be read only after
/// `waitUntilExit()`, so any dump over the ~64 KB pipe buffer blocked sqlite3 on write
/// forever, `initialize()` never finished, and the corrupted file stayed at `omi.db` for
/// the next launch to repeat. Its fallback then wrote a `screenshots` table with
/// later-migration columns and no migration ledger, which failed `migrate()` on every launch.
final class RewindDatabaseRecoveryTests: XCTestCase {
  /// XCTest creates a fresh instance per test method, so each test gets its own directory.
  private let scratch = FileManager.default.temporaryDirectory
    .appendingPathComponent("rewind-db-recovery-\(UUID().uuidString)", isDirectory: true)

  override func setUpWithError() throws {
    try FileManager.default.createDirectory(at: scratch, withIntermediateDirectories: true)
  }

  override func tearDownWithError() throws {
    try? FileManager.default.removeItem(at: scratch)
  }

  // MARK: - .recover pipeline

  func testRecoverPipelineImportsADumpFarLargerThanThePipeBuffer() async throws {
    let source = scratch.appendingPathComponent("source.db").path
    let recovered = scratch.appendingPathComponent("recovered.db").path
    try writeBulkTable(at: source, rows: 2_000, payloadBytes: 2_048)

    let outcome = await RewindSQLiteRecoveryPipeline.run(
      corruptedPath: source, recoveredPath: recovered, timeoutSeconds: 60)

    XCTAssertEqual(outcome, .completed)
    let queue = try DatabaseQueue(path: recovered)
    defer { try? queue.close() }
    let count = try await queue.read { db in try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM bulk") }
    XCTAssertEqual(count, 2_000, "every row of a ~4 MB dump must reach the recovered database")
  }

  func testRecoverPipelineTerminatesAHungSQLiteAtTheDeadline() async throws {
    let hung = try makeFakeSQLite3(body: "exec sleep 30")
    let startedAt = Date()

    let outcome = await RewindSQLiteRecoveryPipeline.run(
      corruptedPath: scratch.appendingPathComponent("source.db").path,
      recoveredPath: scratch.appendingPathComponent("recovered.db").path,
      sqlite3URL: hung,
      timeoutSeconds: 0.2,
      killGraceSeconds: 0.1)

    XCTAssertEqual(outcome, .timedOut)
    XCTAssertLessThan(
      Date().timeIntervalSince(startedAt), 10,
      "both children must be terminated at the deadline, not waited out")
  }

  func testRecoverPipelineReportsChildFailure() async throws {
    let failing = try makeFakeSQLite3(body: "exit 3")

    let outcome = await RewindSQLiteRecoveryPipeline.run(
      corruptedPath: scratch.appendingPathComponent("source.db").path,
      recoveredPath: scratch.appendingPathComponent("recovered.db").path,
      sqlite3URL: failing)

    XCTAssertEqual(outcome, .exited(recoverStatus: 3, importStatus: 3))
  }

  func testRecoverPipelineReportsAMissingExecutable() async throws {
    let outcome = await RewindSQLiteRecoveryPipeline.run(
      corruptedPath: scratch.appendingPathComponent("source.db").path,
      recoveredPath: scratch.appendingPathComponent("recovered.db").path,
      sqlite3URL: scratch.appendingPathComponent("no-such-sqlite3"))

    XCTAssertEqual(outcome, .launchFailed)
  }

  // MARK: - Moving the corrupted file aside

  func testMovingTheCorruptedDatabaseAsideLeavesNothingAtItsPath() throws {
    let dbPath = scratch.appendingPathComponent("omi.db").path
    for suffix in ["", "-wal", "-shm", "-journal"] {
      try Data("corrupted\(suffix)".utf8).write(to: URL(fileURLWithPath: dbPath + suffix))
    }
    let backupPath = scratch.appendingPathComponent("backups/omi_corrupted_test.db").path

    let salvageSource = try RewindDatabase.moveCorruptedDatabaseAside(dbPath: dbPath, backupPath: backupPath)

    XCTAssertEqual(salvageSource, backupPath)
    for suffix in ["", "-wal", "-shm", "-journal"] {
      XCTAssertFalse(
        FileManager.default.fileExists(atPath: dbPath + suffix),
        "omi.db\(suffix) must not survive to be reopened (or replayed into a fresh database)")
    }
    XCTAssertEqual(try String(contentsOfFile: backupPath, encoding: .utf8), "corrupted")
    XCTAssertEqual(try String(contentsOfFile: backupPath + "-wal", encoding: .utf8), "corrupted-wal")
    XCTAssertEqual(try String(contentsOfFile: backupPath + "-journal", encoding: .utf8), "corrupted-journal")
    XCTAssertFalse(FileManager.default.fileExists(atPath: backupPath + "-shm"))
  }

  // MARK: - Recovered database validation

  func testRecoveredDatabaseWithACompleteLedgerIsAccepted() throws {
    let ownerID = "rewind-recovery-\(UUID().uuidString)"
    let path = scratch.appendingPathComponent("recovered.db").path
    try writeFullyMigratedDatabase(at: path, ownerID: ownerID, screenshots: 2)

    XCTAssertEqual(RewindDatabase.validatedRecoveredScreenshotCount(at: path, ownerID: ownerID), 2)
  }

  func testRecoveredDatabaseWithAGapInItsLedgerIsRejected() throws {
    let ownerID = "rewind-recovery-\(UUID().uuidString)"
    let path = scratch.appendingPathComponent("recovered.db").path
    try writeFullyMigratedDatabase(at: path, ownerID: ownerID, screenshots: 2)
    // A ledger row lost to corruption: `migrate` would re-run a migration whose column exists.
    let queue = try DatabaseQueue(path: path)
    try queue.write { db in
      try db.execute(sql: "DELETE FROM grdb_migrations WHERE identifier = 'addOcrDataJson'")
    }
    try queue.close()

    XCTAssertNil(RewindDatabase.validatedRecoveredScreenshotCount(at: path, ownerID: ownerID))
  }

  func testRecoveredDatabaseWithoutALedgerIsRejected() throws {
    let path = scratch.appendingPathComponent("recovered.db").path
    try writeBulkTable(at: path, rows: 1, payloadBytes: 1)

    XCTAssertNil(
      RewindDatabase.validatedRecoveredScreenshotCount(at: path, ownerID: "rewind-recovery-\(UUID().uuidString)"))
  }

  // MARK: - Direct-table fallback

  func testDirectTableFallbackDatabaseCompletesTheMigrationLadder() async throws {
    let ownerID = "rewind-recovery-\(UUID().uuidString)"
    let corrupted = scratch.appendingPathComponent("corrupted.db").path
    let recovered = scratch.appendingPathComponent("recovered.db").path
    try writeFullyMigratedDatabase(at: corrupted, ownerID: ownerID, screenshots: 3)

    let salvaged = await RewindDatabase.rebuildScreenshotsFromCorruptedDatabase(
      at: corrupted, into: recovered, ownerID: ownerID)
    XCTAssertEqual(salvaged, 3)

    // Before the fix this threw on every launch: the ladder re-ran from the top against a
    // table that already had later-migration columns.
    let migrated = try migrateToCompletion(recovered, ownerID: ownerID)
    XCTAssertTrue(migrated.completed)
    XCTAssertEqual(migrated.chunks, ["Videos/chunk-0.mp4", "Videos/chunk-1.mp4", "Videos/chunk-2.mp4"])
  }

  // MARK: - End to end

  /// A corrupted `omi.db` whose `.recover` dump is far larger than a pipe buffer: the open
  /// finishes, the corrupted file ends up in backups/, and the next open does not repeat it.
  func testInitializeMovesACorruptedDatabaseAsideAndStartsFresh() async throws {
    let testUserId = "rewind-db-corrupted-\(UUID().uuidString)"
    let applicationSupportDirectory = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
    )
    let userDir =
      applicationSupportDirectory
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
    defer { try? FileManager.default.removeItem(at: userDir) }
    try FileManager.default.createDirectory(at: userDir, withIntermediateDirectories: true)

    let dbPath = userDir.appendingPathComponent("omi.db").path
    try writeBulkTable(at: dbPath, rows: 2_000, payloadBytes: 2_048)
    try corruptSchemaPage(at: dbPath)

    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    let backupDir = userDir.appendingPathComponent("backups", isDirectory: true)
    let backups = try FileManager.default.contentsOfDirectory(atPath: backupDir.path)
      .filter { $0.hasPrefix("omi_corrupted_") && $0.hasSuffix(".db") }
    XCTAssertEqual(backups.count, 1, "the corrupted file must be kept in backups/")
    XCTAssertFalse(
      FileManager.default.fileExists(atPath: userDir.appendingPathComponent("omi_recovered.db").path))

    let openedPool = await RewindDatabase.shared.getDatabaseQueue()
    let pool = try XCTUnwrap(openedPool)
    let hasLedger = try await pool.read { db in try db.tableExists("grdb_migrations") }
    XCTAssertTrue(hasLedger, "the database at omi.db must be a migrated Rewind database")

    // The next launch opens the database at omi.db normally instead of recovering again.
    await RewindDatabase.shared.close()
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()
    let backupsAfterReopen = try FileManager.default.contentsOfDirectory(atPath: backupDir.path)
      .filter { $0.hasPrefix("omi_corrupted_") && $0.hasSuffix(".db") }
    XCTAssertEqual(backupsAfterReopen.count, 1)

    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = nil
  }

  // MARK: - Fixtures

  private func writeBulkTable(at path: String, rows: Int, payloadBytes: Int) throws {
    let payload = String(repeating: "x", count: payloadBytes)
    let queue = try DatabaseQueue(path: path)
    try queue.write { db in
      try db.execute(sql: "CREATE TABLE bulk (id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
      for row in 0..<rows {
        try db.execute(sql: "INSERT INTO bulk (body) VALUES (?)", arguments: ["\(row)-\(payload)"])
      }
    }
    try queue.close()
  }

  private func writeFullyMigratedDatabase(at path: String, ownerID: String, screenshots: Int) throws {
    let queue = try DatabaseQueue(path: path)
    try RewindDatabase.makeMigrator(contextBucketOwnerID: ownerID, legacyOwnerFallback: nil).migrate(queue)
    try queue.write { db in
      for index in 0..<screenshots {
        try db.execute(
          sql: """
            INSERT INTO screenshots (timestamp, appName, windowTitle, imagePath, videoChunkPath, frameOffset)
            VALUES (?, ?, ?, '', ?, ?)
            """,
          arguments: [
            Date(timeIntervalSince1970: 1_700_000_000 + Double(index)), "Safari", "Tab \(index)",
            "Videos/chunk-\(index).mp4", index,
          ])
      }
    }
    try queue.close()
  }

  /// What `performInitialization` does with a rebuilt file: run the whole ladder on it.
  private func migrateToCompletion(_ path: String, ownerID: String) throws -> (completed: Bool, chunks: [String]) {
    let queue = try DatabaseQueue(path: path)
    defer { try? queue.close() }
    let migrator = RewindDatabase.makeMigrator(contextBucketOwnerID: ownerID, legacyOwnerFallback: nil)
    try migrator.migrate(queue)
    return try queue.read { db -> (completed: Bool, chunks: [String]) in
      let completed = try migrator.hasCompletedMigrations(db)
      let chunks = try String.fetchAll(db, sql: "SELECT videoChunkPath FROM screenshots ORDER BY frameOffset")
      return (completed, chunks)
    }
  }

  /// Overwrites the b-tree header of page 1 (the schema table) while keeping the 100-byte
  /// file header valid, so SQLite recognizes the file but reports it malformed.
  private func corruptSchemaPage(at path: String) throws {
    let handle = try FileHandle(forUpdating: URL(fileURLWithPath: path))
    defer { try? handle.close() }
    try handle.seek(toOffset: 100)
    try handle.write(contentsOf: Data(repeating: 0xFF, count: 400))
  }

  private func makeFakeSQLite3(body: String) throws -> URL {
    let url = scratch.appendingPathComponent("fake-sqlite3-\(UUID().uuidString)")
    try "#!/bin/sh\n\(body)\n".write(to: url, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: url.path)
    return url
  }
}
