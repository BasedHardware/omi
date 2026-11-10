import XCTest

@testable import Omi_Computer

@MainActor
final class ScreenTaskFlagRefreshCadenceTests: XCTestCase {
  func testFirstTickAlwaysReloads() {
    XCTAssertTrue(ScreenTaskFlagRefresh.shouldReloadFlags(now: 0, last: nil))
  }

  func testFlagReloadsOnlyEveryThirtyMinutes() {
    let interval = ScreenTaskFlagRefresh.flagReloadInterval
    XCTAssertEqual(interval, 1800)
    XCTAssertFalse(ScreenTaskFlagRefresh.shouldReloadFlags(now: 130, last: 100))
    XCTAssertFalse(ScreenTaskFlagRefresh.shouldReloadFlags(now: 100 + interval - 1, last: 100))
    XCTAssertTrue(ScreenTaskFlagRefresh.shouldReloadFlags(now: 100 + interval, last: 100))
  }

  func testAnalyticsOptOutWithholdsCachedFlagRenewal() {
    XCTAssertTrue(ScreenTaskFlagRefresh.renewsFlagLease(analyticsOptedOut: false))
    XCTAssertFalse(ScreenTaskFlagRefresh.renewsFlagLease(analyticsOptedOut: true))
  }
}
