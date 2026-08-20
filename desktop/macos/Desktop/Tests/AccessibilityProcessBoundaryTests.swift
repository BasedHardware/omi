import AppKit
import XCTest

@testable import Omi_Computer

/// Regression for a crash observed the moment Accessibility started working: with the Omi window
/// frontmost, the capture tick walked Omi's *own* accessibility tree, evaluated a `@MainActor`
/// SwiftUI binding on a cooperative thread, and the process took a `SIGTRAP` from
/// `_swift_task_checkIsolatedSwift`. Same-process accessibility is not IPC — it runs our own view
/// code on whichever thread asked.
final class AccessibilityProcessBoundaryTests: XCTestCase {
  func testOwnProcessIsNeverForeign() {
    let own = ProcessInfo.processInfo.processIdentifier
    XCTAssertFalse(
      AccessibilityProcessBoundary.isForeignProcess(own),
      "reading our own accessibility tree re-enters our own view graph off the main actor")
    XCTAssertFalse(AccessibilityProcessBoundary.isForeignProcess(42, ownProcessID: 42))
  }

  func testOtherProcessesAreForeign() {
    let own = ProcessInfo.processInfo.processIdentifier
    XCTAssertTrue(AccessibilityProcessBoundary.isForeignProcess(own &+ 1))
    XCTAssertTrue(AccessibilityProcessBoundary.isForeignProcess(7, ownProcessID: 42))
  }

  /// The handle extractor is the path that crashed. Asked about this very process, it must come
  /// back without having read anything — no document URL, no browser URL.
  func testLiveSnapshotDeclinesToReadThisProcess() {
    let ownName = NSRunningApplication.current.localizedName ?? "unknown"
    let snapshot = WorkHistoryHandleExtractor.liveSnapshot(
      appName: ownName,
      windowTitle: "whatever",
      expectedBundleID: Bundle.main.bundleIdentifier)
    XCTAssertNil(snapshot.documentURL, "must not introspect our own accessibility tree")
    XCTAssertNil(snapshot.browserURL, "must not introspect our own accessibility tree")
  }

  /// Losing the accessibility read must not lose the visit: the fallback handle still names it.
  func testFallbackHandleSurvivesTheRefusal() throws {
    let snapshot = WorkHistoryFrontmostSnapshot(
      appName: "Omi", windowTitle: "Settings", bundleID: Bundle.main.bundleIdentifier)
    let handles = WorkHistoryHandleExtractor.handles(from: snapshot)
    let appWindow = try XCTUnwrap(handles.first)
    XCTAssertEqual(appWindow.kind, .appWindow)
    XCTAssertFalse(appWindow.isDurable)
  }
}
