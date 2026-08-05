import XCTest

@testable import Omi_Computer

/// Behavioral coverage for the pure background refresh policy: eligibility,
/// staleness, backoff, and state transitions. Every input including the clock
/// and the backoff jitter is injected, so nothing here depends on wall time.
@MainActor
final class ConnectorRefreshPolicyTests: XCTestCase {
  private let now = Date(timeIntervalSince1970: 1_700_000_000)
  private let sixHours: TimeInterval = 6 * 3600
  private let day: TimeInterval = 24 * 3600

  private func healthyEnvironment() -> ConnectorRefreshEnvironment {
    ConnectorRefreshEnvironment(isSignedIn: true, isOnline: true, isBatteryCritical: false)
  }

  private func decide(
    supportsUnattendedRefresh: Bool = true,
    isConnected: Bool = true,
    refreshInterval: TimeInterval? = nil,
    state: ConnectorRefreshState = ConnectorRefreshState(),
    environment: ConnectorRefreshEnvironment? = nil,
    isRunning: Bool = false,
    at instant: Date? = nil
  ) -> ConnectorRefreshDecision {
    ConnectorRefreshPolicy.decide(
      supportsUnattendedRefresh: supportsUnattendedRefresh,
      isConnected: isConnected,
      refreshInterval: refreshInterval ?? sixHours,
      state: state,
      environment: environment ?? healthyEnvironment(),
      isRunning: isRunning,
      now: instant ?? now
    )
  }

  // MARK: - Eligibility (the consent-prompt guard)

  /// THE regression guard for this subsystem. A connector whose refresh path can
  /// raise a macOS consent dialog must never be run by a timer, no matter how
  /// stale it is and no matter how healthy everything else looks. A naive
  /// scheduler passing `userInitiated: true` would prompt the user out of
  /// nowhere; this is the assertion that stops that shipping.
  func testIneligibleConnectorIsNeverRefreshedInBackground() {
    let thirtyFourDaysAgo = now.addingTimeInterval(-34 * day)
    let decision = decide(
      supportsUnattendedRefresh: false,
      isConnected: true,
      state: ConnectorRefreshState(lastSuccessAt: thirtyFourDaysAgo),
      environment: healthyEnvironment(),
      isRunning: false
    )

    XCTAssertEqual(decision, .skip(.notEligibleForUnattendedRefresh))
  }

  func testNotConnectedConnectorIsSkipped() {
    XCTAssertEqual(decide(isConnected: false), .skip(.notConnected))
  }

  // MARK: - Staleness

  func testIntervalNotElapsedIsSkipped() {
    let state = ConnectorRefreshState(lastSuccessAt: now.addingTimeInterval(-sixHours + 1))
    XCTAssertEqual(decide(state: state), .skip(.intervalNotElapsed))
  }

  func testIntervalExactlyElapsedRefreshes() {
    let state = ConnectorRefreshState(lastSuccessAt: now.addingTimeInterval(-sixHours))
    XCTAssertEqual(decide(state: state), .refresh)
  }

  func testNeverSyncedEligibleConnectorIsDue() {
    XCTAssertEqual(decide(state: ConnectorRefreshState(lastSuccessAt: nil)), .refresh)
  }

  /// The reported production symptom: email last synced 34 days ago. A connector
  /// that stale must refresh on the very first tick, not wait out another
  /// interval.
  func testThirtyFourDayStaleConnectorIsDueOnFirstTick() {
    let state = ConnectorRefreshState(lastSuccessAt: now.addingTimeInterval(-34 * day))
    XCTAssertEqual(decide(state: state), .refresh)
  }

  // MARK: - Backoff and parking

  func testBackoffNotElapsedIsSkipped() {
    let state = ConnectorRefreshState(
      lastSuccessAt: now.addingTimeInterval(-2 * day),
      consecutiveFailures: 2,
      nextEligibleAt: now.addingTimeInterval(60)
    )
    XCTAssertEqual(decide(state: state), .skip(.backoffNotElapsed))
  }

  func testNeedsUserActionParksConnectorIndefinitely() {
    let state = ConnectorRefreshState(
      lastSuccessAt: now.addingTimeInterval(-2 * day),
      consecutiveFailures: 5,
      needsUserAction: .sessionExpired
    )

    for offset in [day, 7 * day, 30 * day] {
      XCTAssertEqual(
        decide(state: state, at: now.addingTimeInterval(offset)),
        .skip(.needsUserAction),
        "a parked connector must stay parked \(Int(offset / day)) days later"
      )
    }
  }

  // MARK: - Environment

  func testSignedOutSkips() {
    var environment = healthyEnvironment()
    environment.isSignedIn = false
    XCTAssertEqual(decide(environment: environment), .skip(.signedOut))
  }

  func testOfflineSkips() {
    var environment = healthyEnvironment()
    environment.isOnline = false
    XCTAssertEqual(decide(environment: environment), .skip(.offline))
  }

  func testBatteryCriticalSkips() {
    var environment = healthyEnvironment()
    environment.isBatteryCritical = true
    XCTAssertEqual(decide(environment: environment), .skip(.batteryCritical))
  }

  // MARK: - Precedence

  /// Precedence is part of the contract, most structural first. The eligibility
  /// gate in particular must win over everything, so a connector that could
  /// prompt is never reported as merely "offline" or "backing off".
  func testSkipReasonPrecedence() {
    var supportsUnattendedRefresh = false
    var isConnected = false
    var isRunning = true
    var state = ConnectorRefreshState(
      lastSuccessAt: now,
      consecutiveFailures: 3,
      nextEligibleAt: now.addingTimeInterval(600),
      needsUserAction: .sessionExpired
    )
    var environment = ConnectorRefreshEnvironment(
      isSignedIn: false,
      isOnline: false,
      isBatteryCritical: true
    )

    func current() -> ConnectorRefreshDecision {
      decide(
        supportsUnattendedRefresh: supportsUnattendedRefresh,
        isConnected: isConnected,
        state: state,
        environment: environment,
        isRunning: isRunning
      )
    }

    XCTAssertEqual(current(), .skip(.notEligibleForUnattendedRefresh))
    supportsUnattendedRefresh = true
    XCTAssertEqual(current(), .skip(.notConnected))
    isConnected = true
    XCTAssertEqual(current(), .skip(.needsUserAction))
    state.needsUserAction = nil
    XCTAssertEqual(current(), .skip(.alreadyRunning))
    isRunning = false
    XCTAssertEqual(current(), .skip(.signedOut))
    environment.isSignedIn = true
    XCTAssertEqual(current(), .skip(.offline))
    environment.isOnline = true
    XCTAssertEqual(current(), .skip(.batteryCritical))
    environment.isBatteryCritical = false
    XCTAssertEqual(current(), .skip(.backoffNotElapsed))
    state.nextEligibleAt = nil
    XCTAssertEqual(current(), .skip(.intervalNotElapsed))
    state.lastSuccessAt = now.addingTimeInterval(-sixHours)
    XCTAssertEqual(current(), .refresh)
  }

  // MARK: - Backoff maths

  func testBackoffIsExponentialAndCapped() {
    let expected: [(failures: Int, delay: TimeInterval)] = [
      (1, 900),
      (2, 1800),
      (3, 3600),
      (4, 7200),
      (5, 14400),
      (6, 21600),
      (7, 21600),
      (12, 21600),
    ]

    for (failures, delay) in expected {
      XCTAssertEqual(
        ConnectorRefreshPolicy.backoffDelay(consecutiveFailures: failures, jitter: 0),
        delay,
        accuracy: 0.001,
        "failure \(failures) should back off \(delay)s"
      )
    }
    XCTAssertEqual(ConnectorRefreshPolicy.backoffDelay(consecutiveFailures: 0, jitter: 0), 0)
  }

  func testBackoffJitterStaysWithinFifteenPercent() {
    for failures in 1...8 {
      let unjittered = ConnectorRefreshPolicy.backoffDelay(consecutiveFailures: failures, jitter: 0)
      let low = ConnectorRefreshPolicy.backoffDelay(consecutiveFailures: failures, jitter: -1)
      let high = ConnectorRefreshPolicy.backoffDelay(consecutiveFailures: failures, jitter: 1)

      XCTAssertEqual(low, unjittered * 0.85, accuracy: 0.001)
      XCTAssertEqual(high, unjittered * 1.15, accuracy: 0.001)
      // Out-of-range jitter is clamped, never amplified.
      XCTAssertEqual(
        ConnectorRefreshPolicy.backoffDelay(consecutiveFailures: failures, jitter: 42),
        high,
        accuracy: 0.001
      )
    }
  }

  // MARK: - State transitions

  func testTransientFailureIncrementsAndSchedulesBackoff() {
    let lastSuccess = now.addingTimeInterval(-2 * day)
    let state = ConnectorRefreshState(lastSuccessAt: lastSuccess, consecutiveFailures: 1)

    let updated = ConnectorRefreshPolicy.applying(
      result: .transientFailure(reason: .network),
      to: state,
      now: now,
      jitter: 0
    )

    XCTAssertEqual(updated.consecutiveFailures, 2)
    XCTAssertEqual(updated.nextEligibleAt, now.addingTimeInterval(1800))
    XCTAssertEqual(updated.lastAttemptAt, now)
    XCTAssertNil(updated.needsUserAction)
    // A failing connector keeps aging so the UI keeps telling the truth.
    XCTAssertEqual(updated.lastSuccessAt, lastSuccess)
  }

  func testFifthConsecutiveTransientFailureEscalatesToNeedsUserAction() {
    let state = ConnectorRefreshState(consecutiveFailures: 4)

    let updated = ConnectorRefreshPolicy.applying(
      result: .transientFailure(reason: .timeout),
      to: state,
      now: now,
      jitter: 0
    )

    XCTAssertEqual(updated.consecutiveFailures, ConnectorRefreshPolicy.maxConsecutiveFailures)
    XCTAssertEqual(updated.needsUserAction, .timeout)
    XCTAssertNil(updated.nextEligibleAt, "an escalated connector must not keep a retry scheduled")
  }

  func testNeedsUserActionResultParksImmediatelyWithoutBackoff() {
    let updated = ConnectorRefreshPolicy.applying(
      result: .needsUserAction(reason: .sessionExpired),
      to: ConnectorRefreshState(),
      now: now,
      jitter: 0
    )

    XCTAssertEqual(updated.needsUserAction, .sessionExpired)
    XCTAssertNil(updated.nextEligibleAt, "a parked connector must not enter the backoff loop")
    XCTAssertNil(updated.lastSuccessAt)
  }

  func testSuccessResetsFailureCountAndClearsAttention() {
    let state = ConnectorRefreshState(
      lastSuccessAt: now.addingTimeInterval(-34 * day),
      consecutiveFailures: 4,
      nextEligibleAt: now.addingTimeInterval(3600),
      needsUserAction: .sessionExpired,
      lastFallbackReportedAt: now.addingTimeInterval(-3600)
    )

    let updated = ConnectorRefreshPolicy.applying(
      result: .success(ConnectorRefreshMetrics(sourceCount: 12, memoryCount: 3, newItems: 2)),
      to: state,
      now: now,
      jitter: 0
    )

    XCTAssertEqual(updated.lastSuccessAt, now)
    XCTAssertEqual(updated.consecutiveFailures, 0)
    XCTAssertNil(updated.nextEligibleAt)
    XCTAssertNil(updated.needsUserAction)
    // The fallback dedupe window survives a success — it is a reporting budget,
    // not failure state.
    XCTAssertEqual(updated.lastFallbackReportedAt, now.addingTimeInterval(-3600))
  }

  // MARK: - Ordering

  func testNextDueOrdersByStalenessWithNeverSyncedFirst() {
    let candidates: [(connectorID: String, state: ConnectorRefreshState)] = [
      ("apple-notes", ConnectorRefreshState(lastSuccessAt: now.addingTimeInterval(-19 * day))),
      ("calendar", ConnectorRefreshState(lastSuccessAt: nil)),
      ("local-files", ConnectorRefreshState(lastSuccessAt: now.addingTimeInterval(-34 * day))),
    ]

    XCTAssertEqual(ConnectorRefreshPolicy.nextDue(candidates, now: now), "calendar")

    let synced: [(connectorID: String, state: ConnectorRefreshState)] = [
      ("apple-notes", ConnectorRefreshState(lastSuccessAt: now.addingTimeInterval(-19 * day))),
      ("local-files", ConnectorRefreshState(lastSuccessAt: now.addingTimeInterval(-34 * day))),
    ]
    XCTAssertEqual(ConnectorRefreshPolicy.nextDue(synced, now: now), "local-files")

    XCTAssertNil(ConnectorRefreshPolicy.nextDue([], now: now))
  }
}
