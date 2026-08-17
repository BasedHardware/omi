import XCTest

@testable import Omi_Computer

@MainActor
final class IntegrationNudgeStoreTests: XCTestCase {
  private let now = Date(timeIntervalSince1970: 1_700_000_000)
  private let telemetryID = "import:email"

  /// A private defaults domain per test, torn down when the test finishes.
  /// `setUp`/`tearDown` are nonisolated, so the fixture is built here instead of
  /// held in main-actor-isolated properties.
  private func makeDefaults() -> UserDefaults {
    let suiteName = "IntegrationNudgeStoreTests.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      preconditionFailure("could not create a private defaults domain for \(suiteName)")
    }
    addTeardownBlock { defaults.removePersistentDomain(forName: suiteName) }
    return defaults
  }

  private func store(
    _ defaults: UserDefaults,
    owner: String? = "user-a"
  ) -> IntegrationNudgeStore {
    IntegrationNudgeStore(defaults: defaults, ownerID: owner)
  }

  func testDeliveryRoundTrips() {
    let defaults = makeDefaults()
    let store = self.store(defaults)
    store.recordDelivery(telemetryID: telemetryID, now: now)

    let state = store.state(for: telemetryID, now: now)
    XCTAssertEqual(state.shownCount, 1)
    XCTAssertEqual(state.lastShownAt?.timeIntervalSince1970, now.timeIntervalSince1970)
    XCTAssertEqual(store.lastAnyNudgeAt(now: now)?.timeIntervalSince1970, now.timeIntervalSince1970)
    XCTAssertEqual(store.nudgesInCurrentDay(now: now), 1)
  }

  /// `snoozedUntil` is a deadline, so it is in the future by definition. A
  /// past-only sanitizer applied to it would mean "Not now" silently snoozed
  /// nothing — the store must read it back even when it is ahead of `now`.
  func testSnoozeSurvivesReadbackWhileStillInTheFuture() {
    let defaults = makeDefaults()
    let store = self.store(defaults)
    store.recordSnooze(telemetryID: telemetryID, now: Date())

    let snoozedUntil = store.state(for: telemetryID).snoozedUntil
    XCTAssertNotNil(snoozedUntil)
    XCTAssertGreaterThan(try XCTUnwrap(snoozedUntil), Date())
  }

  func testSnoozeAndOptOutPersist() {
    let defaults = makeDefaults()
    let store = self.store(defaults)
    store.recordSnooze(telemetryID: telemetryID, now: now)
    XCTAssertEqual(
      store.state(for: telemetryID, now: now).snoozedUntil?.timeIntervalSince1970,
      now.addingTimeInterval(IntegrationNudgePolicy.snoozeDuration).timeIntervalSince1970
    )

    store.recordOptOut(telemetryID: telemetryID)
    XCTAssertTrue(store.state(for: telemetryID, now: now).optedOut)
  }

  func testConnectingClearsTheHistory() {
    let defaults = makeDefaults()
    let store = self.store(defaults)
    store.recordDelivery(telemetryID: telemetryID, now: now)
    store.recordSnooze(telemetryID: telemetryID, now: now)

    store.recordConnected(telemetryID: telemetryID)

    let state = store.state(for: telemetryID, now: now)
    XCTAssertEqual(state.shownCount, 0)
    XCTAssertNil(state.lastShownAt)
    XCTAssertNil(state.snoozedUntil)
  }

  /// Connecting clears the *budget*, not the user's refusal. The grant refresh
  /// re-runs this on every reconnect check while the sheet is open, so a clear
  /// that also dropped `optedOut` would hand back nudges the user had turned
  /// off for good — and would do it repeatedly.
  func testConnectingKeepsAnOptOut() {
    let defaults = makeDefaults()
    let store = self.store(defaults)
    store.recordOptOut(telemetryID: telemetryID)

    store.recordConnected(telemetryID: telemetryID)

    XCTAssertTrue(store.state(for: telemetryID, now: now).optedOut)
  }

  /// "You already declined this" is a fact about a person. A second account on
  /// the same Mac must not inherit it.
  func testHistoryIsScopedToTheOwner() {
    let defaults = makeDefaults()
    store(defaults, owner: "user-a").recordOptOut(telemetryID: telemetryID)

    XCTAssertTrue(store(defaults, owner: "user-a").state(for: telemetryID, now: now).optedOut)
    XCTAssertFalse(store(defaults, owner: "user-b").state(for: telemetryID, now: now).optedOut)
  }

  func testSignedOutStoreNeitherReadsNorWrites() {
    let defaults = makeDefaults()
    let signedOut = store(defaults, owner: nil)
    signedOut.recordDelivery(telemetryID: telemetryID, now: now)

    XCTAssertEqual(signedOut.state(for: telemetryID).shownCount, 0)
    XCTAssertNil(signedOut.lastAnyNudgeAt())
    XCTAssertEqual(signedOut.nudgesInCurrentDay(now: now), 0)
  }

  /// The daily budget rolls continuously. A calendar-day counter would let two
  /// nudges at 23:58 be followed immediately by two more at 00:01.
  func testDayWindowRollsRatherThanResettingOnACalendarBoundary() {
    let defaults = makeDefaults()
    let store = self.store(defaults)
    store.recordDelivery(telemetryID: telemetryID, now: now)
    store.recordDelivery(telemetryID: "import:calendar", now: now)

    let justInside = now.addingTimeInterval(IntegrationNudgePolicy.dayWindow - 1)
    XCTAssertEqual(store.nudgesInCurrentDay(now: justInside), 2)

    let justOutside = now.addingTimeInterval(IntegrationNudgePolicy.dayWindow + 1)
    XCTAssertEqual(store.nudgesInCurrentDay(now: justOutside), 0)
  }

  /// A clock rolled backwards would otherwise strand future-dated entries in
  /// the window forever, permanently capping the user's nudges at zero.
  func testFutureDatedDeliveriesAreNotCountedAgainstTheBudget() {
    let defaults = makeDefaults()
    let store = self.store(defaults)
    store.recordDelivery(telemetryID: telemetryID, now: now.addingTimeInterval(60 * 60))
    XCTAssertEqual(store.nudgesInCurrentDay(now: now), 0)
  }

  /// A clock that moves backwards would leave the cooldown timestamps ahead of
  /// `now`, and the gates that compare elapsed time against a positive budget
  /// would then silence every nudge until the skew passed.
  func testFutureDatedTimestampsAreDiscardedRatherThanSilencingNudges() {
    let defaults = makeDefaults()
    let store = self.store(defaults)
    // Genuinely ahead of the wall clock the store reads, which is what a
    // backwards clock change leaves behind.
    store.recordDelivery(telemetryID: telemetryID, now: Date().addingTimeInterval(60 * 60))

    XCTAssertNil(store.state(for: telemetryID).lastShownAt)
    XCTAssertNil(store.lastAnyNudgeAt())
  }

  func testResetClearsEverythingForTheOwner() {
    let defaults = makeDefaults()
    let store = self.store(defaults)
    store.recordDelivery(telemetryID: telemetryID, now: now)
    store.recordOptOut(telemetryID: telemetryID)

    store.resetAll(telemetryIDs: [telemetryID])

    let state = store.state(for: telemetryID)
    XCTAssertEqual(state.shownCount, 0)
    XCTAssertFalse(state.optedOut)
    XCTAssertNil(store.lastAnyNudgeAt())
    XCTAssertEqual(store.nudgesInCurrentDay(now: now), 0)
  }

  /// The full loop the user actually experiences: offered, offered again after
  /// the cooldown, offered a third time, then never again.
  func testLifetimeBudgetIsSpentAfterThreeOffers() {
    let defaults = makeDefaults()
    let store = self.store(defaults)
    var instant = now

    for _ in 0..<IntegrationNudgePolicy.connectorLifetimeCap {
      let decision = IntegrationNudgePolicy.decide(
        IntegrationNudgePolicy.Input(
          isConnected: false,
          connector: store.state(for: telemetryID, now: instant),
          lastAnyNudgeAt: store.lastAnyNudgeAt(now: instant),
          nudgesInCurrentDay: store.nudgesInCurrentDay(now: instant),
          now: instant
        )
      )
      XCTAssertEqual(decision, .deliver)
      store.recordDelivery(telemetryID: telemetryID, now: instant)
      instant = instant.addingTimeInterval(IntegrationNudgePolicy.connectorCooldown)
    }

    let exhausted = IntegrationNudgePolicy.decide(
      IntegrationNudgePolicy.Input(
        isConnected: false,
        connector: store.state(for: telemetryID, now: instant),
        lastAnyNudgeAt: store.lastAnyNudgeAt(now: instant),
        nudgesInCurrentDay: store.nudgesInCurrentDay(now: instant),
        now: instant
      )
    )
    XCTAssertEqual(exhausted, .suppress(.connectorLifetimeCap))
  }
}
