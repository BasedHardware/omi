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

  /// The re-entrancy window: a flush that is already mid-embed when the owner
  /// retargets must NOT resume and write the previous owner's rowids into the
  /// next owner's database. `reset()` clearing the queue is not enough because
  /// actors are re-entrant and an in-flight flush already captured its batch.
  ///
  /// Drives the exact interleave deterministically: the injected embedder
  /// suspends the flush at its await, the test runs `reset()` during that
  /// suspension, then releases the embedder. The generation fence must drop the
  /// batch before the writer runs.
  func testResetDuringInFlightFlushDropsStaleBatchBeforeWrite() async {
    let dimension = EmbeddingService.embeddingDimension
    let flushSuspended = AsyncGate()
    let releaseEmbed = AsyncGate()
    let writes = WriteSpy()

    let service = OCREmbeddingService(
      batchEmbedderForTesting: { texts, _ in
        // Signal that the flush is now parked inside the embed await, then wait
        // until the test has run reset() before returning results.
        await flushSuspended.open()
        await releaseEmbed.wait()
        return texts.map { _ in [Float](repeating: 0, count: dimension) }
      },
      embeddingWriterForTesting: { screenshotId, _ in
        await writes.record(screenshotId)
      }
    )

    await service.embedScreenshot(
      id: 500, ocrText: String(repeating: "previous owner text ", count: 3),
      appName: "Notes", windowTitle: nil)

    let flush = Task { await service.flushPendingEmbeddings() }

    // Wait until the flush is suspended inside the embedder (batch + generation
    // already captured), then retarget the owner.
    await flushSuspended.wait()
    await service.reset()

    // Let the embed return. The fence must abandon the stale batch.
    await releaseEmbed.open()
    await flush.value

    let recorded = await writes.ids
    XCTAssertTrue(
      recorded.isEmpty,
      "a flush interrupted mid-embed by an owner reset must not write the previous owner's embeddings")
    let pending = await service.pendingCount
    XCTAssertEqual(pending, 0, "the stale batch must be dropped, not re-queued into the new owner's buffer")
  }
}

/// One-shot async gate: `wait()` suspends until the first `open()`.
private actor AsyncGate {
  private var isOpen = false
  private var waiters: [CheckedContinuation<Void, Never>] = []

  func open() {
    guard !isOpen else { return }
    isOpen = true
    let pending = waiters
    waiters.removeAll()
    for waiter in pending { waiter.resume() }
  }

  func wait() async {
    if isOpen { return }
    await withCheckedContinuation { waiters.append($0) }
  }
}

/// Records screenshot rowids handed to the injected embedding writer.
private actor WriteSpy {
  private(set) var ids: [Int64] = []
  func record(_ id: Int64) { ids.append(id) }
}
