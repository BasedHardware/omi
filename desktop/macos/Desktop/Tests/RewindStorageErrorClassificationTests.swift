import AVFoundation
import XCTest

@testable import Omi_Computer

/// Regression coverage for #9193: environmental disk/storage failures (the Rewind
/// ffmpeg "The file couldn't be saved" clusters, OMI-DESKTOP-28/29) must be
/// classified as non-actionable so they collapse into breadcrumbs instead of
/// flooding Sentry with unactionable error groups.
final class RewindStorageErrorClassificationTests: XCTestCase {
  func testDiskFullCocoaErrorIsNonActionable() {
    let err = NSError(domain: NSCocoaErrorDomain, code: NSFileWriteOutOfSpaceError)
    XCTAssertTrue(isNonActionableTransient(err))
  }

  func testReadOnlyVolumeIsNonActionable() {
    let err = NSError(domain: NSCocoaErrorDomain, code: NSFileWriteVolumeReadOnlyError)
    XCTAssertTrue(isNonActionableTransient(err))
  }

  func testNoWritePermissionIsNonActionable() {
    let err = NSError(domain: NSCocoaErrorDomain, code: NSFileWriteNoPermissionError)
    XCTAssertTrue(isNonActionableTransient(err))
  }

  func testCocoaErrorWrappingPosixNoSpaceIsNonActionable() {
    let posix = NSError(domain: NSPOSIXErrorDomain, code: 28)  // ENOSPC
    let cocoa = NSError(
      domain: NSCocoaErrorDomain, code: NSFileWriteUnknownError,
      userInfo: [NSUnderlyingErrorKey: posix])
    XCTAssertTrue(isNonActionableTransient(cocoa))
  }

  func testPosixDiskCodesAreNonActionable() {
    XCTAssertTrue(isNonActionableTransient(NSError(domain: NSPOSIXErrorDomain, code: 28)))  // ENOSPC
    XCTAssertTrue(isNonActionableTransient(NSError(domain: NSPOSIXErrorDomain, code: 69)))  // EDQUOT
    XCTAssertTrue(isNonActionableTransient(NSError(domain: NSPOSIXErrorDomain, code: 30)))  // EROFS
  }

  func testRewindStorageWriteFailureWrappingDiskFullIsNonActionable() {
    let disk = NSError(domain: NSCocoaErrorDomain, code: NSFileWriteOutOfSpaceError)
    let rewindError = RewindError.storageWriteFailed("Failed to append frame to HEVC writer", underlying: disk)
    XCTAssertTrue(isNonActionableTransient(rewindError))
  }

  func testRewindStorageWriteFailureWrappingUnknownAVFoundationErrorIsActionable() {
    let avFoundationError = NSError(domain: AVFoundationErrorDomain, code: AVError.unknown.rawValue)
    let rewindError = RewindError.storageWriteFailed(
      "Failed to finalize HEVC writer", underlying: avFoundationError)

    XCTAssertFalse(isNonActionableTransient(rewindError))
  }

  func testStorageWriterFailuresPassStructuredErrorsToLogger() throws {
    let testFile = URL(fileURLWithPath: #filePath)
    let desktopDir = testFile.deletingLastPathComponent().deletingLastPathComponent()
    // omi-test-quality: source-inspection -- static contract: structured Rewind storage-writer errors must reach logError
    let encoder = try String(
      contentsOf: desktopDir.appendingPathComponent("Sources/Rewind/Core/VideoChunkEncoder.swift"),
      encoding: .utf8
    )
    // omi-test-quality: source-inspection -- static contract: structured Rewind storage-writer errors must reach logError
    let indexer = try String(
      contentsOf: desktopDir.appendingPathComponent("Sources/Rewind/Services/RewindIndexer.swift"),
      encoding: .utf8
    )
    // omi-test-quality: source-inspection -- static contract: all fire-and-forget Rewind writer flushes preserve errors for classification
    let resourceMonitor = try String(
      contentsOf: desktopDir.appendingPathComponent("Sources/ResourceMonitor.swift"),
      encoding: .utf8
    )
    // omi-test-quality: source-inspection -- static contract: all fire-and-forget Rewind writer flushes preserve errors for classification
    let proactiveAssistantsPlugin = try String(
      contentsOf: desktopDir.appendingPathComponent("Sources/ProactiveAssistants/ProactiveAssistantsPlugin.swift"),
      encoding: .utf8
    )

    XCTAssertTrue(
      encoder.contains(
        #"logError("VideoChunkEncoder: Failed to start video writer (\(consecutiveWriteFailures)/\(maxConsecutiveFailures))", error: error)"#
      ))
    XCTAssertTrue(
      encoder.contains(
        #"logError("VideoChunkEncoder: Failed to write frame (\(consecutiveWriteFailures)/\(maxConsecutiveFailures))", error: error)"#
      ))
    XCTAssertTrue(indexer.contains(#"logError("RewindIndexer: Failed to process frame", error: error)"#))
    XCTAssertTrue(indexer.contains(#"logError("RewindIndexer: Failed to process CGImage frame", error: error)"#))
    XCTAssertTrue(indexer.contains(#"logError("RewindIndexer: Failed to process frame with metadata", error: error)"#))
    XCTAssertTrue(indexer.contains(#"logError("RewindIndexer: Failed to flush video chunk", error: error)"#))
    XCTAssertTrue(
      encoder.contains(#"logError("VideoChunkEncoder: Failed to finalize stale video chunk", error: error)"#))
    XCTAssertFalse(encoder.contains("try? await finalizeCurrentChunk()"))
    XCTAssertTrue(
      resourceMonitor.contains(
        #"logError("ResourceMonitor: Failed to flush video chunk during memory remediation", error: error)"#))
    XCTAssertFalse(resourceMonitor.contains("try? await VideoChunkEncoder.shared.flushCurrentChunk()"))
    XCTAssertTrue(
      proactiveAssistantsPlugin.contains(
        #"logError("ProactiveAssistantsPlugin: Failed to flush video chunk before power cadence switch", error: error)"#
      ))
  }

  func testGenericStorageErrorStillCaptured() {
    // A plain storage error with no underlying OS cause may be a real bug — keep it.
    XCTAssertFalse(isNonActionableTransient(RewindError.storageError("Cannot add HEVC writer input")))
  }

  func testUnknownCocoaWriteErrorStillCaptured() {
    // NSFileWriteUnknownError (512) with no disk cause may indicate a real bug.
    let err = NSError(domain: NSCocoaErrorDomain, code: NSFileWriteUnknownError)
    XCTAssertFalse(isNonActionableTransient(err))
  }
}
