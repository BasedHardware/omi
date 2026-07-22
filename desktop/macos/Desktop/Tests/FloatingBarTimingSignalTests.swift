import XCTest

@testable import Omi_Computer

/// Pins the `.asyncAfter(` call-site count under `FloatingControlBar/` to the
/// SwiftLint `omi_floating_control_bar_async_after` custom rule baseline (in
/// `Desktop/.swiftlint.yml`, enforced by the down-only baseline guard).
///
/// Window-key signal helpers (`runWhenMainAppWindowKey` /
/// `didBecomeKeyNotification`) were removed with idle-notch simplification
/// (#10309); do not reintroduce a source-string tripwire for that retired path.
final class FloatingBarTimingSignalTests: XCTestCase {
  /// Keep in sync with the SwiftLint baseline count for omi_floating_control_bar_async_after.
  private static let asyncAfterBaseline = 22

  private func floatingControlBarDir() -> URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests/
      .deletingLastPathComponent()  // Desktop/
      .appendingPathComponent("Sources/FloatingControlBar")
  }

  /// Anti-regression: no new fixed-delay `asyncAfter` may be added under
  /// `FloatingControlBar/` above the pinned baseline. Recurses the directory the
  /// same way the Python ratchet does; comment mentions of the word are excluded
  /// because the match requires the leading dot and open paren.
  // omi-test-quality: source-inspection -- static contract: asyncAfter call-site
  // count under FloatingControlBar/ is a down-only ratchet paired with SwiftLint
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
