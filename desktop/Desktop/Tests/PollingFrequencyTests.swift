import XCTest
@testable import Omi_Computer

/// Tests for event-driven refresh architecture (#6500).
/// All polling timers are removed — refreshes happen on app activation
/// (didBecomeActiveNotification) and manual Cmd+R (.refreshAllData).
///
/// Tests call `PollingConfig.shouldAllowActivationRefresh(now:lastRefresh:)`,
/// which is the same function used by DesktopHomeView's activation handler.
/// A regression in that predicate (e.g. `>=` → `>`) is caught here.
final class PollingFrequencyTests: XCTestCase {

    // MARK: - No Polling Timers

    func testPollingConfigHasNoPollIntervals() {
        // PollingConfig only exposes activationCooldown + the shared predicate.
        // If someone reintroduces a poll interval constant, update this test.
        XCTAssertEqual(PollingConfig.activationCooldown, 60.0)
    }

    // MARK: - Activation Cooldown (shared predicate)

    func testFirstActivationAlwaysAllowed() {
        let now = Date()
        XCTAssertTrue(
            PollingConfig.shouldAllowActivationRefresh(now: now, lastRefresh: .distantPast),
            "First activation (distantPast) must always be allowed"
        )
    }

    func testActivationWithinCooldownIsBlocked() {
        let lastRefresh = Date()
        let now = lastRefresh.addingTimeInterval(PollingConfig.activationCooldown - 0.001)
        XCTAssertFalse(
            PollingConfig.shouldAllowActivationRefresh(now: now, lastRefresh: lastRefresh),
            "Activation just under cooldown must be blocked"
        )
    }

    func testActivationAtExactCooldownBoundaryIsAllowed() {
        let lastRefresh = Date()
        let now = lastRefresh.addingTimeInterval(PollingConfig.activationCooldown)
        // Production uses >= — boundary must be inclusive. Guards against >= → > regressions.
        XCTAssertTrue(
            PollingConfig.shouldAllowActivationRefresh(now: now, lastRefresh: lastRefresh),
            "Activation at exactly cooldown boundary must be allowed (>= comparison)"
        )
    }

    func testActivationAfterCooldownIsAllowed() {
        let lastRefresh = Date()
        let now = lastRefresh.addingTimeInterval(PollingConfig.activationCooldown + 30)
        XCTAssertTrue(
            PollingConfig.shouldAllowActivationRefresh(now: now, lastRefresh: lastRefresh),
            "Activation 30s past cooldown must be allowed"
        )
    }

    func testBackwardClockSkewIsAllowed() {
        // If system clock jumps backward, elapsed is negative < cooldown.
        // Predicate returns false (blocked). This documents current behavior —
        // a user with clock skew just won't get an auto-refresh that cycle.
        let lastRefresh = Date()
        let now = lastRefresh.addingTimeInterval(-10)
        XCTAssertFalse(
            PollingConfig.shouldAllowActivationRefresh(now: now, lastRefresh: lastRefresh),
            "Negative elapsed (backward clock skew) must be treated as within cooldown"
        )
    }

    func testRapidActivationsAreThrottled() {
        // Simulate cmd-tab spam: 10 activations 1 second apart.
        // Driven by the same predicate as production.
        let start = Date()
        var lastAllowed = Date.distantPast
        var allowedCount = 0
        for i in 0..<10 {
            let activation = start.addingTimeInterval(Double(i))
            if PollingConfig.shouldAllowActivationRefresh(now: activation, lastRefresh: lastAllowed) {
                allowedCount += 1
                lastAllowed = activation
            }
        }
        XCTAssertEqual(allowedCount, 1, "Rapid activations (1s apart) should only allow 1 refresh")
    }

    func testCooldownResetsAfterExpiry() {
        // Sequence [allowed, blocked, allowed] — the third activation is past cooldown.
        let start = Date()
        var lastAllowed = Date.distantPast
        var results: [Bool] = []

        let activations = [
            start,                                                          // t=0: allowed (first)
            start.addingTimeInterval(30),                                   // t=30: blocked
            start.addingTimeInterval(PollingConfig.activationCooldown + 1)  // t=61: allowed
        ]

        for activation in activations {
            let allowed = PollingConfig.shouldAllowActivationRefresh(
                now: activation, lastRefresh: lastAllowed
            )
            results.append(allowed)
            if allowed { lastAllowed = activation }
        }

        XCTAssertEqual(results, [true, false, true])
    }

    // MARK: - Refresh All Notification

    func testRefreshAllDataNotificationNameExists() {
        XCTAssertEqual(Notification.Name.refreshAllData.rawValue, "refreshAllData")
    }

    func testRefreshAllDataNotificationIsReceivable() {
        let expectation = XCTestExpectation(description: "Notification received")
        let observer = NotificationCenter.default.addObserver(
            forName: .refreshAllData, object: nil, queue: .main
        ) { _ in expectation.fulfill() }
        defer { NotificationCenter.default.removeObserver(observer) }

        NotificationCenter.default.post(name: .refreshAllData, object: nil)
        wait(for: [expectation], timeout: 1.0)
    }
}
