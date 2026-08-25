import XCTest

@testable import Omi_Computer

/// The capture tick's special-mode gate, stated over synthetic `CGWindowListCopyWindowInfo`
/// snapshots. These rules used to live on `@MainActor` inside `ProactiveAssistantsPlugin` with a
/// live window server as their only input, so they could not be asserted at all; the reason they
/// moved is that the window-server read was blocking the main thread for longer than a frame once
/// a second, and moving it must not change a single decision.
final class ProactiveCaptureSystemProbeTests: XCTestCase {
  private func window(owner: String, name: String? = nil, size: CGSize? = nil) -> [String: Any] {
    var entry: [String: Any] = [kCGWindowOwnerName as String: owner]
    if let name { entry[kCGWindowName as String] = name }
    if let size {
      entry[kCGWindowBounds as String] = ["Width": size.width, "Height": size.height]
    }
    return entry
  }

  func testDockFrontmostIsSpecialModeWhateverIsOnScreen() {
    XCTAssertEqual(
      ProactiveCaptureSystemProbeReader.specialSystemMode(windowList: [], dockIsFrontmost: true),
      .dockFrontmost
    )
  }

  func testLargeUnnamedDockWindowIsMissionControl() {
    let list = [window(owner: "Dock", size: CGSize(width: 1440, height: 900))]
    XCTAssertEqual(
      ProactiveCaptureSystemProbeReader.specialSystemMode(
        windowList: list, dockIsFrontmost: false),
      .dockOverlay(width: 1440, height: 900)
    )
  }

  func testSmallUnnamedDockWindowIsNotMissionControl() {
    // The Dock's own chrome. Treating it as Mission Control would stop capture permanently.
    let list = [window(owner: "Dock", size: CGSize(width: 200, height: 64))]
    XCTAssertNil(
      ProactiveCaptureSystemProbeReader.specialSystemMode(windowList: list, dockIsFrontmost: false)
    )
  }

  func testNamedDockWindowIsNotMissionControl() {
    let list = [window(owner: "Dock", name: "Dock", size: CGSize(width: 1440, height: 900))]
    XCTAssertNil(
      ProactiveCaptureSystemProbeReader.specialSystemMode(windowList: list, dockIsFrontmost: false)
    )
  }

  func testNotificationCenterIsSpecialMode() {
    let list = [window(owner: "NotificationCenter")]
    XCTAssertEqual(
      ProactiveCaptureSystemProbeReader.specialSystemMode(
        windowList: list, dockIsFrontmost: false),
      .notificationCenter
    )
  }

  func testOrdinaryDesktopIsNotSpecialMode() {
    let list = [
      window(owner: "Safari", name: "Omi", size: CGSize(width: 1200, height: 800)),
      window(owner: "Finder", name: "Downloads", size: CGSize(width: 800, height: 600)),
    ]
    XCTAssertNil(
      ProactiveCaptureSystemProbeReader.specialSystemMode(windowList: list, dockIsFrontmost: false)
    )
  }

  func testWindowWithoutOwnerNameIsSkippedRatherThanFatal() {
    let list: [[String: Any]] = [[:], [kCGWindowOwnerName as String: "NotificationCenter"]]
    XCTAssertEqual(
      ProactiveCaptureSystemProbeReader.specialSystemMode(
        windowList: list, dockIsFrontmost: false),
      .notificationCenter
    )
  }
}
