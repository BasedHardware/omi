import Foundation
import XCTest

@testable import Omi_Computer

private actor HangGate {
  private var continuations: [CheckedContinuation<Void, Never>] = []
  private var parkedWaiters: [CheckedContinuation<Void, Never>] = []
  private var released = false
  private(set) var completed = 0
  private(set) var parked = 0

  func park() async {
    if released { return }
    parked += 1
    let waiters = parkedWaiters
    parkedWaiters.removeAll()
    waiters.forEach { $0.resume() }
    await withTaskCancellationHandler {
      await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
        if released {
          continuation.resume()
        } else {
          continuations.append(continuation)
        }
      }
    } onCancel: {
      Task { await self.resumeAll() }
    }
  }

  func waitUntilParked(_ count: Int) async {
    if parked >= count { return }
    await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
      if parked >= count {
        continuation.resume()
      } else {
        parkedWaiters.append(continuation)
      }
    }
  }

  func finish() {
    completed += 1
  }

  func resumeAll() {
    released = true
    let pending = continuations
    continuations.removeAll()
    pending.forEach { $0.resume() }
  }
}

private struct HangingEmbeddingEngine: LocalEmbeddingService {
  let engineID = "hang"
  let modelID = "hang-v1"
  let dimension = 8
  let capabilities = LocalEmbeddingCapabilities(assetsAvailable: true, requiresAppleSilicon: false, maxBatchSize: 8)
  let gate = HangGate()

  func embed(_ texts: [String], task: LocalEmbeddingTask) async throws -> [[Float]] {
    await gate.park()
    try Task.checkCancellation()
    await gate.finish()
    return try await HashEmbeddingEngine().embed(texts, task: task)
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
    await LocalEmbeddingIndexer.shared.drainForTesting()
    hangingEngine = nil
    await LocalEmbeddingIndexer.shared.setRuntimeForTesting(.makeDefault())
    await RewindStorageTestIsolation.tearDown(userDir: userDir)
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
    runtime.embedBudget = .milliseconds(20)
    await LocalEmbeddingIndexer.shared.setRuntimeForTesting(runtime)

    let sessionId = try await TranscriptionStorage.shared.startSession(source: "desktop")
    try await TranscriptionStorage.shared.appendSegment(
      sessionId: sessionId, speaker: 0, text: "synthetic session for local embedding detach", startTime: 0, endTime: 1)
    // omi-test-quality: wall-clock-wait -- timeout so a synchronous-await regression fails instead of hanging
    let accepted: Bool
    do {
      accepted = try await LocalEmbeddingCallBound.run(.milliseconds(400)) {
        try await TranscriptionStorage.shared.markSessionCompleted(
          id: sessionId, backendId: "synthetic-local-embedding-complete")
      }
    } catch is LocalEmbeddingTimeoutError {
      XCTFail("session completion awaited embedding")
      return
    }
    XCTAssertTrue(accepted)
    await engine.gate.waitUntilParked(1)
    let completedAfterSession = await engine.gate.completed
    XCTAssertEqual(completedAfterSession, 0, "session completion must not await NLCE")

    let inserted: MemoryRecord
    do {
      inserted = try await LocalEmbeddingCallBound.run(.milliseconds(400)) {
        try await MemoryStorage.shared.insertLocalMemory(
          MemoryRecord(content: "synthetic memory for local embedding detach"))
      }
    } catch is LocalEmbeddingTimeoutError {
      XCTFail("memory insert awaited embedding")
      return
    }
    XCTAssertNotNil(inserted.id)
    await engine.gate.waitUntilParked(2)
    let completedAfterMemory = await engine.gate.completed
    XCTAssertEqual(completedAfterMemory, 0, "memory insert must not await NLCE")
  }

  func testBatchMemorySyncSchedulesDetachedIndexing() async throws {
    let engine = HangingEmbeddingEngine()
    hangingEngine = engine
    var runtime = LocalEmbeddingRuntime(
      engines: [engine], defaultEngineID: engine.engineID, record: { _, _ in })
    runtime.probe = { _ in
      LocalEmbeddingProbe(
        appleSilicon: true, assetsAvailable: true, fixtureSucceeded: true, elapsed: .zero, dimension: 8)
    }
    runtime.embedBudget = .milliseconds(20)
    await LocalEmbeddingIndexer.shared.setRuntimeForTesting(runtime)

    let memory = ServerMemory(
      id: "batch-local-embedding-\(UUID().uuidString)",
      content: "synthetic batch memory for local embedding detach",
      category: .system,
      tier: .shortTerm,
      tierIsExplicit: true,
      createdAt: Date(timeIntervalSince1970: 1),
      updatedAt: Date(timeIntervalSince1970: 1),
      conversationId: nil,
      reviewed: false,
      userReview: nil,
      visibility: "private",
      manuallyAdded: false,
      scoring: nil,
      source: "desktop",
      confidence: nil,
      sourceApp: nil,
      contextSummary: nil,
      isRead: false,
      isDismissed: false,
      tags: [],
      reasoning: nil,
      currentActivity: nil,
      inputDeviceName: nil,
      windowTitle: nil,
      headline: nil)
    do {
      try await LocalEmbeddingCallBound.run(.milliseconds(400)) {
        try await MemoryStorage.shared.syncServerMemories([memory])
      }
    } catch is LocalEmbeddingTimeoutError {
      XCTFail("batch memory sync awaited embedding")
      return
    }
    await engine.gate.waitUntilParked(1)
    let completed = await engine.gate.completed
    XCTAssertEqual(completed, 0, "batch memory sync must not await NLCE")
  }

  func testUnchangedMemoryRefreshDoesNotReembed() async throws {
    let counter = EmbedCallCounter()
    let engine = CountingEmbeddingEngine(counter: counter)
    var runtime = LocalEmbeddingRuntime(
      engines: [engine], defaultEngineID: engine.engineID, record: { _, _ in })
    runtime.probe = { _ in
      LocalEmbeddingProbe(
        appleSilicon: true, assetsAvailable: true, fixtureSucceeded: true, elapsed: .zero, dimension: 8)
    }
    await LocalEmbeddingIndexer.shared.setRuntimeForTesting(runtime)

    let backendId = "memory-reembed-\(UUID().uuidString)"
    try await MemoryStorage.shared.syncServerMemories([
      Self.serverMemory(id: backendId, content: "unchanged synthetic memory", updatedAt: 1)
    ])
    await LocalEmbeddingIndexer.shared.awaitDetachedForTesting()
    XCTAssertEqual(counter.snapshot(), 1)

    try await MemoryStorage.shared.syncServerMemories([
      Self.serverMemory(id: backendId, content: "unchanged synthetic memory", updatedAt: 2)
    ])
    await LocalEmbeddingIndexer.shared.awaitDetachedForTesting()
    XCTAssertEqual(counter.snapshot(), 1, "already-indexed unchanged memory must not re-embed")

    try await MemoryStorage.shared.syncServerMemories([
      Self.serverMemory(id: backendId, content: "changed synthetic memory", updatedAt: 3)
    ])
    await LocalEmbeddingIndexer.shared.awaitDetachedForTesting()
    XCTAssertEqual(counter.snapshot(), 2)
  }

  private static func serverMemory(id: String, content: String, updatedAt: TimeInterval) -> ServerMemory {
    ServerMemory(
      id: id,
      content: content,
      category: .system,
      tier: .shortTerm,
      tierIsExplicit: true,
      createdAt: Date(timeIntervalSince1970: 1),
      updatedAt: Date(timeIntervalSince1970: updatedAt),
      conversationId: nil,
      reviewed: false,
      userReview: nil,
      visibility: "private",
      manuallyAdded: false,
      scoring: nil,
      source: "desktop",
      confidence: nil,
      sourceApp: nil,
      contextSummary: nil,
      isRead: false,
      isDismissed: false,
      tags: [],
      reasoning: nil,
      currentActivity: nil,
      inputDeviceName: nil,
      windowTitle: nil,
      headline: nil)
  }

  func testMissingSessionOriginSkipsIndexing() async throws {
    let reasons = CapturePathReasonBox()
    let engine = HashEmbeddingEngine()
    var runtime = LocalEmbeddingRuntime(
      engines: [engine], defaultEngineID: engine.engineID,
      record: { _, reason in reasons.append(reason) })
    runtime.probe = { _ in
      LocalEmbeddingProbe(
        appleSilicon: true, assetsAvailable: true, fixtureSucceeded: true, elapsed: .zero, dimension: 8)
    }
    await LocalEmbeddingIndexer.shared.setRuntimeForTesting(runtime)
    await LocalEmbeddingIndexer.shared.indexFinalizedSession(sessionId: 9_999)
    XCTAssertEqual(reasons.snapshot(), ["missing_session_origin"])
  }
}

private final class CapturePathReasonBox: @unchecked Sendable {
  private var reasons: [String] = []
  func append(_ reason: String) { reasons.append(reason) }
  func snapshot() -> [String] { reasons }
}
