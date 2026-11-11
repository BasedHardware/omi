import AppKit
import XCTest

@testable import Omi_Computer

/// The timeline track blends adjacent segments into each other and draws every app as a pastel of
/// its palette hue. Both are arithmetic, so both are asserted here without a window server.
final class RewindTrackGradientTests: XCTestCase {
  private let red = NSColor(deviceRed: 1, green: 0, blue: 0, alpha: 1)
  private let blue = NSColor(deviceRed: 0, green: 0, blue: 1, alpha: 1)

  private func colour(_ app: String) -> NSColor { app == "A" ? red : blue }

  private func components(_ colour: NSColor) throws -> [CGFloat] {
    let rgb = try XCTUnwrap(colour.usingColorSpace(.deviceRGB))
    return [rgb.redComponent, rgb.greenComponent, rgb.blueComponent]
  }

  private func assertSameColour(_ a: NSColor, _ b: NSColor, _ message: String, line: UInt = #line) throws {
    for (x, y) in zip(try components(a), try components(b)) {
      XCTAssertEqual(x, y, accuracy: 0.001, message, line: line)
    }
  }

  // MARK: - Seams

  func testContiguousNeighboursMeetAtOneSharedColour() throws {
    let a = RewindActivityBlock(app: "A", startedAt: 0, endedAt: 100)
    let b = RewindActivityBlock(app: "B", startedAt: 100, endedAt: 200)

    let aEdges = RewindTrackGradient.edges(for: a, previous: nil, next: b, width: 200, colour: colour)
    let bEdges = RewindTrackGradient.edges(for: b, previous: a, next: nil, width: 200, colour: colour)

    let midpoint = RewindTrackGradient.blend(red, blue)
    try assertSameColour(aEdges.trailing, midpoint, "A's trailing edge is the colour halfway to B")
    try assertSameColour(bEdges.leading, midpoint, "B's leading edge is that same colour — the seam is continuous")
    try assertSameColour(aEdges.leading, red, "an edge with no neighbour stays the body colour")
    try assertSameColour(bEdges.trailing, blue, "an edge with no neighbour stays the body colour")
    XCTAssertEqual(try components(midpoint), [0.5, 0, 0.5])
  }

  func testAGapWiderThanAStretchKeepsAHardEdge() throws {
    let a = RewindActivityBlock(app: "A", startedAt: 0, endedAt: 100)
    let b = RewindActivityBlock(
      app: "B", startedAt: 100 + RewindTrackGradient.contiguousGap + 1, endedAt: 400)

    let aEdges = RewindTrackGradient.edges(for: a, previous: nil, next: b, width: 200, colour: colour)
    try assertSameColour(aEdges.trailing, red, "a lunch break is a gap, not a seam to blend across")
  }

  func testASameAppNeighbourIsNotBlendedInto() throws {
    let first = RewindActivityBlock(app: "A", startedAt: 0, endedAt: 100)
    let second = RewindActivityBlock(app: "A", startedAt: 100, endedAt: 200)
    let edges = RewindTrackGradient.edges(for: first, previous: nil, next: second, width: 200, colour: colour)
    try assertSameColour(edges.trailing, red, "one app split across two samples is one colour")
  }

  func testTheBlendNeverEatsMoreThanHalfASegment() throws {
    let block = RewindActivityBlock(app: "A", startedAt: 0, endedAt: 1)
    let wide = RewindTrackGradient.edges(for: block, previous: nil, next: nil, width: 400, colour: colour)
    XCTAssertEqual(wide.blendWidth, RewindTrackGradient.maximumBlendWidth)
    let narrow = RewindTrackGradient.edges(for: block, previous: nil, next: nil, width: 10, colour: colour)
    XCTAssertEqual(narrow.blendWidth, 5, "a narrow segment keeps its centre in its own colour")

    let gradient = try? XCTUnwrap(
      RewindTrackGradient.gradient(body: red, edges: narrow, width: 10))
    XCTAssertEqual(gradient?.numberOfColorStops, 4)
    XCTAssertNil(RewindTrackGradient.gradient(body: red, edges: narrow, width: 0))
  }

  // MARK: - The pastel

  /// Same hue as the vivid swatch (an app keeps its identity), lighter than it (it is a pastel), and
  /// still inside the brand's hue ceiling — over every colour the palette can emit, not a sample.
  func testTheTrackPastelKeepsTheHueAndLightensEverySwatch() throws {
    for bucket in 0..<RewindPalette.hueBuckets {
      let vivid = RewindPalette.swatch(bucket: bucket)
      let pastel = RewindPalette.trackSwatch(bucket: bucket)
      XCTAssertEqual(pastel.hue, vivid.hue, "bucket \(bucket) changed hue on the track")
      XCTAssertLessThan(pastel.hue, RewindPalette.hueCeiling)
      XCTAssertGreaterThan(
        Self.relativeLuminance(RewindPalette.nsColor(pastel)),
        Self.relativeLuminance(RewindPalette.nsColor(vivid)),
        "the track pastel for bucket \(bucket) is not lighter than the badge swatch")
      // The per-band track brightness lands every family in one lightness window: measured
      // 0.457–0.632 over the whole domain (red and blue at the floor, where the largest brightness
      // there is still cannot lift them further at this saturation). A family that drifted above
      // it would sit a hair off the glass and read as an empty stretch.
      let luminance = Self.relativeLuminance(RewindPalette.nsColor(pastel))
      XCTAssertGreaterThan(luminance, 0.44, "bucket \(bucket) is too dark to read as pastel")
      XCTAssertLessThan(luminance, 0.66, "bucket \(bucket) is washing toward the glass")
    }
  }

  func testTheTrackColourIsTheSamePastelForTheSameApp() throws {
    let a = RewindPalette.trackNSColor(forApp: "Google Chrome")
    let b = RewindPalette.trackNSColor(forApp: "google chrome ")
    try assertSameColour(a, b, "the track folds names the same way the palette does")
  }

  // MARK: - Helpers

  private static func relativeLuminance(_ colour: NSColor) -> Double {
    guard let rgb = colour.usingColorSpace(.deviceRGB) else { return 0 }
    func linear(_ channel: CGFloat) -> Double {
      let c = Double(channel)
      return c <= 0.03928 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
    }
    return 0.2126 * linear(rgb.redComponent) + 0.7152 * linear(rgb.greenComponent)
      + 0.0722 * linear(rgb.blueComponent)
  }
}
