import XCTest

@testable import Omi_Computer

/// Plan gate on automatic managed hub warming. Identified basic must not
/// mint an idle Gemini Live session; PTT (`userInitiated: true`) still tries.
@MainActor
final class RealtimeHubIdleWarmPlanGateTests: XCTestCase {
  func testPlanGatedDecisionMakesNoAutomaticWarmAttempt() {
    let controller = gatedController(decision: .planGated)
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }

    controller.ensureWarm()
    controller.ensureWarm()

    XCTAssertEqual(admitted, [])
    XCTAssertNil(controller.session)
  }

  func testPlanGatedDecisionStillAttemptsUserInitiatedWarm() {
    let controller = gatedController(decision: .planGated)
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }

    controller.ensureWarm(userInitiated: true)

    XCTAssertEqual(admitted, [true])
  }

  func testEntitledDecisionStillAdmitsAutomaticWarm() {
    let controller = gatedController(decision: .allowManagedProactivity)
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }

    controller.ensureWarm()

    XCTAssertEqual(admitted, [false])
  }

  func testEntitledPresenceRewarmCadenceUnchanged() {
    XCTAssertEqual(RealtimeHubWarmPresencePolicy.idleThreshold, 10 * 60)
    XCTAssertEqual(RealtimeHubWarmPresencePolicy.presencePollInterval, 10)
    XCTAssertTrue(
      RealtimeHubWarmPresencePolicy.shouldRewarmAfterIdleTeardown(secondsSinceLastUserInput: 0))
    XCTAssertTrue(
      RealtimeHubWarmPresencePolicy.shouldRewarmAfterIdleTeardown(
        secondsSinceLastUserInput: RealtimeHubWarmPresencePolicy.idleThreshold - 1))

    let controller = gatedController(decision: .allowManagedProactivity)
    controller.warmDeferredForUserAway = true
    controller.presenceIdleProvider = { 0 }
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }

    XCTAssertTrue(controller.presencePollTick(elapsedSincePreviousSample: 10))
    XCTAssertEqual(admitted, [false])
    XCTAssertFalse(controller.warmDeferredForUserAway)
  }

  func testServerPlanGatedDenialStopsSubsequentAutomaticWarms() {
    let controller = gatedController(decision: .allowManagedProactivity)
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }

    controller.ensureWarm(userInitiated: true)
    XCTAssertEqual(admitted, [true])

    controller.noteManagedPlanGateFromWarmFailure(Self.planGatedMintError())
    controller.ensureWarm()
    controller.ensureWarm()

    XCTAssertEqual(admitted, [true])
    XCTAssertTrue(controller.managedPlanGateLatch.serverDenied)
  }

  func testLatchClearsWhenDecisionChangesToAllow() {
    let decision = DecisionBox(value: SubscriptionEntitlementDecision.planGated)
    let controller = gatedController(decisionProvider: { decision.value })
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }

    controller.noteManagedPlanGateFromWarmFailure(GeminiClient.GeminiClientError.planGated)
    controller.ensureWarm()
    XCTAssertEqual(admitted, [])

    decision.value = .allowManagedProactivity
    controller.ensureWarm()
    XCTAssertEqual(admitted, [false])
    XCTAssertFalse(controller.managedPlanGateLatch.serverDenied)
  }

  func testLatchClearsAfterBoundedLifetime() {
    var now = Date(timeIntervalSince1970: 1_800_000_000)
    let controller = gatedController(decision: .allowManagedProactivity)
    controller.entitlementNow = { now }
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }

    controller.ensureWarm(userInitiated: true)
    controller.noteManagedPlanGateFromWarmFailure(Self.planGatedMintError())
    controller.ensureWarm()
    XCTAssertEqual(admitted, [true])

    now = now.addingTimeInterval(ManagedPlanGateLatch.defaultLifetime)
    controller.ensureWarm()
    XCTAssertEqual(admitted, [true, false])
    XCTAssertFalse(controller.managedPlanGateLatch.serverDenied)
  }

  func testPresenceReturnDoesNotMintWhenPlanGated() {
    let controller = gatedController(decision: .planGated)
    controller.warmDeferredForUserAway = true
    controller.presenceIdleProvider = { 0 }
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }

    XCTAssertTrue(controller.presencePollTick(elapsedSincePreviousSample: 10))
    XCTAssertEqual(admitted, [])
    XCTAssertFalse(controller.warmDeferredForUserAway)
  }

  func testNonPlanGatedMintFailureDoesNotLatch() {
    let controller = gatedController(decision: .allowManagedProactivity)
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }

    let quota = RealtimeTokenMintError(
      statusCode: 402,
      healthError: .paywalled(message: "trial_expired"),
      payload: APIErrorPayload(
        error: "trial_expired",
        code: nil,
        message: nil,
        detail: nil,
        provider: nil,
        reason: nil,
        backendRoute: nil,
        upstreamStatusCode: nil,
        retryable: nil,
        retryAfterSeconds: nil),
      responseBody: Data(#"{"error":"trial_expired"}"#.utf8))
    controller.noteManagedPlanGateFromWarmFailure(quota)
    controller.ensureWarm()

    XCTAssertEqual(admitted, [false])
    XCTAssertFalse(controller.managedPlanGateLatch.serverDenied)
  }

  private func gatedController(
    decision: SubscriptionEntitlementDecision
  ) -> RealtimeHubController {
    gatedController(decisionProvider: { decision })
  }

  private func gatedController(
    decisionProvider: @escaping () -> SubscriptionEntitlementDecision
  ) -> RealtimeHubController {
    let controller = RealtimeHubController()
    controller.entitlementDecision = decisionProvider
    controller.refreshEntitlement = nil
    return controller
  }

  private static func planGatedMintError() -> RealtimeTokenMintError {
    let body = Data(#"{"detail":{"error":"plan_gated","plan_type":"basic"}}"#.utf8)
    return RealtimeTokenMintError(
      statusCode: 402,
      healthError: .paywalled(message: "plan_gated"),
      payload: nil,
      responseBody: body)
  }
}

private final class DecisionBox: @unchecked Sendable {
  var value: SubscriptionEntitlementDecision
  init(value: SubscriptionEntitlementDecision) {
    self.value = value
  }
}
