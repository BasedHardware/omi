import XCTest

@testable import Omi_Computer

/// BL-005 / S-14b: guards the signal-driven conversions in the floating bar so
/// they aren't silently reverted to fixed-delay `asyncAfter` timing, and pins the
/// `.asyncAfter(` call-site count under `FloatingControlBar/` to the SwiftLint
/// `omi_floating_control_bar_async_after` custom rule baseline (in
/// `Desktop/.swiftlint.yml`, enforced by the down-only baseline guard).
final class FloatingBarTimingSignalTests: XCTestCase {
  /// Keep in sync with the SwiftLint baseline count for omi_floating_control_bar_async_after.
  private static let asyncAfterBaseline = 22

  private func floatingControlBarDir() -> URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests/
      .deletingLastPathComponent()  // Desktop/
      .appendingPathComponent("Sources/FloatingControlBar")
  }

  private func floatingBarViewSource() throws -> String {
    try String(
      contentsOf: floatingControlBarDir().appendingPathComponent("FloatingControlBarView.swift"))
  }

  func testIdleNotchWindowActivationDelegatesToCanonicalAuthorityNotFixedDelay() throws {
    // BL-005: the floating bar must not re-open the main window on a fixed-delay
    // `asyncAfter` guess. Idle-notch activation delegates to the single main-chat
    // window authority (`AppDelegate.openMainAppChat`) via NotchIdleTapRoute — it
    // does not run its own timed window activation. (The earlier
    // `runWhenMainAppWindowKey` / `didBecomeKey` helper was folded into that
    // canonical authority in a4fac7b366; this guard follows the logic there. The
    // request/consume landing signal is covered behaviorally below.)
    let bar = try floatingBarViewSource()
    XCTAssertTrue(
      bar.contains("NotchIdleTapRoute"),
      "idle-notch activation should route through the single tap-route authority")
    XCTAssertTrue(
      bar.contains("openMainAppChat"),
      "the floating bar should delegate window activation to the canonical main-chat "
        + "authority, not run its own timed activation")
  }

  /// The canonical chat-landing keys off a one-shot request that survives window
  /// creation (consumed when the window becomes visible), not a fixed delay.
  /// Exercised behaviorally so it doesn't depend on implementation strings.
  @MainActor
  func testMainChatNavigationRequestIsOneShotSurvivingWindowCreation() {
    let store = MainChatNavigationRequestStore.shared
    _ = store.consume()  // clear any prior state
    XCTAssertFalse(store.isPending)
    store.request()
    XCTAssertTrue(store.isPending, "a raised request must stay pending until the window consumes it")
    XCTAssertTrue(store.consume(), "the window consumes the pending request on mount")
    XCTAssertFalse(store.consume(), "the request is one-shot — a second consume yields nothing")
  }

  /// Anti-regression: no new fixed-delay `asyncAfter` may be added under
  /// `FloatingControlBar/` above the pinned baseline. Recurses the directory the
  /// same way the Python ratchet does; comment mentions of the word are excluded
  /// because the match requires the leading dot and open paren.
  func testAsyncAfterCallSitesAtOrBelowBaseline() throws {
    let fm = FileManager.default
    let dir = floatingControlBarDir()
    var count = 0
    let enumerator = fm.enumerator(at: dir, includingPropertiesForKeys: nil)
    while let url = enumerator?.nextObject() as? URL {
      guard url.pathExtension == "swift" else { continue }
      let source = try String(contentsOf: url)
      count += source.components(separatedBy: ".asyncAfter(").count - 1
    }
    XCTAssertLessThanOrEqual(
      count, Self.asyncAfterBaseline,
      """
      new fixed-delay .asyncAfter( added under FloatingControlBar/ \
      (count \(count) > baseline \(Self.asyncAfterBaseline)). Key the transition off a \
      signal (window didBecomeKey, view lifecycle, state change) or, if the delay is \
      genuinely required, lower/raise the baseline in both this test and \
      the SwiftLint baseline (.swiftlint-baseline.json).
      """)
  }
}
