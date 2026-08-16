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

  func testResyncingWhileArmedKeepsOneTimer() {
    let tracker = CursorScreenTracker(screenCount: { 2 })
    let counter = TickCounter()
    tracker.start { counter.bump() }
    tracker.sync()
    tracker.sync()

    // This used to sleep 400 ms and assert the tick count landed in [1, 2], inferring a duplicate
    // timer from a doubled rate. That reads a wall clock to answer a question about arming, and on
    // a loaded CI machine a ~250 ms poll's tick count in a fixed window is not reliable. Arming is
    // the fact under test, so assert it: three arm attempts, one timer.
    XCTAssertTrue(tracker.isTracking)
    XCTAssertEqual(tracker.timersArmed, 1)
  }

  func testDisarmingAndRearmingCreatesANewTimer() {
    var screens = 2
    let tracker = CursorScreenTracker(screenCount: { screens })
    tracker.start {}
    XCTAssertEqual(tracker.timersArmed, 1)

    screens = 1
    tracker.sync()
    XCTAssertFalse(tracker.isTracking)

    screens = 2
    tracker.sync()
    XCTAssertTrue(tracker.isTracking)
    XCTAssertEqual(tracker.timersArmed, 2, "re-arming after a genuine disarm must build a new timer")
  }
}

@MainActor
private final class TickCounter {
  private(set) var count = 0
  func bump() { count += 1 }
}
