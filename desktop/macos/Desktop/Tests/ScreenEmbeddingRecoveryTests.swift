import Foundation
import XCTest

@testable import Omi_Computer

private final class EmbeddingRecoveryClock: @unchecked Sendable {
  private let lock = NSLock()
  private var value = Date(timeIntervalSince1970: 20_000)
  func now() -> Date { lock.withLock { value } }
  func advance(_ seconds: Double) { lock.withLock { value.addTimeInterval(seconds) } }
}

private actor EmbeddingRecoveryBatchSpy {
  private(set) var batches: [Int] = []
  func embed(_ texts: [String]) -> [[Float]] {
    batches.append(texts.count)
    return texts.map { _ in [Float](repeating: 1, count: EmbeddingService.embeddingDimension) }
  }
}

private actor EmbeddingRecoveryGate {
  private var open = false
  private var continuation: CheckedContinuation<Void, Never>?
  func wait() async {
    if open { return }
    await withCheckedContinuation { continuation = $0 }
  }
  func release() {
    open = true
    continuation?.resume()
    continuation = nil
  }
}

@MainActor
final class ScreenEmbeddingRecoveryTests: XCTestCase {
  private var userDir: URL?
  override func setUp() async throws {
    userDir = try await RewindStorageTestIsolation.setUp(userIdPrefix: "embedding-recovery").userDir
  }
  override func tearDown() async throws { await RewindStorageTestIsolation.tearDown(userDir: userDir) }

  private func paid() throws -> UserSubscriptionResponse {
    try JSONDecoder().decode(
      UserSubscriptionResponse.self,
      from: Data(
        """
        {"subscription":{"plan":"operator","status":"active","features":[],"cancel_at_period_end":false,"limits":{}}}
        """.utf8))
  }

  private func seed(_ count: Int) async throws {
    for index in 0..<count {
      _ = try await RewindDatabase.shared.insertScreenshot(
        Screenshot(
          timestamp: Date(timeIntervalSince1970: 1200),
          appName: "Fixture", windowTitle: "Synthetic bucket \(index)", imagePath: "",
          ocrText: "synthetic OCR long enough for cloud projection", isIndexed: true))
    }
  }

  private func makeService(
    auth: EmbeddingTestAuthorization, clock: EmbeddingRecoveryClock,
    entitlement: ScreenCloudEntitlementService, spy: EmbeddingRecoveryBatchSpy,
    compacted: Bool = false, cap: Int? = nil,
    sleep: @escaping OCREmbeddingService.FlushSleeper = { _ in }
  ) -> OCREmbeddingService {
    OCREmbeddingService(
      ownerAuthorityForTesting: auth.source, backfillLimitForTesting: cap,
      batchEmbedderForTesting: { texts, _, snapshot in
        XCTAssertTrue(auth.source.isCurrent(snapshot))
        return await spy.embed(texts)
      }, embeddingWriterForTesting: { _, _ in }, missingEmbeddingIDsForTesting: { $0 },
      backfillSleeperForTesting: sleep,
      losslessSyncEnabledForTesting: { compacted }, nowForTesting: clock.now,
      screenPolicyForTesting: { ScreenEmbeddingPolicy.cached(entitlementService: entitlement) })
  }

  func testColdGrantAndFreshPaidAcceptRetryTheActualBackfillAPI() async throws {
    try await seed(1)
    let auth = EmbeddingTestAuthorization()
    let clock = EmbeddingRecoveryClock()
    let entitlement = ScreenCloudEntitlementService(
      authority: auth.source, observeAuthChanges: false, now: clock.now,
      fetch: { _ in throw CancellationError() })
    let spy = EmbeddingRecoveryBatchSpy()
    let service = makeService(auth: auth, clock: clock, entitlement: entitlement, spy: spy)
    let denied = await service.backfillIfNeeded()
    XCTAssertEqual(denied, .retry)
    let before = await spy.batches
    XCTAssertTrue(before.isEmpty)
    entitlement.accept(try paid(), authorization: auth.snapshot)
    clock.advance(61)
    let completed = await service.backfillIfNeeded()
    XCTAssertEqual(completed, .complete)
    let batches = await spy.batches
    XCTAssertEqual(batches, [1])
    let missing = try await RewindDatabase.shared.getScreenshotsMissingEmbeddings(limit: 10)
    XCTAssertTrue(missing.isEmpty)
  }

  func testExpiryBetweenBatchesLeavesDurableResumeAndRestoredGrantContinues() async throws {
    try await seed(101)
    let auth = EmbeddingTestAuthorization()
    let clock = EmbeddingRecoveryClock()
    let entitlement = ScreenCloudEntitlementService(
      authority: auth.source, observeAuthChanges: false, now: clock.now,
      fetch: { _ in throw CancellationError() })
    entitlement.accept(try paid(), authorization: auth.snapshot)
    let spy = EmbeddingRecoveryBatchSpy()
    let sleeps = EmbedCallCounter()
    let service = makeService(
      auth: auth, clock: clock, entitlement: entitlement, spy: spy,
      sleep: { _ in
        sleeps.add(1)
        if sleeps.snapshot() == 1 { clock.advance(301) }
      })
    let interrupted = await service.backfillIfNeeded()
    XCTAssertEqual(interrupted, .retry)
    let progress = try await RewindDatabase.shared.getScreenshotEmbeddingBackfillStatus()
    XCTAssertFalse(progress.completed)
    XCTAssertEqual(progress.processedCount, 100)
    let initial = await spy.batches
    XCTAssertEqual(initial, [100])
    entitlement.accept(try paid(), authorization: auth.snapshot)
    clock.advance(61)
    let resumed = await service.backfillIfNeeded()
    XCTAssertEqual(resumed, .complete)
    let all = await spy.batches
    XCTAssertEqual(all, [100, 1])
  }

  func testHistoricalCompletedMarkerRearmsNewMissingRowsOnLegacyAndLossless() async throws {
    let auth = EmbeddingTestAuthorization()
    let clock = EmbeddingRecoveryClock()
    let entitlement = ScreenCloudEntitlementService(
      authority: auth.source, observeAuthChanges: false, now: clock.now,
      fetch: { _ in throw CancellationError() })
    entitlement.accept(try paid(), authorization: auth.snapshot)
    for compacted in [false, true] {
      let spy = EmbeddingRecoveryBatchSpy()
      let service = makeService(auth: auth, clock: clock, entitlement: entitlement, spy: spy, compacted: compacted)
      let initial = await service.backfillIfNeeded()
      XCTAssertEqual(initial, .complete)
      try await seed(1)
      clock.advance(301)
      entitlement.accept(try paid(), authorization: auth.snapshot)
      let completed = await service.backfillIfNeeded()
      XCTAssertEqual(completed, .complete)
      let batches = await spy.batches
      XCTAssertEqual(batches, [1], "a completed historical marker must not suppress new missing vectors")
    }
  }

  func testConcurrentBackfillCallsCoalesceBeforeActualBatchDispatch() async throws {
    try await seed(1)
    let auth = EmbeddingTestAuthorization()
    let clock = EmbeddingRecoveryClock()
    let gate = EmbeddingRecoveryGate()
    let entered = expectation(description: "batch entered")
    let spy = EmbeddingRecoveryBatchSpy()
    let paidPolicy = ScreenEmbeddingPolicy(plan: .operator, status: .active, localRoute: .none, killSwitches: .enabled)
    let service = OCREmbeddingService(
      ownerAuthorityForTesting: auth.source,
      batchEmbedderForTesting: { texts, _, _ in
        entered.fulfill()
        await gate.wait()
        return await spy.embed(texts)
      }, embeddingWriterForTesting: { _, _ in }, missingEmbeddingIDsForTesting: { $0 }, nowForTesting: clock.now,
      screenPolicyForTesting: { paidPolicy })
    let first = Task { await service.backfillIfNeeded() }
    await fulfillment(of: [entered], timeout: 2)
    let second = await service.backfillIfNeeded()
    XCTAssertEqual(second, .running)
    await gate.release()
    let result = await first.value
    XCTAssertEqual(result, .complete)
    let batches = await spy.batches
    XCTAssertEqual(batches, [1])
  }

  func testBatteryDeferralRemainsRetryableAfterACReturns() async throws {
    try await seed(1)
    let auth = EmbeddingTestAuthorization()
    let clock = EmbeddingRecoveryClock()
    let battery = EmbedCallCounter()
    battery.add(1)
    let spy = EmbeddingRecoveryBatchSpy()
    let paidPolicy = ScreenEmbeddingPolicy(plan: .operator, status: .active, localRoute: .none, killSwitches: .enabled)
    let service = OCREmbeddingService(
      ownerAuthorityForTesting: auth.source,
      backfillOnBatteryForTesting: { battery.snapshot() == 1 },
      batchEmbedderForTesting: { texts, _, _ in await spy.embed(texts) }, embeddingWriterForTesting: { _, _ in },
      missingEmbeddingIDsForTesting: { $0 },
      nowForTesting: clock.now, screenPolicyForTesting: { paidPolicy })
    let deferred = await service.backfillIfNeeded()
    XCTAssertEqual(deferred, .retry)
    let before = await spy.batches
    XCTAssertTrue(before.isEmpty)
    battery.add(-1)
    clock.advance(61)
    let completed = await service.backfillIfNeeded()
    XCTAssertEqual(completed, .complete)
    let after = await spy.batches
    XCTAssertEqual(after, [1])
  }

  func testPerLaunchAttemptCapSurvivesRetriesAndReset() async throws {
    try await seed(3)
    let auth = EmbeddingTestAuthorization()
    let clock = EmbeddingRecoveryClock()
    let entitlement = ScreenCloudEntitlementService(
      authority: auth.source, observeAuthChanges: false, now: clock.now,
      fetch: { _ in throw CancellationError() })
    entitlement.accept(try paid(), authorization: auth.snapshot)
    let spy = EmbeddingRecoveryBatchSpy()
    let service = makeService(auth: auth, clock: clock, entitlement: entitlement, spy: spy, cap: 2)
    let capped = await service.backfillIfNeeded()
    XCTAssertEqual(capped, .capped)
    await service.reset()
    clock.advance(1000)
    entitlement.accept(try paid(), authorization: auth.snapshot)
    let again = await service.backfillIfNeeded()
    XCTAssertEqual(again, .capped)
    let batches = await spy.batches
    XCTAssertEqual(batches, [2])
    let missing = try await RewindDatabase.shared.getScreenshotsMissingEmbeddings(limit: 10)
    XCTAssertEqual(missing.count, 1)
  }
}
