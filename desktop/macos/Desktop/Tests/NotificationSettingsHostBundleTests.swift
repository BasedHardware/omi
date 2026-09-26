import UserNotifications
import XCTest

@testable import Omi_Computer

/// #9029: the desktop suite hard-crashed in a single `swift test` process with no assertion
/// failure, and the victim suite moved with test ordering.
///
/// The cause was `UNUserNotificationCenter.current()` in the production notification-settings
/// query. Off an app bundle it raises `NSInternalInconsistencyException`
/// ("bundleProxyForCurrentProcess is nil"), and an Objective-C exception cannot be caught in
/// Swift — so it terminated the whole run, landing on whichever suite happened to be
/// executing rather than the one that reached the query.
///
/// These run in the xctest host, whose main bundle is the Xcode command-line tool, so they
/// exercise the real non-app-bundle condition rather than a simulated one. Before the guard,
/// the second test terminated the process instead of failing.
final class NotificationSettingsHostBundleTests: XCTestCase {
  func testTestHostIsNotAnAppBundle() {
    XCTAssertFalse(
      UserNotificationCallbackBridge.hostProcessIsAppBundle,
      "the xctest host has no .app bundle; if this ever passes, the guard below stops being exercised"
    )
  }

  func testSystemQueryAnswersWithoutTouchingUNUserNotificationCenter() {
    let answered = expectation(description: "settings query completes")
    let box = SnapshotBox()

    UserNotificationCallbackBridge.systemNotificationSettingsQuery { result in
      box.store(result)
      answered.fulfill()
    }

    wait(for: [answered], timeout: 5)
    let snapshot = box.value
    XCTAssertEqual(snapshot?.authorizationStatus, .notDetermined)
    XCTAssertEqual(snapshot?.soundSetting, .notSupported)
  }
}

/// The query answers on an arbitrary queue, so the result crosses an isolation boundary.
private final class SnapshotBox: @unchecked Sendable {
  private let lock = NSLock()
  private var stored: UserNotificationSettingsSnapshot?

  var value: UserNotificationSettingsSnapshot? { lock.withLock { stored } }

  func store(_ snapshot: UserNotificationSettingsSnapshot) {
    lock.withLock { stored = snapshot }
  }
}
