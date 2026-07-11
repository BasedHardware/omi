import XCTest

@testable import Omi_Computer

/// BL-005 / S-14b: guards the signal-driven conversions in the floating bar so
/// they aren't silently reverted to fixed-delay `asyncAfter` timing, and pins the
/// `.asyncAfter(` call-site count under `FloatingControlBar/` to the ratchet
/// baseline (mirrors `scripts/check-async-after-ratchet.py` inside the test suite
/// that `test.sh` runs).
final class FloatingBarTimingSignalTests: XCTestCase {
  /// Keep in sync with `BASELINE` in `scripts/check-async-after-ratchet.py`.
  private static let asyncAfterBaseline = 26

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

  func testWindowActivationKeysOffWindowSignalNotFixedDelay() throws {
    let source = try floatingBarViewSource()
    XCTAssertTrue(
      source.contains("func runWhenMainAppWindowKey"),
      "window activation should route through the window-key signal helper")
    XCTAssertTrue(
      source.contains("NSWindow.didBecomeKeyNotification"),
      "the transition should key off didBecomeKey, not a fixed delay")
  }

  func testFollowUpFocusUsesViewLifecycle() throws {
    let source = try floatingBarViewSource()
    XCTAssertTrue(
      source.contains(".task {"),
      "follow-up focus should be driven by the view lifecycle (.task), not asyncAfter")
    XCTAssertTrue(
      source.contains("isFollowUpFocused = true"), "the field must still be focused on appear")
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
      genuinely required, lower/raise the baseline deliberately in both this test and \
      scripts/check-async-after-ratchet.py.
      """)
  }
}
