import XCTest

@testable import Omi_Computer

final class InterjectDisplayTimerTests: XCTestCase {
  func testPauseFreezesRemainingAndResumeContinues() {
    let start = Date(timeIntervalSince1970: 1_000)
    var timer = InterjectDisplayTimer.start(duration: 10, now: start)

    XCTAssertEqual(timer.remaining(at: start.addingTimeInterval(3)), 7)
    XCTAssertFalse(timer.isPaused)

    timer.pause(now: start.addingTimeInterval(3))
    XCTAssertTrue(timer.isPaused)
    XCTAssertEqual(timer.remaining(at: start.addingTimeInterval(8)), 7, "time while paused does not burn")

    timer.resume(now: start.addingTimeInterval(8))
    XCTAssertFalse(timer.isPaused)
    XCTAssertEqual(timer.remaining(at: start.addingTimeInterval(10)), 5)
    XCTAssertFalse(timer.isExpired(at: start.addingTimeInterval(10)))
    XCTAssertTrue(timer.isExpired(at: start.addingTimeInterval(15)))
  }

  func testPausedTimerIsNeverExpired() {
    let start = Date(timeIntervalSince1970: 1_000)
    var timer = InterjectDisplayTimer.start(duration: 2, now: start)
    timer.pause(now: start.addingTimeInterval(1))
    XCTAssertFalse(timer.isExpired(at: start.addingTimeInterval(60)))
  }

  func testDoublePauseOrResumeIsIdempotent() {
    let start = Date(timeIntervalSince1970: 1_000)
    var timer = InterjectDisplayTimer.start(duration: 6, now: start)
    timer.pause(now: start.addingTimeInterval(2))
    timer.pause(now: start.addingTimeInterval(4))
    XCTAssertEqual(timer.remaining(at: start.addingTimeInterval(4)), 4)

    timer.resume(now: start.addingTimeInterval(5))
    timer.resume(now: start.addingTimeInterval(6))
    XCTAssertEqual(timer.remaining(at: start.addingTimeInterval(7)), 2)
  }
}
