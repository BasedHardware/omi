import CoreGraphics
import Foundation
import XCTest

@testable import Omi_Computer

/// Regression coverage for an encoder append failure after earlier frames from
/// the same writer have already been persisted. Recovery must remove the
/// unusable chunk, reject a delayed stale insert, and leave the next writer
/// generation usable.
final class RewindAbandonedChunkRecoveryTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    await VideoChunkEncoder.shared.setAppendFailureAfterSuccessfulFramesForTesting(nil)
    await VideoChunkEncoder.shared.setAbandonmentMarkerWriteFailuresForTesting(0)
    await VideoChunkEncoder.shared.setFinishWritingFailuresForTesting(0)
    await RewindStorage.shared.setAbandonedChunkCleanupFailuresForTesting(0)
    await RewindStorage.shared.setAbandonedChunkDatabaseFailuresForTesting(0)
    await RewindIndexer.shared.reset()
    await RewindStorage.shared.reset()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "rewind-abandoned-chunk")
    try await RewindIndexer.shared.initialize()
  }

  override func tearDown() async throws {
    await VideoChunkEncoder.shared.setAppendFailureAfterSuccessfulFramesForTesting(nil)
    await VideoChunkEncoder.shared.setAbandonmentMarkerWriteFailuresForTesting(0)
    await VideoChunkEncoder.shared.setFinishWritingFailuresForTesting(0)
    await RewindStorage.shared.setAbandonedChunkCleanupFailuresForTesting(0)
    await RewindStorage.shared.setAbandonedChunkDatabaseFailuresForTesting(0)
    await VideoChunkEncoder.shared.cancel()
    await RewindIndexer.shared.reset()
    await RewindStorage.shared.reset()
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testAbandonedChunkRetriesAtStartupRejectsDelayedInsertAndAllowsNewGeneration() async throws {
    let encoder = VideoChunkEncoder.shared
    let image = try solidRedImage()
    let captureTime = Date()

    for offset in 0..<2 {
      await RewindIndexer.shared.processFrame(
        cgImage: image,
        appName: "AbandonedChunkRecovery",
        windowTitle: "Initial frame \(offset)",
        captureTime: captureTime.addingTimeInterval(Double(offset))
      )
    }

    let initialRows = try await RewindDatabase.shared.getRecentScreenshots(limit: 10)
    XCTAssertEqual(initialRows.count, 2)
    let abandonedPath = try XCTUnwrap(initialRows.first?.videoChunkPath)
    XCTAssertTrue(initialRows.allSatisfy { $0.videoChunkPath == abandonedPath })

    let maybeVideosDirectory = await RewindStorage.shared.getVideosDirectory()
    let videosDirectory = try XCTUnwrap(maybeVideosDirectory)
    let abandonedURL = videosDirectory.appendingPathComponent(abandonedPath)
    XCTAssertTrue(FileManager.default.fileExists(atPath: abandonedURL.path))

    // The first recovery attempt tombstones the rows but cannot complete file
    // cleanup. AVAssetWriter may already have removed its cancelled output, so
    // the durable marker—not file presence—is the retry contract. Reset
    // consumes the second injected failure, leaving the marker for the next
    // storage startup to retry.
    await RewindStorage.shared.setAbandonedChunkCleanupFailuresForTesting(2)

    // Fail the next five appends. The final failure crosses the production
    // emergency-reset threshold and reaches the indexer recovery boundary.
    await encoder.setAppendFailureAfterSuccessfulFramesForTesting(0)
    for offset in 0..<5 {
      await RewindIndexer.shared.processFrame(
        cgImage: image,
        appName: "AbandonedChunkRecovery",
        windowTitle: "Failure \(offset)",
        captureTime: captureTime.addingTimeInterval(Double(offset + 2))
      )
    }

    let rowsAfterRecovery = try await RewindDatabase.shared.getRecentScreenshots(limit: 10)
    XCTAssertTrue(rowsAfterRecovery.isEmpty)
    let markerCountAfterInitialFailure = try await RewindStorage.shared.abandonedVideoChunkMarkerCountForTesting()
    XCTAssertEqual(markerCountAfterInitialFailure, 1)

    await RewindIndexer.shared.reset()
    await RewindStorage.shared.reset()
    XCTAssertEqual(try RewindAbandonedVideoChunkJournal.markers(in: videosDirectory).count, 1)

    // Storage initialization must retry the retained sidecar before it starts
    // a new writer for this user.
    try await RewindIndexer.shared.initialize()
    let markerCountAfterStartupRetry = try await RewindStorage.shared.abandonedVideoChunkMarkerCountForTesting()
    XCTAssertEqual(markerCountAfterStartupRetry, 0)
    XCTAssertFalse(FileManager.default.fileExists(atPath: abandonedURL.path))

    // Simulate an older pipeline continuation completing after the reset. The
    // durable tombstone must reject it inside the same DB transaction as insert.
    let staleScreenshot = Screenshot(
      timestamp: captureTime.addingTimeInterval(10),
      appName: "AbandonedChunkRecovery",
      windowTitle: "Delayed stale insert",
      imagePath: "",
      videoChunkPath: abandonedPath,
      frameOffset: 99,
      isIndexed: false
    )
    do {
      _ = try await RewindDatabase.shared.insertScreenshot(staleScreenshot)
      XCTFail("a stale abandoned-chunk row must be rejected")
    } catch let error as RewindAbandonedVideoChunkError {
      XCTAssertEqual(error.relativePath, abandonedPath)
    } catch {
      XCTFail("expected abandoned-chunk rejection, got \(error)")
    }

    do {
      _ = try await RewindDatabase.shared.replaceScreenshotsForVideoChunk(
        path: abandonedPath,
        screenshots: [staleScreenshot])
      XCTFail("rebuild must not resurrect an abandoned video chunk")
    } catch let error as RewindAbandonedVideoChunkError {
      XCTAssertEqual(error.relativePath, abandonedPath)
    } catch {
      XCTFail("expected abandoned-chunk rebuild rejection, got \(error)")
    }
    let rowsAfterDelayedInsert = try await RewindDatabase.shared.getRecentScreenshots(limit: 10)
    XCTAssertTrue(rowsAfterDelayedInsert.isEmpty)

    await encoder.setAppendFailureAfterSuccessfulFramesForTesting(nil)
    await RewindIndexer.shared.processFrame(
      cgImage: image,
      appName: "AbandonedChunkRecovery",
      windowTitle: "Replacement generation",
      captureTime: captureTime.addingTimeInterval(11)
    )
    let replacementRows = try await RewindDatabase.shared.getRecentScreenshots(limit: 10)
    XCTAssertEqual(replacementRows.count, 1)
    let replacementPath = try XCTUnwrap(replacementRows.first?.videoChunkPath)
    XCTAssertNotEqual(replacementPath, abandonedPath)

    let flush = try await encoder.flushCurrentChunk()
    XCTAssertEqual(flush?.frames.count, 1)
    XCTAssertTrue(FileManager.default.fileExists(atPath: videosDirectory.appendingPathComponent(replacementPath).path))
  }

  func testMarkerWriteFailureUsesDatabaseFirstOwnerResetFallback() async throws {
    let image = try solidRedImage()
    let captureTime = Date()

    await RewindIndexer.shared.processFrame(
      cgImage: image,
      appName: "AbandonedChunkOwnerReset",
      windowTitle: "Initial frame",
      captureTime: captureTime
    )

    let initialRows = try await RewindDatabase.shared.getRecentScreenshots(limit: 10)
    let abandonedPath = try XCTUnwrap(initialRows.first?.videoChunkPath)
    let maybeVideosDirectory = await RewindStorage.shared.getVideosDirectory()
    let videosDirectory = try XCTUnwrap(maybeVideosDirectory)
    let abandonedURL = videosDirectory.appendingPathComponent(abandonedPath)
    XCTAssertTrue(FileManager.default.fileExists(atPath: abandonedURL.path))

    // The sidecar write fails once. RewindStorage must instead tombstone the
    // old DB path before force-cancelling that reservation and clearing owner
    // configuration, rather than leaving a mixed old/new encoder state.
    await VideoChunkEncoder.shared.setAbandonmentMarkerWriteFailuresForTesting(1)
    await RewindIndexer.shared.reset()
    await RewindStorage.shared.reset()

    let rowsAfterFallback = try await RewindDatabase.shared.getRecentScreenshots(limit: 10)
    XCTAssertTrue(rowsAfterFallback.isEmpty)
    XCTAssertFalse(FileManager.default.fileExists(atPath: abandonedURL.path))
    let encoderDirectoryAfterReset = await VideoChunkEncoder.shared.videosDirectoryForTesting()
    XCTAssertNil(encoderDirectoryAfterReset)

    try await RewindIndexer.shared.initialize()
    await RewindIndexer.shared.processFrame(
      cgImage: image,
      appName: "AbandonedChunkOwnerReset",
      windowTitle: "Replacement frame",
      captureTime: captureTime.addingTimeInterval(1)
    )
    let replacementRows = try await RewindDatabase.shared.getRecentScreenshots(limit: 10)
    XCTAssertEqual(replacementRows.count, 1)
    XCTAssertNotEqual(replacementRows.first?.videoChunkPath, abandonedPath)
  }

  func testNonIndexerFlushReconcilesFinishWritingFailure() async throws {
    let image = try solidRedImage()
    let captureTime = Date()

    await RewindIndexer.shared.processFrame(
      cgImage: image,
      appName: "AbandonedChunkFinishFailure",
      windowTitle: "Initial frame",
      captureTime: captureTime
    )
    let initialRows = try await RewindDatabase.shared.getRecentScreenshots(limit: 10)
    let abandonedPath = try XCTUnwrap(initialRows.first?.videoChunkPath)
    let maybeVideosDirectory = await RewindStorage.shared.getVideosDirectory()
    let videosDirectory = try XCTUnwrap(maybeVideosDirectory)
    let abandonedURL = videosDirectory.appendingPathComponent(abandonedPath)

    await VideoChunkEncoder.shared.setFinishWritingFailuresForTesting(1)
    do {
      _ = try await RewindStorage.shared.flushCurrentVideoChunk()
      XCTFail("explicit storage flush must surface finalization failure")
    } catch {
      // Expected after the shared flush boundary reconciles the marker.
    }

    let rowsAfterFinishFailure = try await RewindDatabase.shared.getRecentScreenshots(limit: 10)
    XCTAssertTrue(rowsAfterFinishFailure.isEmpty)
    XCTAssertFalse(FileManager.default.fileExists(atPath: abandonedURL.path))
    let markerCountAfterFinishFailure = try await RewindStorage.shared.abandonedVideoChunkMarkerCountForTesting()
    XCTAssertEqual(markerCountAfterFinishFailure, 0)

    await VideoChunkEncoder.shared.setFinishWritingFailuresForTesting(0)
    await RewindIndexer.shared.processFrame(
      cgImage: image,
      appName: "AbandonedChunkFinishFailure",
      windowTitle: "Replacement frame",
      captureTime: captureTime.addingTimeInterval(1)
    )
    let rowsAfterFinishReplacement = try await RewindDatabase.shared.getRecentScreenshots(limit: 10)
    XCTAssertEqual(rowsAfterFinishReplacement.count, 1)
  }

  func testStaleTimerFinishFailureReconcilesImmediately() async throws {
    let image = try solidRedImage()
    let staleCaptureTime = Date().addingTimeInterval(-3_600)

    await RewindIndexer.shared.processFrame(
      cgImage: image,
      appName: "AbandonedChunkStaleTimer",
      windowTitle: "Stale frame",
      captureTime: staleCaptureTime
    )
    let initialRows = try await RewindDatabase.shared.getRecentScreenshots(limit: 10)
    let abandonedPath = try XCTUnwrap(initialRows.first?.videoChunkPath)
    let maybeVideosDirectory = await RewindStorage.shared.getVideosDirectory()
    let videosDirectory = try XCTUnwrap(maybeVideosDirectory)
    let abandonedURL = videosDirectory.appendingPathComponent(abandonedPath)

    await VideoChunkEncoder.shared.setFinishWritingFailuresForTesting(1)
    await VideoChunkEncoder.shared.finalizeStaleChunkForTesting()

    let rowsAfterRecovery = try await RewindDatabase.shared.getRecentScreenshots(limit: 10)
    let markerCount = try await RewindStorage.shared.abandonedVideoChunkMarkerCountForTesting()
    XCTAssertTrue(rowsAfterRecovery.isEmpty)
    XCTAssertFalse(FileManager.default.fileExists(atPath: abandonedURL.path))
    XCTAssertEqual(markerCount, 0)
  }

  func testStartupReconcilesMarkerWrittenBeforeDatabaseQuarantine() async throws {
    let maybeVideosDirectory = await RewindStorage.shared.getVideosDirectory()
    let videosDirectory = try XCTUnwrap(maybeVideosDirectory)
    let relativePath = "2099-01-02/chunk_crash_gap.mp4"
    let videoURL = videosDirectory.appendingPathComponent(relativePath)
    try FileManager.default.createDirectory(
      at: videoURL.deletingLastPathComponent(),
      withIntermediateDirectories: true)
    try Data("partial-mp4".utf8).write(to: videoURL)

    let row = Screenshot(
      timestamp: Date(),
      appName: "AbandonedChunkCrashGap",
      windowTitle: "Pre-crash row",
      imagePath: "",
      videoChunkPath: relativePath,
      frameOffset: 0,
      isIndexed: false)
    _ = try await RewindDatabase.shared.insertScreenshot(row)
    _ = try RewindAbandonedVideoChunkJournal.record(
      reservation: .init(generation: 99, relativePath: relativePath),
      in: videosDirectory)

    // This is the exact process-loss boundary: volatile actor configuration is
    // gone, while the sidecar, partial file, and unquarantined DB row survive.
    await RewindStorage.shared.clearVolatileConfigurationForProcessRestartTesting()
    await RewindIndexer.shared.reset()
    let rowsBeforeStartup = try await RewindDatabase.shared.getRecentScreenshots(limit: 10)
    XCTAssertEqual(rowsBeforeStartup.count, 1)

    try await RewindIndexer.shared.initialize()

    let rowsAfterStartup = try await RewindDatabase.shared.getRecentScreenshots(limit: 10)
    let markerCount = try await RewindStorage.shared.abandonedVideoChunkMarkerCountForTesting()
    XCTAssertTrue(rowsAfterStartup.isEmpty)
    XCTAssertFalse(FileManager.default.fileExists(atPath: videoURL.path))
    XCTAssertEqual(markerCount, 0)
  }

  func testOwnerTransitionStopsBeforeDefaultsChangeWhenDurableResetFails() async throws {
    let image = try solidRedImage()
    await RewindIndexer.shared.processFrame(
      cgImage: image,
      appName: "AbandonedChunkOwnerFence",
      windowTitle: "Owner A frame",
      captureTime: Date())

    let ownerA = try XCTUnwrap(fixture?.testUserId)
    let ownerB = "\(ownerA)-replacement"
    let maybeVideosDirectory = await RewindStorage.shared.getVideosDirectory()
    let videosDirectory = try XCTUnwrap(maybeVideosDirectory)
    let suiteName = "rewind-owner-transition-\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    defaults.set(ownerA, forKey: .authUserId)

    await VideoChunkEncoder.shared.setAbandonmentMarkerWriteFailuresForTesting(1)
    await RewindStorage.shared.setAbandonedChunkDatabaseFailuresForTesting(1)
    do {
      _ = try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
        defaults: defaults,
        allowAutomationOverride: false,
        plannedNextOwner: { _, _ in ownerB },
        quiesceVoice: { _, _ in },
        revokeKernelOwner: { _, _ in },
        retargetLocalStorage: { _, _ in XCTFail("retarget must not run after failed preparation") },
        ownerDidChange: { XCTFail("owner notification must not publish after failed preparation") }
      ) { defaults in
        defaults.set(ownerB, forKey: .authUserId)
      }
      XCTFail("owner transition must surface a non-durable Rewind reset")
    } catch {
      // Expected: neither the sidecar nor DB tombstone became durable.
    }

    XCTAssertEqual(defaults.string(forKey: .authUserId), ownerA)
    XCTAssertEqual(RewindDatabase.currentUserId, ownerA)
    let encoderDirectory = await VideoChunkEncoder.shared.videosDirectoryForTesting()
    let isSuspended = await RewindIndexer.shared.isOwnerTransitionSuspendedForTesting()
    XCTAssertEqual(encoderDirectory, videosDirectory)
    XCTAssertFalse(isSuspended)
  }

  func testSuspendedOwnerTransitionDropsNewFramesBeforeReinitialization() async throws {
    let image = try solidRedImage()
    let maybeVideosDirectory = await RewindStorage.shared.getVideosDirectory()
    let videosDirectory = try XCTUnwrap(maybeVideosDirectory)
    await RewindIndexer.shared.suspendForOwnerTransition()

    await RewindIndexer.shared.processFrame(
      cgImage: image,
      appName: "AbandonedChunkOwnerFence",
      windowTitle: "Blocked owner A frame",
      captureTime: Date())

    let rows = try await RewindDatabase.shared.getRecentScreenshots(limit: 10)
    XCTAssertTrue(rows.isEmpty)
    let files = try FileManager.default.subpathsOfDirectory(atPath: videosDirectory.path)
    XCTAssertFalse(files.contains(where: { $0.hasSuffix(".mp4") }))
    await RewindIndexer.shared.resumeAfterOwnerTransition()
  }

  private func solidRedImage() throws -> CGImage {
    let context = try XCTUnwrap(
      CGContext(
        data: nil,
        width: 96,
        height: 64,
        bitsPerComponent: 8,
        bytesPerRow: 0,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
      ))
    context.setFillColor(red: 1, green: 0, blue: 0, alpha: 1)
    context.fill(CGRect(x: 0, y: 0, width: 96, height: 64))
    return try XCTUnwrap(context.makeImage())
  }

  func testOwnerTransitionKeepsRewindSuspendedThroughNotification() async throws {
    let ownerA = try XCTUnwrap(fixture?.testUserId)
    let ownerB = "\(ownerA)-replacement"
    let suiteName = "rewind-owner-resume-order-\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    defaults.set(ownerA, forKey: .authUserId)

    _ = try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      defaults: defaults,
      allowAutomationOverride: false,
      plannedNextOwner: { _, _ in ownerB },
      quiesceVoice: { _, _ in },
      revokeKernelOwner: { _, _ in },
      retargetLocalStorage: { _, _ in
        let isSuspended = await RewindIndexer.shared.isOwnerTransitionSuspendedForTesting()
        XCTAssertTrue(isSuspended)
      },
      ownerDidChange: {
        let isSuspended = await RewindIndexer.shared.isOwnerTransitionSuspendedForTesting()
        XCTAssertTrue(isSuspended)
      }
    ) { defaults in
      defaults.set(ownerB, forKey: .authUserId)
    }

    let isSuspended = await RewindIndexer.shared.isOwnerTransitionSuspendedForTesting()
    XCTAssertFalse(isSuspended)
  }
}
