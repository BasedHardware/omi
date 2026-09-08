import XCTest

@testable import Omi_Computer

final class ContextVisitCoordinatorTests: XCTestCase {
  func testStateMachineAdvancesAndTakesExactlyOnce() {
    var state = ContextVisitStateMachine()
    let fence = ContextVisitFence(
      visitID: 7, contextGeneration: 2, poolEpoch: 3, bucketID: "b",
      startedAt: Date(timeIntervalSince1970: 1))
    state.begin(fence)
    XCTAssertEqual(state.generation, 2)
    XCTAssertEqual(state.takeActive(), fence)
    XCTAssertNil(state.takeActive())
  }

  func testStateMachineResetClearsActiveFenceAndGeneration() {
    var state = ContextVisitStateMachine()
    let fence = ContextVisitFence(
      visitID: 9, contextGeneration: 4, poolEpoch: 1, bucketID: "bucket",
      startedAt: Date(timeIntervalSince1970: 2))
    state.begin(fence)
    state.reset()
    XCTAssertNil(state.activeFence)
    XCTAssertEqual(state.generation, 0)
  }

  func testOwnerOrPoolResetClearsStaleInMemoryFence() async {
    let coordinator = ContextVisitCoordinator(store: .shared)
    let stale = ContextVisitFence(
      visitID: 11, contextGeneration: 8, poolEpoch: 99, bucketID: "stale",
      startedAt: Date(timeIntervalSince1970: 3))
    await coordinator.beginForTesting(stale)
    let activeBeforeReset = await coordinator.activeFenceForTesting()
    XCTAssertEqual(activeBeforeReset, stale)

    await coordinator.resetForOwnerOrPoolChange()
    let activeAfterReset = await coordinator.activeFenceForTesting()
    XCTAssertNil(activeAfterReset)
  }

  func testSystemResumePolicyRearmsSameContextOnlyWhenEligible() {
    XCTAssertTrue(
      ContextVisitSystemResumePolicy.shouldRearmContextVisit(
        bucketsEnabled: true,
        wasMonitoringBeforeEvent: true,
        isMonitoring: true,
        appName: "Slack",
        isAppExcluded: false))
    XCTAssertFalse(
      ContextVisitSystemResumePolicy.shouldRearmContextVisit(
        bucketsEnabled: false,
        wasMonitoringBeforeEvent: true,
        isMonitoring: true,
        appName: "Slack",
        isAppExcluded: false))
    XCTAssertFalse(
      ContextVisitSystemResumePolicy.shouldRearmContextVisit(
        bucketsEnabled: true,
        wasMonitoringBeforeEvent: true,
        isMonitoring: true,
        appName: "1Password",
        isAppExcluded: true))
    XCTAssertFalse(
      ContextVisitSystemResumePolicy.shouldRearmContextVisit(
        bucketsEnabled: true,
        wasMonitoringBeforeEvent: false,
        isMonitoring: true,
        appName: "Slack",
        isAppExcluded: false))
    XCTAssertFalse(
      ContextVisitSystemResumePolicy.shouldRearmContextVisit(
        bucketsEnabled: true,
        wasMonitoringBeforeEvent: true,
        isMonitoring: true,
        appName: "Slack",
        isAppExcluded: false,
        displayAvailable: false),
      "wake while the login screen is still locked must not reopen context capture")
  }

  func testDelayedSleepInterruptCannotFinalizeVisitStartedAfterEvent() {
    let event = Date(timeIntervalSince1970: 100)
    XCTAssertTrue(
      ContextVisitSystemResumePolicy.shouldInterrupt(
        activeVisitStartedAt: event.addingTimeInterval(-1), eventTime: event))
    XCTAssertFalse(
      ContextVisitSystemResumePolicy.shouldInterrupt(
        activeVisitStartedAt: event.addingTimeInterval(1), eventTime: event))
  }
}
