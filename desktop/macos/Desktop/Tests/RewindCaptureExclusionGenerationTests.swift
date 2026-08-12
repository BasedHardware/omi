import XCTest

@testable import Omi_Computer

final class RewindCaptureExclusionGenerationTests: XCTestCase {
  func testExclusionInvalidatesQueuedSnapshotAndReincludeStartsNewGeneration() {
    let appName = "RewindCaptureExclusionGenerationTests-\(UUID().uuidString)"
    let initial = RewindCaptureExclusionGeneration.snapshot(appName: appName)
    XCTAssertNotNil(initial)
    XCTAssertTrue(
      initial.map(RewindCaptureExclusionGeneration.isCurrent) ?? false)

    RewindCaptureExclusionGeneration.setExcluded(appName, excluded: true)
    XCTAssertFalse(
      initial.map(RewindCaptureExclusionGeneration.isCurrent) ?? true)
    XCTAssertNil(RewindCaptureExclusionGeneration.snapshot(appName: appName))

    RewindCaptureExclusionGeneration.setExcluded(appName, excluded: false)
    let resumed = RewindCaptureExclusionGeneration.snapshot(appName: appName)
    XCTAssertNotNil(resumed)
    XCTAssertNotEqual(initial?.generation, resumed?.generation)
    XCTAssertTrue(
      resumed.map(RewindCaptureExclusionGeneration.isCurrent) ?? false)
  }

  func testFinalizedChunkCleanupJournalIsOwnerScopedAndIdempotent() {
    let ownerA = "RewindCaptureExclusionGenerationTests-owner-a-\(UUID().uuidString)"
    let ownerB = "RewindCaptureExclusionGenerationTests-owner-b-\(UUID().uuidString)"
    let path = "2026-08-11/chunk-\(UUID().uuidString).mp4"

    RewindExcludedVideoChunkCleanupJournal.enqueue(relativePath: path, ownerID: ownerA)
    RewindExcludedVideoChunkCleanupJournal.enqueue(relativePath: path, ownerID: ownerA)
    XCTAssertEqual(
      RewindExcludedVideoChunkCleanupJournal.pending(ownerID: ownerA), [path])
    XCTAssertTrue(RewindExcludedVideoChunkCleanupJournal.pending(ownerID: ownerB).isEmpty)

    RewindExcludedVideoChunkCleanupJournal.complete(relativePath: path, ownerID: ownerA)
    XCTAssertTrue(RewindExcludedVideoChunkCleanupJournal.pending(ownerID: ownerA).isEmpty)
  }

  func testOwnerTransitionInvalidatesSameOwnerSessionAndRejectsDelayedEmbedding() async {
    await OCREmbeddingService.shared.reset()
    guard let ownerSnapshot = RewindCaptureOwnerSnapshot.capture() else {
      XCTFail("expected an active Rewind owner")
      return
    }

    RewindCaptureOwnerGeneration.beginTransition()
    XCTAssertFalse(ownerSnapshot.isCurrent())
    XCTAssertNil(RewindCaptureOwnerSnapshot.capture())
    await OCREmbeddingService.shared.embedScreenshot(
      id: 42,
      ocrText: "stale owner OCR text that must never enter the next owner batch",
      appName: "Example",
      windowTitle: "Private",
      ownerSnapshot: ownerSnapshot)
    let pendingCount = await OCREmbeddingService.shared.pendingCount
    XCTAssertEqual(pendingCount, 0)
    RewindCaptureOwnerGeneration.endTransition()

    guard let resumed = RewindCaptureOwnerSnapshot.capture() else {
      XCTFail("expected capture to resume")
      return
    }
    XCTAssertNotEqual(ownerSnapshot.generation, resumed.generation)
    XCTAssertTrue(resumed.isCurrent())
    await OCREmbeddingService.shared.reset()
  }
}
