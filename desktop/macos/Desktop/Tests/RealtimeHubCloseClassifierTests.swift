import XCTest

@testable import Omi_Computer

final class RealtimeHubCloseClassifierTests: XCTestCase {
  func testClassifiesLongLivedWebSocket1008AsExpectedIdleTeardownOnlyWhenIdle() {
    let category = RealtimeHubCloseClassifier.category(
      message: "WebSocket closed (1008)",
      aliveFor: RealtimeHubCloseClassifier.idleTeardownThreshold + 1)

    XCTAssertEqual(category, .expectedIdleTeardown)
    XCTAssertFalse(RealtimeHubCloseClassifier.shouldReportToSentry(category))
  }

  func testClassifiesLongLivedActiveWebSocket1008AsProviderPolicyClose() {
    let category = RealtimeHubCloseClassifier.category(
      message: "WebSocket closed (1008)",
      aliveFor: RealtimeHubCloseClassifier.idleTeardownThreshold + 1,
      hasActiveTurn: true)

    XCTAssertEqual(category, .providerPolicyCloseFast)
    XCTAssertTrue(RealtimeHubCloseClassifier.shouldReportToSentry(category))
  }

  func testClassifiesOpenAIMaximumDurationAsExpectedSessionRotation() {
    let category = RealtimeHubCloseClassifier.category(
      message: "Your session hit the maximum duration of 60 minutes.",
      aliveFor: 60 * 60,
      provider: .openai)

    XCTAssertEqual(category, .expectedSessionRotation)
    XCTAssertEqual(
      RealtimeHubCloseClassifier.sessionRotationPlan(
        for: category,
        hasActiveTurn: false),
      .rewarmIdleTransport)
    XCTAssertFalse(RealtimeHubCloseClassifier.shouldReportToSentry(category))
  }

  func testOpenAISessionRotationDuringTurnRequiresReducerOwnedTerminalization() {
    let category = RealtimeHubCloseClassifier.category(
      message: "Your session hit the maximum duration of 60 minutes.",
      aliveFor: 60 * 60,
      hasActiveTurn: true,
      provider: .openai)

    XCTAssertEqual(
      RealtimeHubCloseClassifier.sessionRotationPlan(
        for: category,
        hasActiveTurn: true),
      .terminateActiveTurnAndRewarm)
  }

  func testDoesNotClassifyMaximumDurationForAnotherProvider() {
    let category = RealtimeHubCloseClassifier.category(
      message: "Your session hit the maximum duration of 60 minutes.",
      aliveFor: 60 * 60,
      provider: .gemini)

    XCTAssertNil(category)
  }

  func testClassifiesAgedIdleSocketNotConnectedAsExpectedTeardown() {
    let category = RealtimeHubCloseClassifier.category(
      message: "The operation couldn’t be completed. Socket is not connected",
      aliveFor: 60 * 60,
      provider: .openai)

    XCTAssertEqual(category, .expectedIdleTeardown)
    XCTAssertFalse(RealtimeHubCloseClassifier.shouldReportToSentry(category))
  }

  func testClassifiesActiveTurnSocketNotConnectedAsReportableError() {
    let category = RealtimeHubCloseClassifier.category(
      message: "The operation couldn’t be completed. Socket is not connected",
      aliveFor: 60 * 60,
      hasActiveTurn: true,
      provider: .openai)

    XCTAssertNil(category)
    XCTAssertTrue(RealtimeHubCloseClassifier.shouldReportToSentry(category))
  }

  func testClassifiesFastSocketNotConnectedAsReportableError() {
    let category = RealtimeHubCloseClassifier.category(
      message: "The operation couldn’t be completed. Socket is not connected",
      aliveFor: 3,
      provider: .openai)

    XCTAssertNil(category)
    XCTAssertTrue(RealtimeHubCloseClassifier.shouldReportToSentry(category))
  }

  func testClassifiesFastWebSocket1008AsProviderPolicyClose() {
    let category = RealtimeHubCloseClassifier.category(
      message: "WebSocket closed (1008) policy violation",
      aliveFor: 3)

    XCTAssertEqual(category, .providerPolicyCloseFast)
    XCTAssertTrue(RealtimeHubCloseClassifier.shouldReportToSentry(category))
  }

  func testDoesNotClassifyOtherRealtimeErrors() {
    let category = RealtimeHubCloseClassifier.category(
      message: "WebSocket failed: network connection lost",
      aliveFor: 120)

    XCTAssertNil(category)
    XCTAssertTrue(RealtimeHubCloseClassifier.shouldReportToSentry(category))
  }

  func testCredentialClassifierDetectsProviderAuthFailures() {
    let failure = CredentialHealthManager.classifyProviderClose(
      message: "Request had invalid authentication credentials",
      provider: .openai)

    XCTAssertEqual(failure, .providerAuthFailed(provider: .openai, mode: .byok))
  }

  func testCredentialClassifierDetectsQuotaFailures() {
    let failure = CredentialHealthManager.classifyProviderClose(
      message: "insufficient_quota.insufficient_quota",
      provider: .gemini)

    XCTAssertEqual(failure, .providerQuotaExceeded(provider: .gemini))
  }

  func testCloseClassifierUsesCurrentProviderForCredentialFailures() {
    let category = RealtimeHubCloseClassifier.category(
      message: "WebSocket closed (1008) insufficient_quota.insufficient_quota",
      aliveFor: 3,
      provider: .gemini)

    XCTAssertEqual(category, .providerQuotaExceeded)
  }
}
