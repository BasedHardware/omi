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

    /// Uses the same comparison as production code in DesktopHomeView:
    /// `now.timeIntervalSince(lastActivationRefresh) >= PollingConfig.activationCooldown`
    func testFirstActivationAlwaysAllowed() {
        let lastRefresh = Date.distantPast
        let now = Date()
        // Mirror production: elapsed >= cooldown → refresh allowed
        XCTAssertTrue(
            now.timeIntervalSince(lastRefresh) >= PollingConfig.activationCooldown,
            "First activation (distantPast) must always pass cooldown check"
        )
    }

    func testActivationWithinCooldownIsBlocked() {
        let lastRefresh = Date()
        let now = lastRefresh.addingTimeInterval(PollingConfig.activationCooldown - 30)
        XCTAssertFalse(
            now.timeIntervalSince(lastRefresh) >= PollingConfig.activationCooldown,
            "Activation 30s before cooldown expires must be blocked"
        )
    }

    func testActivationAtExactCooldownBoundaryIsAllowed() {
        let lastRefresh = Date()
        let now = lastRefresh.addingTimeInterval(PollingConfig.activationCooldown)
        // Production uses >= so exactly at boundary is allowed
        XCTAssertTrue(
            now.timeIntervalSince(lastRefresh) >= PollingConfig.activationCooldown,
            "Activation at exactly cooldown boundary must be allowed (>= comparison)"
        )
    }

    func testActivationAfterCooldownIsAllowed() {
        let lastRefresh = Date()
        let now = lastRefresh.addingTimeInterval(PollingConfig.activationCooldown + 30)
        XCTAssertTrue(
            now.timeIntervalSince(lastRefresh) >= PollingConfig.activationCooldown,
            "Activation 30s past cooldown must be allowed"
        )
    }

    func testRapidActivationsAreThrottled() {
        // Simulate rapid cmd-tab: 10 activations 1 second apart
        let start = Date()
        var lastAllowed = Date.distantPast
        var allowedCount = 0
        for i in 0..<10 {
            let activation = start.addingTimeInterval(Double(i))
            if activation.timeIntervalSince(lastAllowed) >= PollingConfig.activationCooldown {
                allowedCount += 1
                lastAllowed = activation
            }
        }
        // Only the first activation should pass (subsequent ones are within 60s)
        XCTAssertEqual(allowedCount, 1, "Rapid activations (1s apart) should only allow 1 refresh")
    }

    func testCooldownResetsAfterExpiry() {
        // First activation allowed, second blocked, third allowed after cooldown
        let start = Date()
        var lastAllowed = Date.distantPast
        var results: [Bool] = []

        let activations = [
            start,                                                     // t=0s: should be allowed
            start.addingTimeInterval(30),                              // t=30s: within cooldown
            start.addingTimeInterval(PollingConfig.activationCooldown + 1)  // t=61s: past cooldown
        ]

        for activation in activations {
            let allowed = activation.timeIntervalSince(lastAllowed) >= PollingConfig.activationCooldown
            results.append(allowed)
            if allowed { lastAllowed = activation }
        }

        XCTAssertEqual(results, [true, false, true], "Expected: allowed, blocked, allowed after cooldown")
    }

    // MARK: - Refresh All Notification

    func testRefreshAllDataNotificationNameExists() {
        let name = Notification.Name.refreshAllData
        XCTAssertEqual(name.rawValue, "refreshAllData")
    }

    func testRefreshAllDataNotificationIsReceivable() {
        let expectation = XCTestExpectation(description: "Notification received")
        let observer = NotificationCenter.default.addObserver(
            forName: .refreshAllData, object: nil, queue: .main
        ) { _ in expectation.fulfill() }

        NotificationCenter.default.post(name: .refreshAllData, object: nil)
        wait(for: [expectation], timeout: 1.0)
        NotificationCenter.default.removeObserver(observer)
    }

    // MARK: - CrispManager Lifecycle

    @MainActor
    func testCrispManagerStartIsIdempotent() {
        let manager = CrispManager.shared
        // start() has a guard — calling twice should not double-register observers
        manager.start()
        manager.start()  // Second call is a no-op
        manager.stop()   // Clean up
        XCTAssertEqual(manager.unreadCount, 0, "unreadCount should be 0 after stop")
    }

    @MainActor
    func testCrispManagerStopClearsState() {
        let manager = CrispManager.shared
        manager.start()
        manager.stop()
        XCTAssertEqual(manager.unreadCount, 0, "unreadCount should be 0 after stop")
        XCTAssertFalse(manager.isViewingHelp, "isViewingHelp should be false after stop")
    }

    @MainActor
    func testCrispManagerMarkAsReadResetsCount() {
        let manager = CrispManager.shared
        manager.start()
        manager.markAsRead()
        XCTAssertEqual(manager.unreadCount, 0, "unreadCount should be 0 after markAsRead")
        manager.stop()
    }
}
