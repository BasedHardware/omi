import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// Rewind's two objects, held where they are arithmetic rather than a screenshot.
///
/// The claim that matters is a pair of widths that deliberately disagree: the header is on the lane
/// every other route's panel takes, and the player is **not**, because the track under it maps a
/// pointer's x to a capture timestamp and the lane's 900 pt reading clamp would throw away more than
/// half of that resolution on a wide window.
@MainActor
final class RewindSurfaceLayoutTests: XCTestCase {

  /// Window widths worth checking: below the clamp, at it, and well past it.
  private static let widths: [CGFloat] = [720, 900, 932, 1_100, 1_400, 1_920, 3_440]

  // MARK: - The header is on everyone else's lane

  func testTheHeaderTakesTheSameLaneAsTheTopBarAndEveryOtherRoutesPanel() {
    for available in Self.widths {
      XCTAssertEqual(
        RewindSurfaceLayout.headerWidth(for: available),
        TopNavigationLayoutMetrics.contentLaneWidth(for: available),
        accuracy: 0.01,
        "the lane is delegated to the top bar's, never restated")
      XCTAssertEqual(
        RewindSurfaceLayout.headerWidth(for: available),
        PageGlassLaneLayout.laneWidth(for: available),
        accuracy: 0.01,
        "Rewind's header and a wrapped destination's panel share a leading edge")
      XCTAssertEqual(
        RewindSurfaceLayout.headerWidth(for: available),
        QueryShellLayout.laneWidth(for: available),
        accuracy: 0.01,
        "…and so does Home's query bar")
    }
  }

  // MARK: - The player is not

  /// The player keeps the page's margin and drops the *reading* clamp. Below the clamp the two are
  /// one number and the panels line up exactly; past it the player keeps the width the ruler needs.
  func testThePlayerKeepsThePageMarginAndDropsTheReadingClamp() {
    for available in Self.widths {
      let player = RewindSurfaceLayout.playerWidth(for: available)
      XCTAssertEqual(
        player,
        available - ChatComposerLayout.pageMargin * 2,
        accuracy: 0.01,
        "the player is the page's own margin — the same one the lane is measured from")
      XCTAssertGreaterThanOrEqual(
        player, RewindSurfaceLayout.headerWidth(for: available),
        "the scrubber may never be narrower than the bar above it")
    }
  }

  func testTheTwoPanelsShareALeadingEdgeUntilTheReadingClampBinds() {
    let clampBinds = ChatComposerLayout.contentLaneMaxWidth + ChatComposerLayout.pageMargin * 2

    XCTAssertTrue(RewindSurfaceLayout.edgesCoincide(availableWidth: clampBinds - 40))
    XCTAssertTrue(RewindSurfaceLayout.edgesCoincide(availableWidth: clampBinds))
    XCTAssertFalse(
      RewindSurfaceLayout.edgesCoincide(availableWidth: clampBinds + 40),
      "past the clamp the header stays a readable bar and the player takes the room")
  }

  /// The number the choice is actually about. On the window sizes this app is used at, putting the
  /// track on the reading lane would cost it most of its horizontal resolution — and the track
  /// resolves a scrub by mapping x onto the day, so those points are seconds the user cannot hit.
  func testTheReadingLaneWouldCostTheTrackMostOfItsScrubResolution() {
    for available in [1_920, 3_440] as [CGFloat] {
      let lane = RewindSurfaceLayout.headerWidth(for: available)
      let player = RewindSurfaceLayout.playerWidth(for: available)
      XCTAssertGreaterThan(
        player, lane * 1.5,
        "at \(available) pt the lane keeps under two thirds of the track's width")
    }
  }

  // MARK: - Nothing here invents a number

  func testTheGapCornerAndMarginsAreTheProductsOwn() {
    XCTAssertEqual(RewindSurfaceLayout.panelGap, RewindSearchLayout.panelGap)
    XCTAssertEqual(RewindSurfaceLayout.panelGap, QueryShellLayout.panelGap)
    XCTAssertEqual(RewindSurfaceLayout.panelCornerRadius, InkGlass.cornerRadius)
    XCTAssertEqual(RewindSurfaceLayout.topGap, PageGlassLaneLayout.topGap)
    XCTAssertEqual(RewindSurfaceLayout.bottomGap, RewindSurfaceLayout.topGap)
  }

  // MARK: - What the mounted panels actually do

  /// Asserted against a real layout pass rather than against the constants twice: the header is
  /// placed at exactly the lane, and the player at exactly the page width with the gap above it.
  func testTheMountedPanelsArePlacedAtTheWidthsTheyWereGiven() {
    let size = CGSize(width: 1_400, height: 800)
    let header = RewindSurfaceLayout.headerWidth(for: size.width)
    let player = RewindSurfaceLayout.playerWidth(for: size.width)
    let headerFrame = RewindSurfaceProbeRecorder()
    let playerFrame = RewindSurfaceProbeRecorder()

    // A header is as tall as its bar; the player takes everything left. 60 pt stands in for
    // `RewindSearchLayout.barHeight` plus the bar's own padding.
    let headerHeight: CGFloat = 60
    let host = NSHostingView(
      rootView: VStack(spacing: 0) {
        RewindSurfaceProbe(recorder: headerFrame)
          .frame(height: headerHeight)
          .rewindHeaderPanel(width: header)
        RewindSurfaceProbe(recorder: playerFrame).rewindPlayerPanel(width: player)
      }
      .frame(width: size.width, height: size.height)
    )
    host.frame = NSRect(origin: .zero, size: size)
    host.layoutSubtreeIfNeeded()

    guard let placedHeader = headerFrame.frame, let placedPlayer = playerFrame.frame else {
      return XCTFail("expected both panels to be placed")
    }
    XCTAssertEqual(placedHeader.width, header, accuracy: 0.5)
    XCTAssertEqual(placedPlayer.width, player, accuracy: 0.5)
    XCTAssertGreaterThan(
      placedPlayer.width, placedHeader.width,
      "at 1,400 pt the lane clamps and the player does not")
    XCTAssertEqual(placedHeader.height, headerHeight, accuracy: 0.5)
    XCTAssertEqual(
      placedPlayer.height,
      size.height - headerHeight - RewindSurfaceLayout.panelGap,
      accuracy: 0.5,
      "the player fills what the header leaves, less the gap that keeps them two objects")
  }
}

/// Holds the one frame a probe is placed at, so the assertion reads a real layout pass rather than a
/// recomputation of the arithmetic under test.
private final class RewindSurfaceProbeRecorder: @unchecked Sendable {
  private(set) var frame: CGRect?

  func record(_ frame: CGRect) {
    self.frame = frame
  }
}

private struct RewindSurfaceProbe: View {
  let recorder: RewindSurfaceProbeRecorder

  var body: some View {
    RewindSurfaceProbeLayout(recorder: recorder) { Color.clear }
  }
}

private struct RewindSurfaceProbeLayout: Layout {
  let recorder: RewindSurfaceProbeRecorder

  func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
    CGSize(width: proposal.width ?? 0, height: proposal.height ?? 0)
  }

  func placeSubviews(
    in bounds: CGRect,
    proposal: ProposedViewSize,
    subviews: Subviews,
    cache: inout ()
  ) {
    recorder.record(bounds)
    for subview in subviews {
      subview.place(at: bounds.origin, proposal: ProposedViewSize(bounds.size))
    }
  }
}
