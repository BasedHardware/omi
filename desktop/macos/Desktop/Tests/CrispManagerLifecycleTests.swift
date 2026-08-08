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
    savedLastSeen = UserDefaults.standard.double(forKey: "crisp_lastSeenTimestamp")
    savedLatestOperator = UserDefaults.standard.double(forKey: "crisp_latestOperatorTimestamp")
    // Reset the singleton to a clean state — previous tests may have called start()
    CrispManager.shared.stop()
  }

  override func tearDown() async throws {
    CrispManager.shared.stop()
    UserDefaults.standard.set(savedLastSeen, forKey: "crisp_lastSeenTimestamp")
    UserDefaults.standard.set(savedLatestOperator, forKey: "crisp_latestOperatorTimestamp")
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

  func testStopCanPreserveReadStateForNormalTermination() {
    let manager = CrispManager.shared
    manager.lastSeenTimestamp = 111_111
    manager.latestOperatorTimestamp = 222_222
    manager.start(performInitialPoll: false)

    manager.stop(preserveReadState: true)

    XCTAssertFalse(manager.isStarted)
    XCTAssertEqual(manager.lastSeenTimestamp, 111_111)
    XCTAssertEqual(manager.latestOperatorTimestamp, 222_222)
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

  // MARK: - The banner has somewhere to go

  /// A support reply's banner used to record that it was tapped and do nothing else, so the app
  /// interrupted the user about a message and then refused to show it. The tap keys on the
  /// notification's **provenance**, not on its display title, so renaming the banner cannot quietly
  /// disconnect it again.
  func testASupportReplyTapResolvesToTheSupportThread() {
    XCTAssertEqual(
      NotificationService.openAction(
        assistantId: SupportThreadRoute.assistantId, title: "Help from Founder"),
      .openSupportThread)
    XCTAssertEqual(
      NotificationService.openAction(
        assistantId: SupportThreadRoute.assistantId, title: "A note from the team"),
      .openSupportThread,
      "the tap must survive a copy change to the banner's title")

    // The other two branches are unchanged by this: the repair notification still repairs, and an
    // ordinary proactive notification still has nothing to open.
    XCTAssertEqual(
      NotificationService.openAction(
        assistantId: "screen_capture", title: NotificationService.screenCaptureResetTitle),
      .resetScreenCapture)
    XCTAssertEqual(
      NotificationService.openAction(assistantId: "memory", title: "Saved a memory"),
      .none)
  }

  /// Opening the thread has to *navigate*, and it has to navigate somewhere the user could also
  /// have walked to themselves — a banner that lands on a page with no door is the bug this
  /// replaced. Driven through the real service instance rather than a real notification delivery:
  /// `registerWithSystemNotificationCenter: false` is the existing seam for exactly this.
  func testOpeningTheSupportThreadNavigatesToTheHelpRowInSettings() {
    let inbox = NavigationInbox()
    let observer = NotificationCenter.default.addObserver(
      forName: .navigateToSidebarItem, object: nil, queue: nil
    ) { notification in
      inbox.record(notification.userInfo)
    }
    defer { NotificationCenter.default.removeObserver(observer) }

    let service = NotificationService(registerWithSystemNotificationCenter: false)
    service.openSupportThread(source: "unit_test")

    guard let received = inbox.userInfo else {
      return XCTFail("tapping a support reply raised no navigation at all")
    }
    XCTAssertEqual(
      received["rawValue"] as? Int, SidebarNavItem.settings.rawValue,
      "the support thread lives behind the settings gear")
    guard let sectionRaw = received["settingsSection"] as? String else {
      return XCTFail("navigation named Settings but not which row")
    }
    // The receiver resolves the payload with `automationMatch`, so assert the payload against that
    // rather than against a string literal — the two used to be able to disagree silently.
    XCTAssertEqual(
      SettingsContentView.SettingsSection.automationMatch(sectionRaw),
      SupportThreadRoute.destination.settingsSection)

    XCTAssertFalse(
      ShellDestination.unreachable().contains(SupportThreadRoute.destination),
      "the page a support banner opens must be one the user can reach on their own (INV-NAV-1)")
  }
}

/// Holds the one navigation the support tap raises. `Notification.userInfo` is not `Sendable`, and
/// the observer closure is, so the value crosses through a reference the test owns rather than a
/// captured `var`. The post is synchronous on the main actor with `queue: nil`, so no wait is
/// needed and none is added.
private final class NavigationInbox: @unchecked Sendable {
  private(set) var userInfo: [AnyHashable: Any]?

  func record(_ userInfo: [AnyHashable: Any]?) {
    self.userInfo = userInfo
  }
}
