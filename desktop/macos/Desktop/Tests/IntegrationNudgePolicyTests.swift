import XCTest

@testable import Omi_Computer

/// The whole product risk of proactive integration nudges is nagging: an offer
/// that repeats is worse than one that never fires. Every budget the policy
/// enforces gets a test, including its exact boundary, because an off-by-one on
/// a cooldown is the difference between "offered once" and "offered every time
/// the user opens Finder".
final class IntegrationNudgePolicyTests: XCTestCase {
  private let now = Date(timeIntervalSince1970: 1_700_000_000)

  private func decide(
    isConnected: Bool = false,
    isFeatureEnabled: Bool = true,
    isSignedIn: Bool = true,
    isOnboardingComplete: Bool = true,
    connector: IntegrationNudgePolicy.ConnectorState = .init(),
    lastAnyNudgeAt: Date? = nil,
    nudgesInCurrentDay: Int = 0,
    at instant: Date? = nil
  ) -> IntegrationNudgePolicy.Decision {
    IntegrationNudgePolicy.decide(
      IntegrationNudgePolicy.Input(
        isConnected: isConnected,
        isFeatureEnabled: isFeatureEnabled,
        isSignedIn: isSignedIn,
        isOnboardingComplete: isOnboardingComplete,
        connector: connector,
        lastAnyNudgeAt: lastAnyNudgeAt,
        nudgesInCurrentDay: nudgesInCurrentDay,
        now: instant ?? now
      )
    )
  }

  func testDeliversForAFreshUnconnectedIntegration() {
    XCTAssertEqual(decide(), .deliver)
  }

  func testConnectedIntegrationNeverNudges() {
    XCTAssertEqual(decide(isConnected: true), .suppress(.alreadyConnected))
  }

  /// Connected wins over every other reason so the suppression funnel is not
  /// dominated by the steady state of a fully set-up user.
  func testConnectedOutranksEveryOtherSuppression() {
    XCTAssertEqual(
      decide(
        isConnected: true,
        isFeatureEnabled: false,
        isSignedIn: false,
        connector: .init(shownCount: 99, optedOut: true)
      ),
      .suppress(.alreadyConnected)
    )
  }

  func testFeatureToggleOffSuppresses() {
    XCTAssertEqual(decide(isFeatureEnabled: false), .suppress(.featureDisabled))
  }

  func testSignedOutSuppresses() {
    XCTAssertEqual(decide(isSignedIn: false), .suppress(.notSignedIn))
  }

  func testOnboardingInProgressSuppresses() {
    XCTAssertEqual(decide(isOnboardingComplete: false), .suppress(.onboardingIncomplete))
  }

  func testOptOutIsPermanent() {
    let farFuture = now.addingTimeInterval(10 * 365 * 24 * 60 * 60)
    XCTAssertEqual(
      decide(connector: .init(optedOut: true), at: farFuture),
      .suppress(.optedOut)
    )
  }

  func testSnoozeBlocksUntilItHasFullyElapsed() {
    let snoozedUntil = now.addingTimeInterval(IntegrationNudgePolicy.snoozeDuration)
    let state = IntegrationNudgePolicy.ConnectorState(snoozedUntil: snoozedUntil)

    XCTAssertEqual(
      decide(connector: state, at: snoozedUntil.addingTimeInterval(-1)),
      .suppress(.snoozed)
    )
    XCTAssertEqual(decide(connector: state, at: snoozedUntil), .deliver)
  }

  func testLifetimeCapStopsFurtherNudgesForThatIntegration() {
    let spent = IntegrationNudgePolicy.ConnectorState(
      shownCount: IntegrationNudgePolicy.connectorLifetimeCap,
      lastShownAt: now.addingTimeInterval(-10 * 365 * 24 * 60 * 60)
    )
    XCTAssertEqual(decide(connector: spent), .suppress(.connectorLifetimeCap))
  }

  func testConnectorCooldownBlocksUntilItHasFullyElapsed() {
    let lastShownAt = now.addingTimeInterval(-IntegrationNudgePolicy.connectorCooldown + 1)
    XCTAssertEqual(
      decide(connector: .init(shownCount: 1, lastShownAt: lastShownAt)),
      .suppress(.connectorCooldown)
    )

    let elapsed = now.addingTimeInterval(-IntegrationNudgePolicy.connectorCooldown)
    XCTAssertEqual(decide(connector: .init(shownCount: 1, lastShownAt: elapsed)), .deliver)
  }

  func testDailyCapStopsNudgesAcrossIntegrations() {
    XCTAssertEqual(
      decide(nudgesInCurrentDay: IntegrationNudgePolicy.dailyCap),
      .suppress(.dailyCap)
    )
    XCTAssertEqual(decide(nudgesInCurrentDay: IntegrationNudgePolicy.dailyCap - 1), .deliver)
  }

  /// Opening Notion right after Gmail must not produce a second card.
  func testGlobalCooldownBlocksUntilItHasFullyElapsed() {
    XCTAssertEqual(
      decide(lastAnyNudgeAt: now.addingTimeInterval(-IntegrationNudgePolicy.globalCooldown + 1)),
      .suppress(.globalCooldown)
    )
    XCTAssertEqual(
      decide(lastAnyNudgeAt: now.addingTimeInterval(-IntegrationNudgePolicy.globalCooldown)),
      .deliver
    )
  }

  /// Emitting a funnel event on every activation for an answer the user settled
  /// once is unbounded volume, and it inflates the denominator the event exists
  /// to provide.
  /// A user whose Gmail is already connected must still be offered ChatGPT when
  /// they switch tabs, so a settlement about one integration cannot end
  /// recognition for the whole browser session.
  func testPerIntegrationSuppressionsDoNotEndTheSession() {
    for reason in [
      IntegrationNudgePolicy.Suppression.alreadyConnected, .optedOut, .connectorLifetimeCap,
      .snoozed, .connectorCooldown,
    ] {
      XCTAssertTrue(IntegrationNudgePolicy.isPerIntegration(reason), "\(reason) is per-integration")
    }
    for reason in [
      IntegrationNudgePolicy.Suppression.featureDisabled, .notSignedIn, .onboardingIncomplete,
      .globalCooldown, .dailyCap, .barUnavailable,
    ] {
      XCTAssertFalse(IntegrationNudgePolicy.isPerIntegration(reason), "\(reason) is global")
    }
  }

  /// The connection check is a local config scan for export destinations, so
  /// every gate that does not need it must settle first — otherwise a user who
  /// pressed "Never" pays for that scan on every activation, forever.
  func testGatesThatDoNotNeedConnectionStateSettleWithoutIt() {
    let optedOut = IntegrationNudgePolicy.Input(isConnected: false, connector: .init(optedOut: true))
    XCTAssertEqual(
      IntegrationNudgePolicy.decideWithoutConnectionState(optedOut), .suppress(.optedOut))

    let spent = IntegrationNudgePolicy.Input(
      isConnected: false,
      connector: .init(shownCount: IntegrationNudgePolicy.connectorLifetimeCap)
    )
    XCTAssertEqual(
      IntegrationNudgePolicy.decideWithoutConnectionState(spent),
      .suppress(.connectorLifetimeCap))
  }

  /// Connectedness is the one thing it cannot answer, so an otherwise-eligible
  /// window must fall through rather than being wrongly settled.
  func testAnEligibleWindowIsNotSettledWithoutTheConnectionCheck() {
    XCTAssertNil(
      IntegrationNudgePolicy.decideWithoutConnectionState(
        IntegrationNudgePolicy.Input(isConnected: false)))
  }

  // MARK: - Transitions

  func testDeliveryAdvancesCountAndTimestamp() {
    let next = IntegrationNudgePolicy.stateAfterDelivery(.init(shownCount: 1), now: now)
    XCTAssertEqual(next.shownCount, 2)
    XCTAssertEqual(next.lastShownAt, now)
  }

  /// A snooze that has already expired must not survive the next delivery as a
  /// stale field that a later clock comparison could resurrect.
  func testDeliveryClearsALapsedSnooze() {
    let lapsed = IntegrationNudgePolicy.ConnectorState(snoozedUntil: now.addingTimeInterval(-1))
    XCTAssertNil(IntegrationNudgePolicy.stateAfterDelivery(lapsed, now: now).snoozedUntil)
  }

  func testDeliveryKeepsAnActiveSnooze() {
    let active = now.addingTimeInterval(60)
    let state = IntegrationNudgePolicy.ConnectorState(snoozedUntil: active)
    XCTAssertEqual(IntegrationNudgePolicy.stateAfterDelivery(state, now: now).snoozedUntil, active)
  }

  func testSnoozeSetsTheFullDuration() {
    let next = IntegrationNudgePolicy.stateAfterSnooze(.init(), now: now)
    XCTAssertEqual(next.snoozedUntil, now.addingTimeInterval(IntegrationNudgePolicy.snoozeDuration))
  }

  /// Connecting is the goal state, so the pitch budget resets: a user who
  /// connects and later disconnects should be offered it again rather than
  /// silently never hearing about it.
  func testConnectResetsTheHistory() {
    let spent = IntegrationNudgePolicy.ConnectorState(
      shownCount: 3,
      lastShownAt: now,
      snoozedUntil: now.addingTimeInterval(1000)
    )
    let next = IntegrationNudgePolicy.stateAfterConnect(spent)
    XCTAssertEqual(next.shownCount, 0)
    XCTAssertNil(next.lastShownAt)
    XCTAssertNil(next.snoozedUntil)
    XCTAssertEqual(decide(connector: next), .deliver)
  }

  /// Opting out is a statement about the integration, not about the current
  /// connection, so connecting must not silently clear it.
  func testConnectDoesNotUndoAnOptOut() {
    let next = IntegrationNudgePolicy.stateAfterConnect(.init(optedOut: true))
    XCTAssertTrue(next.optedOut)
  }
}
