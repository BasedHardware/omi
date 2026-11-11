import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// Rewind's two objects, held where they are arithmetic rather than a screenshot.
///
/// The claim that matters is that every Rewind glass panel shares the lane used by the rest of the
/// chat-first shell.
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

  // MARK: - The player shares the lane

  func testThePlayerUsesTheSharedLaneAtEveryWindowWidth() {
    for available in Self.widths {
      let player = RewindSurfaceLayout.playerWidth(for: available)
      XCTAssertEqual(
        player,
        RewindSurfaceLayout.headerWidth(for: available),
        accuracy: 0.01,
        "the player and header share one lane")
    }
  }

  func testTheTwoPanelsAlwaysShareALeadingEdge() {
    for available in Self.widths {
      XCTAssertTrue(RewindSurfaceLayout.edgesCoincide(availableWidth: available))
    }
  }

  // MARK: - Nothing here invents a number

  func testTheGapCornerAndMarginsAreTheProductsOwn() {
    XCTAssertEqual(RewindSurfaceLayout.panelGap, RewindSearchLayout.panelGap)
    XCTAssertEqual(RewindSurfaceLayout.panelGap, QueryShellLayout.panelGap)
    XCTAssertEqual(RewindSurfaceLayout.panelCornerRadius, InkGlass.cornerRadius)
    XCTAssertEqual(RewindSurfaceLayout.topGap, PageGlassLaneLayout.topGap)
    // Delegated, not mirrored. The two gaps were the same number until the shell was flushed to its
    // glass and `PageGlassLaneLayout.bottomGap` became 0 so the resize handle sits on the visible
    // panel; restating "bottom equals top" here would make Rewind hold its own opinion again, which
    // is the one thing this section forbids.
    XCTAssertEqual(RewindSurfaceLayout.bottomGap, PageGlassLaneLayout.bottomGap)
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
    XCTAssertEqual(placedPlayer.width, placedHeader.width, accuracy: 0.5)
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
