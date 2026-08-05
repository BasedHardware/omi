import XCTest

@testable import Omi_Computer

/// The floating bar's cursor poll is a main-queue timer that used to run unconditionally, four
/// wake-ups a second for the life of the process, on machines that had nowhere to move the bar to.
/// These state the arming rule that replaced "always".
@MainActor
final class CursorScreenTrackerTests: XCTestCase {
  func testDoesNotArmOnASingleScreen() {
    let tracker = CursorScreenTracker(screenCount: { 1 })
    tracker.start {}
    XCTAssertFalse(tracker.isTracking)
  }

  func testArmsWhenASecondScreenExists() {
    let tracker = CursorScreenTracker(screenCount: { 2 })
    tracker.start {}
    XCTAssertTrue(tracker.isTracking)
  }

  func testArmsWhenAScreenIsPluggedIn() {
    var screens = 1
    let tracker = CursorScreenTracker(screenCount: { screens })
    tracker.start {}
    XCTAssertFalse(tracker.isTracking)

    screens = 2
    tracker.sync()
    XCTAssertTrue(tracker.isTracking)
  }

  func testDisarmsWhenTheSecondScreenIsUnplugged() {
    var screens = 2
    let tracker = CursorScreenTracker(screenCount: { screens })
    tracker.start {}
    XCTAssertTrue(tracker.isTracking)

    screens = 1
    tracker.sync()
    XCTAssertFalse(tracker.isTracking)
  }

  func testResyncingWhileArmedKeepsOneTimer() async {
    let tracker = CursorScreenTracker(screenCount: { 2 })
    let counter = TickCounter()
    tracker.start { counter.bump() }
    tracker.sync()
    tracker.sync()
    XCTAssertTrue(tracker.isTracking)

    // Two stacked timers would tick at twice the rate. One ~250 ms poll fires at most twice in
    // 400 ms (the schedule starts immediately), so a third tick means a duplicate timer.
    try? await Task.sleep(for: .milliseconds(400))
    XCTAssertLessThanOrEqual(counter.count, 2)
    XCTAssertGreaterThanOrEqual(counter.count, 1)
  }
}

@MainActor
private final class TickCounter {
  private(set) var count = 0
  func bump() { count += 1 }
}
