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
  /// Scoped to Home's own file — `QueryShellHome`, since `DashboardPage` was deleted — and to
  /// `Color(red:` specifically: a page hosted on the panel has no
  /// business mixing its own opaque colour at all, and every legitimate surface on it is a token.
  func testStaticCheck_HomeMixesNoColourLiteralOfItsOwn() {
    let home = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests
      .deletingLastPathComponent()  // Desktop
      .appendingPathComponent("Sources/MainWindow/QueryShell/QueryShellHome.swift")
    // omi-test-quality: source-inspection -- static contract: which token a call site names is a source fact; a rendered view cannot report it.
    guard let source = try? String(contentsOf: home, encoding: .utf8) else {
      return XCTFail("Could not read QueryShellHome.swift at \(home.path)")
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

  // MARK: - The ground is not a colour, it is a picture of another app

  /// **The defect this bar exists for, and the reason the file above it could not see it.**
  ///
  /// Every assertion in this class composites onto `Ink.surface` — one flat colour — because that is
  /// what a WCAG ratio is defined against. The glass ground is not flat. It is
  /// `InkGlass.scrim` of `surface` over a *blurred picture of whatever is behind the window*, and at
  /// the scrim that shipped it passed 35.4% of that picture through. A browser page puts both ends of
  /// that range inside one panel — a white article beside a dark hero banner — and the panel then
  /// carries a second image straight through the pixels the chat text is drawn in.
  ///
  /// Nothing above catches it. At *every individual pixel* the type still cleared AA against the
  /// ground under that pixel; the ground had simply become a competing picture. So the guard is a
  /// different quantity: the foreign image's amplitude over this app's own type's amplitude, taken at
  /// the darkest ground where the panel is weakest.
  ///
  /// **The bar is 1 and it is not invented here — it is where the accepted case already sat.**
  /// Measured off the tester's own frames, median-filtering our own glyphs out of the panel to leave
  /// the ground: over the wallpaper they called correct the ratio is **1.00** (ground 141 → 192/255);
  /// over the browser page they called unreadable it is **1.62** (ground 157 → 240/255). At the shipped
  /// scrim the modelled worst case was **2.02**.
  func testTheGlassCarriesItsOwnWordsMoreStronglyThanTheAppBehindIt() {
    // The faintest rung the panel is allowed to carry, so the bound is evaluated where the surface is
    // weakest. Resolved rather than restated: `Ink.secondary` is `labelColor` (0.85 in `.aqua`) at
    // 0.80, and a test that hardcoded 0.68 would keep passing if either factor moved.
    let alpha = resolved(Ink.secondary).alphaComponent
    let ratio = InkGlass.interferenceRatio(typeAlpha: alpha)

    XCTAssertLessThanOrEqual(
      ratio, 1.0,
      """
      The glass shows the app behind it \(String(format: "%.2f", ratio))× as strongly as it shows \
      its own words. Above 1 the browser page is the stronger mark on this surface, which is what \
      "the page text and the chat text interleave" is when it is measured. Raise `InkGlass.scrim`; \
      note that swapping `InkGlass.material` moves the identical quantity and moves it slightly \
      worse (see the header of InkGlass.swift), so it is not an alternative.
      """
    )

    // …and the panel must still be glass. Stated as its own floor so that a future edit cannot fix
    // legibility by quietly walking the scrim to opaque: this bound and the one above are the two
    // sides the ground is squeezed between, and a change that satisfies one by abandoning the other
    // should fail here rather than ship a white rectangle.
    XCTAssertGreaterThanOrEqual(
      InkGlass.backdropPassthrough, 0.20,
      """
      The panel passes only \(String(format: "%.1f", InkGlass.backdropPassthrough * 100))% of what \
      is behind it. Below a fifth this stops reading as a floating surface at all, which is the \
      product decision the material exists to serve.
      """
    )
  }

  /// The ground model itself, checked against the hardware samples `InkGlass` publishes.
  ///
  /// The arithmetic above is only worth anything if `InkGlass.ground(overBackdrop:)` is the surface
  /// the user actually gets. A glass panel cannot be rendered offscreen — `NSVisualEffectView` blends
  /// `.behindWindow` and a test process has no desktop behind its windows — so the model is the only
  /// route to a guard, and the model has to be pinned to something real. These are the two figures
  /// `InkGlass` sampled with `screencapture` over solid backdrops.
  func testTheModelledGroundMatchesWhatWasSampledOnHardware() {
    let surface = resolved(Ink.surface)
    // Sampled at scrim 0 over a black desktop: the material's own ceiling, 136.2/255.
    let bare =
      InkGlass.measuredMaterialTint * InkGlass.measuredMaterialOpacity * 255
    XCTAssertEqual(
      bare, 136.2, accuracy: 3.0,
      "The material model no longer reproduces the 136.2/255 sampled at scrim zero over black.")
    // The surface the scrim is made of must really be white in the pinned appearance, or the ground
    // function's single-channel form is measuring a colour the panel does not draw.
    XCTAssertEqual(
      surface.redComponent, 1.0, accuracy: 0.01,
      "Ink.surface no longer resolves white in the glass's pinned appearance.")
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

/// The same claim as `GlassLegibilityTests`' interference bound, made through the renderer instead of
/// through arithmetic — over a **bright**, a **dark** and a **busy** ground.
///
/// The arithmetic guard is a function of four numbers and would keep passing if a call site drew this
/// app's prose in something fainter than the rung those numbers were solved for. This hosts the
/// production type — the real colour `OmiMarkdown` hands its assistant prose, at the real `InkType`
/// role — over a modelled ground and reads the pixels back, so what is asserted is what the renderer
/// draws.
///
/// **The busy ground is the whole point.** Bright and dark are flat, and every flat ground passed even
/// on the panel that shipped unreadable; the defect only exists once one panel spans both. So the busy
/// backdrop is the shape from the tester's frames — a white page with a dark hero banner across it —
/// and the assertion on it is not a contrast ratio but an amplitude comparison.
@MainActor
final class GlassGroundInterferenceRenderTests: XCTestCase {

  /// What is behind the window. Bright and dark bound the range; busy is the case that broke.
  private enum Backdrop: String, CaseIterable {
    case bright, dark, busy

    /// The backdrop's own brightness at a row, as a fraction of white.
    func tone(row: Int, of height: Int) -> CGFloat {
      switch self {
      case .bright: return 1
      case .dark: return 0
      case .busy:
        // A dark hero banner across the middle third of an otherwise white page.
        let third = height / 3
        return (row >= third && row < third * 2) ? 0.02 : 1
      }
    }
  }

  private static let size = NSSize(width: 300, height: 210)

  private func resolved(_ color: Color) -> NSColor {
    var out = NSColor(color)
    InkGlass.appearance.performAsCurrentDrawingAppearance {
      out = NSColor(color).usingColorSpace(.sRGB) ?? out
    }
    return out.usingColorSpace(.sRGB) ?? out
  }

  private func contrast(_ a: CGFloat, _ b: CGFloat) -> CGFloat {
    let l1 = InkGlass.luminance(a)
    let l2 = InkGlass.luminance(b)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
  }

  /// The ground this app actually draws, row by row, straight from `InkGlass`.
  private func groundTone(_ backdrop: Backdrop, row: Int, height: Int) -> CGFloat {
    InkGlass.ground(
      overBackdrop: backdrop.tone(row: row, of: height),
      surfaceTone: resolved(Ink.surface).redComponent)
  }

  /// The ground as an image, so a real view can be composited over a real surface.
  private func groundImage(_ backdrop: Backdrop, size: NSSize) -> NSImage {
    let width = Int(size.width)
    let height = Int(size.height)
    let image = NSImage(size: size)
    image.lockFocus()
    for row in 0..<height {
      let tone = groundTone(backdrop, row: row, height: height)
      NSColor(srgbRed: tone, green: tone, blue: tone, alpha: 1).setFill()
      // AppKit's origin is bottom-left; rows are counted from the top so the banner lands where the
      // model says it does.
      NSBezierPath(rect: NSRect(x: 0, y: height - row - 1, width: width, height: 1)).fill()
    }
    image.unlockFocus()
    return image
  }

  /// Production prose, at a production role, in the colour production hands it.
  private func prose(_ color: Color) -> some View {
    Text(
      """
      MSG Entertainment's venues — including Madison Square Garden, Radio City Music Hall, \
      and the Beacon Theatre — all have shows running through August.
      """
    )
    .inkStyle(.prose, color: color)
    .frame(width: Self.size.width - 24, alignment: .leading)
    .padding(12)
  }

  private func render(_ view: some View, over backdrop: Backdrop) throws -> NSBitmapImageRep {
    let host = NSHostingView(
      rootView: view.frame(width: Self.size.width, height: Self.size.height))
    host.appearance = InkGlass.appearance
    host.frame = NSRect(origin: .zero, size: Self.size)

    let ground = NSImageView(frame: host.frame)
    ground.appearance = InkGlass.appearance
    ground.imageScaling = .scaleAxesIndependently
    ground.image = groundImage(backdrop, size: Self.size)
    ground.addSubview(host)
    ground.layoutSubtreeIfNeeded()

    let rep = try XCTUnwrap(ground.bitmapImageRepForCachingDisplay(in: ground.bounds))
    ground.cacheDisplay(in: ground.bounds, to: rep)
    return rep
  }

  /// Every pixel, paired with the ground the model says is under it.
  private func samples(_ rep: NSBitmapImageRep, _ backdrop: Backdrop) -> [(ground: CGFloat, ink: CGFloat)] {
    var out: [(CGFloat, CGFloat)] = []
    let scale = rep.pixelsHigh / Int(Self.size.height)
    for y in 0..<rep.pixelsHigh {
      let ground = groundTone(backdrop, row: y / max(scale, 1), height: Int(Self.size.height))
      for x in 0..<rep.pixelsWide {
        guard let color = rep.colorAt(x: x, y: y)?.usingColorSpace(.sRGB) else { continue }
        out.append((ground, color.redComponent))
      }
    }
    return out
  }

  // MARK: - The harness has to be measuring the surface it claims to

  /// **Read this before trusting either test below.** Everything here rests on the rendered ground
  /// being the ground `InkGlass` models; if `cacheDisplay` ever stopped capturing the backdrop, both
  /// tests would quietly measure black type on white paper and pass forever. So the harness proves
  /// itself first, on the bare ground with nothing drawn on it.
  func testTheHarnessRendersTheGroundInkGlassModels() throws {
    for backdrop in Backdrop.allCases {
      let rep = try render(Color.clear, over: backdrop)
      for (expected, rendered) in samples(rep, backdrop) {
        XCTAssertEqual(
          rendered, expected, accuracy: 0.02,
          """
          The harness rendered \(String(format: "%.3f", rendered)) where InkGlass models \
          \(String(format: "%.3f", expected)) over a \(backdrop.rawValue) backdrop. The offscreen \
          ground is not the panel's ground, so nothing measured on it means anything.
          """)
        return  // one row proves the pipeline; the rest is the same fill.
      }
    }
  }

  // MARK: - What the renderer actually produces

  /// Body prose clears AA against the ground under it on all three — including the busy one, where it
  /// always did. Kept because it is the claim people *think* covers this defect, and stating it
  /// alongside the one that does is the point: this passed on the broken panel too.
  func testProseClearsAAOnBrightDarkAndBusyGrounds() throws {
    for backdrop in Backdrop.allCases {
      let rep = try render(prose(OmiMarkdownContent.baseColor(for: .assistant)), over: backdrop)
      let ink = samples(rep, backdrop).filter { $0.ground - $0.ink > 0.25 }
      XCTAssertFalse(ink.isEmpty, "no prose rendered over a \(backdrop.rawValue) backdrop")

      // The glyph *body*, not its antialiased edge. A contrast bar is stated between a text colour
      // and a background colour, i.e. at full coverage; the fringe around a stroke is partially
      // covered by construction and is never what "the text colour" means. Taking the minimum over
      // every touched pixel measures the faintest fringe the rasteriser produced and reports 1.9:1
      // for type that is plainly black — so this reads the strongest ink, as `strongest(_:)` does in
      // `ShellStatusIconLegibilityTests` for the same reason.
      let body = ink.map { contrast($0.ground, $0.ink) }.max() ?? 0
      XCTAssertGreaterThanOrEqual(
        body, 4.5,
        """
        Chat prose measures \(String(format: "%.2f", body)):1 against its own local ground over a \
        \(backdrop.rawValue) backdrop.
        """)
    }
  }

  /// **The regression.** On the busy ground, the type's own amplitude has to be at least the ground's.
  ///
  /// At the scrim that shipped, the ground travelled further between the banner and the page than the
  /// prose travelled from the ground — 2.02× at the modelled extreme — so the strongest edges inside
  /// the panel belonged to the other application. Both quantities are read off the rendered bitmap.
  func testOnABusyGroundTheProseIsAStrongerMarkThanThePageBehindIt() throws {
    let rep = try render(prose(Ink.secondary), over: .busy)
    let all = samples(rep, .busy)

    // The ground's own travel across the panel, measured where nothing is drawn on it. The tolerance
    // is tight on purpose: at 0.02 it admits the outermost antialiased fringe around a glyph, which
    // is type rather than ground and drags the minimum down, reporting a ground that travels further
    // than it does.
    let bare = all.filter { abs($0.ground - $0.ink) <= 0.004 }.map { InkGlass.luminance($0.ink) }
    let backdropAmplitude = (bare.max() ?? 0) - (bare.min() ?? 0)

    // The type's travel from its ground, taken over the banner — the darkest ground, where the panel
    // is weakest and where the shipped surface failed.
    let banner = all.filter { $0.ground < InkGlass.ground(overBackdrop: 0.5) && $0.ground - $0.ink > 0.25 }
    XCTAssertFalse(banner.isEmpty, "no prose landed over the banner; the fixture moved")
    let typeAmplitude =
      banner.map { InkGlass.luminance($0.ground) - InkGlass.luminance($0.ink) }.max() ?? 0

    XCTAssertGreaterThanOrEqual(
      typeAmplitude, backdropAmplitude,
      """
      Across one panel the ground travels \(String(format: "%.3f", backdropAmplitude)) in luminance \
      while the prose on it travels \(String(format: "%.3f", typeAmplitude)). The page behind the \
      window is the stronger mark on this surface — which is the reported defect, measured. See \
      `InkGlass.scrim`.
      """)
  }
}

/// **A first-run card has to bring its own ground, because nothing else in the window has one.**
///
/// Every test above measures type against `Ink.surface` or against a modelled panel — it assumes a
/// ground exists and asks whether the ink on it is dark enough. That assumption is what broke here.
/// `ShellGlassGround` used to install an `InkGlassView` as the main window's `contentView`, so
/// *everything* floated on one full-bleed slab of glass and a first-run card could correctly draw
/// nothing but a wash (`glassCard` — `Ink.rowFill`, 4.5% of `labelColor`). When `ShellWindowChrome`
/// retired the slab, every other destination was handed its own panel (`PageGlassLane`) and onboarding
/// was not. A *darkening* wash over no ground leaves the ground the user's wallpaper: the reported
/// frame is near-black copy and near-black trust rows drawn straight onto a bright photograph of a
/// city, inside a faint rounded outline with nothing in it.
///
/// **Nothing above can see that**, because every assertion there composites onto `Ink.surface` — a
/// ground the broken card did not have. So there are two different claims here and they need two
/// different harnesses:
///
/// 1. **Is there a surface under the type at all?** Rendered over a raw desktop, where the card's own
///    ground is the whole of what separates this app's ink from the wallpaper.
/// 2. **Is the ink dark enough on the ground that surface produces?** Rendered over the *modelled*
///    ground, bright and dark, against the ordinary AA bar.
///
/// ## Why the two cannot be one test
///
/// **A glass panel cannot be rendered over a chosen backdrop offscreen.** `InkGlassBackdrop` is an
/// `NSVisualEffectView` blending `.behindWindow`; a test process has no desktop behind its windows, and
/// AppKit does not fall through to whatever the harness put underneath — it renders its own flat
/// substitute and hides the backdrop completely. An earlier version of this file tried to supply the
/// material as a backdrop image and let production draw the scrim on top; its self-check caught it
/// immediately, reporting the same ground over a black desktop and a white one. So (1) reads only the
/// *presence* of the surface, and (2) uses the modelled ground — the same technique, for the same
/// reason, as `GlassGroundInterferenceRenderTests` above.
@MainActor
final class OnboardingGlassGroundRenderTests: XCTestCase {

  /// What is behind the window. Bright stands for the photograph in the reported frame; dark is where
  /// near-black type on no ground disappears completely.
  private enum Desktop: String, CaseIterable {
    case bright, dark
    var tone: CGFloat { self == .bright ? 1 : 0 }
  }

  private static let size = NSSize(width: 320, height: 200)

  private func resolved(_ color: Color) -> NSColor {
    var out = NSColor(color)
    InkGlass.appearance.performAsCurrentDrawingAppearance {
      out = NSColor(color).usingColorSpace(.sRGB) ?? out
    }
    return out.usingColorSpace(.sRGB) ?? out
  }

  private func contrast(_ a: CGFloat, _ b: CGFloat) -> CGFloat {
    let l1 = InkGlass.luminance(a)
    let l2 = InkGlass.luminance(b)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
  }

  /// The ground the panel really draws over a desktop of a given brightness.
  private func modelledGround(_ desktop: Desktop) -> CGFloat {
    InkGlass.ground(
      overBackdrop: desktop.tone, surfaceTone: resolved(Ink.surface).redComponent)
  }

  /// The first step's copy, at the faintest rung the card carries.
  ///
  /// `Ink.secondary` because that is what `SBOnboardingView.omiRow` sets Omi's turn in, and what the
  /// `OPEN` / `PRIVATE` / `YOURS` tags on the reported frame are — the weakest thing on the surface, so
  /// the bound is evaluated where the card is weakest.
  private func copy(_ color: Color) -> some View {
    Text(
      """
      Hey, I'm Omi, your second brain. I hear your conversations, remember everything, and \
      handle the follow-ups. Three quick things:
      """
    )
    .inkStyle(.prose, color: color)
    .frame(width: Self.size.width - 56, alignment: .leading)
    .padding(28)
    .frame(width: Self.size.width, height: Self.size.height, alignment: .top)
  }

  /// Renders `view` over a flat tone and reads the bitmap back.
  private func render(_ view: some View, overTone tone: CGFloat) throws -> NSBitmapImageRep {
    let host = NSHostingView(
      rootView: view.frame(width: Self.size.width, height: Self.size.height))
    host.appearance = InkGlass.appearance
    host.frame = NSRect(origin: .zero, size: Self.size)

    let backdrop = NSView(frame: host.frame)
    backdrop.appearance = InkGlass.appearance
    backdrop.wantsLayer = true
    backdrop.layer?.backgroundColor =
      NSColor(srgbRed: tone, green: tone, blue: tone, alpha: 1).cgColor
    backdrop.addSubview(host)
    backdrop.layoutSubtreeIfNeeded()

    let rep = try XCTUnwrap(backdrop.bitmapImageRepForCachingDisplay(in: backdrop.bounds))
    backdrop.cacheDisplay(in: backdrop.bounds, to: rep)
    return rep
  }

  private func tones(_ rep: NSBitmapImageRep) -> [CGFloat] {
    var out: [CGFloat] = []
    for y in 0..<rep.pixelsHigh {
      for x in 0..<rep.pixelsWide {
        guard let color = rep.colorAt(x: x, y: y)?.usingColorSpace(.sRGB) else { continue }
        out.append(color.redComponent)
      }
    }
    return out
  }

  /// The surface's tone where no glyph is drawn on it: the mode of the rendered tones.
  ///
  /// The mode rather than the mean or the maximum — the frame is mostly bare surface with type over
  /// part of it, so the most common tone *is* the surface, while a mean is dragged down by the ink and
  /// a maximum would report the sheen's 1 pt specular line along the top edge.
  private func surfaceTone(_ rep: NSBitmapImageRep) -> CGFloat {
    var histogram: [Int: Int] = [:]
    for tone in tones(rep) { histogram[Int((tone * 255).rounded()), default: 0] += 1 }
    let peak = histogram.max { $0.value < $1.value }?.key ?? 0
    return CGFloat(peak) / 255
  }

  // MARK: - The harness has to be measuring what it claims to

  /// **The control.** With nothing grounding it, the harness really does show the desktop straight
  /// through — which is both the proof that the next test can see a missing ground, and the defect's
  /// whole mechanism in one line.
  func testWithoutACardTheDesktopComesStraightThrough() throws {
    for desktop in Desktop.allCases {
      let rendered = surfaceTone(try render(copy(Ink.secondary), overTone: desktop.tone))
      XCTAssertEqual(
        rendered, desktop.tone, accuracy: 0.02,
        """
        An ungrounded first-run column rendered \(String(format: "%.3f", rendered)) over a \
        \(desktop.rawValue) desktop. If the harness cannot show the bare desktop it cannot tell a \
        card that grounds itself from one that does not.
        """)
    }
  }

  // MARK: - (1) The defect: the card had no ground of its own

  /// **The regression, stated as the thing that was missing rather than as a contrast ratio.**
  ///
  /// Over a raw black desktop the card's own ground is the entire distance between this app's type and
  /// the user's wallpaper. A `glassCard` wash *darkens* — `Ink.rowFill` is 4.5% of `labelColor` — so
  /// the broken card renders a surface of about 0.02 there and the near-black copy on it is simply not
  /// present. `inkGlassPanel` lays the app's material and `InkGlass.scrim` of `Ink.surface` down
  /// instead.
  ///
  /// The bound is the design system's own number rather than one invented here: whatever a first-run
  /// card puts between the user and their desktop must be at least the ground the glass is specified to
  /// have (`InkGlass.groundAlpha`), because that is the ground every other panel in this app gets.
  /// The rendered value comfortably exceeds it, because `NSVisualEffectView`'s offscreen substitute is
  /// lighter than the material it stands in for — which is exactly why the *ratio* is measured against
  /// the modelled ground below and not against this one.
  func testTheCardPutsItsOwnGroundBetweenTheCopyAndTheDesktop() throws {
    let floor = InkGlass.groundAlpha(reduceTransparency: false)
    let rendered = surfaceTone(try render(copy(Ink.secondary).onboardingCard(), overTone: 0))

    XCTAssertGreaterThanOrEqual(
      rendered, floor - 0.03,
      """
      Over a black desktop the first-run card renders a surface of \
      \(String(format: "%.3f", rendered)) where the glass specifies at least \
      \(String(format: "%.3f", floor)). The card is not grounding itself — which is the reported \
      defect: a wash (`glassCard`) is the treatment for a card that already sits on a panel, and \
      since `ShellWindowChrome` retired the window's ground there is no panel under this one. Use \
      `onboardingCard()`, which is `inkGlassPanel`.
      """)
  }

  // MARK: - (2) …and the ink on that ground is dark enough, at both ends

  /// The faintest rung the card carries clears AA on the ground the panel draws, over a **bright** and
  /// a **dark** desktop alike.
  ///
  /// Both ends, because they fail in opposite directions and tuning against one of them is how this
  /// surface has been mistuned before: over a bright desktop near-black type is safe and it is the
  /// *panel* that disappears; over a dark one the panel is obvious and the type is what goes.
  func testTheCardsFaintestRungClearsAAOverABrightAndADarkDesktop() throws {
    for desktop in Desktop.allCases {
      let ground = modelledGround(desktop)
      let rep = try render(copy(Ink.secondary), overTone: ground)
      // The glyph *body*, not its antialiased fringe: a contrast bar is stated at full coverage, and
      // the partially-covered edge of a stroke is never what "the text colour" means. Same reason
      // `GlassGroundInterferenceRenderTests` reads the strongest ink.
      let ink = tones(rep).filter { ground - $0 > 0.15 }
      XCTAssertFalse(ink.isEmpty, "no copy rendered over a \(desktop.rawValue) desktop")

      let measured = ink.map { contrast(ground, $0) }.max() ?? 0
      XCTAssertGreaterThanOrEqual(
        measured, 4.5,
        """
        The card's faintest rung measures \(String(format: "%.2f", measured)):1 on the ground the \
        panel draws over a \(desktop.rawValue) desktop. A first-run screen is the one surface whose \
        reader has never seen the app work.
        """)
    }
  }
}
