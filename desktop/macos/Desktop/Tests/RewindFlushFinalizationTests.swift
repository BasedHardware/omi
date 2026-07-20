import CoreGraphics
import Foundation
import XCTest

@testable import Omi_Computer

/// A no-sleep barrier that pauses the owning flush after it has published the
/// in-flight finalization, then proves a second flush registered as a waiter.
private final class RewindFlushFinalizationBarrier: @unchecked Sendable {
  private let stateLock = NSLock()
  private var ownerIsPaused = false
  private var joinerRegistered = false
  private var ownerWasReleased = false
  private var ownerPauseWaiters: [CheckedContinuation<Void, Never>] = []
  private var joinerWaiters: [CheckedContinuation<Void, Never>] = []
  private var ownerReleaseWaiters: [CheckedContinuation<Void, Never>] = []

  func pauseOwnerBeforeFinishWriting() async {
    let pauseWaiters = stateLock.withLock { () -> [CheckedContinuation<Void, Never>] in
      ownerIsPaused = true
      defer { ownerPauseWaiters.removeAll() }
      return ownerPauseWaiters
    }
    pauseWaiters.forEach { $0.resume() }

    if stateLock.withLock({ ownerWasReleased }) { return }
    await withCheckedContinuation { continuation in
      let shouldResume = stateLock.withLock {
        if ownerWasReleased { return true }
        ownerReleaseWaiters.append(continuation)
        return false
      }
      if shouldResume {
        continuation.resume()
      }
    }
  }

  func markJoinerRegistered() {
    let waiters = stateLock.withLock { () -> [CheckedContinuation<Void, Never>] in
      joinerRegistered = true
      defer { joinerWaiters.removeAll() }
      return joinerWaiters
    }
    waiters.forEach { $0.resume() }
  }

  func waitUntilOwnerIsPaused() async {
    if stateLock.withLock({ ownerIsPaused }) { return }
    await withCheckedContinuation { continuation in
      let shouldResume = stateLock.withLock {
        if ownerIsPaused { return true }
        ownerPauseWaiters.append(continuation)
        return false
      }
      if shouldResume {
        continuation.resume()
      }
    }
  }

  func waitUntilJoinerIsRegistered() async {
    if stateLock.withLock({ joinerRegistered }) { return }
    await withCheckedContinuation { continuation in
      let shouldResume = stateLock.withLock {
        if joinerRegistered { return true }
        joinerWaiters.append(continuation)
        return false
      }
      if shouldResume {
        continuation.resume()
      }
    }
  }

  func releaseOwner() {
    let waiters = stateLock.withLock { () -> [CheckedContinuation<Void, Never>] in
      ownerWasReleased = true
      defer { ownerReleaseWaiters.removeAll() }
      return ownerReleaseWaiters
    }
    waiters.forEach { $0.resume() }
  }
}

/// Regression coverage for the shutdown path where two components flush the
/// same video writer while AVFoundation is still writing its MP4 trailer.
final class RewindFlushFinalizationTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    await VideoChunkEncoder.shared.setFinalizationHooksForTesting(
      beforeFinishWriting: nil,
      finalizationJoined: nil)
    await RewindStorage.shared.reset()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "rewind-flush-finalization")
    try await RewindStorage.shared.initialize()
  }

  override func tearDown() async throws {
    await VideoChunkEncoder.shared.setFinalizationHooksForTesting(
      beforeFinishWriting: nil,
      finalizationJoined: nil)
    await VideoChunkEncoder.shared.cancel()
    await RewindStorage.shared.reset()
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testConcurrentFlushesJoinFinalizationAndBothReturnDurableChunk() async throws {
    let encoder = VideoChunkEncoder.shared
    let image = try solidRedImage()
    let startedAt = Date()

    let firstFrame = try await encoder.addFrame(image: image, timestamp: startedAt)
    let secondFrame = try await encoder.addFrame(image: image, timestamp: startedAt.addingTimeInterval(1))
    XCTAssertNotNil(firstFrame)
    XCTAssertNotNil(secondFrame)

    let barrier = RewindFlushFinalizationBarrier()
    await encoder.setFinalizationHooksForTesting(
      beforeFinishWriting: { await barrier.pauseOwnerBeforeFinishWriting() },
      finalizationJoined: { barrier.markJoinerRegistered() })
    defer { barrier.releaseOwner() }

    let ownerFlush = Task { try await encoder.flushCurrentChunk() }
    await barrier.waitUntilOwnerIsPaused()

    let joiningFlush = Task { try await encoder.flushCurrentChunk() }
    await barrier.waitUntilJoinerIsRegistered()
    barrier.releaseOwner()

    let ownerValue = try await ownerFlush.value
    let joiningValue = try await joiningFlush.value
    let ownerResult = try XCTUnwrap(ownerValue)
    let joiningResult = try XCTUnwrap(joiningValue)

    XCTAssertEqual(ownerResult.videoChunkPath, joiningResult.videoChunkPath)
    XCTAssertEqual(ownerResult.frames.map(\.frameOffset), [0, 1])
    XCTAssertEqual(joiningResult.frames.map(\.frameOffset), [0, 1])
    XCTAssertEqual(ownerResult.frames.map(\.timestamp), joiningResult.frames.map(\.timestamp))

    let maybeVideosDirectory = await RewindStorage.shared.getVideosDirectory()
    let videosDirectory = try XCTUnwrap(maybeVideosDirectory)
    let videoURL = videosDirectory.appendingPathComponent(ownerResult.videoChunkPath)
    XCTAssertTrue(FileManager.default.fileExists(atPath: videoURL.path))

    let center = try await RewindStorage.shared.videoFrameCenterPixel(
      videoPath: ownerResult.videoChunkPath,
      frameOffset: 0)
    XCTAssertGreaterThan(center.red, center.green)
    XCTAssertGreaterThan(center.red, center.blue)
  }

  func testStopFailsWhenJoinedFinalizationIsCancelled() async throws {
    let encoder = VideoChunkEncoder.shared
    let image = try solidRedImage()
    let startedAt = Date()

    let firstFrame = try await encoder.addFrame(image: image, timestamp: startedAt)
    let secondFrame = try await encoder.addFrame(image: image, timestamp: startedAt.addingTimeInterval(1))
    XCTAssertNotNil(firstFrame)
    XCTAssertNotNil(secondFrame)

    let barrier = RewindFlushFinalizationBarrier()
    await encoder.setFinalizationHooksForTesting(
      beforeFinishWriting: { await barrier.pauseOwnerBeforeFinishWriting() },
      finalizationJoined: { barrier.markJoinerRegistered() })
    defer { barrier.releaseOwner() }

    let ownerFlush = Task { try await encoder.flushCurrentChunk() }
    await barrier.waitUntilOwnerIsPaused()

    let stopTask = Task { await RewindIndexer.shared.stop() }
    await barrier.waitUntilJoinerIsRegistered()

    await encoder.cancel()
    barrier.releaseOwner()

    let stopSucceeded = await stopTask.value
    XCTAssertFalse(stopSucceeded, "shutdown must surface an abandoned in-flight flush")
    do {
      let ownerResult = try await ownerFlush.value
      XCTAssertNil(ownerResult, "cancelled finalization must not report a successful flush")
    } catch RewindError.storageError {
      // Expected: the owner observed the same abandoned finalization.
    } catch {
      XCTFail("expected a finalization storage error, got \(error)")
    }
  }

  private func solidRedImage() throws -> CGImage {
    let width = 96
    let height = 64
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    let context = try XCTUnwrap(
      CGContext(
        data: nil,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: 0,
        space: colorSpace,
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
      ))
    context.setFillColor(red: 1, green: 0, blue: 0, alpha: 1)
    context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    return try XCTUnwrap(context.makeImage())
  }
}
