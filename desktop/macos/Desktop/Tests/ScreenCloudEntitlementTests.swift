import Foundation
import XCTest

@testable import Omi_Computer

private final class ScreenEntitlementClock: @unchecked Sendable {
  private let lock = NSLock()
  private var value = Date(timeIntervalSince1970: 10_000)
  func now() -> Date { lock.withLock { value } }
  func advance(_ seconds: Double) { lock.withLock { value.addTimeInterval(seconds) } }
}

private actor ScreenSubscriptionFetch {
  private(set) var calls = 0
  private var continuation: CheckedContinuation<UserSubscriptionResponse, Error>?
  func run(started: @Sendable () -> Void) async throws -> UserSubscriptionResponse {
    calls += 1
    return try await withCheckedThrowingContinuation {
      continuation = $0
      started()
    }
  }
  func complete(_ response: UserSubscriptionResponse) {
    continuation?.resume(returning: response)
    continuation = nil
  }
}

final class ScreenCloudEntitlementTests: XCTestCase {
  private func response(_ plan: String) throws -> UserSubscriptionResponse {
    try JSONDecoder().decode(
      UserSubscriptionResponse.self,
      from: Data(
        """
        {"subscription":{"plan":"\(plan)","status":"active","features":[],"cancel_at_period_end":false,"limits":{}}}
        """.utf8))
  }

  func testFreshDowngradeOverridesStalePaidUIHintAndStopsOCR() async throws {
    let auth = EmbeddingTestAuthorization()
    let service = ScreenCloudEntitlementService(
      authority: auth.source, observeAuthChanges: false,
      fetch: { _ in
        XCTFail("fresh snapshot should not fetch")
        throw CancellationError()
      })
    let defaults = try makeIsolatedDefaults()
    defaults.set("operator", forKey: .floatingBarCachedPlan)
    service.accept(try response("operator"), authorization: auth.snapshot)
    XCTAssertTrue(ScreenEmbeddingPolicy.cached(defaults: defaults, entitlementService: service).shouldEmbedWithGemini)
    for plan in ["basic", "plus"] {
      service.accept(try response(plan), authorization: auth.snapshot)
      XCTAssertFalse(service.allowsCloud(auth.snapshot))
      let ocr = OCREmbeddingService(
        ownerAuthorityForTesting: auth.source,
        batchEmbedderForTesting: { _, _, _ in
          XCTFail("fresh downgrade spent Gemini")
          return []
        },
        embeddingWriterForTesting: { _, _ in XCTFail("downgrade wrote cloud vectors") },
        missingEmbeddingIDsForTesting: { $0 },
        screenPolicyForTesting: { ScreenEmbeddingPolicy.cached(entitlementService: service) })
      await ocr.embedScreenshot(
        id: 1, ocrText: "synthetic OCR exceeding minimum length", appName: "Fixture", windowTitle: nil)
      await ocr.flushPendingEmbeddings()
      let count = await ocr.pendingCount
      XCTAssertEqual(count, 0)
      await ocr.reset()
    }
  }

  func testExpiryDeniesImmediatelyAndCoalescesRefreshWithoutConversationUpload() async throws {
    let auth = EmbeddingTestAuthorization()
    let clock = ScreenEntitlementClock()
    let fetch = ScreenSubscriptionFetch()
    let started = expectation(description: "background subscription fetch")
    let service = ScreenCloudEntitlementService(
      authority: auth.source, observeAuthChanges: false, now: clock.now,
      fetch: { snapshot in
        XCTAssertEqual(snapshot, auth.snapshot)
        return try await fetch.run(started: { started.fulfill() })
      })
    service.accept(try response("operator"), authorization: auth.snapshot)
    XCTAssertTrue(service.allowsCloud(auth.snapshot))
    clock.advance(301)
    for _ in 0..<1000 { XCTAssertFalse(service.allowsCloud(auth.snapshot)) }
    await fulfillment(of: [started], timeout: 2)
    // An authoritative downgrade arriving during a prior refresh invalidates its receipt.
    service.accept(try response("basic"), authorization: auth.snapshot)
    await fetch.complete(try response("operator"))
    for _ in 0..<20 { await Task.yield() }
    XCTAssertFalse(service.allowsCloud(auth.snapshot))
    let calls = await fetch.calls
    XCTAssertEqual(calls, 1)
    service.accept(try response("operator"), authorization: auth.snapshot)
    XCTAssertTrue(service.allowsCloud(auth.snapshot), "healthy paid lifecycle fetch restores eligibility immediately")
  }

  func testColdPaidStartupRefreshesOutsideCaptureWithoutConversationUpload() async throws {
    let auth = EmbeddingTestAuthorization()
    let paid = try response("operator")
    let started = expectation(description: "startup refresh")
    let service = ScreenCloudEntitlementService(
      authority: auth.source, observeAuthChanges: false,
      fetch: { _ in
        started.fulfill()
        return paid
      })
    XCTAssertNil(service.peek())
    await fulfillment(of: [started], timeout: 2)
    for _ in 0..<1000 {
      if service.allowsCloud(auth.snapshot) { return }
      await Task.yield()
    }
    XCTFail("healthy paid subscription did not become eligible")
  }

  func testOwnerSwitchAndSameOwnerReauthenticationRevokeFreshPaidAuthority() throws {
    for next in ["synthetic-a", "synthetic-b"] {
      let auth = EmbeddingTestAuthorization(ownerID: "synthetic-a")
      let original = auth.snapshot
      let service = ScreenCloudEntitlementService(
        authority: auth.source, observeAuthChanges: false,
        fetch: { _ in throw CancellationError() })
      service.accept(try response("operator"), authorization: original)
      XCTAssertTrue(service.allowsCloud(original))
      auth.authority.beginTransition()
      XCTAssertNil(service.peek())
      XCTAssertFalse(service.allowsCloud(original))
      auth.authority.endTransition(ownerID: next)
      service.accept(try response("operator"), authorization: original)
      XCTAssertFalse(service.allowsCloud(original))
      if next == "synthetic-a" { XCTAssertFalse(service.allowsCloud(auth.snapshot)) }
    }
  }

  func testMissingOwnerFailsClosedBeforeOCRDispatchOrBackfill() async throws {
    let service = OCREmbeddingService(
      ownerAuthorityForTesting: EmbeddingOwnerAuthority(capture: { nil }, isCurrent: { _ in false }),
      batchEmbedderForTesting: { _, _, _ in
        XCTFail("missing owner dispatched")
        return []
      },
      embeddingWriterForTesting: { _, _ in XCTFail("missing owner wrote") }, missingEmbeddingIDsForTesting: { $0 })
    await service.embedScreenshot(
      id: 1, ocrText: "synthetic OCR exceeding minimum length", appName: "Fixture", windowTitle: nil)
    await service.flushPendingEmbeddings()
    await service.backfillIfNeeded()
    do {
      _ = try await service.searchSimilar(query: "synthetic query")
      XCTFail("missing owner searched")
    } catch { XCTAssertTrue(error is LocalMutationAuthorizationError) }
    let count = await service.pendingCount
    XCTAssertEqual(count, 0)
  }

  func testQueuedOCRCannotRebindToReauthenticatedOwner() async {
    let auth = EmbeddingTestAuthorization()
    let service = OCREmbeddingService(
      ownerAuthorityForTesting: auth.source,
      batchEmbedderForTesting: { _, _, _ in
        XCTFail("old queued OCR dispatched after reauthentication")
        return []
      },
      embeddingWriterForTesting: { _, _ in XCTFail("old queued OCR wrote") }, missingEmbeddingIDsForTesting: { $0 })
    await service.embedScreenshot(
      id: 1, ocrText: "synthetic OCR exceeding minimum length", appName: "Fixture", windowTitle: nil)
    let count = await service.pendingCount
    XCTAssertEqual(count, 1)
    auth.authority.beginTransition()
    auth.authority.endTransition(ownerID: auth.ownerID)
    await service.flushPendingEmbeddings()
    let after = await service.pendingCount
    XCTAssertEqual(after, 0)
    await service.reset()
  }
}
