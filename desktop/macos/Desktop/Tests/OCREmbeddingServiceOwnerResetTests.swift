import XCTest

@testable import Omi_Computer

/// Regression coverage for the OCR-embedding queue surviving account switch.
///
/// `OCREmbeddingService` is a process-lifetime singleton whose pending batch
/// carries the previous owner's screenshot rowids and OCR-derived text. It
/// used to be absent from `RuntimeOwnerIdentity.retargetOwnerBoundLocalStorage`,
/// so its 60s flush (or the next semantic search) wrote the previous owner's
/// embeddings into the next owner's Rewind database. `reset()` must drop all
/// queued owner-bound state at the transition boundary.
final class OCREmbeddingServiceOwnerResetTests: XCTestCase {
  override func setUp() async throws {
    try await super.setUp()
    await OCREmbeddingService.shared.reset()
  }

  override func tearDown() async throws {
    await OCREmbeddingService.shared.reset()
    try await super.tearDown()
  }

  func testResetDropsPendingQueueAndDedupHashes() async {
    let text = "sensitive on-screen text from the previous account, long enough to queue"
    await OCREmbeddingService.shared.embedScreenshot(
      id: 41, ocrText: text, appName: "Notes", windowTitle: "Draft")
    var pending = await OCREmbeddingService.shared.pendingCount
    XCTAssertEqual(pending, 1, "enqueue should buffer the screenshot")

    await OCREmbeddingService.shared.reset()
    pending = await OCREmbeddingService.shared.pendingCount
    XCTAssertEqual(pending, 0, "owner-boundary reset must drop the previous owner's queue")

    // The dedup hash set is also owner-bound state: identical text from the
    // next owner must be embeddable again after reset.
    await OCREmbeddingService.shared.embedScreenshot(
      id: 7, ocrText: text, appName: "Notes", windowTitle: "Draft")
    pending = await OCREmbeddingService.shared.pendingCount
    XCTAssertEqual(pending, 1, "reset must clear recent-hash dedup state")

    await OCREmbeddingService.shared.reset()
  }

  func testFlushAfterResetIsANoOp() async {
    await OCREmbeddingService.shared.embedScreenshot(
      id: 99, ocrText: String(repeating: "previous owner screen text ", count: 3),
      appName: "Safari", windowTitle: nil)
    await OCREmbeddingService.shared.reset()
    // Must return without touching the (new owner's) database or network.
    await OCREmbeddingService.shared.flushPendingEmbeddings()
    let pending = await OCREmbeddingService.shared.pendingCount
    XCTAssertEqual(pending, 0)
  }
}
