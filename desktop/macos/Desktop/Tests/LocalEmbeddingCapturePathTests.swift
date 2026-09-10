import Foundation
import XCTest

@testable import Omi_Computer

private final class HangingEmbeddingEngine: LocalEmbeddingService, @unchecked Sendable {
  let engineID = "hang"
  let modelID = "hang-v1"
  let dimension = 8
  let capabilities = LocalEmbeddingCapabilities(assetsAvailable: true, requiresAppleSilicon: false, maxBatchSize: 8)
  private let parked = OSAllocatedUnfairLock(initialState: [CheckedContinuation<Void, Never>]())
  private(set) var completed = 0

  func embed(_ texts: [String], task: LocalEmbeddingTask) async throws -> [[Float]] {
    await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
      parked.withLock { $0.append(continuation) }
    }
    completed += 1
    return try await HashEmbeddingEngine().embed(texts, task: task)
  }

  func resumeAll() {
    let pending = parked.withLock { parked -> [CheckedContinuation<Void, Never>] in
      let pending = parked
      parked.removeAll()
      return pending
    }
    pending.forEach { $0.resume() }
  }
}

@MainActor
final class LocalEmbeddingCapturePathTests: XCTestCase {
  private var userDir: URL?
  private var hangingEngine: HangingEmbeddingEngine?

  override func setUp() async throws {
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "local-embedding-capture")
    userDir = fixture.userDir
  }

  override func tearDown() async throws {
    hangingEngine?.resumeAll()
    hangingEngine = nil
    await LocalEmbeddingIndexer.shared.setRuntimeForTesting(.makeDefault())
    await RewindStorageTestIsolation.tearDown(userDir: userDir)
    try await super.tearDown()
  }

  func testSessionAndMemoryCompletionDoNotWaitForEmbedding() async throws {
    let engine = HangingEmbeddingEngine()
    hangingEngine = engine
    var runtime = LocalEmbeddingRuntime(
      engines: [engine], defaultEngineID: engine.engineID, record: { _, _ in })
    runtime.probe = { _ in
      LocalEmbeddingProbe(
        appleSilicon: true, assetsAvailable: true, fixtureSucceeded: true, elapsed: .zero, dimension: 8)
    }
    await LocalEmbeddingIndexer.shared.setRuntimeForTesting(runtime)

    let sessionId = try await TranscriptionStorage.shared.startSession(source: "desktop")
    try await TranscriptionStorage.shared.appendSegment(
      sessionId: sessionId, speaker: 0, text: "synthetic session for local embedding detach", startTime: 0, endTime: 1)
    let accepted = try await TranscriptionStorage.shared.markSessionCompleted(
      id: sessionId, backendId: "synthetic-local-embedding-complete")
    XCTAssertTrue(accepted)
    XCTAssertEqual(engine.completed, 0, "session completion must not await NLCE")

    let inserted = try await MemoryStorage.shared.insertLocalMemory(
      MemoryRecord(content: "synthetic memory for local embedding detach"))
    XCTAssertNotNil(inserted.id)
    XCTAssertEqual(engine.completed, 0, "memory insert must not await NLCE")
  }
}
