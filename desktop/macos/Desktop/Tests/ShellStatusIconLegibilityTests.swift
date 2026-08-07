import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// The top bar's wordless controls, measured on the ground they are actually drawn on.
///
/// `ShellStatusIcons.swift` states the contract these controls live or die by: the label was removed
/// and its job handed to a **state dot**, so the dot is not decorative — it is the entire readout.
/// That claim is only true if the dot is legible, and "legible" is a number, not an opinion. What
/// shipped was not:
///
/// | mark | black desktop | white desktop |
/// |---|---|---|
/// | dot, on | 2.66:1 | 2.00:1 |
/// | dot, off | 2.57:1 | 1.57:1 |
/// | dot, blocked | 2.54:1 | 3.22:1 |
///
/// Five of six under the 3:1 bar — and worse than the individual figures, over a black desktop all
/// three states landed within 5% of each other, because the strongest thing in the badge was its
/// near-white *ring* and the state colour inside it had been shrunk to 3.5 pt by a `strokeBorder`
/// drawn on the fill's own frame. Three states, one glance. The reported symptom was "the icons are
/// not clear enough"; the measurable defect was that the icons had no working state readout at all.
///
/// **A glass panel cannot be rendered offscreen** — `NSVisualEffectView` blends `.behindWindow` and a
/// test process has no desktop behind its windows. So the ground is *modelled* from the same measured
/// constants `InkGlass` publishes for exactly this purpose (`measuredMaterialOpacity`,
/// `measuredMaterialTint`, `scrim`), for the two desktops that bound the range: solid black and solid
/// white. The model reproduces `InkGlass`'s own published table (black desktop → 152/255 against the
/// 154/255 it sampled on hardware). The control is then hosted over that opaque ground and the pixels
/// are read back, so what is asserted is what the renderer draws, not what a token is named.
///
/// Bars: **3:1**, WCAG 2.1 SC 1.4.11 non-text contrast — every mark here is a graphic that carries
/// meaning. Separability of the three states is **CIE ΔE\*ab ≥ 25**, because "is this green or is it
/// grey" is a colour-difference question and a luminance ratio answers a different one.
@MainActor
final class ShellStatusIconLegibilityTests: XCTestCase {

  /// `CGPoint` only became `Hashable` in macOS 15 and the deployment floor is 14.
  private struct Pixel: Hashable {
    let x: Int
    let y: Int
  }

  // MARK: - The ground

  /// The desktops that bound the range. Everything a user can put behind this window composites
  /// between these two, so a mark that clears both clears every wallpaper.
  private enum Desktop: String, CaseIterable {
    case black
    case white

    var backdrop: CGFloat { self == .black ? 0 : 1 }
  }

  /// The glass ground over one desktop, as an sRGB colour.
  ///
  /// Two layers, in the order the window draws them: the material over the desktop, then
  /// `InkGlass.scrim` of `Ink.surface` over that. The material's opacity and tint are measurements
  /// `InkGlass` took on real hardware precisely so a contrast guard can be arithmetic rather than a
  /// screenshot.
  private func ground(over desktop: Desktop) -> NSColor {
    let material =
      InkGlass.measuredMaterialTint * InkGlass.measuredMaterialOpacity
      + desktop.backdrop * (1 - InkGlass.measuredMaterialOpacity)
    let surface = resolved(Ink.surface)
    let scrim = InkGlass.scrim
    func channel(_ tint: CGFloat) -> CGFloat { tint * scrim + material * (1 - scrim) }
    return NSColor(
      srgbRed: channel(surface.redComponent),
      green: channel(surface.greenComponent),
      blue: channel(surface.blueComponent),
      alpha: 1)
  }

  /// Resolves a SwiftUI `Color` to sRGB **in the appearance the glass pins** (`InkGlass.appearance`).
  /// Outside it, `Ink`'s dynamic colours answer for whatever appearance the test host happens to be in.
  private func resolved(_ color: Color) -> NSColor {
    var out = NSColor(color)
    InkGlass.appearance.performAsCurrentDrawingAppearance {
      out = NSColor(color).usingColorSpace(.sRGB) ?? out
    }
    return out.usingColorSpace(.sRGB) ?? out
  }

  // MARK: - Contrast and colour difference

  private func relativeLuminance(_ color: NSColor) -> CGFloat {
    func linear(_ c: CGFloat) -> CGFloat {
      c <= 0.03928 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
    }
    return 0.2126 * linear(color.redComponent)
      + 0.7152 * linear(color.greenComponent)
      + 0.0722 * linear(color.blueComponent)
  }

  private func contrast(_ a: NSColor, _ b: NSColor) -> CGFloat {
    let l1 = relativeLuminance(a)
    let l2 = relativeLuminance(b)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
  }

  /// CIE L\*a\*b\*, D65. Needed because the states differ by **hue** as much as by lightness, and a
  /// WCAG ratio — which is a function of luminance only — reports green-on-grey as 1.28:1 while a
  /// person sees two obviously different colours. Contrast answers "can I see this mark"; ΔE answers
  /// "is this the same mark as that one", and the dot has to pass both questions.
  private func lab(_ color: NSColor) -> (CGFloat, CGFloat, CGFloat) {
    func linear(_ c: CGFloat) -> CGFloat {
      c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
    }
    let r = linear(color.redComponent)
    let g = linear(color.greenComponent)
    let b = linear(color.blueComponent)
    // sRGB → XYZ (D65), then normalised by the D65 white point.
    let x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    let y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    let z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    func f(_ t: CGFloat) -> CGFloat {
      t > 0.008856 ? pow(t, 1.0 / 3.0) : (7.787 * t + 16.0 / 116.0)
    }
    return (116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z)))
  }

  private func deltaE(_ a: NSColor, _ b: NSColor) -> CGFloat {
    let first = lab(a)
    let second = lab(b)
    return sqrt(
      pow(first.0 - second.0, 2) + pow(first.1 - second.1, 2) + pow(first.2 - second.2, 2))
  }

  // MARK: - Rendering

  /// The canvas one control is rendered into. Wider than the 32 pt button so the dot — an overlay
  /// that deliberately rides outside the button's own bounds — is not clipped by the harness.
  private static let canvas = NSSize(width: 56, height: 56)

  /// Renders a view over an opaque glass ground and returns the bitmap.
  ///
  /// The host is pinned to `InkGlass.appearance` for the same reason `resolved` is: every colour in
  /// this cluster is dynamic, and an unpinned host measures the machine rather than the product.
  private func render(_ view: some View, over desktop: Desktop) throws -> NSBitmapImageRep {
    let host = NSHostingView(
      rootView: view.frame(width: Self.canvas.width, height: Self.canvas.height))
    host.appearance = InkGlass.appearance
    host.frame = NSRect(origin: .zero, size: Self.canvas)

    let backdrop = NSView(frame: host.frame)
    backdrop.appearance = InkGlass.appearance
    backdrop.wantsLayer = true
    backdrop.layer?.backgroundColor = ground(over: desktop).cgColor
    backdrop.addSubview(host)
    backdrop.layoutSubtreeIfNeeded()

    let rep = try XCTUnwrap(backdrop.bitmapImageRepForCachingDisplay(in: backdrop.bounds))
    backdrop.cacheDisplay(in: backdrop.bounds, to: rep)
    return rep
  }

  private func button(
    _ systemImage: String, state: HomeStatusState, showsDot: Bool = true
  ) -> some View {
    ShellStatusIconButton(
      systemImage: systemImage, tooltip: "probe", state: state, showsDot: showsDot, action: {})
  }

  // MARK: - Reading marks back out of the bitmap

  private func pixels(_ rep: NSBitmapImageRep) -> [(Pixel, NSColor)] {
    var out: [(Pixel, NSColor)] = []
    for y in 0..<rep.pixelsHigh {
      for x in 0..<rep.pixelsWide {
        guard let color = rep.colorAt(x: x, y: y)?.usingColorSpace(.sRGB) else { continue }
        out.append((Pixel(x: x, y: y), color))
      }
    }
    return out
  }

  /// Every pixel that is a **mark** rather than the ground or a wash on it.
  ///
  /// Qualified by contrast rather than by raw distance, because the button's own active fill
  /// (`Ink.wash`, 0.06 on the label colour) is a real difference from the ground and is emphatically
  /// not a mark — including it would let a control pass this file by tinting its background.
  private func marks(_ rep: NSBitmapImageRep, over desktop: Desktop) -> [(Pixel, NSColor)] {
    let ground = ground(over: desktop)
    return pixels(rep).filter { contrast($0.1, ground) >= 1.5 || deltaE($0.1, ground) >= 20 }
  }

  /// Exactly the pixels the state dot is responsible for, and the render they came from.
  ///
  /// Isolated by **difference** — the same control rendered with and without its dot — rather than by
  /// carving out a corner of the frame. A geometric window has to guess where the badge lands, and a
  /// guess that clips one edge silently under-reports the badge's size, which is the very quantity
  /// under test. The difference is exact and stays exact if anyone moves the dot.
  ///
  /// It is also the only way to read the *hollow* state honestly: "off" draws nothing but a ring, so
  /// its interior is identical in both renders and correctly does not count as ink.
  private func dotRender(_ glyph: String, state: HomeStatusState, over desktop: Desktop) throws -> (
    rep: NSBitmapImageRep, marks: [(Pixel, NSColor)]
  ) {
    let shown = try render(button(glyph, state: state, showsDot: true), over: desktop)
    let hidden = try render(button(glyph, state: state, showsDot: false), over: desktop)
    var out: [(Pixel, NSColor)] = []
    for y in 0..<shown.pixelsHigh {
      for x in 0..<shown.pixelsWide {
        guard let a = shown.colorAt(x: x, y: y)?.usingColorSpace(.sRGB),
          let b = hidden.colorAt(x: x, y: y)?.usingColorSpace(.sRGB)
        else { continue }
        // Just above a just-noticeable difference, so the badge's antialiased edge is included and
        // identical pixels are not.
        if deltaE(a, b) > 2.5 { out.append((Pixel(x: x, y: y), a)) }
      }
    }
    return (shown, out)
  }

  /// Everything the glyph draws — every mark that is not the dot's.
  private func glyphMarks(_ rep: NSBitmapImageRep, dot: [(Pixel, NSColor)], over desktop: Desktop)
    -> [(Pixel, NSColor)]
  {
    let claimed = Set(dot.map(\.0))
    return marks(rep, over: desktop).filter { !claimed.contains($0.0) }
  }

  /// The mark furthest from the ground — the one a glance actually lands on.
  private func strongest(_ marks: [(Pixel, NSColor)], over desktop: Desktop) -> NSColor? {
    let ground = ground(over: desktop)
    return marks.map(\.1).max { contrast($0, ground) < contrast($1, ground) }
  }

  /// The widest horizontal run across a set of pixels, in points.
  private func widestRun(_ marks: [(Pixel, NSColor)], in rep: NSBitmapImageRep) -> CGFloat {
    guard !marks.isEmpty else { return 0 }
    let pixelScale = CGFloat(rep.pixelsWide) / Self.canvas.width
    var widest: CGFloat = 0
    for row in Set(marks.map(\.0.y)) {
      let xs = marks.filter { $0.0.y == row }.map(\.0.x)
      guard let lo = xs.min(), let hi = xs.max() else { continue }
      widest = max(widest, CGFloat(hi - lo + 1) / pixelScale)
    }
    return widest
  }

  /// The colour at the centre of the dot — the fill, which is what names the state.
  private func dotCentre(_ rep: NSBitmapImageRep, dot: [(Pixel, NSColor)]) throws -> NSColor {
    let xs = dot.map(\.0.x)
    let ys = dot.map(\.0.y)
    guard let minX = xs.min(), let maxX = xs.max(), let minY = ys.min(), let maxY = ys.max() else {
      return try XCTUnwrap(nil as NSColor?, "the dot drew nothing")
    }
    return try XCTUnwrap(
      rep.colorAt(x: (minX + maxX) / 2, y: (minY + maxY) / 2)?.usingColorSpace(.sRGB))
  }

  // MARK: - The dot is the readout, so the dot has to be readable

  /// **The load-bearing claim of the whole cluster.** The header says a wordless control is on when
  /// its dot is filled green, off when it is hollow and blocked when it is filled red — so all three
  /// have to be visible marks, on both desktops. A badge under 3:1 is not a quiet report, it is no
  /// report at all, and a control with no report is the label this design removed coming back as a
  /// tooltip nobody hovers.
  func testEveryStateOfTheDotClearsTheNonTextContrastBarOnBothDesktops() throws {
    for desktop in Desktop.allCases {
      for state in [HomeStatusState.active, .inactive, .blocked] {
        let dot = try dotRender(ShellStatusGlyph.listening, state: state, over: desktop)
        let mark = try XCTUnwrap(
          strongest(dot.marks, over: desktop),
          "the \(state) dot drew nothing over a \(desktop.rawValue) desktop")
        let ratio = contrast(mark, ground(over: desktop))
        XCTAssertGreaterThanOrEqual(
          ratio, 3.0,
          """
          the \(state) dot measures \(String(format: "%.2f", ratio)):1 over a \(desktop.rawValue) \
          desktop, under the 3:1 WCAG non-text bar. This dot is the control's only state readout.
          """)
      }
    }
  }

  /// The three states have to be three *colours*, not three weights of one.
  ///
  /// Compared at the dot's centre, which is the fill, and in ΔE rather than in contrast: over a black
  /// desktop the shipped badge measured 2.54 / 2.57 / 2.66:1 for blocked / off / on — a 5% spread,
  /// because what a glance landed on was the ring all three shared. Whatever the ring does, the fill
  /// underneath it must still be able to answer "which state".
  func testOnOffAndBlockedAreThreeDistinguishableGlances() throws {
    for desktop in Desktop.allCases {
      var centre: [HomeStatusState: NSColor] = [:]
      for state in [HomeStatusState.active, .inactive, .blocked] {
        let dot = try dotRender(ShellStatusGlyph.listening, state: state, over: desktop)
        centre[state] = try dotCentre(dot.rep, dot: dot.marks)
      }
      for (a, b) in [
        (HomeStatusState.active, HomeStatusState.inactive),
        (.active, .blocked),
        (.inactive, .blocked),
      ] {
        guard let first = centre[a], let second = centre[b] else { continue }
        let difference = deltaE(first, second)
        XCTAssertGreaterThanOrEqual(
          difference, 25,
          """
          the \(a) and \(b) dots differ by ΔE \(String(format: "%.1f", difference)) over a \
          \(desktop.rawValue) desktop — two names for one glance.
          """)
      }
    }
  }

  /// The dot has to be as big on screen as the layout reserves for it.
  ///
  /// It shipped smaller than it reads in source: the ring was `strokeBorder` on the **fill's own**
  /// frame, and `strokeBorder` insets — so a 1.5 pt ring on a 6.5 pt circle left 3.5 pt of colour
  /// inside a 9.5 pt slot. Measured off the pixels in both directions, so neither the badge nor the
  /// colour inside it can shrink again while the source keeps claiming the old numbers.
  ///
  /// Read on `.blocked`, the one filled state that does not also switch the button to its active
  /// wash — so what is measured is the badge and nothing behind it.
  func testTheDotAndItsColouredCoreAreAsWideOnScreenAsTheSourceClaims() throws {
    let render = try dotRender(ShellStatusGlyph.listening, state: .blocked, over: .black)
    let dot = render.marks
    let rep = render.rep

    let outer = ShellStatusDot.diameter + ShellStatusDot.ringWidth * 2
    let rendered = widestRun(dot, in: rep)
    XCTAssertGreaterThanOrEqual(
      rendered, outer - 0.5,
      """
      the state dot renders \(String(format: "%.1f", rendered)) pt across but reserves \
      \(outer) pt. A ring drawn inside the fill's own bounds shrinks the fill it is supposed to \
      separate; draw it outside so the diameter in the source is the diameter on screen.
      """)

    // The coloured core, isolated by hue: `Ink.errorRed` is the only strongly red thing in the frame.
    let core = dot.filter { $0.1.redComponent - $0.1.greenComponent > 0.3 }
    let coreWidth = widestRun(core, in: rep)
    XCTAssertGreaterThanOrEqual(
      coreWidth, ShellStatusDot.diameter - 0.5,
      """
      the dot's coloured core renders \(String(format: "%.1f", coreWidth)) pt across against the \
      \(ShellStatusDot.diameter) pt the source declares. The state colour is the only thing that \
      says *which* state; a ring that eats it leaves three states wearing one badge.
      """)
  }

  // MARK: - The glyph names the control; the dot never does

  /// The glyph must clear the non-text bar too, in every form it can take. It is the only thing that
  /// says *which* capability this is, and the two controls sit adjacent.
  func testEveryGlyphClearsTheNonTextContrastBarOnBothDesktops() throws {
    let glyphs = [
      ShellStatusGlyph.listening, ShellStatusGlyph.listeningBlocked, ShellStatusGlyph.screen,
    ]
    for desktop in Desktop.allCases {
      for glyph in glyphs {
        let rep = try render(button(glyph, state: .inactive, showsDot: false), over: desktop)
        let mark = try XCTUnwrap(
          strongest(marks(rep, over: desktop), over: desktop),
          "\(glyph) drew nothing over a \(desktop.rawValue) desktop")
        let ratio = contrast(mark, ground(over: desktop))
        XCTAssertGreaterThanOrEqual(
          ratio, 3.0,
          """
          the \(glyph) glyph measures \(String(format: "%.2f", ratio)):1 over a \
          \(desktop.rawValue) desktop, under the 3:1 WCAG non-text bar.
          """)
      }
    }
  }

  /// **A control's glyph is its name, and a name does not change when the thing is switched off.**
  ///
  /// The listening control drew `waveform` while transcribing and `mic` while idle — the dot's job
  /// done a second time and done worse, because the two glyphs have different silhouettes: the button
  /// appeared to become a different button when it changed state, and the user had to learn two
  /// shapes to recognise one control.
  ///
  /// **The primary guard is the type, not this test.** `ShellStatusGlyph.listeningGlyph(isBlocked:)`
  /// cannot see whether transcription is running, so the rule is unexpressible rather than merely
  /// untested — which is the order `AGENTS.md` asks for. What this adds is the *rendered* half the
  /// signature cannot state: that the control genuinely looks the same in both toggle positions
  /// through the real button, including the fact that the button legitimately darkens its glyph when
  /// active. A future edit that reaches for a differently-named symbol drawing the same thing passes;
  /// one that changes the shape does not.
  func testTheListeningControlKeepsItsSilhouetteWhenItIsSwitchedOn() throws {
    func silhouette(_ state: HomeStatusState) throws -> Set<Pixel> {
      let dot = try dotRender(
        ShellStatusGlyph.listeningGlyph(isBlocked: false), state: state, over: .black)
      return Set(glyphMarks(dot.rep, dot: dot.marks, over: .black).map(\.0))
    }
    let off = try silhouette(.inactive)
    let on = try silhouette(.active)
    let shared = CGFloat(off.intersection(on).count) / CGFloat(max(off.union(on).count, 1))
    XCTAssertGreaterThan(
      shared, 0.9,
      """
      the listening glyph covers only \(Int(shared * 100))% of the same pixels when the control is \
      on as when it is off — it is redrawing itself to report state, which is the dot's job.
      """)
  }

  /// The two capture controls sit adjacent at 32 pt with near-identical weight, so if their glyphs
  /// share a silhouette the pair reads as one button drawn twice — which is what the reported
  /// screenshot showed. Compared as *rendered coverage* rather than by name: two different symbol
  /// names that draw the same wide filled slab are the same defect.
  ///
  /// **This assertion only works beside the one above it, and the bar is set to say so.** The shipped
  /// pair measured 0.56 *while listening* (`waveform` against
  /// `rectangle.inset.filled.and.person.filled`, both wide horizontal masses) but only 0.31 at rest —
  /// so a silhouette check on the resting pair alone would have passed on the broken shape. It is the
  /// glyph being *stable* that makes one measurement stand for every state, which is why 0.45 sits
  /// below the both-on figure rather than below the resting one.
  func testTheTwoCaptureControlsDoNotShareASilhouette() throws {
    func silhouette(_ glyph: String) throws -> Set<Pixel> {
      let rep = try render(button(glyph, state: .inactive, showsDot: false), over: .black)
      return Set(marks(rep, over: .black).map(\.0))
    }
    let listening = try silhouette(ShellStatusGlyph.listening)
    let screen = try silhouette(ShellStatusGlyph.screen)
    let shared =
      CGFloat(listening.intersection(screen).count) / CGFloat(max(listening.union(screen).count, 1))
    XCTAssertLessThan(
      shared, 0.45,
      """
      the microphone and screen glyphs cover \(Int(shared * 100))% of the same pixels — adjacent \
      wordless controls that share a silhouette read as one capability, not two.
      """)
  }
}
