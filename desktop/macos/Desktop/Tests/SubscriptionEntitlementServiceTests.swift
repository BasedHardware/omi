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

  func testManagedPlanGateHTTPTypedMintIgnoresProsePlanGated() {
    let body = Data(
      #"{"error":"trial_expired","detail":"This failure is not plan_gated; the chat trial expired."}"#
        .utf8)
    XCTAssertFalse(ManagedPlanGateHTTP.isPlanGatedTypedJSON(status: 402, data: body))
    XCTAssertFalse(
      ManagedPlanGateHTTP.isPlanGated(
        status: 402,
        payload: APIErrorPayload(
          error: "trial_expired",
          code: nil,
          message: nil,
          detail: "This failure is not plan_gated; the chat trial expired.",
          provider: nil,
          reason: nil,
          backendRoute: nil,
          upstreamStatusCode: nil,
          retryable: nil,
          retryAfterSeconds: nil)))
    let error = RealtimeTokenMintError(
      statusCode: 402,
      healthError: .paywalled(message: "trial_expired"),
      payload: APIErrorPayload(
        error: "trial_expired",
        code: nil,
        message: nil,
        detail: "This failure is not plan_gated; the chat trial expired.",
        provider: nil,
        reason: nil,
        backendRoute: nil,
        upstreamStatusCode: nil,
        retryable: nil,
        retryAfterSeconds: nil),
      responseBody: body)
    XCTAssertFalse(ManagedPlanGateHTTP.isPlanGatedMint(error))
    XCTAssertFalse(ManagedPlanGateHTTP.isPlanGatedWarmFailure(error))
    // Legacy Gemini/lane scanner still matches substring containment. The hub
    // mint path must not use it.
    XCTAssertTrue(ManagedPlanGateHTTP.isPlanGated(status: 402, data: body))
  }

  func testManagedPlanGateHTTPTypedCodeTrimsAndLowercases() {
    XCTAssertTrue(ManagedPlanGateHTTP.isTypedPlanGatedCode(" Plan_Gated "))
    XCTAssertFalse(ManagedPlanGateHTTP.isTypedPlanGatedCode("not plan_gated"))
    XCTAssertTrue(
      ManagedPlanGateHTTP.isPlanGatedTypedJSON(
        status: 402, data: Data(#"{"code":"PLAN_GATED"}"#.utf8)))
    XCTAssertTrue(
      ManagedPlanGateHTTP.isPlanGatedTypedJSON(
        status: 402, data: Data(#"{"detail":{"error":"plan_gated"}}"#.utf8)))
  }

  func testMintErrorDescriptionDoesNotSurfaceResponseBody() {
    let marker = "raw-mint-body-must-not-surface"
    let body = Data(#"{"detail":{"error":"plan_gated","secret":"\#(marker)"}}"#.utf8)
    let error = RealtimeTokenMintError(
      statusCode: 402,
      healthError: .paywalled(message: "plan_gated"),
      payload: nil,
      responseBody: body)
    let description = error.errorDescription ?? ""
    XCTAssertFalse(description.contains(marker))
    XCTAssertFalse(description.contains(String(data: body, encoding: .utf8) ?? marker))
  }

  func testManagedPlanGateHTTPRecognizesMintBodyWhenPayloadDecodeFails() {
    let body = Data(#"{"detail":{"error":"plan_gated","plan_type":"basic"}}"#.utf8)
    let error = RealtimeTokenMintError(
      statusCode: 402,
      healthError: .paywalled(message: "plan_gated"),
      payload: nil,
      responseBody: body)
    XCTAssertTrue(ManagedPlanGateHTTP.isPlanGatedMint(error))
    XCTAssertTrue(ManagedPlanGateHTTP.isPlanGatedWarmFailure(error))
    XCTAssertTrue(
      ManagedPlanGateHTTP.isPlanGatedWarmFailure(GeminiClient.GeminiClientError.planGated))
    XCTAssertFalse(
      ManagedPlanGateHTTP.isPlanGatedWarmFailure(
        CredentialHealthError.backendTransient(statusCode: 500, message: "boom")))
  }

  func testManagedPlanGateLatchSkipsWhenDecisionIsPlanGated() {
    var latch = ManagedPlanGateLatch()
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    XCTAssertTrue(
      latch.shouldSkipAutomaticManagedWork(decision: .planGated, now: now))
    XCTAssertFalse(
      latch.shouldSkipAutomaticManagedWork(decision: .allowManagedProactivity, now: now))
  }

  func testManagedPlanGateLatchClearsWhenDecisionBecomesAllow() {
    var latch = ManagedPlanGateLatch()
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    _ = latch.shouldSkipAutomaticManagedWork(decision: .planGated, now: now)
    latch.latchServerDenial(at: now)
    XCTAssertTrue(latch.shouldSkipAutomaticManagedWork(decision: .planGated, now: now))
    XCTAssertFalse(
      latch.shouldSkipAutomaticManagedWork(decision: .allowManagedProactivity, now: now))
    XCTAssertFalse(latch.serverDenied)
  }

  func testManagedPlanGateLatchExpiresAfterBoundedLifetime() {
    var latch = ManagedPlanGateLatch()
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    _ = latch.shouldSkipAutomaticManagedWork(decision: .allowManagedProactivity, now: now)
    latch.latchServerDenial(at: now)
    XCTAssertTrue(
      latch.shouldSkipAutomaticManagedWork(decision: .allowManagedProactivity, now: now))
    XCTAssertFalse(
      latch.shouldSkipAutomaticManagedWork(
        decision: .allowManagedProactivity,
        now: now.addingTimeInterval(ManagedPlanGateLatch.defaultLifetime)))
    XCTAssertFalse(latch.serverDenied)
  }

  func testManagedPlanGateLatchLifetimeDoesNotUseSleep() {
    XCTAssertEqual(ManagedPlanGateLatch.defaultLifetime, 10 * 60)
  }

  func testManagedPlanGateLatchResetsWhenOwnerChanges() {
    var latch = ManagedPlanGateLatch()
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    XCTAssertFalse(
      latch.shouldSkipAutomaticManagedWork(
        decision: .allowManagedProactivity, now: now, ownerID: "user-a"))
    latch.latchServerDenial(at: now, ownerID: "user-a")
    XCTAssertTrue(
      latch.shouldSkipAutomaticManagedWork(
        decision: .allowManagedProactivity, now: now, ownerID: "user-a"))
    XCTAssertFalse(
      latch.shouldSkipAutomaticManagedWork(
        decision: .allowManagedProactivity, now: now, ownerID: "user-b"))
    XCTAssertFalse(latch.serverDenied)
  }

  func testManagedPlanGateLatchKeepsDenialWhenFirstObservationIsAllow() {
    var latch = ManagedPlanGateLatch()
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    latch.latchServerDenial(at: now, ownerID: "user-a")
    XCTAssertTrue(
      latch.shouldSkipAutomaticManagedWork(
        decision: .allowManagedProactivity, now: now, ownerID: "user-a"))
    XCTAssertTrue(latch.serverDenied)
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
