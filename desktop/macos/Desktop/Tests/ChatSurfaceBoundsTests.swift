import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// **Everything on the chat surface has to stay inside the box that draws it.**
///
/// Three defects in one session were the same mistake in three places: a shape that decided how much
/// room it needed without asking what it was drawing over. A reply's ground rounded its corner into
/// the reply's own first line; the panel pinned a body taller than the window it was in; the
/// jump-to-latest disc claimed a corner the message column already occupied. Each is arithmetic, so
/// each is held here rather than in a screenshot.
@MainActor
final class ChatSurfaceBoundsTests: XCTestCase {

  // MARK: - A message body's ground never reaches its own text

  /// **The regression that ate the first character of every assistant line.**
  ///
  /// `chatMessageBlock` used to clip its content to a `PageGlass.cardRadius` rounded rectangle in both
  /// states. That is fine on a user turn, whose padding holds text well clear of the curve, and fatal
  /// on an assistant reply, which the spacing rebuild correctly stripped of padding: with none, the
  /// corner withdrew up to a full radius from the leading edge and cut the opening glyph off the
  /// block's first and last lines — on a taper, so the lines between them were untouched.
  ///
  /// The property is geometric, not a restatement of the constants: for a corner of radius `r` on a
  /// box of height `h`, the drawn radius is `min(r, h/2)` and the leading edge has withdrawn
  /// `r' - sqrt(r'² - (r' - d)²)` at `d` points down. Text starts `d = verticalPadding` down, so that
  /// is the number `horizontalPadding` has to cover — at every height a message can be.
  func testAMessageBlocksGroundNeverReachesTheFirstGlyphOfItsText() {
    // One line of 14 pt prose is ~17 pt; the tallest is a long reply. Sweep both, plus the pathological
    // short box where the radius clamps hardest.
    let blockHeights: [CGFloat] = [8, 17, 20, 34, 51, 120, 640]

    for filled in [true, false] {
      let padding = ChatMessageBlockGeometry.horizontalPadding(filled: filled)
      for height in blockHeights {
        let reach = leadingReachOfGround(filled: filled, blockHeight: height)
        XCTAssertLessThanOrEqual(
          reach, padding,
          """
          a \(filled ? "filled" : "bare") block \(height) pt tall lets its ground reach \(reach) pt \
          into a text column indented \(padding) pt — that is the clipped-first-glyph defect
          """)
      }
    }
  }

  /// The reason the bare block is safe at zero padding: it paints nothing, so there is no shape to
  /// round and nothing that could clip the text handed to it. A reintroduced corner here is the defect
  /// coming back, whether it is drawn as a fill or as a clip.
  func testOnlyAFilledTurnDrawsAGroundAndOnlyAGroundHasACorner() {
    XCTAssertTrue(ChatMessageBlockGeometry.drawsGround(filled: true))
    XCTAssertEqual(ChatMessageBlockGeometry.cornerRadius(filled: true), PageGlass.cardRadius)

    XCTAssertFalse(ChatMessageBlockGeometry.drawsGround(filled: false))
    XCTAssertEqual(
      ChatMessageBlockGeometry.cornerRadius(filled: false), 0,
      "an assistant reply's ground is the glass panel; it has no corner of its own to cut text with")
    XCTAssertEqual(
      ChatMessageBlockGeometry.horizontalPadding(filled: false), 0,
      "and no padding either — the spacing rebuild's saving, which is what made the corner fatal")
  }

  /// How far a rounded ground has withdrawn from its own leading edge where the first line of text
  /// sits. The specification, computed from the circle rather than from the code under test.
  private func leadingReachOfGround(filled: Bool, blockHeight: CGFloat) -> CGFloat {
    let radius = min(ChatMessageBlockGeometry.cornerRadius(filled: filled), blockHeight / 2)
    guard radius > 0 else { return 0 }
    let depth = min(ChatMessageBlockGeometry.verticalPadding(filled: filled), radius)
    let remaining = radius - depth
    return radius - (radius * radius - remaining * remaining).squareRoot()
  }

  // MARK: - The jump-to-latest control lands in the gutter, not on a message

  /// The ask panel is the surface the defect was filed against: a 36 pt disc inset 16 pt reached
  /// 52 pt in from the trailing edge while the message column stops at 32, so it covered the trailing
  /// edge of the user bubbles it floated over.
  func testTheJumpControlClearsTheMessageColumnOnTheAskPanel() {
    let gutter = ChatOmiMarkPlacement.markGutter

    XCTAssertTrue(
      ChatScrollJumpPlacement.clearsMessageColumn(trailingContentInset: gutter),
      "the ask panel's transcript keeps a \(gutter) pt trailing gutter; the disc has to fit inside it")
    XCTAssertLessThanOrEqual(
      ChatScrollJumpPlacement.diameter(trailingContentInset: gutter)
        + ChatScrollJumpPlacement.trailingInset(trailingContentInset: gutter),
      gutter)
  }

  /// A host with no gutter to speak of gets a control that is still worth clicking, and says so:
  /// shrinking a target below `minimumDiameter` to honour a 4 pt inset is the worse trade, and
  /// `clearsMessageColumn` is how a caller finds out which case it is in rather than assuming.
  func testANarrowGutterKeepsAClickableTargetAndReportsTheOverlap() {
    for narrow in [CGFloat(0), 4, 12] {
      XCTAssertEqual(
        ChatScrollJumpPlacement.diameter(trailingContentInset: narrow),
        ChatScrollJumpPlacement.minimumDiameter)
      XCTAssertEqual(ChatScrollJumpPlacement.trailingInset(trailingContentInset: narrow), 0)
      XCTAssertFalse(ChatScrollJumpPlacement.clearsMessageColumn(trailingContentInset: narrow))
    }
  }

  /// A generous gutter does not buy a bigger disc — it buys a gap. The control is chrome on the edge
  /// of a reading column, not an object that grows with the window.
  func testAGenerousGutterBuysAGapRatherThanABiggerDisc() {
    let generous: CGFloat = 64
    XCTAssertEqual(
      ChatScrollJumpPlacement.diameter(trailingContentInset: generous),
      ChatScrollJumpPlacement.maximumDiameter)
    XCTAssertEqual(ChatScrollJumpPlacement.trailingInset(trailingContentInset: generous), OmiSpacing.sm)
    XCTAssertTrue(ChatScrollJumpPlacement.clearsMessageColumn(trailingContentInset: generous))
  }

  // MARK: - The panel ends inside the window

  /// **The overflow.** At the shell's own default size (960 × 700) the page has 600 pt for Home, and
  /// the panel used to ask for 654 in results mode: the surface ran past the bottom edge and AppKit cut
  /// the last row through the middle of its text, outside the scroll view and so unreachable by
  /// scrolling. The derived height has to fit whatever the page actually has, at the default size and
  /// at `DesktopWindowLayoutPolicy`'s floor.
  func testThePanelFitsThePageAtTheDefaultAndMinimumWindowSizes() {
    for page in pageHeights(windowHeights: [ShellSummonPlacement.defaultSize.height, DesktopWindowLayoutPolicy.height])
    {
      for mode in [QueryShellMode.results, .answer] {
        let body = QueryShellLayout.panelBodyHeight(
          availableHeight: page, heroBarHeight: QueryShellLayout.barMinHeight, mode: mode)
        XCTAssertLessThanOrEqual(
          surfaceHeight(bodyHeight: body, heroBarHeight: QueryShellLayout.barMinHeight, mode: mode),
          page,
          "the \(mode) panel still runs off a \(page) pt page")
      }
    }
  }

  /// A staged file makes the bar taller. Reserving its resting height instead of its real one is how
  /// the overflow comes back through the paperclip.
  func testAGrownHeroBarTakesItsSpaceFromTheBodyRatherThanFromTheWindow() {
    let page = pageHeights(windowHeights: [ShellSummonPlacement.defaultSize.height])[0]
    let grown = QueryShellLayout.barMinHeight + 72

    let resting = QueryShellLayout.panelBodyHeight(
      availableHeight: page, heroBarHeight: QueryShellLayout.barMinHeight, mode: .results)
    let withAttachments = QueryShellLayout.panelBodyHeight(
      availableHeight: page, heroBarHeight: grown, mode: .results)

    XCTAssertLessThan(withAttachments, resting)
    XCTAssertLessThanOrEqual(
      surfaceHeight(bodyHeight: withAttachments, heroBarHeight: grown, mode: .results), page)
  }

  /// The floor and the ceiling both still hold: a window too short for a panel gets a short panel
  /// rather than a negative one, and a tall display does not turn the second object on Home into the
  /// whole surface.
  func testTheBodyStaysBetweenItsFloorAndItsCeiling() {
    XCTAssertEqual(
      QueryShellLayout.panelBodyHeight(
        availableHeight: 120, heroBarHeight: QueryShellLayout.barMinHeight, mode: .results),
      QueryShellLayout.minimumBodyHeight)
    XCTAssertEqual(
      QueryShellLayout.panelBodyHeight(
        availableHeight: 4000, heroBarHeight: QueryShellLayout.barMinHeight, mode: .results),
      QueryShellLayout.maximumBodyHeight)
  }

  /// Answer mode drops the type chips, so it has more room for the transcript than the list has for
  /// its rows. The chrome measurement is what makes that true rather than a coincidence.
  func testAnswerModeSpendsTheTypeChipsRowOnTheTranscript() {
    XCTAssertEqual(
      QueryShellLayout.panelChromeHeight(mode: .results)
        - QueryShellLayout.panelChromeHeight(mode: .answer),
      QueryShellLayout.chipHeight + QueryShellLayout.panelHeaderSpacing)
  }

  /// What Home's `GeometryReader` is actually handed: the window's content height less the traffic
  /// lights' clearance and the floating top bar above the page.
  private func pageHeights(windowHeights: [CGFloat]) -> [CGFloat] {
    let chrome =
      GlassShell.titlebarClearance + TopNavigationLayoutMetrics.barHeight + (OmiSpacing.sm * 2)
    return windowHeights.map { $0 - chrome }
  }

  /// The whole surface, bottom to top, for a given body height.
  private func surfaceHeight(bodyHeight: CGFloat, heroBarHeight: CGFloat, mode: QueryShellMode)
    -> CGFloat
  {
    QueryShellLayout.surfaceTopInset + heroBarHeight + QueryShellLayout.panelGap
      + QueryShellLayout.panelChromeHeight(mode: mode) + bodyHeight
  }
}
