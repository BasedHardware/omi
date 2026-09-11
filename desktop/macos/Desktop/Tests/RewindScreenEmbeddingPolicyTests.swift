import Foundation
import XCTest
import os

@testable import Omi_Computer

private final class ScreenPolicyBox: Sendable {
  private let state: OSAllocatedUnfairLock<ScreenEmbeddingPolicy>
  init(_ policy: ScreenEmbeddingPolicy) { state = OSAllocatedUnfairLock(initialState: policy) }
  func get() -> ScreenEmbeddingPolicy { state.withLock { $0 } }
  func set(_ policy: ScreenEmbeddingPolicy) { state.withLock { $0 = policy } }
}

private final class ScreenRouteSpy: Sendable {
  private let state = OSAllocatedUnfairLock(initialState: [ScreenEmbeddingPolicy]())
  func record(_ policy: ScreenEmbeddingPolicy) { state.withLock { $0.append(policy) } }
  func snapshot() -> [ScreenEmbeddingPolicy] { state.withLock { $0 } }
}

private actor ScreenBatchSpy {
  private(set) var calls = 0
  func embed(_ texts: [String]) -> [[Float]] {
    calls += 1
    return texts.map { _ in [Float](repeating: 1, count: EmbeddingService.embeddingDimension) }
  }
}

@MainActor
final class RewindScreenEmbeddingPolicyTests: XCTestCase {
  private var userDir: URL?

  override func setUp() async throws {
    userDir = try await RewindStorageTestIsolation.setUp(userIdPrefix: "screen-policy").userDir
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: userDir)
  }

  func testFreeCaptureWritesLocalVectorWithoutGemini() async throws {
    try await assertCapture(
      plan: .basic, status: .active, available: true, hardKill: false, cloudCalls: 0, localRows: 1)
  }

  func testUnknownCaptureWritesLocalVectorWithoutGemini() async throws {
    try await assertCapture(plan: nil, status: nil, available: true, hardKill: false, cloudCalls: 0, localRows: 1)
  }

  func testFreeCaptureWithoutEngineStaysFTSOnly() async throws {
    try await assertCapture(
      plan: .basic, status: .active, available: false, hardKill: false, cloudCalls: 0, localRows: 0)
  }

  func testPaidCaptureRetainsGeminiAndAlsoWritesLocalVector() async throws {
    try await assertCapture(
      plan: .operator, status: .active, available: true, hardKill: false, cloudCalls: 1, localRows: 1)
  }

  func testPaidCaptureWithoutEngineRetainsGemini() async throws {
    try await assertCapture(
      plan: .plus, status: .active, available: false, hardKill: false, cloudCalls: 1, localRows: 0)
  }

  func testHardKillRestoresGeminiForUnknownPlan() async throws {
    try await assertCapture(plan: nil, status: nil, available: true, hardKill: true, cloudCalls: 1, localRows: 0)
  }

  private func assertCapture(
    plan: SubscriptionPlanType?, status: SubscriptionStatusType?, available: Bool, hardKill: Bool,
    cloudCalls: Int, localRows: Int
  ) async throws {
    let engine = HashEmbeddingEngine()
    let flags = LocalEmbeddingKillSwitches(isDisabled: hardKill, forcedEngineRaw: nil)
    let decision = ScreenEmbeddingPolicy(
      plan: plan, status: status, localRoute: available ? .engine(engine) : .none, killSwitches: flags)
    var runtime = LocalEmbeddingRuntime(
      engines: available ? [engine] : [], killSwitches: flags,
      defaultEngineID: engine.engineID, record: { _, _ in })
    runtime.probe = { _ in
      LocalEmbeddingProbe(
        appleSilicon: true, assetsAvailable: true, fixtureSucceeded: true, elapsed: .zero, dimension: 8)
    }
    let spy = ScreenBatchSpy()
    let routes = ScreenRouteSpy()
    let cloud = makeCloud(spy: spy, policy: { decision })
    let owner = try XCTUnwrap(RewindCaptureOwnerSnapshot.capture())
    let timestamp = Date(timeIntervalSince1970: 1_200)
    let text = "synthetic screen policy fixture with enough OCR text"
    let screenshot = try await RewindDatabase.shared.insertScreenshot(
      Screenshot(
        timestamp: timestamp, appName: "SyntheticApp", windowTitle: nil, imagePath: "",
        ocrText: text, isIndexed: true))
    let id = try XCTUnwrap(screenshot.id)

    await RewindIndexer.indexScreenshotEmbeddings(
      id: id, timestamp: timestamp, ocrText: text, appName: "SyntheticApp", windowTitle: nil,
      ownerSnapshot: owner, runtime: runtime, policy: { _, _ in decision }, cloud: cloud,
      record: { routes.record($0) })
    let queued = await cloud.pendingCount
    XCTAssertEqual(queued, cloudCalls, "free frames must not enter the Gemini queue")
    await cloud.flushPendingEmbeddings()
    let calls = await spy.calls
    XCTAssertEqual(calls, cloudCalls, "assert the actual batch embedder boundary")
    XCTAssertEqual(routes.snapshot(), [decision], "one decision counter per frame")
    let store = try await RewindDatabase.shared.localEmbeddingStore(owner: owner)
    let rows = try store.readBatch(
      modelID: engine.modelID, dimension: engine.dimension, startDate: nil, endDate: nil, appFilter: nil)
    XCTAssertEqual(rows.count, localRows)
    let keywords = try store.keywordCandidates(
      query: "synthetic", startDate: nil, endDate: nil, appFilter: nil, sourceKinds: [.screenshot])
    XCTAssertEqual(keywords.map(\.sourceId), [id], "OCR and FTS survive every vector route")
    await cloud.reset()
  }

  func testDowngradeAfterQueueingBlocksActualBatchDispatch() async throws {
    let paid = ScreenEmbeddingPolicy(plan: .operator, status: .active, localRoute: .none, killSwitches: .enabled)
    let free = ScreenEmbeddingPolicy(plan: .basic, status: .active, localRoute: .none, killSwitches: .enabled)
    let box = ScreenPolicyBox(paid)
    let spy = ScreenBatchSpy()
    let cloud = makeCloud(spy: spy, policy: { box.get() })
    await cloud.embedScreenshot(
      id: 1, ocrText: "synthetic queued frame before plan downgrade", appName: "SyntheticApp", windowTitle: nil)
    let queued = await cloud.pendingCount
    XCTAssertEqual(queued, 1)
    box.set(free)
    await cloud.flushPendingEmbeddings()
    let calls = await spy.calls
    let remaining = await cloud.pendingCount
    XCTAssertEqual(calls, 0)
    XCTAssertEqual(remaining, 0)
    await cloud.reset()
  }

  func testFreeAndUnknownBackfillNeverDispatchOrMarkCompleted() async throws {
    try await seedBackfillRow()
    for plan in [SubscriptionPlanType.basic, nil, .unknown("future")] {
      let decision = ScreenEmbeddingPolicy(plan: plan, status: nil, localRoute: .none, killSwitches: .enabled)
      let spy = ScreenBatchSpy()
      let routes = ScreenRouteSpy()
      let cloud = makeCloud(spy: spy, policy: { decision }, record: { routes.record($0) })
      await cloud.backfillIfNeeded()
      let calls = await spy.calls
      let backfill = try await RewindDatabase.shared.getScreenshotEmbeddingBackfillStatus()
      XCTAssertEqual(calls, 0)
      XCTAssertFalse(backfill.completed, "skip must leave Gemini backfill available for a later upgrade")
      XCTAssertEqual(routes.snapshot(), [decision])
    }
  }

  func testPaidBackfillRetainsGemini() async throws {
    try await assertBackfillDispatch(plan: .operator, hardKill: false)
  }

  func testHardKillRestoresGeminiBackfillForUnknownPlan() async throws {
    try await assertBackfillDispatch(plan: nil, hardKill: true)
  }

  private func assertBackfillDispatch(plan: SubscriptionPlanType?, hardKill: Bool) async throws {
    try await seedBackfillRow()
    let decision = ScreenEmbeddingPolicy(
      plan: plan, status: .active, localRoute: .none,
      killSwitches: LocalEmbeddingKillSwitches(isDisabled: hardKill, forcedEngineRaw: nil))
    let spy = ScreenBatchSpy()
    let cloud = makeCloud(spy: spy, policy: { decision })
    await cloud.backfillIfNeeded()
    let calls = await spy.calls
    let backfill = try await RewindDatabase.shared.getScreenshotEmbeddingBackfillStatus()
    XCTAssertEqual(calls, 1)
    XCTAssertTrue(backfill.completed)
    let missing = try await RewindDatabase.shared.getScreenshotsMissingEmbeddings(limit: 10)
    XCTAssertTrue(missing.isEmpty, "backfill persists the Gemini vector")
  }

  func testBackfillRechecksEntitlementAfterAwait() async throws {
    try await seedBackfillRow()
    let paid = ScreenEmbeddingPolicy(plan: .operator, status: .active, localRoute: .none, killSwitches: .enabled)
    let free = ScreenEmbeddingPolicy(plan: .basic, status: .active, localRoute: .none, killSwitches: .enabled)
    let box = ScreenPolicyBox(paid)
    let spy = ScreenBatchSpy()
    let cloud = OCREmbeddingService(
      batchEmbedderForTesting: { texts, _ in await spy.embed(texts) },
      embeddingWriterForTesting: { _, _ in },
      losslessSyncEnabledForTesting: {
        box.set(free)
        return false
      },
      screenPolicyForTesting: { box.get() })
    await cloud.backfillIfNeeded()
    let calls = await spy.calls
    let backfill = try await RewindDatabase.shared.getScreenshotEmbeddingBackfillStatus()
    XCTAssertEqual(calls, 0)
    XCTAssertFalse(backfill.completed)
  }

  private func seedBackfillRow() async throws {
    _ = try await RewindDatabase.shared.insertScreenshot(
      Screenshot(
        timestamp: Date(timeIntervalSince1970: 1_200), appName: "SyntheticApp", windowTitle: nil,
        imagePath: "", ocrText: "synthetic old frame with enough OCR text for backfill", isIndexed: true))
  }

  private func makeCloud(
    spy: ScreenBatchSpy, policy: @escaping @Sendable () -> ScreenEmbeddingPolicy,
    record: @escaping @Sendable (ScreenEmbeddingPolicy) -> Void = { _ in }
  ) -> OCREmbeddingService {
    OCREmbeddingService(
      batchEmbedderForTesting: { texts, _ in await spy.embed(texts) },
      embeddingWriterForTesting: { _, _ in },
      flushSleeperForTesting: { _ in throw CancellationError() },
      screenPolicyForTesting: policy, recordRouteForTesting: record)
  }
}
