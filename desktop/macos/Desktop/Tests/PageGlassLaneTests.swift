import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// The panel every destination that is not Home or Rewind floats on, held where it is arithmetic
/// rather than a screenshot.
@MainActor
final class PageGlassLaneTests: XCTestCase {

  // MARK: - Which destinations already have glass

  /// Home and Rewind build their own panels. Wrapping them again does not stack two materials — a
  /// nested `.behindWindow` surface takes a *second* copy of the desktop and doubles the scrim — so a
  /// double-wrapped page reads visibly muddier than the pages around it.
  func testHomeAndRewindKeepTheirOwnPanelsAndEveryOtherDestinationIsGivenOne() {
    XCTAssertTrue(
      PageGlassLanePolicy.ownsItsPanels(selectedIndex: SidebarNavItem.dashboard.rawValue))
    XCTAssertTrue(PageGlassLanePolicy.ownsItsPanels(selectedIndex: SidebarNavItem.rewind.rawValue))

    for item in SidebarNavItem.allCases where item != .dashboard && item != .rewind {
      XCTAssertFalse(
        PageGlassLanePolicy.ownsItsPanels(selectedIndex: item.rawValue),
        "\(item.title) has no glass of its own and must be given the lane's")
    }
  }

  /// The router sends every unrecognised index to Home through its `default:` branch. An index the
  /// nav enum does not carry must therefore resolve to Home here too, or those routes wrap Home's
  /// two panels inside a third one.
  func testAnUnrecognisedIndexFollowsTheRouterBackToHome() {
    for unknown in [2, 11, 13, -1, Int.max] {
      XCTAssertNil(SidebarNavItem(rawValue: unknown), "fixture \(unknown) must not be a real route")
      XCTAssertTrue(
        PageGlassLanePolicy.ownsItsPanels(selectedIndex: unknown),
        "an unknown index renders Home, which already owns its panels")
    }
  }

  // MARK: - The geometry is Home's

  /// The panel takes the top bar's own lane — the same call Home makes — so a page and the
  /// navigation above it share a leading edge and nothing shifts sideways on navigation.
  func testThePanelTakesTheSameLaneAsHomeAtEveryWindowWidth() {
    for available in [DesktopWindowLayoutPolicy.width, 900, 1_280, 1_920, 3_440] as [CGFloat] {
      XCTAssertEqual(
        PageGlassLaneLayout.laneWidth(for: available),
        QueryShellLayout.laneWidth(for: available),
        accuracy: 0.01,
        "the lane is delegated to the top bar's, never restated")
    }
  }

  /// One corner for every panel in the product. A page cut to a different radius than the query bar
  /// above it reads as two products.
  func testThePanelIsCutToTheOneSharedCorner() {
    XCTAssertEqual(PageGlassLaneLayout.cornerRadius, InkGlass.cornerRadius)
    XCTAssertEqual(PageGlassLaneLayout.cornerRadius, QueryShellLayout.panelCornerRadius)
    XCTAssertEqual(PageGlassLaneLayout.cornerRadius, RewindSearchLayout.panelCornerRadius)
  }

  /// The panel opens at the same distance under the top bar as Home's query bar does, and closes the
  /// same distance above the window's bottom edge.
  func testThePanelKeepsHomesGapAboveItAndTheSameMarginBelow() {
    XCTAssertEqual(PageGlassLaneLayout.topGap, OmiSpacing.sm)
    XCTAssertEqual(PageGlassLaneLayout.bottomGap, PageGlassLaneLayout.topGap)
  }

  // MARK: - What the mounted view actually does

  /// The claim worth holding is geometric, so it is asserted against a real mounted view rather
  /// than against the constants twice: a destination without its own glass is placed in the lane,
  /// centred, and inset from both ends by the gap.
  func testAWrappedDestinationIsPlacedInTheLaneWithTheGapAboveAndBelowIt() {
    let size = CGSize(width: 1_400, height: 800)
    let recorder = PageGlassLaneFrameRecorder()
    let host = NSHostingView(
      rootView: PageGlassLane(selectedIndex: SidebarNavItem.tasks.rawValue) {
        PageGlassLaneProbe(recorder: recorder) { Color.clear }
      }
      .frame(width: size.width, height: size.height)
    )
    host.frame = NSRect(origin: .zero, size: size)
    host.layoutSubtreeIfNeeded()

    guard let placed = recorder.frame else {
      return XCTFail("expected the wrapped destination to be placed")
    }
    let lane = PageGlassLaneLayout.laneWidth(for: size.width)
    XCTAssertEqual(placed.width, lane, accuracy: 0.5)
    XCTAssertEqual(
      placed.height,
      size.height - PageGlassLaneLayout.topGap - PageGlassLaneLayout.bottomGap,
      accuracy: 0.5,
      "one tall panel: the page fills the window and scrolls inside itself")
  }

  /// **The desktop survives on all four sides of the panel, at every window size.**
  ///
  /// This is the claim the two cases around it exist to serve, and the one they cannot make. Both
  /// assert the panel *matches* `laneWidth` and the gaps — which stays true if `contentLaneWidth` is
  /// ever changed to return the whole window, or if the gaps go to zero. Either change turns the
  /// lane back into a full-bleed sheet of glass behind the UI, renders identically to the window
  /// ground `ShellWindowChrome` deleted, and logs nothing.
  ///
  /// Measured off a real layout pass rather than recomputed: the recorded frame is in the hosting
  /// view's own coordinates, so the four margins are the wallpaper the user actually keeps.
  func testTheLanesGlassNeverReachesAnyEdgeOfTheWindow() {
    let sizes: [CGSize] = [
      CGSize(width: DesktopWindowLayoutPolicy.width, height: DesktopWindowLayoutPolicy.height),
      CGSize(width: 900, height: 600),
      CGSize(width: 1_280, height: 800),
      CGSize(width: 3_440, height: 1_440),
    ]

    for size in sizes {
      let recorder = PageGlassLaneFrameRecorder()
      let host = NSHostingView(
        rootView: PageGlassLane(selectedIndex: SidebarNavItem.tasks.rawValue) {
          PageGlassLaneProbe(recorder: recorder) { Color.clear }
        }
        .frame(width: size.width, height: size.height)
      )
      host.frame = NSRect(origin: .zero, size: size)
      host.layoutSubtreeIfNeeded()

      guard let placed = recorder.frame else {
        return XCTFail("expected the wrapped destination to be placed at \(size)")
      }

      let leading = placed.minX
      let trailing = size.width - placed.maxX
      let top = placed.minY
      let bottom = size.height - placed.maxY

      for (edge, margin) in [("leading", leading), ("trailing", trailing), ("top", top), ("bottom", bottom)] {
        XCTAssertGreaterThan(
          margin, 0,
          "at \(size) the panel reaches the \(edge) edge: that is a ground spanning the window, not a "
            + "panel floating on the desktop")
      }
      // The horizontal margin is the page's own, never smaller — a panel one point inside the frame
      // is a full-bleed sheet with a rounding error, not a floating object.
      XCTAssertGreaterThanOrEqual(leading, ChatComposerLayout.pageMargin - 0.5)
      XCTAssertGreaterThanOrEqual(trailing, ChatComposerLayout.pageMargin - 0.5)
      // …and it is centred, so neither side is the one that got the desktop.
      XCTAssertEqual(leading, trailing, accuracy: 0.5, "the panel drifted off the window's axis")
    }
  }

  /// …and a destination that already has glass is handed through untouched, at the full size it was
  /// given. Home positions its own panels inside that space.
  func testADestinationThatOwnsItsPanelsIsHandedTheWholeSurface() {
    let size = CGSize(width: 1_400, height: 800)
    let recorder = PageGlassLaneFrameRecorder()
    let host = NSHostingView(
      rootView: PageGlassLane(selectedIndex: SidebarNavItem.dashboard.rawValue) {
        PageGlassLaneProbe(recorder: recorder) { Color.clear }
      }
      .frame(width: size.width, height: size.height)
    )
    host.frame = NSRect(origin: .zero, size: size)
    host.layoutSubtreeIfNeeded()

    guard let placed = recorder.frame else {
      return XCTFail("expected the pass-through destination to be placed")
    }
    XCTAssertEqual(placed.width, size.width, accuracy: 0.5)
    XCTAssertEqual(placed.height, size.height, accuracy: 0.5)
  }
}

/// Holds the one frame the probe places, so the assertion reads a real layout pass rather than a
/// recomputation of the same arithmetic under test.
private final class PageGlassLaneFrameRecorder: @unchecked Sendable {
  private(set) var frame: CGRect?

  func record(_ frame: CGRect) {
    self.frame = frame
  }
}

private struct PageGlassLaneProbe<Content: View>: View {
  let recorder: PageGlassLaneFrameRecorder
  @ViewBuilder var content: () -> Content

  var body: some View {
    PageGlassLaneProbeLayout(recorder: recorder) { content() }
  }
}

private struct PageGlassLaneProbeLayout: Layout {
  let recorder: PageGlassLaneFrameRecorder

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
