import XCTest

@testable import Omi_Computer

private final class TestCounter: @unchecked Sendable {
  var value = 0
}

private final class TestFlag: @unchecked Sendable {
  var value = false
}

final class SubscriptionEntitlementServiceTests: XCTestCase {
  override func tearDown() {
    ManagedProactivityDecisionSource.setOverride(nil)
    super.tearDown()
  }

  func testIdentifiedBasicWithoutBYOKIsPlanGated() {
    XCTAssertEqual(
      SubscriptionEntitlement.decision(plan: .basic, features: [], isByokActive: false),
      .planGated)
  }

  func testPaidPlansAreAllowed() {
    for plan in [
      SubscriptionPlanType.plus, .unlimited, .unlimitedV2, .architect, .pro, .operator,
    ] {
      XCTAssertEqual(
        SubscriptionEntitlement.decision(plan: plan, features: [], isByokActive: false),
        .allowManagedProactivity,
        "\(plan.rawValue) must stay allowed")
    }
  }

  func testUnknownPlanFailsOpen() {
    XCTAssertEqual(
      SubscriptionEntitlement.decision(plan: .unknown("neo"), features: [], isByokActive: false),
      .allowManagedProactivity)
    XCTAssertEqual(
      SubscriptionEntitlement.decision(plan: nil, features: [], isByokActive: false),
      .allowManagedProactivity)
  }

  func testBYOKAllowsIdentifiedBasic() {
    XCTAssertEqual(
      SubscriptionEntitlement.decision(plan: .basic, features: [], isByokActive: true),
      .allowManagedProactivity)
    XCTAssertEqual(
      SubscriptionEntitlement.decision(plan: .basic, features: ["byok"], isByokActive: false),
      .allowManagedProactivity)
  }

  func testUnknownPlanDoesNotUseHasPaidCapability() {
    XCTAssertFalse(SubscriptionPlanType.unknown("neo").hasPaidCapability)
    XCTAssertEqual(
      SubscriptionEntitlement.decision(plan: .unknown("neo"), features: [], isByokActive: false),
      .allowManagedProactivity)
  }

  func testServiceCachesSnapshotAndRecomputesBYOKLive() async throws {
    let fetches = TestCounter()
    let byok = TestFlag()
    let service = SubscriptionEntitlementService(
      ttl: 60,
      observeAuthChanges: false,
      now: { Date(timeIntervalSince1970: 1_800_000_000) },
      fetchSubscription: {
        fetches.value += 1
        return try Self.decodeSubscription(plan: "basic")
      },
      isByokActive: { byok.value })
    let first = await service.decisionForManagedProactivity()
    XCTAssertEqual(first, .planGated)
    XCTAssertEqual(fetches.value, 1)
    byok.value = true
    let second = await service.decisionForManagedProactivity()
    XCTAssertEqual(second, .allowManagedProactivity)
    XCTAssertEqual(fetches.value, 1)
  }

  func testCachedDecisionFailsOpenUntilSnapshotLands() async throws {
    let service = SubscriptionEntitlementService(
      observeAuthChanges: false,
      fetchSubscription: { try Self.decodeSubscription(plan: "basic") },
      isByokActive: { false })
    XCTAssertEqual(service.cachedDecisionForManagedProactivity(), .allowManagedProactivity)
    let fetched = await service.decisionForManagedProactivity()
    XCTAssertEqual(fetched, .planGated)
    XCTAssertEqual(service.cachedDecisionForManagedProactivity(), .planGated)
  }

  func testServiceFetchFailureFailsOpen() async {
    let service = SubscriptionEntitlementService(
      observeAuthChanges: false,
      fetchSubscription: { throw URLError(.notConnectedToInternet) },
      isByokActive: { false })
    let decision = await service.decisionForManagedProactivity()
    XCTAssertEqual(decision, .allowManagedProactivity)
  }

  func testAuthChangeInvalidatesCache() async throws {
    let fetches = TestCounter()
    let service = SubscriptionEntitlementService(
      observeAuthChanges: true,
      fetchSubscription: {
        fetches.value += 1
        return try Self.decodeSubscription(plan: "plus")
      },
      isByokActive: { false })
    let before = await service.decisionForManagedProactivity()
    XCTAssertEqual(before, .allowManagedProactivity)
    NotificationCenter.default.post(name: .userDidSignOut, object: nil)
    let after = await service.decisionForManagedProactivity()
    XCTAssertEqual(after, .allowManagedProactivity)
    XCTAssertEqual(fetches.value, 2)
  }

  func testRealtimeUsageBodyIncludesTurnIdWhenProvided() {
    let withTurn = APIClient.realtimeUsageReportBody(
      provider: "gemini",
      model: "gemini-live",
      inputText: 1,
      inputAudio: 2,
      inputCached: 0,
      outputText: 3,
      outputAudio: 4,
      contextPlanID: "plan",
      stableCacheIdentity: "stable",
      dynamicContextIdentity: "dynamic",
      contextCacheReplaced: false,
      turnId: "turn-1")
    XCTAssertEqual(withTurn["turn_id"] as? String, "turn-1")
    let withoutTurn = APIClient.realtimeUsageReportBody(
      provider: "gemini",
      model: "gemini-live",
      inputText: 1,
      inputAudio: 2,
      inputCached: 0,
      outputText: 3,
      outputAudio: 4,
      contextPlanID: "plan",
      stableCacheIdentity: "stable",
      dynamicContextIdentity: "dynamic",
      contextCacheReplaced: false,
      turnId: "")
    XCTAssertNil(withoutTurn["turn_id"])
  }

  func testManagedPlanGateHTTPReadsFastAPIDetail() {
    let detail = Data(#"{"detail":{"error":"plan_gated","plan_type":"basic"}}"#.utf8)
    XCTAssertTrue(ManagedPlanGateHTTP.isPlanGated(status: 402, data: detail))
    let root = Data(#"{"error":"plan_gated"}"#.utf8)
    XCTAssertTrue(ManagedPlanGateHTTP.isPlanGated(status: 402, data: root))
    let quota = Data(#"{"error":"trial_expired"}"#.utf8)
    XCTAssertFalse(ManagedPlanGateHTTP.isPlanGated(status: 402, data: quota))
    XCTAssertFalse(ManagedPlanGateHTTP.isPlanGated(status: 403, data: detail))
  }

  private static func decodeSubscription(plan: String, features: [String] = []) throws
    -> UserSubscriptionResponse
  {
    let featureJSON = String(data: try JSONSerialization.data(withJSONObject: features), encoding: .utf8) ?? "[]"
    let json = """
      {"subscription":{"plan":"\(plan)","status":"active","features":\(featureJSON),"cancel_at_period_end":false,"limits":{}}}
      """
    return try JSONDecoder().decode(UserSubscriptionResponse.self, from: Data(json.utf8))
  }
}
