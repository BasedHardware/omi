import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// The panel every destination that is not Home or Rewind floats on, held where it is arithmetic
/// rather than a screenshot.
///
/// This file is the guard for one defect class: **nothing in the shell may paint at window scale.**
/// The window has no ground and no visible extent (`ShellWindowChrome`), so anything drawn edge to
/// edge is a hard-edged rectangle stamped on the user's wallpaper. `PageGlassLaneTests` holds it for
/// the page panel; `ShellModalScrimTests` at the foot of this file holds it for the modal dim and for
/// the confirmation drawn on it, off the same measurement rather than a second harness.
///
/// The class has a second mechanism, so there is a third guard here. A dim is a *fill*; a system
/// focus effect is a *stroke*, drawn by AppKit around whatever holds keyboard focus. Around a page-
/// scale container that is a 1 pt accent rectangle on the window's edges, which is the same wallpaper
/// rectangle in outline — `ShellPageKeyboardTargetTests`.
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

// MARK: - The modal dim

/// **A modal dim may darken a surface. It may not darken the window.**
///
/// The same claim as `testTheLanesGlassNeverReachesAnyEdgeOfTheWindow`, one layer up, and it is held
/// the same way — off a real render at four window sizes rather than off the arithmetic under test.
/// It is measured on the **pixels** rather than on a placed frame, because the thing that went wrong
/// is not where a view was laid out: `Color.black.opacity(0.3).ignoresSafeArea()` is a paint, and a
/// dim that is inset in layout but bleeds in the render is exactly the bug read backwards.
///
/// Both directions are held. A dim that reaches the window's edge fails, and so does a dim that stops
/// painting altogether — deleting every scrim would trade this visual bug for a usability one, so the
/// guard has to be able to tell "bounded" from "gone".
@MainActor
final class ShellModalScrimTests: XCTestCase {

  private static let windowSizes: [CGSize] = [
    CGSize(width: DesktopWindowLayoutPolicy.width, height: DesktopWindowLayoutPolicy.height),
    CGSize(width: 900, height: 600),
    CGSize(width: 1_280, height: 800),
    CGSize(width: 3_440, height: 1_440),
  ]

  /// The dim mounted over the whole shell, and the dim mounted in the content area under the top bar,
  /// both keep desktop on all four sides at every window size.
  func testTheDimNeverPaintsToAnyEdgeOfTheWindow() throws {
    for bounds in [ShellModalScrimBounds.wholeShell, .contentArea] {
      for size in Self.windowSizes {
        let painted = try XCTUnwrap(
          PaintedExtent.of(ShellModalScrim().shellModalScrimBounds(bounds), in: size),
          "\(bounds) at \(size) painted nothing — a modal with no dim does not read as modal")

        for (edge, margin) in [
          ("leading", painted.minX),
          ("trailing", size.width - painted.maxX),
          ("top", painted.minY),
          ("bottom", size.height - painted.maxY),
        ] {
          XCTAssertGreaterThan(
            margin, 0,
            "\(bounds) at \(size) painted to the \(edge) edge: that is a dark rectangle on the "
              + "user's wallpaper, not a dimmed app")
        }
      }
    }
  }

  /// A dim mounted inside a page is the panel's own extent — **exactly**, not a smaller box floating
  /// inside it and not one point more.
  ///
  /// This is the case that must *not* be lane-clamped a second time: a page riding on
  /// `PageGlassLane` is already the lane, so clamping again would leave an undimmed 24 pt border of
  /// glass and the modal would read as sitting under the page. That the panel itself keeps desktop on
  /// all four sides is `testTheLanesGlassNeverReachesAnyEdgeOfTheWindow` above; the two compose into
  /// the window-scale claim, and neither is provable from the other.
  func testAPagesOwnDimFillsThePanelItSitsOnAndNoMore() throws {
    for size in Self.windowSizes {
      let host = CGSize(
        width: PageGlassLaneLayout.laneWidth(for: size.width),
        height: size.height - PageGlassLaneLayout.topGap - PageGlassLaneLayout.bottomGap)
      let painted = try XCTUnwrap(
        PaintedExtent.of(ShellModalScrim().shellModalScrimBounds(.ownSurface), in: host),
        "no dim painted in a \(host) panel")

      XCTAssertEqual(painted.minX, 0, accuracy: 0.5, "the panel keeps an undimmed leading border")
      XCTAssertEqual(painted.minY, 0, accuracy: 0.5, "the panel keeps an undimmed top border")
      XCTAssertEqual(painted.width, host.width, accuracy: 1.5)
      XCTAssertEqual(painted.height, host.height, accuracy: 1.5)
    }
  }

  /// **The surface tells the dim what it is, and no call site chooses.**
  ///
  /// The wiring that replaces a `bounds:` argument at every modal in the app, so it is the thing most
  /// worth holding: a page added tomorrow inherits the right bounds by being a page, and Home and
  /// Rewind — handed the whole content area rather than a panel — cannot silently inherit a page's.
  ///
  /// Read out of a real environment through a real layout pass, from inside `PageGlassLane`'s own
  /// content closure, which is exactly where every modal in the app is mounted.
  func testTheSurfaceTellsTheDimWhichSurfaceItIs() {
    for item in SidebarNavItem.allCases {
      let expected: ShellModalScrimBounds =
        PageGlassLanePolicy.ownsItsPanels(selectedIndex: item.rawValue) ? .contentArea : .ownSurface
      XCTAssertEqual(
        Self.boundsPublished(toDestination: item.rawValue), expected,
        "\(item.title) hands its modals the wrong surface")
    }
  }

  /// …and a modal that is *not* inside a destination — the shell's own overlays: the required update,
  /// the usage-limit card, the post-onboarding prompt, the goal celebration — gets the whole shell.
  /// This is the environment's default, so it is also what any future surface inherits by omission,
  /// and it must be the conservative one.
  func testAModalOutsideAnyDestinationDimsTheShell() {
    let recorder = ShellModalScrimBoundsRecorder()
    let host = NSHostingView(
      rootView: ShellModalScrimBoundsProbe(recorder: recorder).frame(width: 1_400, height: 800))
    host.frame = NSRect(x: 0, y: 0, width: 1_400, height: 800)
    host.layoutSubtreeIfNeeded()

    XCTAssertEqual(recorder.bounds, .wholeShell)
  }

  /// The dim is still doing its job. A scrim that painted nothing would satisfy every "does not reach
  /// the edge" assertion above, so the guard states the other half: what darkens is most of the app.
  func testTheDimActuallyCoversTheAppItIsDimming() throws {
    let size = CGSize(width: 1_400, height: 800)
    let painted = try XCTUnwrap(PaintedExtent.of(ShellModalScrim(), in: size))

    XCTAssertEqual(
      painted.width, ShellModalScrimLayout.laneWidth(for: size.width), accuracy: 1.5,
      "the dim is not on the shell's lane")
    XCTAssertEqual(
      painted.height,
      size.height - ShellModalScrimLayout.topInset(.wholeShell)
        - ShellModalScrimLayout.bottomInset(.wholeShell),
      accuracy: 1.5,
      "the dim does not reach from under the drag band to the panel's bottom margin")
  }

  // MARK: - The confirmation that used to be a system alert

  /// **A confirmation the shell raises must be drawn by the shell.**
  ///
  /// `.alert` is presented by AppKit *against the host window*, and the backdrop it puts up is that
  /// window's size. On a window whose frame is the app's edge that is right; on this one — a
  /// transparent rectangle noticeably larger than the panels inside it — it is the whole defect, and
  /// it arrives without any dim in this codebase being wrong. Measured live on Settings → Advanced →
  /// Reset Onboarding: everything inside the window frame changed, including the wallpaper between
  /// the panels, and nothing outside it did.
  ///
  /// Held on pixels rather than on presentation, which is what makes it catch the regression that
  /// matters: a system alert paints **nothing at all** into the app's own render tree, so going back
  /// to `.alert` fails the unwrap below, and deleting the dim instead of bounding it fails the width.
  func testTheShellsConfirmationPaintsOnItsSurfaceAndNotOnTheWindow() throws {
    for bounds in [ShellModalScrimBounds.wholeShell, .contentArea] {
      for size in Self.windowSizes {
        let painted = try XCTUnwrap(
          PaintedExtent.of(Self.confirmation.shellModalScrimBounds(bounds), in: size),
          "\(bounds) at \(size): the confirmation painted nothing into the app. A modal presented by "
            + "the system draws its backdrop on the window instead — which is the desktop here")

        for (edge, margin) in [
          ("leading", painted.minX),
          ("trailing", size.width - painted.maxX),
          ("top", painted.minY),
          ("bottom", size.height - painted.maxY),
        ] {
          XCTAssertGreaterThan(
            margin, 0,
            "\(bounds) at \(size): the confirmation painted to the \(edge) edge, which on this "
              + "window is the user's wallpaper")
        }

        // …and it is still a modal. A card floating on an undimmed app would keep every margin
        // above and say nothing about the app being unavailable, so the dim's own extent is asserted
        // rather than merely "something was drawn".
        XCTAssertEqual(
          painted.width, ShellModalScrimLayout.laneWidth(for: size.width), accuracy: 1.5,
          "the confirmation's card is drawn but its dim is not: at \(size) the paint is narrower "
            + "than the shell's lane")
      }
    }
  }

  /// …and inside a page — where Settings raises this one — the dim is the panel's own extent,
  /// exactly. The page is already the lane, so clamping again would leave an undimmed border of
  /// glass and the confirmation would read as sitting *under* the page it is asking about.
  func testTheShellsConfirmationInsideAPageFillsThatPanel() throws {
    for size in Self.windowSizes {
      let host = CGSize(
        width: PageGlassLaneLayout.laneWidth(for: size.width),
        height: size.height - PageGlassLaneLayout.topGap - PageGlassLaneLayout.bottomGap)
      let painted = try XCTUnwrap(
        PaintedExtent.of(Self.confirmation.shellModalScrimBounds(.ownSurface), in: host),
        "no confirmation painted in a \(host) panel")

      XCTAssertEqual(painted.minX, 0, accuracy: 0.5, "the panel keeps an undimmed leading border")
      XCTAssertEqual(painted.minY, 0, accuracy: 0.5, "the panel keeps an undimmed top border")
      XCTAssertEqual(painted.width, host.width, accuracy: 1.5)
      XCTAssertEqual(painted.height, host.height, accuracy: 1.5)
    }
  }

  /// The confirmation as a surface raises it: mounted on a host that paints nothing of its own, so
  /// everything the measurement sees belongs to the modal.
  private static var confirmation: some View {
    Color.clear.shellConfirmation(
      isPresented: .constant(true),
      title: "Reset Onboarding?",
      message: "This will reset onboarding for this app build only.",
      confirmTitle: "Reset & Restart"
    ) {}
  }

  // **Modality is deliberately not asserted here.** The scrim keeps an invisible, full-host barrier
  // (`blocksInteraction`) so a click outside the painted dim is still swallowed and still dismisses —
  // that is what stops this fix trading a visual bug for a usability one. It has no hermetic seam:
  // `NSHostingView.hitTest` returns the hosting view for any point inside its bounds whether or not
  // the SwiftUI content beneath accepts the click, so a test written against it passes identically
  // with the barrier deleted. Rather than ship an assertion that proves nothing, the barrier is
  // covered by exercising a real modal (click outside a sheet dismisses it; the page behind does not
  // respond) and by the `onTap` wiring at each call site.

  /// Mounts a probe exactly where a page's modals are mounted and reads back the surface it was told
  /// it is on.
  private static func boundsPublished(toDestination index: Int) -> ShellModalScrimBounds? {
    let recorder = ShellModalScrimBoundsRecorder()
    let host = NSHostingView(
      rootView: PageGlassLane(selectedIndex: index) {
        ShellModalScrimBoundsProbe(recorder: recorder)
      }
      .frame(width: 1_400, height: 800))
    host.frame = NSRect(x: 0, y: 0, width: 1_400, height: 800)
    host.layoutSubtreeIfNeeded()
    return recorder.bounds
  }

}

// MARK: - The page-scale keyboard target

/// **A page may hold keyboard focus. It may not draw a focus ring around the window.**
///
/// The third member of this file's defect class and the one that is not a fill: a page that answers
/// arrow keys anywhere on itself has to be `focusable()`, and AppKit strokes a focus effect around
/// whatever holds focus. On a control that is the point of the effect; on a container the size of the
/// shell's content area it is a 1 pt system-accent rectangle along the window's left, right and
/// bottom edges with a full-width line under the top bar — reported from a live build as Rewind
/// drawing a blue rectangle on the wallpaper, and in a hue this product uses nowhere (INV-UI-1).
///
/// Not measured on pixels, and deliberately so: `ImageRenderer` has no focus, so no offscreen render
/// can show a focus ring whether or not one would be drawn. The seam that *is* real is the
/// environment the effect reads, which is asserted here through a live layout pass — the same shape
/// `testTheSurfaceTellsTheDimWhichSurfaceItIs` uses. Both directions are held: the page must not draw
/// one, and a view that has not asked to be a page target must still get one, or the assertion above
/// it would pass against a harness that never had focus effects at all.
@MainActor
final class ShellPageKeyboardTargetTests: XCTestCase {

  func testAPageScaleKeyboardTargetDrawsNoSystemFocusEffect() {
    XCTAssertEqual(
      Self.focusEffectEnabled(pageTarget: true), false,
      "the page draws AppKit's focus effect: at content-area scale that is an accent rectangle on "
        + "the window's edges, which on this window is the user's wallpaper")
  }

  /// The control case. Without the modifier the effect is on, which is what makes the assertion
  /// above a claim about `shellPageKeyboardTarget` rather than about the test host.
  func testAnOrdinaryFocusableViewKeepsItsFocusEffect() {
    XCTAssertEqual(
      Self.focusEffectEnabled(pageTarget: false), true,
      "focus effects are off everywhere in this harness, so the assertion above proves nothing")
  }

  /// Reads `\.isFocusEffectEnabled` out of a real environment through a real layout pass, from
  /// exactly where the page's own content sits.
  private static func focusEffectEnabled(pageTarget: Bool) -> Bool? {
    let recorder = FocusEffectRecorder()
    let host = NSHostingView(
      rootView: ShellPageKeyboardTargetProbe(recorder: recorder, pageTarget: pageTarget)
        .frame(width: 1_400, height: 800))
    host.frame = NSRect(x: 0, y: 0, width: 1_400, height: 800)
    host.layoutSubtreeIfNeeded()
    return recorder.isFocusEffectEnabled
  }
}

private final class FocusEffectRecorder: @unchecked Sendable {
  private(set) var isFocusEffectEnabled: Bool?

  func record(_ enabled: Bool) {
    isFocusEffectEnabled = enabled
  }
}

/// Owns the `@FocusState` the modifier binds, because a `FocusState.Binding` can only come from a
/// view that declares one — the same constraint every page under test lives with.
private struct ShellPageKeyboardTargetProbe: View {
  let recorder: FocusEffectRecorder
  let pageTarget: Bool
  @FocusState private var focused: Bool

  var body: some View {
    if pageTarget {
      FocusEffectReader(recorder: recorder).shellPageKeyboardTarget($focused)
    } else {
      FocusEffectReader(recorder: recorder).focusable().focused($focused)
    }
  }
}

private struct FocusEffectReader: View {
  let recorder: FocusEffectRecorder
  @Environment(\.isFocusEffectEnabled) private var isFocusEffectEnabled

  var body: some View {
    FocusEffectReaderLayout(recorder: recorder, enabled: isFocusEffectEnabled) { Color.clear }
  }
}

private struct FocusEffectReaderLayout: Layout {
  let recorder: FocusEffectRecorder
  let enabled: Bool

  func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
    CGSize(width: proposal.width ?? 0, height: proposal.height ?? 0)
  }

  func placeSubviews(
    in bounds: CGRect,
    proposal: ProposedViewSize,
    subviews: Subviews,
    cache: inout ()
  ) {
    recorder.record(enabled)
    for subview in subviews {
      subview.place(at: bounds.origin, proposal: ProposedViewSize(bounds.size))
    }
  }
}

// MARK: - Measuring what was painted

/// The bounding box of everything a view actually draws, in that view's own coordinates.
///
/// Rendered rather than laid out, because "does not reach the window's edge" is a claim about paint.
/// A frame probe cannot see `.ignoresSafeArea()` bleeding a fill past the box it was placed in, and
/// bleeding a fill past its box is the whole defect this guards.
///
/// `ImageRenderer` is the deployment floor's (macOS 13+) offscreen SwiftUI render, so this needs no
/// window and no display — it is hermetic in CI.
@MainActor
enum PaintedExtent {

  /// Anything at or above this alpha counts as painted. Well under the dim's own composited alpha
  /// (`Ink.primary` is `labelColor`, black at 0.85, times `ShellModalScrimLayout.dim`), and well above
  /// the antialiasing fringe at a rounded corner.
  static let alphaFloor: UInt8 = 8

  /// `nil` when the view paints nothing at all.
  static func of(_ view: some View, in size: CGSize) -> CGRect? {
    let renderer = ImageRenderer(content: view.frame(width: size.width, height: size.height))
    renderer.scale = 1
    guard let image = renderer.cgImage else { return nil }

    let width = image.width
    let height = image.height
    var pixels = [UInt8](repeating: 0, count: width * height * 4)
    guard
      let context = CGContext(
        data: &pixels,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: width * 4,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
    else { return nil }
    context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))

    var minX = width
    var maxX = -1
    var minY = height
    var maxY = -1
    for y in 0..<height {
      let row = y * width * 4
      for x in 0..<width where pixels[row + x * 4 + 3] >= alphaFloor {
        minX = min(minX, x)
        maxX = max(maxX, x)
        minY = min(minY, y)
        maxY = max(maxY, y)
      }
    }
    guard maxX >= minX, maxY >= minY else { return nil }

    // `ImageRenderer` draws top-down, which is the orientation the assertions read in.
    return CGRect(
      x: CGFloat(minX), y: CGFloat(minY),
      width: CGFloat(maxX - minX + 1), height: CGFloat(maxY - minY + 1))
  }
}

/// Reads `\.shellModalScrimBounds` out of a live environment, so the wiring assertion is about what a
/// modal mounted there would actually receive rather than about the modifier having been written.
private final class ShellModalScrimBoundsRecorder: @unchecked Sendable {
  private(set) var bounds: ShellModalScrimBounds?

  func record(_ bounds: ShellModalScrimBounds) {
    self.bounds = bounds
  }
}

private struct ShellModalScrimBoundsProbe: View {
  let recorder: ShellModalScrimBoundsRecorder
  @Environment(\.shellModalScrimBounds) private var bounds

  var body: some View {
    // Recorded from a layout pass rather than an `onAppear`, so the value is read whenever the tree
    // is measured — the same shape `PageGlassLaneProbe` below uses, and for the same reason.
    ShellModalScrimBoundsProbeLayout(recorder: recorder, bounds: bounds) { Color.clear }
  }
}

private struct ShellModalScrimBoundsProbeLayout: Layout {
  let recorder: ShellModalScrimBoundsRecorder
  let bounds: ShellModalScrimBounds

  func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
    CGSize(width: proposal.width ?? 0, height: proposal.height ?? 0)
  }

  func placeSubviews(
    in bounds: CGRect,
    proposal: ProposedViewSize,
    subviews: Subviews,
    cache: inout ()
  ) {
    recorder.record(self.bounds)
    for subview in subviews {
      subview.place(at: bounds.origin, proposal: ProposedViewSize(bounds.size))
    }
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
