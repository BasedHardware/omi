import XCTest

@testable import Omi_Computer

final class OCREmbeddingLosslessTests: XCTestCase {
  func testFiveMinuteCompactionEmbedsOnlyLongestOCRText() async throws {
    let now = Date(timeIntervalSince1970: 2_000)
    let spy = LosslessEmbeddingSpy()
    let service = makeService(now: now, spy: spy) { texts, _ in
      await spy.recordTexts(texts)
      return texts.map { _ in [Float](repeating: 0, count: EmbeddingService.embeddingDimension) }
    }
    let ownerSnapshot = try XCTUnwrap(RewindCaptureOwnerSnapshot.capture())

    await service.embedScreenshot(
      id: 1, timestamp: Date(timeIntervalSince1970: 1_200), ocrText: "short synthetic OCR text",
      appName: "SyntheticApp", windowTitle: "SyntheticWindow", ownerSnapshot: ownerSnapshot)
    await service.embedScreenshot(
      id: 2, timestamp: Date(timeIntervalSince1970: 1_220),
      ocrText: "the longest synthetic OCR text in this completed bucket",
      appName: "SyntheticApp", windowTitle: "SyntheticWindow", ownerSnapshot: ownerSnapshot)
    await service.embedScreenshot(
      id: 3, timestamp: Date(timeIntervalSince1970: 1_240), ocrText: "medium synthetic OCR text here",
      appName: "SyntheticApp", windowTitle: "SyntheticWindow", ownerSnapshot: ownerSnapshot)

    await service.flushPendingEmbeddings()

    let embeddedTexts = await spy.texts
    XCTAssertEqual(embeddedTexts.count, 1)
    XCTAssertTrue(embeddedTexts[0].contains("the longest synthetic OCR text"))
    let writtenIDs = await spy.ids
    let pendingCount = await service.pendingCount
    XCTAssertEqual(writtenIDs, [2])
    XCTAssertEqual(pendingCount, 0)
    await service.reset()
  }

  func testGatedAndFailedBatchesRemainQueuedForRetry() async throws {
    let now = Date(timeIntervalSince1970: 2_000)
    let ownerSnapshot = try XCTUnwrap(RewindCaptureOwnerSnapshot.capture())
    let embedders: [OCREmbeddingService.BatchEmbedder] = [
      { _, _ in
        throw EmbeddingService.EmbeddingError.serverError(statusCode: 402, body: "synthetic gate")
      },
      { _, _ in throw SyntheticEmbeddingFailure.failed },
    ]

    for (index, embedder) in embedders.enumerated() {
      let spy = LosslessEmbeddingSpy()
      let service = makeService(now: now, spy: spy, embedder: embedder)
      await service.embedScreenshot(
        id: Int64(index + 10), timestamp: Date(timeIntervalSince1970: 1_200),
        ocrText: "synthetic retryable OCR text long enough to embed",
        appName: "SyntheticApp", windowTitle: nil, ownerSnapshot: ownerSnapshot)

      await service.flushPendingEmbeddings()

      let pendingCount = await service.pendingCount
      let writtenIDs = await spy.ids
      XCTAssertEqual(pendingCount, 1, "both gated and failed batches must remain durable in the queue")
      XCTAssertEqual(writtenIDs, [])
      await service.reset()
    }
  }

  private func makeService(
    now: Date,
    spy: LosslessEmbeddingSpy,
    embedder: @escaping OCREmbeddingService.BatchEmbedder
  ) -> OCREmbeddingService {
    OCREmbeddingService(
      batchEmbedderForTesting: embedder,
      embeddingWriterForTesting: { id, _ in await spy.recordID(id) },
      losslessSyncEnabledForTesting: { true },
      nowForTesting: { now })
  }
}

private enum SyntheticEmbeddingFailure: Error {
  case failed
}

private actor LosslessEmbeddingSpy {
  private(set) var texts: [String] = []
  private(set) var ids: [Int64] = []

  func recordTexts(_ values: [String]) { texts.append(contentsOf: values) }
  func recordID(_ value: Int64) { ids.append(value) }
}
