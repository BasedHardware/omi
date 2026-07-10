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

    let startedAt = Date(timeIntervalSince1970: 1_700_000_000)
    let attempt = UpdateRelaunchWindowPolicy.markPendingRelaunch(
      restoreMainWindow: false,
      sourceVersion: "0.12.0",
      sourceBuild: "12000",
      targetVersion: "0.12.64",
      targetBuild: "12064",
      channel: "beta",
      attemptID: "attempt-123",
      startedAt: startedAt,
      defaults: defaults
    )

    XCTAssertEqual(attempt.id, "attempt-123")
    XCTAssertEqual(attempt.targetBuild, "12064")
    let pending = UpdateRelaunchWindowPolicy.consumePendingRelaunch(defaults: defaults)
    XCTAssertEqual(pending?.restoreMainWindow, false)
    XCTAssertEqual(pending?.attempt, attempt)
    XCTAssertNil(UpdateRelaunchWindowPolicy.consumePendingRelaunch(defaults: defaults))
  }
}
