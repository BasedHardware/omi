import XCTest

@testable import Omi_Computer

/// Synchronizes a lock-holding startup task with the async test without a
/// scheduler sleep. Its semaphore is used only while the production mutation
/// lock is synchronously held, which is exactly the writer-startup contract.
private final class RewindVideoDirectoryLockBarrier: @unchecked Sendable {
  private let stateLock = NSLock()
  private let releaseWriter = DispatchSemaphore(value: 0)
  private var writerHoldingLock = false
  private var cleanupWillAcquireLock = false
  private var writerWaiters: [CheckedContinuation<Void, Never>] = []
  private var cleanupWaiters: [CheckedContinuation<Void, Never>] = []

  func writerIsHoldingLock() {
    let waiters = stateLock.withLock { () -> [CheckedContinuation<Void, Never>] in
      writerHoldingLock = true
      defer { writerWaiters.removeAll() }
      return writerWaiters
    }
    waiters.forEach { $0.resume() }
  }

  func cleanupIsAboutToAcquireLock() {
    let waiters = stateLock.withLock { () -> [CheckedContinuation<Void, Never>] in
      cleanupWillAcquireLock = true
      defer { cleanupWaiters.removeAll() }
      return cleanupWaiters
    }
    waiters.forEach { $0.resume() }
  }

  func waitUntilWriterIsHoldingLock() async {
    if stateLock.withLock({ writerHoldingLock }) { return }
    await withCheckedContinuation { continuation in
      let shouldResume = stateLock.withLock {
        if writerHoldingLock { return true }
        writerWaiters.append(continuation)
        return false
      }
      if shouldResume {
        continuation.resume()
      }
    }
  }

  func waitUntilCleanupWillAcquireLock() async {
    if stateLock.withLock({ cleanupWillAcquireLock }) { return }
    await withCheckedContinuation { continuation in
      let shouldResume = stateLock.withLock {
        if cleanupWillAcquireLock { return true }
        cleanupWaiters.append(continuation)
        return false
      }
      if shouldResume {
        continuation.resume()
      }
    }
  }

  func waitForWriterRelease() {
    releaseWriter.wait()
  }

  func releaseWriterStartup() {
    releaseWriter.signal()
  }
}

/// Exercises the first-frame interleaving where the encoder has created the
/// active day directory but AVAssetWriter has not created its output file yet.
/// Retention cleanup must keep that directory while still removing unrelated
/// empty day directories.
final class RewindActiveChunkRetentionCleanupTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "rewind-active-chunk-cleanup")
    try await RewindStorage.shared.initialize()
  }

  override func tearDown() async throws {
    await VideoChunkEncoder.shared.cancel()
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testCleanupWaitsForWriterStartupAndKeepsEmptyActiveParent() async throws {
    let maybeVideosDirectory = await RewindStorage.shared.getVideosDirectory()
    let videosDirectory = try XCTUnwrap(maybeVideosDirectory)
    let activeChunkPath = "2030-01-02/chunk_030405.mp4"
    let activeDayDirectory = videosDirectory.appendingPathComponent("2030-01-02", isDirectory: true)
    let staleDayDirectory = videosDirectory.appendingPathComponent("2000-01-01", isDirectory: true)
    let fileManager = FileManager.default
    let barrier = RewindVideoDirectoryLockBarrier()

    // Hold the real mutation lock after writer startup creates the empty day
    // directory. Cleanup reaches its real pre-lock seam before startup can
    // continue, recreating the first-frame interleaving without a wall-clock
    // wait or scheduler retry.
    let startupTask = Task.detached { () throws -> RewindVideoChunkReservation in
      try RewindVideoDirectoryMutation.startActiveChunk(at: activeChunkPath) {
        try FileManager.default.createDirectory(at: activeDayDirectory, withIntermediateDirectories: true)
        barrier.writerIsHoldingLock()
        barrier.waitForWriterRelease()
      }
    }
    defer { barrier.releaseWriterStartup() }

    await barrier.waitUntilWriterIsHoldingLock()

    try fileManager.createDirectory(at: staleDayDirectory, withIntermediateDirectories: true)
    XCTAssertTrue(fileManager.fileExists(atPath: activeDayDirectory.path), "precondition: active day is empty")
    XCTAssertTrue(fileManager.fileExists(atPath: staleDayDirectory.path), "precondition: stale day is empty")

    let cleanupTask = Task.detached { () throws -> Void in
      try await RewindStorage.shared.cleanupEmptyDirectories(
        beforeVideoCleanupLock: { barrier.cleanupIsAboutToAcquireLock() }
      )
    }
    await barrier.waitUntilCleanupWillAcquireLock()
    barrier.releaseWriterStartup()

    let activeReservation = try await startupTask.value
    defer { RewindVideoDirectoryMutation.finishActiveChunk(activeReservation) }
    try await cleanupTask.value

    XCTAssertTrue(
      fileManager.fileExists(atPath: activeDayDirectory.path),
      "cleanup must not delete the current encoder chunk's parent before the writer creates its file"
    )
    XCTAssertFalse(
      fileManager.fileExists(atPath: staleDayDirectory.path),
      "the guard must not disable cleanup for unrelated empty video day directories"
    )
  }

  func testStaleFinalizerCannotReleaseSamePathRestartReservation() throws {
    let relativePath = "2030-01-02/chunk_030405.mp4"

    let oldReservation = RewindVideoDirectoryMutation.startActiveChunk(at: relativePath) {}
    var lifecycle = RewindVideoChunkLifecycle()
    lifecycle.install(oldReservation)
    XCTAssertTrue(lifecycle.isWriting(oldReservation))
    XCTAssertTrue(lifecycle.beginFinalization(of: oldReservation))
    XCTAssertFalse(lifecycle.isWriting(oldReservation), "finalizing A must fence later frame writes")
    XCTAssertFalse(lifecycle.beginFinalization(of: oldReservation), "only one caller may finalize A")

    // Simulate cancel/reset of A before its suspended finalization resumes.
    XCTAssertEqual(lifecycle.reset(), oldReservation)
    RewindVideoDirectoryMutation.finishActiveChunk(oldReservation)

    // A restart inside the same second gets the same path but a new lease.
    let newReservation = RewindVideoDirectoryMutation.startActiveChunk(at: relativePath) {}
    defer { RewindVideoDirectoryMutation.finishActiveChunk(newReservation) }
    XCTAssertNotEqual(oldReservation, newReservation)
    XCTAssertEqual(oldReservation.relativePath, newReservation.relativePath)
    lifecycle.install(newReservation)

    XCTAssertNil(
      lifecycle.reset(onlyIfCurrent: oldReservation),
      "late cleanup from A must not clear B just because the paths match"
    )
    XCTAssertTrue(lifecycle.owns(newReservation))
    XCTAssertEqual(
      RewindVideoDirectoryMutation.withActiveChunk { $0 },
      newReservation,
      "late A cleanup must not release B's directory reservation"
    )
  }
}
