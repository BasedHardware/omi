import AppKit
import XCTest

@testable import Omi_Computer

/// The row of controls under Rewind's picture — the date pill and the zoom cluster — and the two
/// things the move asserts: the row shares its margins with the objects above and below it, and
/// nothing about the picture's own frame is keyed to the app's palette colour any more.
///
/// **The defect this holds shut.** The pill and the zoom buttons used to sit *on* the photograph, in
/// its bottom corners, over whatever the capture showed there; and the picture wore a 2 pt ring in
/// the app's palette colour, which read as a selection state rather than as a frame. Both are layout
/// facts a screenshot would show and a `body` would silently lose, so they are stated here as values
/// and as a narrow static tripwire.
final class RewindStageControlBarTests: XCTestCase {

  // MARK: - One margin down the panel

  func testTheControlRowSharesTheStagesHorizontalInset() {
    XCTAssertEqual(
      RewindStageControlBarLayout.horizontalInset, RewindStageFit.horizontalInset, accuracy: 0.001,
      "the pill's leading edge and the stage's leading edge are one line")
  }

  func testTheControlRowSitsAsFarFromTheTrackAsItDoesFromThePicture() {
    // Above the row: the stage's own vertical inset. Below it: the row's bottom gap plus the track's
    // top padding. The two must agree or the row reads as belonging to one neighbour and not the other.
    let above = RewindStageFit.verticalInset
    let below = RewindStageControlBarLayout.bottomGap + RewindTrackBar.topPadding
    XCTAssertEqual(above, below, accuracy: 0.001)
    XCTAssertGreaterThanOrEqual(RewindStageControlBarLayout.bottomGap, 0, "a negative gap overlaps the track")
  }

  func testTheControlsAreOneHeightSoTheRowHasOneBaseline() {
    XCTAssertGreaterThanOrEqual(
      RewindStageControlBarLayout.controlHeight, 28, "below 28 pt a circle button is under the click target floor")
  }

  // MARK: - The picture is not keyed to the app colour, and the pill is not on it

  // Which view owns the pill and what the frame's border is drawn with are SwiftUI `body` facts with
  // no inspectable runtime value; see the reasoned annotation on `source(_:)`.
  func testStaticCheckerTheFrameBorderIsNeutralAndThePillIsUnderThePictureNotOnIt() throws {
    let page = try source("Rewind/UI/RewindPage.swift")
    XCTAssertFalse(
      page.contains("strokeBorder(frameBorderColor"),
      "RewindPage strokes the frame in the app's palette colour again; the ring reads as a selection state")
    XCTAssertFalse(
      page.contains("RewindPalette.color(forApp"),
      "RewindPage keys the picture to the app's palette colour; the track segment already says which app it is")
    XCTAssertTrue(
      page.contains("RewindStageControlBar("),
      "RewindPage no longer places the control bar under the picture")

    let chrome = try source("Rewind/UI/RewindPlaybackChrome.swift")
    let stageChrome = try body(ofType: "RewindStageChrome", in: chrome)
    for banished in ["timestampPill", "controlCluster", "showsDatePicker", "magnifyingglass"] {
      XCTAssertFalse(
        stageChrome.contains(banished),
        "RewindStageChrome carries `\(banished)` again — the pill and zoom cluster belong under the picture, not on it")
    }
  }

  // MARK: - Helpers

  private func source(_ relativePath: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    // omi-test-quality: source-inspection -- static contract: the frame's border colour and the pill's owner are SwiftUI body facts with no runtime value
    return try String(contentsOf: url, encoding: .utf8)
  }

  /// The text from `struct <name>` to the next top-level `// MARK: -`, which is how this file is
  /// sectioned. Fails loudly if the type or the section break moves.
  private func body(ofType name: String, in source: String) throws -> Substring {
    guard let start = source.range(of: "struct \(name): View") else {
      throw XCTSkip("`struct \(name): View` not found — the type was renamed; update this test")
    }
    let rest = source[start.lowerBound...]
    guard let end = rest.range(of: "\n// MARK: -") else { return rest }
    return rest[..<end.lowerBound]
  }
}
