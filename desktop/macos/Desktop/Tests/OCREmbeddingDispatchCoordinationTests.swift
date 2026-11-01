import Foundation
import XCTest

@testable import Omi_Computer

private final class DispatchCoordinationClock: @unchecked Sendable {
  private let lock = NSLock()
  private var value = Date(timeIntervalSince1970: 20_000)
  func now() -> Date { lock.withLock { value } }
  func advance() { lock.withLock { value.addTimeInterval(61) } }
}

private actor DispatchCoordinationGate {
  private var released = false
  private var continuation: CheckedContinuation<Void, Never>?
  func wait() async {
    if released { return }
    await withCheckedContinuation { continuation = $0 }
  }
  func release() {
    released = true
    continuation?.resume()
    continuation = nil
  }
}

private actor DispatchCoordinationSpy {
  private(set) var calls = 0
  func embed(_ texts: [String]) -> [[Float]] {
    calls += 1
    return texts.map { _ in [Float](repeating: 1, count: EmbeddingService.embeddingDimension) }
  }
}

@MainActor
final class OCREmbeddingDispatchCoordinationTests: XCTestCase {
  private var userDir: URL?

  override func setUp() async throws {
    userDir = try await RewindStorageTestIsolation.setUp(userIdPrefix: "embedding-dispatch").userDir
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: userDir)
  }

  private func seed() async throws -> Int64 {
    let row = try await RewindDatabase.shared.insertScreenshot(
      Screenshot(
        timestamp: Date(timeIntervalSince1970: 1200), appName: "Fixture", windowTitle: "Synthetic",
        imagePath: "", ocrText: "synthetic OCR long enough for shared dispatch", isIndexed: true))
    return try XCTUnwrap(row.id)
  }

  private func service(
    clock: DispatchCoordinationClock, compacted: Bool,
    embed: @escaping OCREmbeddingService.BatchEmbedder
  ) -> OCREmbeddingService {
    let auth = EmbeddingTestAuthorization()
    return OCREmbeddingService(
      ownerAuthorityForTesting: auth.source,
      batchEmbedderForTesting: embed,
      embeddingWriterForTesting: { id, data in
        try await RewindDatabase.shared.updateScreenshotEmbedding(id: id, embedding: data)
      },
      missingEmbeddingIDsForTesting: { try await RewindDatabase.shared.screenshotIDsMissingEmbeddings($0) },
      flushSleeperForTesting: { _ in throw CancellationError() },
      losslessSyncEnabledForTesting: { compacted }, nowForTesting: clock.now,
      screenPolicyForTesting: {
        ScreenEmbeddingPolicy(plan: .operator, status: .active, localRoute: .none, killSwitches: .enabled)
      })
  }

  private func enqueue(_ id: Int64, into service: OCREmbeddingService) async {
    await service.embedScreenshot(
      id: id, timestamp: Date(timeIntervalSince1970: 1200),
      ocrText: "synthetic OCR long enough for shared dispatch", appName: "Fixture", windowTitle: "Synthetic")
  }

  func testRecoveryDoesNotSpendForRowsWaitingInLiveQueue() async throws {
    for compacted in [false, true] {
      let id = try await seed()
      let clock = DispatchCoordinationClock()
      let spy = DispatchCoordinationSpy()
      let service = service(clock: clock, compacted: compacted) { texts, _, _ in await spy.embed(texts) }
      await enqueue(id, into: service)
      let deferred = await service.backfillIfNeeded()
      XCTAssertEqual(deferred, .retry)
      let before = await spy.calls
      XCTAssertEqual(before, 0)
      await service.flushPendingEmbeddings()
      clock.advance()
      let completed = await service.backfillIfNeeded()
      XCTAssertEqual(completed, .complete)
      let calls = await spy.calls
      XCTAssertEqual(calls, 1)
      await service.reset()
    }
  }

  func testRecoveryCannotDuplicateAnInFlightLiveFlush() async throws {
    for compacted in [false, true] {
      let id = try await seed()
      let clock = DispatchCoordinationClock()
      let spy = DispatchCoordinationSpy()
      let gate = DispatchCoordinationGate()
      let entered = expectation(description: "live provider entered")
      let service = service(clock: clock, compacted: compacted) { texts, _, _ in
        entered.fulfill()
        await gate.wait()
        return await spy.embed(texts)
      }
      await enqueue(id, into: service)
      let live = Task { await service.flushPendingEmbeddings() }
      await fulfillment(of: [entered], timeout: 2)
      let deferred = await service.backfillIfNeeded()
      XCTAssertEqual(deferred, .retry)
      await gate.release()
      await live.value
      clock.advance()
      _ = await service.backfillIfNeeded()
      let calls = await spy.calls
      XCTAssertEqual(calls, 1)
      await service.reset()
    }
  }

  func testLiveFlushRechecksPersistedVectorAfterInFlightRecovery() async throws {
    for compacted in [false, true] {
      let id = try await seed()
      let clock = DispatchCoordinationClock()
      let spy = DispatchCoordinationSpy()
      let gate = DispatchCoordinationGate()
      let entered = expectation(description: "recovery provider entered")
      let service = service(clock: clock, compacted: compacted) { texts, _, _ in
        entered.fulfill()
        await gate.wait()
        return await spy.embed(texts)
      }
      let recovery = Task { await service.backfillIfNeeded() }
      await fulfillment(of: [entered], timeout: 2)
      await enqueue(id, into: service)
      await service.flushPendingEmbeddings()
      await gate.release()
      _ = await recovery.value
      await service.flushPendingEmbeddings()
      let calls = await spy.calls
      let pending = await service.pendingCount
      XCTAssertEqual(calls, 1)
      XCTAssertEqual(pending, 0)
      await service.reset()
    }
  }
}
