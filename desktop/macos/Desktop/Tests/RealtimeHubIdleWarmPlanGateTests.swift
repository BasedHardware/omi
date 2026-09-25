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

  /// Pins the presence policy numbers and that an entitled poll tick still
  /// admits a warm. Idle-close scheduling is `testEntitledIdleCloseSchedulesRewarm`.
  func testEntitledPresencePollTickStillAdmitsWarm() {
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

  func testLaunchPrepareAutomaticWarmSkipsWhenPlanGated() {
    let controller = gatedController(decision: .planGated)
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }

    PushToTalkManager.warmHubOnLaunchIfNeeded(localProfileEnabled: false, hub: controller)

    XCTAssertEqual(admitted, [])
  }

  func testLaunchPrepareAutomaticWarmAdmitsWhenEntitled() {
    let controller = gatedController(decision: .allowManagedProactivity)
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }

    PushToTalkManager.warmHubOnLaunchIfNeeded(localProfileEnabled: false, hub: controller)

    XCTAssertEqual(admitted, [false])
  }

  /// Re-entrant `PushToTalkManager.setup` while HID still looks idle: launch
  /// is not `userInitiated`, but it must still clear the away deferral.
  func testReentrantLaunchClearsAwayDeferralForEntitledUser() {
    let controller = gatedController(decision: .allowManagedProactivity)
    controller.warmDeferredForUserAway = true
    controller.presenceIdleProvider = { RealtimeHubWarmPresencePolicy.idleThreshold * 2 }
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }

    PushToTalkManager.warmHubOnLaunchIfNeeded(localProfileEnabled: false, hub: controller)

    XCTAssertEqual(admitted, [false])
    XCTAssertFalse(controller.warmDeferredForUserAway)
  }

  func testReentrantLaunchStillGatesPlanGatedUser() {
    let controller = gatedController(decision: .planGated)
    controller.warmDeferredForUserAway = true
    controller.presenceIdleProvider = { RealtimeHubWarmPresencePolicy.idleThreshold * 2 }
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }

    PushToTalkManager.warmHubOnLaunchIfNeeded(localProfileEnabled: false, hub: controller)

    XCTAssertEqual(admitted, [])
    XCTAssertFalse(controller.warmDeferredForUserAway)
  }

  func testSetupCallsiteUsesLaunchWarmHelperNotEnsureWarm() throws {
    let testFile = URL(fileURLWithPath: #filePath)
    // omi-test-quality: source-inspection -- static contract: PushToTalkManager.setup must call warmHubOnLaunchIfNeeded, not ensureWarm
    let source = try String(
      contentsOf:
        testFile
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("Sources/FloatingControlBar/PushToTalkManager.swift"),
      encoding: .utf8)
    guard
      let start = source.range(of: "func setup(barState: FloatingControlBarState)"),
      let end = source.range(of: "log(\"PushToTalkManager: setup complete")
    else {
      XCTFail("could not locate PushToTalkManager.setup")
      return
    }
    let setup = String(source[start.lowerBound..<end.lowerBound])
    XCTAssertTrue(
      setup.contains("warmHubOnLaunchIfNeeded"),
      "setup must go through the launch helper so an away deferral is cleared without userInitiated")
    XCTAssertFalse(
      setup.contains("ensureWarm("),
      "setup must not call ensureWarm directly; reverting that bypasses the plan gate or the deferral clear")
  }

  func testRealtimeBYOKAutomaticWarmIsNeverPlanGated() {
    let controller = gatedController(decision: .planGated)
    controller.realtimeBYOKKeyResolver = { _ in "AIza-test-gemini-voice-key" }
    controller.canUseRealtimeBYOK = { _, _ in true }
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }
    var minted = 0
    controller.managedMintProbe = { minted += 1 }

    controller.ensureWarm()
    PushToTalkManager.warmHubOnLaunchIfNeeded(localProfileEnabled: false, hub: controller)

    XCTAssertEqual(admitted, [false, false])
    if case .clientDirect = controller.resolvedRealtimeWarmCredential() {
    } else {
      XCTFail("usable voice BYOK must authorize client-direct")
    }
    XCTAssertEqual(minted, 0)
  }

  #if DEBUG  // testingWarmAfterDrain is a DEBUG-only seam; release builds have no warm bypass surface
    func testRealtimeBYOKIdleCloseIsNeverPlanGated() {
      let controller = gatedController(decision: .planGated)
      controller.realtimeBYOKKeyResolver = { _ in "AIza-test-gemini-voice-key" }
      controller.canUseRealtimeBYOK = { _, _ in true }
      controller.presenceIdleProvider = { 0 }
      controller.testingWarmAfterDrain = {}

      let result = controller.continueWarmAfterLifecycleClose(closeCategory: .expectedIdleTeardown)

      XCTAssertEqual(result, .started)
    }
  #endif

  func testUnusableRealtimeBYOKDoesNotMintWhenPlanGatedAndFailoverExhausted() {
    let key = "AIza-test-gemini-voice-key"
    let controller = gatedController(decision: .planGated)
    controller.realtimeBYOKKeyResolver = { _ in key }
    controller.canUseRealtimeBYOK = { _, _ in false }
    controller.fallbackProvider = .openai
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }
    var minted = 0
    controller.managedMintProbe = { minted += 1 }

    let fingerprint = APIKeyService.byokFingerprint(key)
    XCTAssertEqual(
      controller.resolvedRealtimeWarmCredential(),
      .unusableBYOK(key: key, fingerprint: fingerprint))
    XCTAssertTrue(controller.shouldSkipAutomaticManagedWarm())

    controller.ensureWarm()
    PushToTalkManager.warmHubOnLaunchIfNeeded(localProfileEnabled: false, hub: controller)

    XCTAssertEqual(admitted, [])
    XCTAssertEqual(minted, 0)
    XCTAssertNil(controller.session)

    controller.ensureWarm(userInitiated: true)
    XCTAssertEqual(admitted, [true])
  }

  #if DEBUG  // testingWarmAfterDrain is a DEBUG-only seam; release builds have no warm bypass surface
    func testUnusablePrimaryBYOKDoesNotSkipWhenAlternateIsHealthy() {
      let geminiKey = "AIza-test-gemini-voice-key"
      let openAIKey = "sk-test-openai-realtime-key"
      let controller = gatedController(decision: .planGated)
      let previousProvider = RealtimeOmniSettings.shared.selectedProvider
      RealtimeOmniSettings.shared.selectedProvider = .geminiFlashLive
      defer { RealtimeOmniSettings.shared.selectedProvider = previousProvider }

      controller.fallbackProvider = nil
      controller.realtimeBYOKKeyResolver = { provider in
        switch provider {
        case .gemini: return geminiKey
        case .openai: return openAIKey
        }
      }
      controller.canUseRealtimeBYOK = { byokProvider, _ in byokProvider == .openai }
      controller.prefetchedVoiceContextOwnerScope = controller.currentOwnerScope
      controller.prefetchedVoiceContextSessionID = "test-session"
      controller.prefetchedVoiceContextFreshnessIdentity = "fresh"
      controller.testingWarmAfterDrain = {}
      var admitted: [Bool] = []
      controller.warmAdmissionProbe = { admitted.append($0) }
      var minted = 0
      controller.managedMintProbe = { minted += 1 }

      XCTAssertEqual(controller.resolvedRealtimeWarmCredential(), .failoverToClientDirect)
      XCTAssertFalse(controller.shouldSkipAutomaticManagedWarm())

      controller.ensureWarm()

      XCTAssertEqual(admitted, [false])
      XCTAssertEqual(minted, 0)
      XCTAssertEqual(controller.fallbackProvider, .openai)
    }
  #endif

  #if DEBUG  // testingWarmAfterDrain is a DEBUG-only seam; release builds have no warm bypass surface
    func testPlanGatedIdleCloseDoesNotScheduleRewarm() {
      let controller = gatedController(decision: .planGated)
      var drainStarted = false
      controller.testingWarmAfterDrain = { drainStarted = true }

      let result = controller.continueWarmAfterLifecycleClose(closeCategory: .expectedIdleTeardown)

      XCTAssertEqual(result, .deferredPlanGated)
      XCTAssertFalse(drainStarted)
    }
  #endif

  #if DEBUG  // testingWarmAfterDrain is a DEBUG-only seam; release builds have no warm bypass surface
    func testEntitledIdleCloseSchedulesRewarm() async {
      let controller = gatedController(decision: .allowManagedProactivity)
      controller.presenceIdleProvider = { 0 }
      controller.lifecycleRewarmDelayNanoseconds = 0
      let rewarmed = expectation(description: "idle close rewarm")
      controller.testingWarmAfterDrain = { rewarmed.fulfill() }

      let result = controller.continueWarmAfterLifecycleClose(closeCategory: .expectedIdleTeardown)

      XCTAssertEqual(result, .started)
      await fulfillment(of: [rewarmed], timeout: 1)
    }
  #endif

  func testOwnerChangeDoesNotCarryPlanGateLatchOntoNextAccount() {
    let owner = OwnerBox(value: "user-a")
    let controller = gatedController(decision: .allowManagedProactivity)
    controller.managedPlanGateOwnerID = { owner.value }
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }

    controller.ensureWarm()
    XCTAssertEqual(admitted, [false])

    controller.noteManagedPlanGateFromWarmFailure(Self.planGatedMintError())
    controller.ensureWarm()
    XCTAssertEqual(admitted, [false])
    XCTAssertTrue(controller.managedPlanGateLatch.serverDenied)

    owner.value = "user-b"
    controller.ensureWarm()
    XCTAssertEqual(admitted, [false, false])
    XCTAssertFalse(controller.managedPlanGateLatch.serverDenied)
  }

  #if DEBUG  // testingWarmAfterDrain is a DEBUG-only seam; release builds have no warm bypass surface
    func testDiscardSessionAfterOwnerChangeClearsPlanGateLatch() {
      let controller = gatedController(decision: .allowManagedProactivity)
      controller.planGateRetryDelayNanoseconds = 3_600_000_000_000
      controller.testingWarmAfterDrain = {}

      controller.noteManagedPlanGateFromWarmFailure(Self.planGatedMintError())
      XCTAssertTrue(controller.managedPlanGateLatch.serverDenied)
      XCTAssertNotNil(controller.planGateRetryTask)

      controller.discardSessionAfterOwnerChange()
      XCTAssertFalse(controller.managedPlanGateLatch.serverDenied)
      XCTAssertNil(controller.planGateRetryTask)
    }
  #endif

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

  func testServerDenialSchedulesBoundedRetryAndRewarmAfterLifetime() {
    var now = Date(timeIntervalSince1970: 1_800_000_000)
    let controller = gatedController(decision: .allowManagedProactivity)
    controller.entitlementNow = { now }
    controller.planGateRetryDelayNanoseconds = 3_600_000_000_000
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }

    controller.ensureWarm(userInitiated: true)
    controller.noteManagedPlanGateFromWarmFailure(Self.planGatedMintError())
    XCTAssertNotNil(controller.planGateRetryTask)
    controller.ensureWarm()
    XCTAssertEqual(admitted, [true])

    now = now.addingTimeInterval(ManagedPlanGateLatch.defaultLifetime)
    controller.performScheduledManagedWarmRetry()
    XCTAssertEqual(admitted, [true, false])
    XCTAssertFalse(controller.managedPlanGateLatch.serverDenied)
    controller.resetManagedPlanGateForOwnerChange()
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

  func testEntitlementRefreshRewarmsWhenDecisionBecomesAllow() async {
    let decision = DecisionBox(value: SubscriptionEntitlementDecision.planGated)
    let controller = gatedController(decisionProvider: { decision.value })
    let rewarmed = expectation(description: "refresh rewarm")
    controller.warmAdmissionProbe = { userInitiated in
      XCTAssertFalse(userInitiated)
      rewarmed.fulfill()
    }
    controller.refreshEntitlement = {
      decision.value = .allowManagedProactivity
    }

    controller.ensureWarm()
    await fulfillment(of: [rewarmed], timeout: 1)
  }

  func testEntitlementRefreshCompletionIsDroppedAfterOwnerChange() async {
    let owner = OwnerBox(value: "user-a")
    let controller = gatedController(decisionProvider: {
      owner.value == "user-a" ? .planGated : .allowManagedProactivity
    })
    controller.managedPlanGateOwnerID = { owner.value }
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }
    var minted = 0
    controller.managedMintProbe = { minted += 1 }

    let refreshStarted = expectation(description: "refresh started")
    let refreshFinished = expectation(description: "refresh finished")
    let gate = RefreshGate()
    controller.refreshEntitlement = {
      await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
        Task { @MainActor in
          gate.continuation = cont
          refreshStarted.fulfill()
        }
      }
    }
    controller.planGateRefreshDidFinish = { refreshFinished.fulfill() }

    controller.ensureWarm()
    await fulfillment(of: [refreshStarted], timeout: 1)
    XCTAssertTrue(controller.entitlementRefreshInFlight)

    owner.value = "user-b"
    controller.resetManagedPlanGateForOwnerChange()
    XCTAssertFalse(controller.entitlementRefreshInFlight)

    gate.continuation?.resume()
    await fulfillment(of: [refreshFinished], timeout: 1)
    XCTAssertEqual(admitted, [])
    XCTAssertEqual(minted, 0)
  }

  func testEntitlementRefreshInFlightClearsWhenRefreshHangs() async {
    let controller = gatedController(decision: .planGated)
    controller.entitlementRefreshTimeoutNanoseconds = 0
    let finished = expectation(description: "refresh bounded")
    controller.planGateRefreshDidFinish = { finished.fulfill() }
    controller.refreshEntitlement = {
      while !Task.isCancelled {
        await Task.yield()
      }
    }

    controller.ensureWarm()
    await fulfillment(of: [finished], timeout: 1)
    XCTAssertFalse(controller.entitlementRefreshInFlight)
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

  func testProsePlanGatedIn402BodyDoesNotLatch() {
    let controller = gatedController(decision: .allowManagedProactivity)
    var admitted: [Bool] = []
    controller.warmAdmissionProbe = { admitted.append($0) }

    let prose = RealtimeTokenMintError(
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
      responseBody: Data(
        #"{"error":"trial_expired","detail":"This failure is not plan_gated; the chat trial expired."}"#
          .utf8))
    controller.noteManagedPlanGateFromWarmFailure(prose)
    controller.ensureWarm()

    XCTAssertEqual(admitted, [false])
    XCTAssertFalse(controller.managedPlanGateLatch.serverDenied)
    XCTAssertNil(controller.planGateRetryTask)
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
    controller.planGateRetryDelayNanoseconds = nil
    controller.managedPlanGateOwnerID = { "test-owner" }
    controller.lifecycleRewarmDelayNanoseconds = 0
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

private final class OwnerBox: @unchecked Sendable {
  var value: String?
  init(value: String?) {
    self.value = value
  }
}

private final class RefreshGate: @unchecked Sendable {
  var continuation: CheckedContinuation<Void, Never>?
}
