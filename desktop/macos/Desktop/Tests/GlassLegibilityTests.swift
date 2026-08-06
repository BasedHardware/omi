import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// The last screens to leave the hardcoded-dark `OmiColors` palette, and the failure they all shared.
///
/// `OmiColors` was dark by construction — `textPrimary` was `#FFFFFF`, `backgroundPrimary` was
/// `#0F0F0F`. When the app was pinned to light glass, every surviving call site kept compiling,
/// kept laying out, and kept drawing; it just drew white on white. **A type checker cannot see this
/// and neither can a crash log.** The screens went blank-but-functional: assistant replies and the
/// whole conversational onboarding rendered invisible text into correctly-sized bubbles.
///
/// So the guard here is not "which token does this call site name" — that is a spelling check that a
/// synonym defeats. It resolves the colours the production code actually returns, composites them
/// over the ground they are actually drawn on, and asserts the result is *readable*. A future edit
/// that swaps in another near-white token fails this file even though it names no banned symbol.
///
/// Contrast is WCAG 2.1 relative luminance. 4.5:1 is the AA bar for normal text, 3:1 for a
/// non-text boundary (a track, a knob, a hairline) — the same two bars `Ink`'s ladder is built to.
final class GlassLegibilityTests: XCTestCase {

  // MARK: - Resolving colours the way the screen does

  /// The panel's ground: what a hosted page's translucent washes composite onto.
  ///
  /// `Ink.surface` under the glass's pinned light appearance — not "white", because the whole point
  /// is to measure against the real resolved value rather than a constant this test made up.
  private var glassGround: NSColor {
    resolved(Ink.surface)
  }

  /// Resolves a SwiftUI `Color` to concrete sRGB **in the glass's pinned light appearance**.
  ///
  /// This is the step that reproduces the bug. `Ink`'s colours are dynamic `NSColor`s, so asking one
  /// for its components outside an appearance gives whatever the test host happens to be in;
  /// `InkGlass.appearance` is the appearance the panel actually pins (`WindowGlass.wear`), so this
  /// is what the user sees.
  private func resolved(_ color: Color) -> NSColor {
    var out = NSColor(color)
    InkGlass.appearance.performAsCurrentDrawingAppearance {
      out = NSColor(color).usingColorSpace(.sRGB) ?? out
    }
    return out.usingColorSpace(.sRGB) ?? out
  }

  /// Source-over composite, because every glass wash is translucent and its *apparent* colour — the
  /// one contrast is actually experienced against — only exists once it is over the ground.
  private func composite(_ top: NSColor, over ground: NSColor) -> NSColor {
    let a = top.alphaComponent
    guard a < 1 else { return top }
    return NSColor(
      srgbRed: top.redComponent * a + ground.redComponent * (1 - a),
      green: top.greenComponent * a + ground.greenComponent * (1 - a),
      blue: top.blueComponent * a + ground.blueComponent * (1 - a),
      alpha: 1
    )
  }

  private func relativeLuminance(_ color: NSColor) -> CGFloat {
    func linear(_ c: CGFloat) -> CGFloat {
      c <= 0.03928 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
    }
    return 0.2126 * linear(color.redComponent)
      + 0.7152 * linear(color.greenComponent)
      + 0.0722 * linear(color.blueComponent)
  }

  /// WCAG contrast between two colours, each first flattened onto the glass ground.
  private func contrast(_ foreground: Color, on background: Color) -> CGFloat {
    let ground = glassGround
    let back = composite(resolved(background), over: ground)
    let front = composite(resolved(foreground), over: back)
    let l1 = relativeLuminance(front)
    let l2 = relativeLuminance(back)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
  }

  /// Contrast against the bare panel, for content that draws no ground of its own.
  private func contrastOnGlass(_ foreground: Color) -> CGFloat {
    contrast(foreground, on: Ink.surface)
  }

  // MARK: - The reported defect: assistant copy was white on the light panel

  func testEveryChatBubbleStyleIsReadableOnTheSurfaceItIsActuallyDrawnOn() {
    // The assistant bubble paints no ground (the glass owns it) and both user bubbles are a wash
    // over that glass — `ChatBubble.messageTextBubble` uses `Ink.rowFillHover`, onboarding's user
    // bubble uses `glassCard(emphasized:)`, which is the same wash. So the grounds are the panel
    // and that one wash, and prose has to clear the 4.5:1 normal-text bar on both.
    let grounds: [(String, Color)] = [
      ("the bare glass panel", Ink.surface),
      ("a user bubble's wash", Ink.rowFillHover),
    ]

    for style in [OmiMarkdown.Style.assistant, .user, .onboardingUser] {
      let color = OmiMarkdownContent.baseColor(for: style)
      for (name, ground) in grounds {
        let ratio = contrast(color, on: ground)
        XCTAssertGreaterThanOrEqual(
          ratio, 4.5,
          """
          OmiMarkdown \(style) prose measures \(String(format: "%.2f", ratio)):1 on \(name). \
          This is the exact shape of the bug this test exists for: the old palette returned \
          #FFFFFF here, which compiled and drew and was invisible. Pair chat prose with a dynamic \
          label colour (Ink.primary), never a fixed near-white or near-black.
          """
        )
      }
    }
  }

  func testNoChatBubbleStyleKeepsAFixedNearWhiteOrNearBlackLabel() {
    // The narrow regression assertion, stated as the value rather than the ratio: all three styles
    // resolve to the *dynamic* label. `.assistant` was `OmiColors.textPrimary` (#FFFFFF) and
    // `.user` was a literal `.white`; both were correct only against a near-black page that no
    // longer exists anywhere in this renderer.
    for style in [OmiMarkdown.Style.assistant, .user, .onboardingUser] {
      XCTAssertEqual(
        OmiMarkdownContent.baseColor(for: style), Ink.primary,
        "OmiMarkdown \(style) must use the dynamic label so it tracks the panel's appearance."
      )
    }
  }

  // MARK: - The app-wide switch

  func testSwitchTrackShowsItsStateAndTheKnobIsVisibleInBothStates() {
    let on = OmiToggleStyle.trackFill(isOn: true)
    let off = OmiToggleStyle.trackFill(isOn: false)

    // The one thing a switch has to do. The dark palette's "on" track was `OmiColors.accent`, which
    // was `#FFFFFF`: on the light panel every switch in Settings was a white track on a white
    // ground under a white knob, i.e. identical to "off" and to nothing at all.
    XCTAssertNotEqual(on, off, "The on and off tracks must not resolve to the same colour.")

    let knob = OmiToggleStyle.knobFill
    for (state, track) in [("on", on), ("off", off)] {
      let ratio = contrast(knob, on: track)
      XCTAssertGreaterThanOrEqual(
        ratio, 3.0,
        """
        The switch knob measures \(String(format: "%.2f", ratio)):1 against the \(state) track. \
        A knob that cannot be told from its track is a switch with no readable position.
        """
      )
    }

    // And the off track has to hold its own shape against the panel, or "off" reads as "absent".
    XCTAssertGreaterThanOrEqual(
      contrastOnGlass(off), 1.1,
      "The off track vanishes into the glass; it needs more weight than a row wash."
    )
  }

  // MARK: - The washes the converted screens were rebuilt on

  func testTheTwoTypeRungsGlassCarriesAreBothReadableOnIt() {
    // Every `tertiary`/`quaternary` run in the converted screens was promoted to `Ink.secondary`
    // rather than thinned. That promotion is only correct if the second rung genuinely clears the
    // normal-text bar on the panel — otherwise it is the same invisibility one step along.
    XCTAssertGreaterThanOrEqual(
      contrastOnGlass(Ink.primary), 4.5,
      "The primary rung must clear WCAG AA for normal text on the glass panel."
    )
    XCTAssertGreaterThanOrEqual(
      contrastOnGlass(Ink.secondary), 4.5,
      """
      The second rung fails WCAG AA on glass. The converted screens promote every third-rung run \
      to Ink.secondary, so this is the colour most of their small copy is drawn in.
      """
    )
  }

  func testRowWashesStayDistinguishableFromEachOtherAndFromThePanel() {
    // The converted screens express hover/rest and track/pill entirely as these two washes, so a
    // change that collapsed them would silently delete every hover affordance on those pages.
    let rest = composite(resolved(Ink.rowFill), over: glassGround)
    let hover = composite(resolved(Ink.rowFillHover), over: glassGround)

    XCTAssertNotEqual(
      relativeLuminance(rest), relativeLuminance(hover),
      "rowFill and rowFillHover composite to the same colour; hover states would be invisible."
    )
    XCTAssertLessThan(
      relativeLuminance(hover), relativeLuminance(glassGround),
      "A wash on this panel must darken it — a lighter wash on light glass is not a surface."
    )
  }

  // MARK: - Home: the page that kept its own ground

  func testHomePaintsNoGroundOfItsOwn() {
    // The reported defect. Home's palette was mapped onto `Ink` — so every colour on the page
    // resolved *dark* against the light-pinned panel — but the page still painted a near-black
    // canvas edge to edge underneath them (`HomeCanvasBackground`, a hardcoded 0.056/0.058/0.065
    // gradient with `.ignoresSafeArea()`). Dark type on a dark canvas inside a light window: the
    // whole transcript, the greeting, the knows list and the connect tray were present, hit-
    // testable, and unreadable.
    //
    // Stated as "the page is transparent" rather than as a contrast ratio because that is the
    // actual contract — `glassShellGround()` owns the one ground in this window, and a second
    // opaque ground is wrong even on the days it happens to be light enough to read on.
    XCTAssertEqual(
      resolved(HomePalette.paper).alphaComponent, 0,
      """
      Home is painting a ground of its own. The window already has exactly one \
      (`glassShellGround`); a page that paints a second decides the colour every `Ink` token on \
      it is read against, and `Ink` is resolving for the panel's light appearance, not for this.
      """
    )
  }

  /// **Static checker, not behavioural coverage.** It reads source rather than running it, and it
  /// is here because the behavioural assertion above cannot reach the defect it is paired with:
  /// `HomePalette.paper` was *already* `Color.clear` when Home went dark. The ground came from a
  /// second view stacked under the page with a literal RGB gradient in it, and no token that any
  /// test could resolve ever changed. A component-scoped tripwire on the literal is the only thing
  /// that would have failed on that commit.
  ///
  /// Scoped to Home's own file and to `Color(red:` specifically: a page hosted on the panel has no
  /// business mixing its own opaque colour at all, and every legitimate surface on it is a token.
  func testStaticCheck_HomeMixesNoColourLiteralOfItsOwn() {
    let home = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests
      .deletingLastPathComponent()  // Desktop
      .appendingPathComponent("Sources/MainWindow/Pages/DashboardPage.swift")
    // omi-test-quality: source-inspection -- static contract: which token a call site names is a source fact; a rendered view cannot report it.
    guard let source = try? String(contentsOf: home, encoding: .utf8) else {
      return XCTFail("Could not read DashboardPage.swift at \(home.path)")
    }
    XCTAssertFalse(
      source.contains("Color(red:"),
      """
      Home mixes a colour literal. This page is hosted on the shell's glass and every surface on \
      it has to be an `Ink`/`PageGlass` token, because only a token tracks the panel's pinned \
      appearance. The literal that shipped here was a near-black canvas under a page whose type \
      had already been converted to resolve dark.
      """
    )
  }

  func testHomeProseAndTheAskBarsFilledButtonsAreReadableWhereTheyAreDrawn() {
    // Home's two rungs land straight on the panel now that the canvas is gone.
    for (name, color) in [("ink", HomePalette.ink), ("secondary", HomePalette.secondary)] {
      XCTAssertGreaterThanOrEqual(
        contrastOnGlass(color), 4.5,
        "HomePalette.\(name) fails WCAG AA on the glass Home is actually drawn on.")
    }

    // The ask bar's Send / Stop / active-Connect were a white disc with a black glyph and a white
    // capsule with black text — a filled control picked for a near-black page, which on light
    // glass is a control you cannot find wearing a label you can read. Both halves have to work:
    // the label against its own fill, and the fill against the panel it sits on.
    XCTAssertGreaterThanOrEqual(
      contrast(HomeAskBarPalette.primaryLabel, on: HomeAskBarPalette.primaryFill), 4.5,
      "The ask bar's filled action button cannot read its own label.")
    XCTAssertGreaterThanOrEqual(
      contrastOnGlass(HomeAskBarPalette.primaryFill), 3.0,
      """
      The ask bar's primary action does not clear the 3:1 non-text bar against the panel, so the \
      button itself is invisible even when the glyph on it is not.
      """
    )
    XCTAssertGreaterThanOrEqual(
      contrast(HomeAskBarPalette.secondaryLabel, on: HomeAskBarPalette.secondaryFill(isHovering: false)),
      4.5,
      "Connect-at-rest cannot read its own label.")
  }

  func testTheAskBarsRestAndEngagedStatesAreTellableApart() {
    // The well was one wash at two alphas eight percent apart — about 0.4/255 once composited,
    // i.e. a focus state with no visible difference. Hover and focus are the only feedback this
    // control has; if they collapse, the bar never looks focused.
    let rest = composite(resolved(HomeAskBarPalette.wellFill(isEngaged: false)), over: glassGround)
    let engaged = composite(resolved(HomeAskBarPalette.wellFill(isEngaged: true)), over: glassGround)
    XCTAssertGreaterThan(
      abs(relativeLuminance(rest) - relativeLuminance(engaged)), 0.005,
      "The ask bar's resting and engaged wells composite to the same colour.")

    XCTAssertNotEqual(
      HomeAskBarPalette.wellStroke(isFocused: true, isDropTargeted: false),
      HomeAskBarPalette.wellStroke(isFocused: false, isDropTargeted: false),
      "The focus ring is the same colour as the resting edge; focus is invisible.")
  }

  func testTheSeparatorIsAVisibleEdgeOnTheLightPanel() {
    // Several converted files drew their borders as `Color.white.opacity(0.05…0.18)` — hairlines
    // that existed only because the page behind them was near-black. On glass they were nothing.
    // `Ink.separator` replaced all of them, so it has to actually read as an edge.
    let separator = composite(resolved(Ink.separator), over: glassGround)
    XCTAssertNotEqual(
      relativeLuminance(separator), relativeLuminance(glassGround),
      "Ink.separator composites to the panel's own colour; every converted border would vanish."
    )
    XCTAssertGreaterThan(
      resolved(Ink.separator).alphaComponent, 0.0,
      "A fully transparent separator is the white-on-white bug wearing a different name."
    )
  }
}
