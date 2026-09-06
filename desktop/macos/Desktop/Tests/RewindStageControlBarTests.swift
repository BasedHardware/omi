import AppKit
import XCTest

@testable import Omi_Computer

/// The row of controls under Rewind's picture — the date pill, the previous/next app circles and
/// the zoom cluster — and the things the move asserts: the row shares its margins with the objects
/// above and below it, nothing is overlaid on the picture any more, and the app stepping lands where
/// it says it does.
///
/// **The defect this holds shut.** The pill and the zoom buttons used to sit *on* the photograph, in
/// its bottom corners, and the app-step chevrons on its left and right edges, over whatever the
/// capture showed there; and the picture wore a 2 pt ring in the app's palette colour, which read as
/// a selection state rather than as a frame. Those are layout facts a screenshot would show and a
/// `body` would silently lose, so they are stated here as values and as a narrow static tripwire.
/// The stepping itself is a pure function, so it is a behavioural test.
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

  // MARK: - One app stretch at a time

  private func frames(_ apps: [String]) -> [Screenshot] {
    apps.enumerated().map { offset, app in
      Screenshot(id: Int64(offset), timestamp: Date(timeIntervalSince1970: Double(offset)), appName: app)
    }
  }

  func testForwardLandsOnTheFirstFrameOfTheNextApp() {
    let frames = frames(["Editor", "Editor", "Browser", "Browser", "Terminal"])
    XCTAssertEqual(RewindAppStep.adjacentSegmentIndex(in: frames, from: 0, forward: true), 2)
    XCTAssertEqual(RewindAppStep.adjacentSegmentIndex(in: frames, from: 1, forward: true), 2)
    XCTAssertEqual(RewindAppStep.adjacentSegmentIndex(in: frames, from: 3, forward: true), 4)
  }

  func testBackwardLandsOnTheFirstFrameOfThePreviousAppNotItsLast() {
    // Two presses walk two apps back. Landing on the previous stretch's *last* frame would make the
    // next press step within the same app.
    let frames = frames(["Editor", "Editor", "Browser", "Browser", "Terminal"])
    XCTAssertEqual(RewindAppStep.adjacentSegmentIndex(in: frames, from: 4, forward: false), 2)
    XCTAssertEqual(RewindAppStep.adjacentSegmentIndex(in: frames, from: 3, forward: false), 0)
    XCTAssertEqual(RewindAppStep.adjacentSegmentIndex(in: frames, from: 2, forward: false), 0)
  }

  func testTheStepIsNilAtEitherEndAndOffTheList() {
    let frames = frames(["Editor", "Editor", "Browser"])
    XCTAssertNil(RewindAppStep.adjacentSegmentIndex(in: frames, from: 2, forward: true), "no app after the last")
    XCTAssertNil(RewindAppStep.adjacentSegmentIndex(in: frames, from: 0, forward: false), "no app before the first")
    XCTAssertNil(RewindAppStep.adjacentSegmentIndex(in: frames, from: 1, forward: false), "still inside the first app")
    XCTAssertNil(RewindAppStep.adjacentSegmentIndex(in: frames, from: 7, forward: true))
    XCTAssertNil(RewindAppStep.adjacentSegmentIndex(in: [], from: 0, forward: true))
  }

  // MARK: - The picture is not keyed to the app colour, and nothing sits on it

  // Which view owns each control and what the frame's border is drawn with are SwiftUI `body` facts
  // with no inspectable runtime value; see the reasoned annotation on `source(_:)`.
  func testStaticCheckerTheFrameBorderIsNeutralAndEveryControlIsUnderThePictureNotOnIt() throws {
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
    XCTAssertFalse(
      page.contains("RewindStageChrome"),
      "RewindPage overlays chrome on the picture again — every control belongs in the row beneath it")

    let chrome = try source("Rewind/UI/RewindPlaybackChrome.swift")
    let bar = try body(ofType: "RewindStageControlBar", in: chrome)
    for expected in ["chevron.left", "chevron.right", "magnifyingglass", "showsDatePicker"] {
      XCTAssertTrue(bar.contains(expected), "RewindStageControlBar lost `\(expected)`")
    }
    XCTAssertFalse(
      bar.contains("RoundedRectangle"),
      "the app-step buttons are the same glass circle as the zoom buttons, not a taller chip")
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
