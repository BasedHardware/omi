import AppKit
import XCTest
@testable import Omi_Computer

/// Tests for `CrispManager` event-driven lifecycle (#6500).
///
/// After removing the 120s polling timer, `CrispManager` relies entirely on
/// `start()`/`stop()` registering/unregistering `didBecomeActive` + `.refreshAllData`
/// observers. These tests cover the highest-risk branch: the observer lifecycle
/// and `markAsRead()` timestamp advancement.
@MainActor
final class CrispManagerLifecycleTests: XCTestCase {

    // Save and restore the UserDefaults-backed timestamps so each test runs
    // against a known state without clobbering real app data.
    private var savedLastSeen: Double = 0
    private var savedLatestOperator: Double = 0

    override func setUp() async throws {
        try await super.setUp()
        savedLastSeen = UserDefaults.standard.double(forKey: "crisp_lastSeenTimestamp")
        savedLatestOperator = UserDefaults.standard.double(forKey: "crisp_latestOperatorTimestamp")
        // Reset the singleton to a clean state — previous tests may have called start()
        CrispManager.shared.stop()
    }

    override func tearDown() async throws {
        CrispManager.shared.stop()
        UserDefaults.standard.set(savedLastSeen, forKey: "crisp_lastSeenTimestamp")
        UserDefaults.standard.set(savedLatestOperator, forKey: "crisp_latestOperatorTimestamp")
        try await super.tearDown()
    }

    func testStartIsIdempotent() {
        let manager = CrispManager.shared
        XCTAssertFalse(manager.isStarted, "Manager must be stopped after setUp()")

        manager.start(performInitialPoll: false)
        XCTAssertTrue(manager.isStarted, "start() must set isStarted true")
        let firstActivationObs = manager.activationObserver
        let firstRefreshObs = manager.refreshAllObserver
        XCTAssertNotNil(firstActivationObs, "start() must register activation observer")
        XCTAssertNotNil(firstRefreshObs, "start() must register refreshAllData observer")

        // Second start() call must be a no-op — observers must NOT be replaced.
        // A new token would mean we leaked the first registration.
        manager.start(performInitialPoll: false)
        XCTAssertTrue(manager.isStarted)
        XCTAssertTrue(
            manager.activationObserver === firstActivationObs as AnyObject,
            "Second start() must not replace the activation observer (leak guard)"
        )
        XCTAssertTrue(
            manager.refreshAllObserver === firstRefreshObs as AnyObject,
            "Second start() must not replace the refreshAllData observer (leak guard)"
        )
    }

    func testStopRemovesBothObservers() {
        let manager = CrispManager.shared
        manager.start(performInitialPoll: false)
        XCTAssertNotNil(manager.activationObserver)
        XCTAssertNotNil(manager.refreshAllObserver)
        XCTAssertTrue(manager.isStarted)

        manager.stop()
        XCTAssertNil(manager.activationObserver, "stop() must nil the activation observer")
        XCTAssertNil(manager.refreshAllObserver, "stop() must nil the refreshAllData observer")
        XCTAssertFalse(manager.isStarted, "stop() must clear isStarted so start() can run again")

        // After stop(), a subsequent start() must succeed (observer lifecycle reusable).
        manager.start(performInitialPoll: false)
        XCTAssertTrue(manager.isStarted, "start() after stop() must re-register observers")
        XCTAssertNotNil(manager.activationObserver)
        XCTAssertNotNil(manager.refreshAllObserver)
    }

    func testStopIsIdempotent() {
        let manager = CrispManager.shared
        manager.start(performInitialPoll: false)
        manager.stop()
        // Second stop() must not crash or change state
        manager.stop()
        XCTAssertFalse(manager.isStarted)
        XCTAssertNil(manager.activationObserver)
        XCTAssertNil(manager.refreshAllObserver)
    }

    func testMarkAsReadAdvancesPersistedTimestamp() {
        let manager = CrispManager.shared
        manager.latestOperatorTimestamp = 999_999
        manager.lastSeenTimestamp = 111_111

        manager.markAsRead()

        XCTAssertEqual(
            manager.lastSeenTimestamp, 999_999,
            "markAsRead() must advance lastSeenTimestamp to latestOperatorTimestamp"
        )
        XCTAssertEqual(manager.unreadCount, 0, "markAsRead() must clear unreadCount")
    }

    func testMarkAsReadIsSafeWhenNoNewMessages() {
        let manager = CrispManager.shared
        manager.latestOperatorTimestamp = 0
        manager.lastSeenTimestamp = 0

        manager.markAsRead()

        XCTAssertEqual(manager.lastSeenTimestamp, 0)
        XCTAssertEqual(manager.unreadCount, 0)
    }

    func testDidBecomeActiveNotificationTriggersPoll() async {
        let manager = CrispManager.shared
        manager.start(performInitialPoll: false)
        let baseline = manager.pollInvocations

        NotificationCenter.default.post(
            name: NSApplication.didBecomeActiveNotification, object: nil
        )
        // Observer posts on main queue; yield so the block runs.
        await Task.yield()
        try? await Task.sleep(nanoseconds: 50_000_000)

        XCTAssertEqual(
            manager.pollInvocations, baseline + 1,
            "didBecomeActive must route to pollForMessages() via the activation observer"
        )
    }

    func testRefreshAllDataNotificationTriggersPoll() async {
        let manager = CrispManager.shared
        manager.start(performInitialPoll: false)
        let baseline = manager.pollInvocations

        NotificationCenter.default.post(name: .refreshAllData, object: nil)
        await Task.yield()
        try? await Task.sleep(nanoseconds: 50_000_000)

        XCTAssertEqual(
            manager.pollInvocations, baseline + 1,
            ".refreshAllData (Cmd+R) must route to pollForMessages() via the refresh observer"
        )
    }

    func testStoppedManagerDoesNotRespondToNotifications() async {
        let manager = CrispManager.shared
        manager.start(performInitialPoll: false)
        manager.stop()
        let baseline = manager.pollInvocations

        NotificationCenter.default.post(
            name: NSApplication.didBecomeActiveNotification, object: nil
        )
        NotificationCenter.default.post(name: .refreshAllData, object: nil)
        await Task.yield()
        try? await Task.sleep(nanoseconds: 50_000_000)

        XCTAssertEqual(
            manager.pollInvocations, baseline,
            "After stop(), neither notification should reach pollForMessages()"
        )
    }
}
