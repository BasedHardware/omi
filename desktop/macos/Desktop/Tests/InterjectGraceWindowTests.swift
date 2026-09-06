import XCTest

@testable import Omi_Computer

final class InterjectGraceWindowTests: XCTestCase {
  func testDismissThenHoverReshowsBeforeExpiry() {
    let now = Date(timeIntervalSince1970: 5_000)
    var window = InterjectGraceWindow()
    window.arm(now: now)

    XCTAssertTrue(window.isArmed)
    XCTAssertTrue(window.isActive(at: now.addingTimeInterval(9.9)))
    XCTAssertTrue(window.consume(at: now.addingTimeInterval(3)))
    XCTAssertFalse(window.isArmed)
    XCTAssertFalse(window.consume(at: now.addingTimeInterval(4)), "consume is one-shot")
  }

  func testPTTStartReshowsInsideTheGraceWindow() {
    let now = Date(timeIntervalSince1970: 5_000)
    var window = InterjectGraceWindow()
    window.arm(now: now, duration: 10)
    XCTAssertTrue(window.consume(at: now.addingTimeInterval(10).addingTimeInterval(-0.01)))
  }

  func testExpiryClearsTheWindowWithoutAReshow() {
    let now = Date(timeIntervalSince1970: 5_000)
    var window = InterjectGraceWindow()
    window.arm(now: now)
    XCTAssertFalse(window.isActive(at: now.addingTimeInterval(10)))
    XCTAssertFalse(window.consume(at: now.addingTimeInterval(10)))
    XCTAssertFalse(window.isArmed)
  }

  func testClearDropsAnArmedWindow() {
    var window = InterjectGraceWindow()
    window.arm(now: Date(timeIntervalSince1970: 1))
    window.clear()
    XCTAssertFalse(window.isArmed)
    XCTAssertFalse(window.consume(at: Date(timeIntervalSince1970: 2)))
  }
}
