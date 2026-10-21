import XCTest

@testable import Omi_Computer

@MainActor
final class ScreenTaskFlagRefreshCadenceTests: XCTestCase {
  func testFirstTickAlwaysReloads() {
    XCTAssertTrue(ScreenTaskFlagRefresh.shouldReloadFlags(enabled: false, now: 0, last: nil))
  }

  func testEnabledFlagKeepsThirtySecondCadence() {
    XCTAssertTrue(ScreenTaskFlagRefresh.shouldReloadFlags(enabled: true, now: 130, last: 100))
  }

  func testDisabledFlagReloadsOnlyEveryThirtyMinutes() {
    let interval = ScreenTaskFlagRefresh.disabledReloadInterval
    XCTAssertEqual(interval, 1800)
    XCTAssertFalse(ScreenTaskFlagRefresh.shouldReloadFlags(enabled: false, now: 130, last: 100))
    XCTAssertFalse(
      ScreenTaskFlagRefresh.shouldReloadFlags(enabled: false, now: 100 + interval - 1, last: 100))
    XCTAssertTrue(ScreenTaskFlagRefresh.shouldReloadFlags(enabled: false, now: 100 + interval, last: 100))
  }
}
