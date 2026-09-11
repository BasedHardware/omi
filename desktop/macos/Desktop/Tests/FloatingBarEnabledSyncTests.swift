import XCTest

@testable import Omi_Computer

/// The notch's Hide control and the Settings "Show floating bar" switch write one preference. The
/// switch cannot poll it, so the preference announces its own changes and the switch re-reads.
final class FloatingBarEnabledSyncTests: XCTestCase {
  /// Posts arrive synchronously on the posting thread; the box exists only so the observer closure
  /// has no captured `var`.
  private final class AnnouncementCounter: @unchecked Sendable {
    private(set) var count = 0
    func increment() { count += 1 }
  }

  @MainActor
  func testChangingTheEnabledPreferenceAnnouncesItselfOncePerRealChange() {
    let manager = FloatingControlBarManager.shared
    let previous = manager.isEnabled
    defer { manager.isEnabled = previous }

    let announcements = AnnouncementCounter()
    let observer = NotificationCenter.default.addObserver(
      forName: .floatingBarEnabledDidChange, object: nil, queue: nil
    ) { _ in announcements.increment() }
    defer { NotificationCenter.default.removeObserver(observer) }

    manager.isEnabled = true
    let afterArming = announcements.count

    manager.isEnabled = false
    XCTAssertEqual(announcements.count, afterArming + 1, "hiding is a change the Settings switch must hear")
    XCTAssertFalse(manager.isEnabled)

    manager.isEnabled = false
    XCTAssertEqual(announcements.count, afterArming + 1, "re-writing the same value is not a change")

    manager.isEnabled = true
    XCTAssertEqual(announcements.count, afterArming + 2, "a Push-to-Talk reveal flips it back and must be heard too")
  }
}
