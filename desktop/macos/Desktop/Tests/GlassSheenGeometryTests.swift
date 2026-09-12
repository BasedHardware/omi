import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// The glass sheen is a highlight *on* the panel's top edge, and these guard the one thing that can
/// silently stop being true: where the line is allowed to be.
///
/// The reported defect was a bright white line hanging above the chat transcript's jump-to-latest
/// disc. Nothing logged and nothing crashed — the sheen was a full-width 1 pt band relying on the
/// panel's `clipShape` to trim it, and on a disc (`cornerRadius` at half the side) a clip does not
/// trim a straight band into an arc, it leaves the chord across the top of the circle. The chord sat
/// over a 1 pt sliver of ground, so it read as a detached line rather than as an edge catching light.
@MainActor
final class GlassSheenGeometryTests: XCTestCase {

  // MARK: - The rule

  /// A disc has no straight top edge, so it gets no straight highlight. This is the reported case.
  func testADiscGetsNoSheenBecauseItHasNoFlatTopEdge() {
    XCTAssertEqual(
      InkGlass.sheenWidth(panelSize: CGSize(width: 32, height: 32), cornerRadius: 16), 0,
      "a disc's top edge is entirely curve; any straight line drawn across it is the floating chord")
  }

  /// A card's highlight spans the run between its corners — not the full width, which is what carried
  /// the line into the curve in the first place.
  func testACardsSheenSpansTheRunBetweenItsCorners() {
    let size = CGSize(width: 400, height: 200)
    XCTAssertEqual(InkGlass.sheenWidth(panelSize: size, cornerRadius: 22), 400 - 44)
    XCTAssertEqual(
      InkGlass.sheenWidth(panelSize: size, cornerRadius: 0), 400,
      "a square-cornered panel is all flat top edge")
  }

  /// **The case that makes this a clamp rather than a subtraction.** Several call sites ask for a
  /// stadium with `cornerRadius: 999`; the shape resolves that to half the height, and so must this,
  /// or every pill in the app loses the highlight its flat top actually has.
  func testAStadiumAskingFor999KeepsTheRunItsFlatTopHas() {
    let bar = CGSize(width: 300, height: 38)
    XCTAssertEqual(
      InkGlass.sheenWidth(panelSize: bar, cornerRadius: 999), 300 - 38,
      "measured on the requested radius instead of the resolved one, a pill's run goes negative and "
        + "the highlight disappears from surfaces that never had the defect")
    XCTAssertEqual(
      InkGlass.sheenWidth(panelSize: bar, cornerRadius: 19), 300 - 38,
      "the stadium and its explicit-radius twin are the same shape and must get the same line")
  }

  /// Never negative, whatever a caller passes.
  func testTheRunIsNeverNegative() {
    XCTAssertEqual(InkGlass.sheenWidth(panelSize: CGSize(width: 10, height: 80), cornerRadius: 999), 0)
    XCTAssertEqual(InkGlass.sheenWidth(panelSize: .zero, cornerRadius: 12), 0)
    XCTAssertEqual(
      InkGlass.sheenWidth(panelSize: CGSize(width: 40, height: 40), cornerRadius: -5), 40,
      "a negative radius is a square corner, not a run wider than the panel")
  }

  // MARK: - …and the rule really reaches the pixels

  /// The defect as the user saw it: a bright run across the top of the disc.
  ///
  /// Both tones are **measured by this harness in this run** rather than written down. An offscreen
  /// `NSVisualEffectView` renders as a lighter substitute for the material it stands in for, so any
  /// absolute number here would be a property of the substitute; what is stable is the *gap* the
  /// sheen opens between its own row and the row under it. So a flat-topped panel supplies the two
  /// references — the tone of a sheen that is supposed to be there, and the ground beneath it — and
  /// the disc is then required to land on the ground side of the midpoint between them.
  ///
  /// The panels ask for `reduceTransparency: false` because the sheen is hidden under that setting by
  /// design: read from the machine, this case would pass on an accessibility-configured Mac while
  /// drawing nothing at all.
  func testTheDiscDoesNotWearTheLineAFlatToppedPanelWears() throws {
    let cardSize = CGSize(width: 120, height: 60)
    let card = try render(
      Color.clear.frame(width: cardSize.width, height: cardSize.height)
        .inkGlassPanel(cornerRadius: 0, shadow: nil, reduceTransparency: false),
      size: cardSize, overTone: 0.5)

    let sheenTone = try XCTUnwrap(brightness(card, x: card.pixelsWide / 2, y: 0))
    let groundTone = try XCTUnwrap(
      brightness(card, x: card.pixelsWide / 2, y: sheenBandRows(card, pointHeight: cardSize.height)))

    // **The control.** Without it, "the disc has no bright line" is also what a harness that renders
    // no sheen at all reports, and the case would survive the highlight being deleted outright.
    XCTAssertGreaterThan(
      sheenTone, groundTone + 0.02,
      "the harness cannot see a specular line on a panel that has one, so it cannot miss one either")

    let discSize = CGSize(width: 32, height: 32)
    let disc = try render(
      Color.clear.frame(width: discSize.width, height: discSize.height)
        .inkGlassPanel(cornerRadius: 16, shadow: nil, reduceTransparency: false),
      size: discSize, overTone: 0.5)

    let band = sheenBandRows(disc, pointHeight: discSize.height)
    let brightest = (0..<band).flatMap { y in
      (0..<disc.pixelsWide).compactMap { brightness(disc, x: $0, y: y) }
    }.max()
    let peak = try XCTUnwrap(brightest, "the disc did not render")

    XCTAssertLessThan(
      peak, (groundTone + sheenTone) / 2,
      """
      The brightest pixel across the disc's top band rendered \(String(format: "%.3f", peak)), \
      nearer a drawn specular line (\(String(format: "%.3f", sheenTone))) than the ground under one \
      (\(String(format: "%.3f", groundTone))). A shape with no straight top edge is wearing a \
      straight highlight — the stray white line reported above the jump-to-latest button.
      """)
  }

  // MARK: - Harness

  /// Renders `view` over a flat tone and reads the bitmap back. Top-left origin, matching the
  /// coordinates the assertions above are written in.
  private func render(_ view: some View, size: CGSize, overTone tone: CGFloat) throws
    -> NSBitmapImageRep
  {
    let host = NSHostingView(rootView: view.frame(width: size.width, height: size.height))
    host.appearance = InkGlass.appearance
    host.frame = NSRect(origin: .zero, size: size)

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

  /// How many device rows the 1 pt sheen occupies in `rep`, from the backing scale the harness
  /// actually rendered at. Asserting on row 0 alone would read half the line on a Retina render and
  /// none of it on a 1x one.
  private func sheenBandRows(_ rep: NSBitmapImageRep, pointHeight: CGFloat) -> Int {
    let scale = CGFloat(rep.pixelsHigh) / pointHeight
    return max(1, Int((InkGlassView.sheenHeight * scale).rounded()))
  }

  private func brightness(_ rep: NSBitmapImageRep, x: Int, y: Int) -> CGFloat? {
    guard x >= 0, y >= 0, x < rep.pixelsWide, y < rep.pixelsHigh else { return nil }
    return rep.colorAt(x: x, y: y)?.usingColorSpace(.sRGB)?.brightnessComponent
  }
}
