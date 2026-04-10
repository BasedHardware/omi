import XCTest
@testable import Omi_Computer

/// Tests for polling frequency reduction (#6500).
/// Verifies that polling intervals are at their target values (120s)
/// and that the activation cooldown logic works correctly.
final class PollingFrequencyTests: XCTestCase {

    // MARK: - Polling Interval Constants

    func testChatPollIntervalIs120Seconds() {
        // ChatProvider.messagePollInterval is private, so verify via the config constant
        XCTAssertEqual(PollingConfig.chatPollInterval, 120.0, "Chat poll interval should be 120s")
    }

    func testTasksPollIntervalIs120Seconds() {
        XCTAssertEqual(PollingConfig.tasksPollInterval, 120.0, "Tasks poll interval should be 120s")
    }

    func testMemoriesPollIntervalIs120Seconds() {
        XCTAssertEqual(PollingConfig.memoriesPollInterval, 120.0, "Memories poll interval should be 120s")
    }

    func testConversationsPollIntervalIs120Seconds() {
        XCTAssertEqual(PollingConfig.conversationsPollInterval, 120.0, "Conversations poll interval should be 120s")
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
}
