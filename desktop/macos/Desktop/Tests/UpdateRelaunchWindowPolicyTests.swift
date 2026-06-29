import Foundation
import XCTest

@testable import Omi_Computer

final class UpdateRelaunchWindowPolicyTests: XCTestCase {
  func testRestoresWhenMainWindowIsCurrentlyForeground() {
    XCTAssertTrue(
      UpdateRelaunchWindowPolicy.shouldRestoreMainWindow(
        appIsActive: true,
        frontmostBundleMatches: true,
        mainWindowIsKey: true,
        lastMainWindowForegroundAt: nil
      ))
  }

  func testSuppressesWhenAppWasNotRecentlyForeground() {
    let now = Date()

    XCTAssertFalse(
      UpdateRelaunchWindowPolicy.shouldRestoreMainWindow(
        appIsActive: false,
        frontmostBundleMatches: false,
        mainWindowIsKey: false,
        lastMainWindowForegroundAt: now.addingTimeInterval(-31),
        now: now,
        foregroundGraceInterval: 30
      ))
  }

  func testRestoresWhenSparkleTemporarilyTookFocusFromForegroundWindow() {
    let now = Date()

    XCTAssertTrue(
      UpdateRelaunchWindowPolicy.shouldRestoreMainWindow(
        appIsActive: false,
        frontmostBundleMatches: false,
        mainWindowIsKey: false,
        lastMainWindowForegroundAt: now.addingTimeInterval(-5),
        now: now,
        foregroundGraceInterval: 30
      ))
  }

  func testPendingRelaunchMarkerIsConsumedOnce() {
    let suiteName = "UpdateRelaunchWindowPolicyTests-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defer { defaults.removePersistentDomain(forName: suiteName) }

    UpdateRelaunchWindowPolicy.markPendingRelaunch(restoreMainWindow: false, defaults: defaults)

    XCTAssertEqual(
      UpdateRelaunchWindowPolicy.consumePendingRelaunch(defaults: defaults),
      false
    )
    XCTAssertNil(UpdateRelaunchWindowPolicy.consumePendingRelaunch(defaults: defaults))
  }
}
