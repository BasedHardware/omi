import AppKit
import XCTest

@testable import Omi_Computer

final class RewindDatabaseLifecycleTests: XCTestCase {

  func testAcceptedAccountDeletionRemovesOwnerAndLegacyMigrationSources() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("rewind-account-delete-\(UUID().uuidString)", isDirectory: true)
    let profileRoot = root.appendingPathComponent("profile", isDirectory: true)
    let legacyRoot = root.appendingPathComponent("legacy", isDirectory: true)
    let ownerID = "deleted-owner"
    let ownerRoot =
      profileRoot
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(ownerID, isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }

    try FileManager.default.createDirectory(at: ownerRoot, withIntermediateDirectories: true)
    try Data("owner-db".utf8).write(to: ownerRoot.appendingPathComponent("omi.db"))
    try FileManager.default.createDirectory(at: legacyRoot, withIntermediateDirectories: true)
    for artifact in ["omi.db", "omi.db-wal", "omi.db-shm", ".omi_running"] {
      try Data(artifact.utf8).write(to: legacyRoot.appendingPathComponent(artifact))
    }
    for directory in ["Screenshots", "Videos", "backups"] {
      let url = legacyRoot.appendingPathComponent(directory, isDirectory: true)
      try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
      try Data("deleted-owner".utf8).write(to: url.appendingPathComponent("sentinel"))
    }
    let legacyAnonymousRoot =
      legacyRoot
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent("anonymous", isDirectory: true)
    try FileManager.default.createDirectory(at: legacyAnonymousRoot, withIntermediateDirectories: true)
    try Data("anonymous-db".utf8).write(to: legacyAnonymousRoot.appendingPathComponent("omi.db"))

    try await RewindDatabase.shared.applyAcceptedAccountDeletionLocalDataPolicy(
      ownerID: ownerID,
      accepted: true,
      profileRoot: profileRoot,
      legacyRoot: legacyRoot,
      includeLegacyStorage: true)

    XCTAssertFalse(FileManager.default.fileExists(atPath: ownerRoot.path))
    for artifact in [
      "omi.db", "omi.db-wal", "omi.db-shm", ".omi_running",
      "Screenshots", "Videos", "backups",
    ] {
      XCTAssertFalse(
        FileManager.default.fileExists(atPath: legacyRoot.appendingPathComponent(artifact).path),
        "a fresh UID must not be able to migrate \(artifact) from the deleted owner")
    }
    XCTAssertFalse(FileManager.default.fileExists(atPath: legacyAnonymousRoot.path))
  }

  func testAcceptedAccountDeletionWithoutOwnerFailsClosed() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("rewind-account-delete-missing-owner-\(UUID().uuidString)", isDirectory: true)
    let legacyDatabase = root.appendingPathComponent("omi.db")
    defer { try? FileManager.default.removeItem(at: root) }

    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    try Data("must-survive".utf8).write(to: legacyDatabase)

    do {
      try await RewindDatabase.shared.applyAcceptedAccountDeletionLocalDataPolicy(
        ownerID: nil,
        accepted: true,
        profileRoot: root,
        legacyRoot: root,
        includeLegacyStorage: true)
      XCTFail("Accepted deletion without an owner must fail closed")
    } catch {
      XCTAssertTrue(String(describing: error).contains("no cleanup owner"))
    }
    XCTAssertTrue(FileManager.default.fileExists(atPath: legacyDatabase.path))
  }

  func testFailedDeletionRequestPreservesOwnerAndLegacyData() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("rewind-account-delete-failed-\(UUID().uuidString)", isDirectory: true)
    let profileRoot = root.appendingPathComponent("profile", isDirectory: true)
    let legacyRoot = root.appendingPathComponent("legacy", isDirectory: true)
    let ownerRoot =
      profileRoot
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent("retained-owner", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }

    try FileManager.default.createDirectory(at: ownerRoot, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: legacyRoot, withIntermediateDirectories: true)
    let ownerDatabase = ownerRoot.appendingPathComponent("omi.db")
    let legacyDatabase = legacyRoot.appendingPathComponent("omi.db")
    try Data("owner-db".utf8).write(to: ownerDatabase)
    try Data("legacy-db".utf8).write(to: legacyDatabase)

    try await RewindDatabase.shared.applyAcceptedAccountDeletionLocalDataPolicy(
      ownerID: "retained-owner",
      accepted: false,
      profileRoot: profileRoot,
      legacyRoot: legacyRoot,
      includeLegacyStorage: true)

    XCTAssertTrue(FileManager.default.fileExists(atPath: ownerDatabase.path))
    XCTAssertTrue(FileManager.default.fileExists(atPath: legacyDatabase.path))
  }

  func testCloseClearsRunningFlag() async throws {
    let testUserId = "rewind-db-lifecycle-\(UUID().uuidString)"
    let applicationSupportDirectory = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
    )
    let userDir =
      applicationSupportDirectory
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

  /// `App Startup Timing` reported `had_unclean_shutdown = true` on 10 of 11
  /// samples. The flag file is created at the end of `performInitialization()`,
  /// so any of the seventeen storage actors that open the database lazily could
  /// beat the startup-timing reader to it — after which the reader observed
  /// *this* session's flag and called every launch a crash. The verdict must be
  /// a property of the process, not of who asked first.
  func testUncleanShutdownVerdictSurvivesTheDatabaseOpeningFirst() async throws {
    let testUserId = "rewind-db-unclean-order-\(UUID().uuidString)"
    let applicationSupportDirectory = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
    )
    let userDir =
      applicationSupportDirectory
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
    defer { try? FileManager.default.removeItem(at: userDir) }

    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)

    // A storage actor opens the database before anything reads the verdict.
    try await RewindDatabase.shared.initialize()
    let runningFlag = userDir.appendingPathComponent(".omi_running")
    XCTAssertTrue(
      FileManager.default.fileExists(atPath: runningFlag.path),
      "this session's running flag must exist, otherwise the test proves nothing")

    let verdict = await RewindDatabase.shared.hadUncleanShutdown()
    XCTAssertFalse(
      verdict,
      "the previous session ended cleanly; this session's own running flag must not be read as a crash")

    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = nil
  }

  /// The latch must not swallow a real crash: a running flag left behind by a
  /// previous session still reports unclean, whatever order it is read in.
  func testPreviousSessionCrashIsStillReportedAfterTheDatabaseOpens() async throws {
    let testUserId = "rewind-db-unclean-crash-\(UUID().uuidString)"
    let applicationSupportDirectory = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
    )
    let userDir =
      applicationSupportDirectory
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
    defer { try? FileManager.default.removeItem(at: userDir) }

    // Simulate a previous launch that never removed its running flag.
    try FileManager.default.createDirectory(at: userDir, withIntermediateDirectories: true)
    FileManager.default.createFile(
      atPath: userDir.appendingPathComponent(".omi_running").path, contents: nil)

    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    let verdict = await RewindDatabase.shared.hadUncleanShutdown()
    XCTAssertTrue(verdict, "a stale running flag from the previous session is a real unclean shutdown")

    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = nil
  }

  func testPoolGenerationAdvancesAcrossReopen() async throws {
    let testUserId = "rewind-db-pool-generation-\(UUID().uuidString)"
    let applicationSupportDirectory = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
    )
    let userDir =
      applicationSupportDirectory
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

  func testAgentSyncDatabaseFailureReportingClosesPoolForRecovery() async throws {
    let testUserId = "rewind-agent-sync-recovery-\(UUID().uuidString)"
    let applicationSupportDirectory = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
    )
    let userDir =
      applicationSupportDirectory
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
    defer { try? FileManager.default.removeItem(at: userDir) }

    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    // DatabasePool can bridge SQLite error 10 through a generic NSError while
    // preserving it in the localized text; AgentSync must still let the shared
    // recovery owner rotate the stale pool.
    let ioError = NSError(
      domain: "GRDB.DatabaseError",
      code: 1,
      userInfo: [NSLocalizedDescriptionKey: "SQLite error 10: disk I/O error"])
    for _ in 0..<5 {
      await AgentSyncService.reportDatabaseReadFailure(ioError)
    }

    let isInitializedAfterFailures = await RewindDatabase.shared.isInitialized
    XCTAssertFalse(
      isInitializedAfterFailures,
      "AgentSync must let repeated recoverable local read failures rotate the stale pool"
    )

    try await RewindDatabase.shared.initialize()
    let isInitializedAfterRecovery = await RewindDatabase.shared.isInitialized
    XCTAssertTrue(isInitializedAfterRecovery)

    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = nil
  }

  func testInitializeReopensDatabaseClosedAfterIndexerInitialization() async throws {
    let testUserId = "rewind-indexer-reinitialize-\(UUID().uuidString)"
    let applicationSupportDirectory = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
    )
    let userDir =
      applicationSupportDirectory
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
    defer { try? FileManager.default.removeItem(at: userDir) }

    await RewindIndexer.shared.reset()
    await RewindStorage.shared.reset()
    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindIndexer.shared.initialize()
    let initializedBeforeClose = await RewindDatabase.shared.isInitialized
    XCTAssertTrue(initializedBeforeClose)

    // Runtime I/O/corruption recovery closes the pool without resetting the indexer.
    await RewindDatabase.shared.close()
    let initializedAfterClose = await RewindDatabase.shared.isInitialized
    XCTAssertFalse(initializedAfterClose)

    try await RewindIndexer.shared.initialize()
    let initializedAfterReinitialize = await RewindDatabase.shared.isInitialized
    XCTAssertTrue(
      initializedAfterReinitialize,
      "initializing the indexer must reopen a database closed after the indexer was initialized")

    await RewindIndexer.shared.reset()
    await RewindStorage.shared.reset()
    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = nil
  }

  func testProcessFrameReopensDatabaseClosedAfterIndexerInitialization() async throws {
    let testUserId = "rewind-indexer-process-frame-reinitialize-\(UUID().uuidString)"
    let applicationSupportDirectory = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
    )
    let userDir =
      applicationSupportDirectory
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
    defer { try? FileManager.default.removeItem(at: userDir) }

    await RewindIndexer.shared.reset()
    await RewindStorage.shared.reset()
    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindIndexer.shared.initialize()
    let frame = try makeTestFrameImage()

    // Prime the frame pipeline before simulating recovery so its first-frame
    // retention cleanup cannot reopen the database independently of ensureInitialized.
    await RewindIndexer.shared.processFrame(
      cgImage: frame,
      appName: "RewindDatabaseLifecycleTests",
      windowTitle: "prime retention cleanup",
      captureTime: Date())

    // Runtime I/O/corruption recovery closes the pool without resetting the indexer.
    await RewindDatabase.shared.close()
    let initializedAfterClose = await RewindDatabase.shared.isInitialized
    XCTAssertFalse(initializedAfterClose)

    await RewindIndexer.shared.processFrame(
      cgImage: frame,
      appName: "RewindDatabaseLifecycleTests",
      windowTitle: "reopen after close",
      captureTime: Date())

    let initializedAfterProcessFrame = await RewindDatabase.shared.isInitialized
    XCTAssertTrue(
      initializedAfterProcessFrame,
      "processing a frame must reopen a database closed after the indexer was initialized")

    await RewindIndexer.shared.reset()
    await RewindStorage.shared.reset()
    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = nil
  }

  private func makeTestFrameImage() throws -> CGImage {
    let width = 96
    let height = 64
    let context = try XCTUnwrap(
      CGContext(
        data: nil,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: width * 4,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
    context.setFillColor(NSColor.systemBlue.cgColor)
    context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    return try XCTUnwrap(context.makeImage())
  }
}
