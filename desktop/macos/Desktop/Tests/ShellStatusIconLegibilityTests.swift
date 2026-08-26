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
/// test process has no desktop behind its windows. So the ground is *modelled*, by
/// `InkGlass.ground(overBackdrop:surfaceTone:)`, for the two desktops that bound the range: solid black
/// and solid white. That function is `InkGlass`'s own, published for exactly this purpose and checked
/// against hardware by `GlassLegibilityTests`; this file used to carry a second copy of the arithmetic,
/// which is one more place for the modelled surface to drift from the drawn one. The control is then
/// hosted over that opaque ground and the pixels are read back, so what is asserted is what the
/// renderer draws, not what a token is named.
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

  /// The glass ground over one desktop, as an sRGB colour — `InkGlass`'s own model, per channel.
  private func ground(over desktop: Desktop) -> NSColor {
    let surface = resolved(Ink.surface)
    func channel(_ tone: CGFloat) -> CGFloat {
      InkGlass.ground(overBackdrop: desktop.backdrop, surfaceTone: tone)
    }
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
    _ systemImage: String, state: HomeStatusState, showsDot: Bool = true, isSelected: Bool = false
  ) -> some View {
    ShellStatusIconButton(
      systemImage: systemImage, tooltip: "probe", state: state, showsDot: showsDot,
      isSelected: isSelected, action: {})
  }

  /// Everything one control draws in one state, with the badge suppressed: the base glyph, plus the
  /// off-slash in the states that wear one. `showsDot: false` moves nothing but the dot, which is the
  /// contract `ShellStatusIconButton` documents on that flag.
  ///
  /// **`isSelected` is the experimental control, not a product state being asserted.** The button
  /// draws its glyph in `Ink.primary` when prominent and `Ink.secondary` otherwise, and `display` is
  /// mostly a large low-opacity interior — so ~34% of its pixels cross the mark threshold on that
  /// change alone (measured). Comparing a running control against a stopped one therefore compares
  /// two inks as well as two states, and on `display` the ink difference is the larger of the two. A
  /// comparison that varies one thing at a time pins prominence with this flag, which `isSelected`
  /// already feeds (`isSelected || isActive`), rather than inventing a second seam for it.
  private func silhouette(
    _ glyph: String, state: HomeStatusState, over desktop: Desktop, prominent: Bool = false
  ) throws -> Set<Pixel> {
    let rep = try render(
      button(glyph, state: state, showsDot: false, isSelected: prominent), over: desktop)
    return Set(marks(rep, over: desktop).map(\.0))
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

  /// Every pixel that visibly moves between two renders of the same control, and the largest move.
  ///
  /// Counted in ΔE against the same just-noticeable threshold `dotRender` uses, rather than by
  /// counting mark-threshold crossings, because on a filled glyph most of the off-slash lands where
  /// ink already was: `display` gains only 17 mark pixels but 134 pixels visibly move. A metric that
  /// only sees ink appear over bare ground would report the slash on `mic` and miss it on `display`.
  private func movement(_ before: NSBitmapImageRep, _ after: NSBitmapImageRep) -> (
    pixels: [Pixel], peak: CGFloat
  ) {
    var moved: [Pixel] = []
    var peak: CGFloat = 0
    for y in 0..<before.pixelsHigh {
      for x in 0..<before.pixelsWide {
        guard let a = before.colorAt(x: x, y: y)?.usingColorSpace(.sRGB),
          let b = after.colorAt(x: x, y: y)?.usingColorSpace(.sRGB)
        else { continue }
        let difference = deltaE(a, b)
        if difference > 2.5 {
          moved.append(Pixel(x: x, y: y))
          peak = max(peak, difference)
        }
      }
    }
    return (moved, peak)
  }

  /// Half the width of the band the off-slash occupies, in points — **derived from the production
  /// shape's own constants and the real symbol metrics**, so widening the mark widens the band the
  /// test allows it to occupy instead of turning this file red for the wrong reason.
  ///
  /// The extra point absorbs the antialiased edge and any subpixel disagreement between where SwiftUI
  /// centres the symbol and where `NSImage` reports its size.
  private func slashHalfWidth(_ glyph: String) -> CGFloat {
    let configuration = NSImage.SymbolConfiguration(pointSize: OmiType.body, weight: .semibold)
    let size =
      NSImage(systemSymbolName: glyph, accessibilityDescription: nil)?
      .withSymbolConfiguration(configuration)?.size ?? .zero
    let side = min(size.width, size.height) * ShellStatusSlash.extent
    let stroke = side * ShellStatusSlash.weight * (1 + 2 * ShellStatusSlash.clearance)
    return stroke / 2 + 1
  }

  /// Does this pixel lie on the diagonal the off-slash runs along?
  ///
  /// The slash is centred on the glyph and the glyph is centred in the canvas, so the diagonal is the
  /// canvas's own — top-leading to bottom-trailing, which in bitmap coordinates (y downward, as
  /// `colorAt` reads them) is the line `x - centre == y - centre`.
  private func isOnSlashDiagonal(_ pixel: Pixel, in rep: NSBitmapImageRep, halfWidth: CGFloat)
    -> Bool
  {
    let scale = CGFloat(rep.pixelsWide) / Self.canvas.width
    let dx = CGFloat(pixel.x) - CGFloat(rep.pixelsWide) / 2
    let dy = CGFloat(pixel.y) - CGFloat(rep.pixelsHigh) / 2
    return abs(dx - dy) / 2.0.squareRoot() <= halfWidth * scale
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
    let glyphs = [ShellStatusGlyph.listening, ShellStatusGlyph.screen]
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

  /// **A control's glyph is its name, and a name does not change when the thing is switched off — the
  /// off-slash is drawn *on top of* that name, never in place of it.**
  ///
  /// This test used to assert the stronger claim that the control looks *identical* in both toggle
  /// positions, because the defect it was written against was a glyph swap: the listening control drew
  /// `waveform` while transcribing and `mic` while idle, so the button appeared to become a different
  /// button and the user had to learn two shapes to recognise one control.
  ///
  /// **A slash is not that defect, and the change here is to say so precisely rather than to drop the
  /// guard.** Swapping `waveform` for `mic` *replaces* the silhouette; `ShellStatusSlash` *adds* to it.
  /// The underlying rule — the control must not become unrecognisable when it toggles — is unchanged,
  /// and it is now measured as the two things it actually consists of:
  ///
  /// - **the base survives**: nearly every pixel the running control draws is still drawn when it is
  ///   off, so the capability is still read from the same shape;
  /// - **the slash is additive**: the off state draws ink the on state does not, which is the whole
  ///   point of the mark.
  ///
  /// Only the first can regress into a swap, so only the first needs a calibrated floor. It is
  /// deliberately measured *against the on state* (`|on ∩ off| / |on|`) rather than as a Jaccard
  /// overlap, because Jaccard counts the slash's own pixels as disagreement and would punish the
  /// feature for existing.
  ///
  /// **The primary guard is still the type, not this test.** `ShellStatusGlyph.listening` is now a
  /// single constant with no state-dependent sibling left in the enum at all — `mic.slash` is gone —
  /// so a swap is unexpressible rather than merely untested, which is the order `AGENTS.md` asks for.
  /// What this adds is the rendered half the type cannot state, including that the button legitimately
  /// darkens its glyph when active (which makes both figures below conservative: the on state has
  /// antialiased edge pixels the off state does not, and they count against the base surviving).
  func testStoppingACapabilityMarksItsGlyphAndNeverRedrawsIt() throws {
    for desktop in Desktop.allCases {
      for glyph in [ShellStatusGlyph.listening, ShellStatusGlyph.screen] {
        // Prominence pinned on both sides — see `silhouette(_:state:over:prominent:)`. Without it
        // this compares two inks as well as two states, and on `display` the ink is the larger term.
        let running = try render(
          button(glyph, state: .active, showsDot: false, isSelected: true), over: desktop)
        let on = Set(marks(running, over: desktop).map(\.0))

        for state in [HomeStatusState.inactive, .blocked] {
          let stopped = try render(
            button(glyph, state: state, showsDot: false, isSelected: true), over: desktop)
          let off = Set(marks(stopped, over: desktop).map(\.0))
          let context = "\(glyph) went \(state) over a \(desktop.rawValue) desktop"

          // 1. Nothing is taken away. Measured at exactly zero on both controls and both desktops;
          //    the 2% allowance is for a renderer that antialiases the clearance differently, not
          //    for a glyph that has started redrawing itself.
          let lost = on.subtracting(off)
          XCTAssertLessThanOrEqual(
            CGFloat(lost.count), CGFloat(on.count) * 0.02,
            """
            \(context) and stopped drawing \(lost.count) of the \(on.count) pixels it draws while \
            running. The slash is supposed to be laid *over* the capability's name; a state that \
            erases the name is the `waveform`/`mic` swap coming back in another form.
            """)

          // 2. Everything that changed lies on the one diagonal the slash runs along. This is the
          //    claim that makes the first one meaningful: a glyph could preserve every pixel and
          //    still smear new ink across its whole area.
          let moved = movement(running, stopped)
          let strays = moved.pixels.filter {
            !isOnSlashDiagonal($0, in: stopped, halfWidth: slashHalfWidth(glyph))
          }
          XCTAssertLessThanOrEqual(
            CGFloat(strays.count), CGFloat(moved.pixels.count) * 0.05,
            """
            \(context) and \(strays.count) of the \(moved.pixels.count) pixels that changed are off \
            the slash's diagonal. Stopping a capability may add one mark to its glyph and must do \
            nothing else to it.
            """)

          // 3. The mark is actually there. `.blocked` and `.inactive` differ only in the dot, which
          //    is suppressed here, so both off states must move the same ink.
          XCTAssertGreaterThan(
            moved.peak, 25,
            """
            \(context) and the largest change to its glyph is ΔE \
            \(String(format: "%.1f", moved.peak)) — under the 25 this file already calls the bar \
            for two distinguishable glances. The off state is not marking the glyph at all.
            """)
        }
      }
    }
  }

  /// **Off has to read as off on both controls, over any wallpaper.** The reported symptom was that a
  /// coloured dot alone does not say "this is switched off" — so the slash is the readout now, and a
  /// slash under the non-text bar is the same non-report the dot was.
  ///
  /// All four combinations the cluster can be in are covered by construction: both controls, each in
  /// its running and not-running state, over both bounding desktops.
  ///
  /// The slash is isolated as the ink the off state adds to the on state. That difference is exact in
  /// the conservative direction: the button draws its glyph *darker* when active, so the on state
  /// contributes extra antialiased edge pixels and can only ever shrink what counts as added — a slash
  /// that measures here measures for real.
  func testTheOffStateAddsALegibleSlashToBothControlsOverBothDesktops() throws {
    for desktop in Desktop.allCases {
      for glyph in [ShellStatusGlyph.listening, ShellStatusGlyph.screen] {
        let on = try silhouette(glyph, state: .active, over: desktop)
        let offRep = try render(button(glyph, state: .inactive, showsDot: false), over: desktop)
        let added = marks(offRep, over: desktop).filter { !on.contains($0.0) }

        let mark = try XCTUnwrap(
          strongest(added, over: desktop),
          "\(glyph) draws nothing extra when it is off over a \(desktop.rawValue) desktop")
        let ratio = contrast(mark, ground(over: desktop))
        XCTAssertGreaterThanOrEqual(
          ratio, 3.0,
          """
          the off-slash on \(glyph) measures \(String(format: "%.2f", ratio)):1 over a \
          \(desktop.rawValue) desktop, under the 3:1 WCAG non-text bar. It is the mark that says \
          this capability is not running.
          """)
      }
    }
  }

  /// The two capture controls sit adjacent at 32 pt with near-identical weight, so if their glyphs
  /// share a silhouette the pair reads as one button drawn twice — which is what the reported
  /// screenshot showed. Compared as *rendered coverage* rather than by name: two different symbol
  /// names that draw the same wide filled slab are the same defect.
  ///
  /// **Measured in both states, because the off state deliberately puts the *same* slash on both
  /// controls.** One vocabulary, one mark per state — so the shared mark is the feature, and the open
  /// question is whether it swamps the two names underneath it. It does not: the pair measures 0.299
  /// shared while running and 0.309 while off, so adding the slash to both costs one point of
  /// distinctness and the capability still reads from the glyph.
  ///
  /// **This assertion only works beside the one above it, and the bar is set to say so.** The shipped
  /// pair measured 0.56 *while listening* (`waveform` against
  /// `rectangle.inset.filled.and.person.filled`, both wide horizontal masses) but only 0.31 at rest —
  /// so a silhouette check on one state alone would have passed on the broken shape. It is the base
  /// glyph being stable across states that makes this one measurement stand for every state, which is
  /// why 0.45 sits below the both-on figure rather than below the resting one.
  func testTheTwoCaptureControlsDoNotShareASilhouette() throws {
    for state in [HomeStatusState.active, .inactive] {
      let listening = try silhouette(ShellStatusGlyph.listening, state: state, over: .black)
      let screen = try silhouette(ShellStatusGlyph.screen, state: state, over: .black)
      let shared =
        CGFloat(listening.intersection(screen).count)
        / CGFloat(max(listening.union(screen).count, 1))
      XCTAssertLessThan(
        shared, 0.45,
        """
        while \(state), the microphone and screen glyphs cover \(Int(shared * 100))% of the same \
        pixels — adjacent wordless controls that share a silhouette read as one capability, not two.
        """)
    }
  }

  // MARK: - The sentence the marks are short for

  /// **A wordless control's tooltip is its label, so it has to start by being the label.**
  ///
  /// The shipped strings opened with the state — "Listening — In meeting", "Not listening. Click to
  /// start." — which answers a question you can only be asking if you already know which of the two
  /// icons you are pointing at. The screen control at least contained the word "screen"; the audio
  /// control never named its capability in any state. On a cluster whose premise is that the labels
  /// were deleted, that leaves the capability nameable only by recognising the glyph, which is exactly
  /// the fallback the tooltip exists to remove.
  ///
  /// Asserts the property rather than the prose: every state of both controls opens with the
  /// capability's name, so no future state can be added that forgets to.
  func testEveryTooltipOpensWithTheNameOfItsCapability() {
    for state in [HomeStatusState.active, .inactive, .blocked] {
      let audio = ShellStatusTooltip.audio(state: state, mode: "In meeting", next: "Off")
      XCTAssertTrue(
        audio.hasPrefix("Audio"),
        """
        the \(state) audio tooltip reads "\(audio)" — it never says what the control is. Hovering a \
        wordless icon has to answer "which capability is this", not only "what is it doing".
        """)

      let screen = ShellStatusTooltip.screen(state: state)
      XCTAssertTrue(
        screen.hasPrefix("Screen"),
        """
        the \(state) screen tooltip reads "\(screen)" — it never says what the control is.
        """)
    }
  }

  /// Naming the capability must not cost the qualifier. "Listening" with no mode is a claim the
  /// meetings-only mode does not actually make, so the mode still has to survive into the sentence.
  func testTheRunningAudioTooltipStillCarriesItsCaptureMode() {
    let tooltip = ShellStatusTooltip.audio(state: .active, mode: "Meetings only", next: "Off")
    XCTAssertTrue(
      tooltip.contains("Meetings only"),
      """
      the running audio tooltip reads "\(tooltip)" and has dropped its capture mode — unqualified \
      "listening" overclaims whenever the mode is armed rather than live.
      """)
  }

  func testTheAwaitingMeetingAudioTooltipDoesNotClaimOffOrStart() {
    let tooltip = ShellStatusTooltip.audio(
      state: .inactive, mode: "Only Meetings", isAwaitingMeeting: true,
      next: CaptureListeningLogic.audioRecordingModeTitle(
        CaptureListeningLogic.nextAudioRecordingMode(after: .onlyMeetings)))
    XCTAssertTrue(tooltip.hasPrefix("Audio"))
    XCTAssertTrue(tooltip.contains("waiting for a call"))
    XCTAssertTrue(tooltip.contains("Only Meetings"))
    XCTAssertTrue(tooltip.contains("Click for Off"))
    XCTAssertFalse(
      tooltip.contains("Click to start"),
      "An armed Only Meetings wait is not off; clicking turns listening off, it does not start it.")
  }
}
