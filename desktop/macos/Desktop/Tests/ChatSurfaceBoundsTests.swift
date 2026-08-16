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
        let composer = restingComposerHeight(mode: mode)
        let body = QueryShellLayout.panelBodyHeight(
          availableHeight: page, composerHeight: composer, mode: mode)
        XCTAssertLessThanOrEqual(
          surfaceHeight(bodyHeight: body, composerHeight: composer, mode: mode),
          page,
          "the \(mode) panel still runs off a \(page) pt page")
      }
    }
  }

  /// **The composer is paid for exactly once, on the side of the panel it is standing on.**
  ///
  /// Searching pays for it above the panel: the hero bar plus the 12 pt of air under it. Chatting
  /// pays for it inside, under the transcript, and pays nothing above — the bar is not there. Charge
  /// it in both places and the panel stops short of the window; charge it in neither and you get the
  /// overflow the three tests around this one exist for.
  func testTheComposerIsPaidForOnTheSideOfThePanelItStandsOn() {
    for page in pageHeights(windowHeights: [ShellSummonPlacement.defaultSize.height, DesktopWindowLayoutPolicy.height])
    {
      for mode in [QueryShellMode.results, .answer] {
        let composer = restingComposerHeight(mode: mode)
        let body = QueryShellLayout.panelBodyHeight(
          availableHeight: page, composerHeight: composer, mode: mode)
        let surface = surfaceHeight(bodyHeight: body, composerHeight: composer, mode: mode)
        if body < QueryShellLayout.maximumBodyHeight {
          XCTAssertEqual(
            surface, page, accuracy: 0.5,
            "the \(mode) surface leaves part of a \(page) pt page unspent")
        } else {
          XCTAssertEqual(body, QueryShellLayout.maximumBodyHeight)
          XCTAssertLessThanOrEqual(
            surface, page,
            "the \(mode) panel still runs off a \(page) pt page")
        }
      }
    }
  }

  /// **Opening chat spends the search bar's room on the conversation.** The bar and the gap under it
  /// are 76 pt that stop existing; the composer costs 54 back inside the panel, so the transcript is
  /// strictly better off than the list it replaced. If this ever inverts, the composer is being
  /// reserved twice.
  func testOpeningChatLeavesTheTranscriptMoreRoomThanTheListHad() {
    let page = pageHeights(windowHeights: [ShellSummonPlacement.defaultSize.height])[0]

    let list = QueryShellLayout.panelBodyHeight(
      availableHeight: page, composerHeight: restingComposerHeight(mode: .results), mode: .results)
    let chat = QueryShellLayout.panelBodyHeight(
      availableHeight: page, composerHeight: restingComposerHeight(mode: .answer), mode: .answer)

    XCTAssertGreaterThan(
      chat, list,
      "the conversation has less room than the list did — the hero bar is still being reserved for")
  }

  /// A staged file makes the bar taller. Reserving its resting height instead of its real one is how
  /// the overflow comes back through the paperclip.
  func testAGrownHeroBarTakesItsSpaceFromTheBodyRatherThanFromTheWindow() {
    let page = pageHeights(windowHeights: [ShellSummonPlacement.defaultSize.height])[0]
    let grown = QueryShellLayout.barMinHeight + 72

    let resting = QueryShellLayout.panelBodyHeight(
      availableHeight: page, composerHeight: QueryShellLayout.barMinHeight, mode: .results)
    let withAttachments = QueryShellLayout.panelBodyHeight(
      availableHeight: page, composerHeight: grown, mode: .results)

    XCTAssertLessThan(withAttachments, resting)
    XCTAssertLessThanOrEqual(
      surfaceHeight(bodyHeight: withAttachments, composerHeight: grown, mode: .results), page)
  }

  /// The same rule from inside the panel: a five-line follow-up grows the composer, and that growth
  /// has to come out of the transcript above it rather than off the bottom of the window. This is the
  /// one the move actually risks — the composer is now *below* the thing whose height it changes.
  func testAGrownInPanelComposerTakesItsSpaceFromTheTranscript() {
    let page = pageHeights(windowHeights: [ShellSummonPlacement.defaultSize.height])[0]
    let grown = QueryShellLayout.panelComposerMinHeight + 72

    let resting = QueryShellLayout.panelBodyHeight(
      availableHeight: page, composerHeight: restingComposerHeight(mode: .answer), mode: .answer)
    let withLongDraft = QueryShellLayout.panelBodyHeight(
      availableHeight: page, composerHeight: grown, mode: .answer)

    XCTAssertLessThan(withLongDraft, resting)
    XCTAssertLessThanOrEqual(
      surfaceHeight(bodyHeight: withLongDraft, composerHeight: grown, mode: .answer), page)
  }

  /// The floor and the ceiling both still hold: a window too short for a panel gets a short panel
  /// rather than a negative one, and a tall display does not turn the second object on Home into the
  /// whole surface.
  func testTheBodyStaysBetweenItsFloorAndItsCeiling() {
    for mode in [QueryShellMode.results, .answer] {
      let composer = restingComposerHeight(mode: mode)
      XCTAssertEqual(
        QueryShellLayout.panelBodyHeight(
          availableHeight: 120, composerHeight: composer, mode: mode),
        QueryShellLayout.minimumBodyHeight)
      XCTAssertEqual(
        QueryShellLayout.panelBodyHeight(
          availableHeight: 4000, composerHeight: composer, mode: mode),
        QueryShellLayout.maximumBodyHeight)
    }
  }

  /// Answer mode drops the type chips — there is nothing to narrow by type in a conversation — and
  /// spends that row, plus the room the hero bar gave back, on the composer it now holds.
  func testAnswerModeTradesTheTypeChipsRowForTheComposerItNowHolds() {
    let composer = QueryShellLayout.panelComposerMinHeight
    let list = QueryShellLayout.panelChromeHeight(mode: .results, composerHeight: composer)
    let chat = QueryShellLayout.panelChromeHeight(mode: .answer, composerHeight: composer)

    XCTAssertEqual(
      chat - list,
      composer + QueryShellLayout.panelHeaderSpacing
        - (QueryShellLayout.chipHeight + QueryShellLayout.panelHeaderSpacing),
      "the conversation's chrome is the list's, less the chips, plus the composer")
    XCTAssertGreaterThan(chat, list, "a panel that now holds a composer costs more chrome, not less")
  }

  /// The list's panel holds no composer, so its chrome must not move when one grows. Reading the
  /// measured height in both modes is the mistake this guards: it would shrink the spine's rows every
  /// time somebody typed a long question and went back to the list.
  func testTheListsPanelReservesNothingForAComposerItDoesNotHold() {
    XCTAssertEqual(
      QueryShellLayout.panelChromeHeight(mode: .results, composerHeight: 240),
      QueryShellLayout.panelChromeHeight(mode: .results, composerHeight: 0))
  }

  /// What Home's `GeometryReader` is actually handed: the window's content height less the
  /// floating top bar and the gap beneath it.
  private func pageHeights(windowHeights: [CGFloat]) -> [CGFloat] {
    let chrome =
      GlassShell.titlebarClearance + TopNavigationLayoutMetrics.barHeight + OmiSpacing.sm
    return windowHeights.map { $0 - chrome }
  }

  /// What the composer measures at rest wherever this mode puts it.
  private func restingComposerHeight(mode: QueryShellMode) -> CGFloat {
    QueryShellLayout.composerContainerMinHeight(placement: QueryComposerPlacement.of(mode))
  }

  /// The whole surface, bottom to top, for a given body height — including the hero bar and its gap
  /// only in the mode that actually draws them.
  private func surfaceHeight(bodyHeight: CGFloat, composerHeight: CGFloat, mode: QueryShellMode)
    -> CGFloat
  {
    let above =
      QueryShellLayout.surfaceTopInset
      + (QueryComposerPlacement.of(mode) == .hero ? composerHeight + QueryShellLayout.panelGap : 0)
    return above
      + QueryShellLayout.panelChromeHeight(mode: mode, composerHeight: composerHeight) + bodyHeight
  }
}
