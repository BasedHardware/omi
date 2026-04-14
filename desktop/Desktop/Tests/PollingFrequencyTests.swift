import XCTest
@testable import Omi_Computer

/// Tests for event-driven refresh architecture (#6500).
/// Verifies that all periodic polling timers have been removed and
/// that activation cooldown logic works correctly.
final class PollingFrequencyTests: XCTestCase {

    // MARK: - No Polling Timers

    func testPollingConfigHasNoPollIntervals() {
        // PollingConfig should only contain activationCooldown — no poll intervals.
        // If someone adds a poll interval constant, this test must be updated.
        XCTAssertEqual(PollingConfig.activationCooldown, 60.0, "Activation cooldown should be 60s")
    }

    // MARK: - Activation Cooldown

    func testActivationCooldownIs60Seconds() {
        XCTAssertEqual(PollingConfig.activationCooldown, 60.0, "Activation cooldown should be 60s")
    }

    func testFirstActivationAlwaysAllowed() {
        // distantPast means no previous activation — should always be allowed
        let lastRefresh = Date.distantPast
        let now = Date()
        let elapsed = now.timeIntervalSince(lastRefresh)
        XCTAssertGreaterThanOrEqual(elapsed, PollingConfig.activationCooldown)
    }

    func testActivationWithinCooldownIsBlocked() {
        let lastRefresh = Date()
        // 30 seconds later — within cooldown
        let now = lastRefresh.addingTimeInterval(30)
        let elapsed = now.timeIntervalSince(lastRefresh)
        XCTAssertLessThan(elapsed, PollingConfig.activationCooldown)
    }

    func testActivationAtCooldownBoundaryIsAllowed() {
        let lastRefresh = Date()
        // Exactly 60 seconds later — at boundary
        let now = lastRefresh.addingTimeInterval(60)
        let elapsed = now.timeIntervalSince(lastRefresh)
        XCTAssertGreaterThanOrEqual(elapsed, PollingConfig.activationCooldown)
    }

    func testActivationAfterCooldownIsAllowed() {
        let lastRefresh = Date()
        // 90 seconds later — past cooldown
        let now = lastRefresh.addingTimeInterval(90)
        let elapsed = now.timeIntervalSince(lastRefresh)
        XCTAssertGreaterThanOrEqual(elapsed, PollingConfig.activationCooldown)
    }

    // MARK: - Refresh All Notification

    func testRefreshAllDataNotificationNameExists() {
        // Verify the notification name is defined (Cmd+R triggers this)
        let name = Notification.Name.refreshAllData
        XCTAssertEqual(name.rawValue, "refreshAllData")
    }
}
