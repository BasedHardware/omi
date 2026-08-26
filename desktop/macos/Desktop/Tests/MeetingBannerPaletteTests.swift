//
//  MeetingBannerPaletteTests.swift — the banner ground, and the two ways the obvious version is wrong.
//

import XCTest

@testable import Omi_Computer

final class MeetingBannerPaletteTests: XCTestCase {

  /// Build an RGBA buffer from repeated colours.
  private func rgba(_ colours: [(UInt8, UInt8, UInt8)], each: Int = 1) -> [UInt8] {
    var out: [UInt8] = []
    for colour in colours {
      for _ in 0..<each {
        out.append(contentsOf: [colour.0, colour.1, colour.2, 255])
      }
    }
    return out
  }

  // MARK: - Achromatic frames must not be given a colour

  func testBlackEditorIsNeutralRatherThanAnInventedHue() {
    // A dark editor: near-black with faint syntax colour that antialiasing smears toward grey.
    let ground = MeetingBannerPalette.ground(fromRGBA: rgba([(18, 18, 20), (24, 24, 26)], each: 128))
    XCTAssertTrue(ground.isNeutral, "a near-black frame carries no hue and must not be assigned one")
  }

  func testWhiteDocumentIsNeutralRatherThanAnInventedHue() {
    let ground = MeetingBannerPalette.ground(
      fromRGBA: rgba([(252, 252, 250), (238, 238, 240)], each: 128))
    XCTAssertTrue(ground.isNeutral)
  }

  func testEmptyBufferIsNeutral() {
    XCTAssertTrue(MeetingBannerPalette.ground(fromRGBA: []).isNeutral)
  }

  // MARK: - The mode, not the mean

  /// The bug this replaced: averaging hues around the wheel returns a hue that is in neither input.
  /// A diff is exactly this shape — a lot of red, a lot of green, and the mean of the two is a
  /// muddy yellow that appears nowhere in the picture.
  func testOpposedHuesResolveToOneOfThemNotTheAverage() {
    // 70% red, 30% green. The mode is red; a circular mean would land near yellow.
    let ground = MeetingBannerPalette.ground(
      fromRGBA: rgba([(200, 40, 40)], each: 70) + rgba([(40, 200, 40)], each: 30))
    XCTAssertFalse(ground.isNeutral)
    let hue = ground.stops[0].hue
    // Red is ~0.0 (wrapping to ~1.0); yellow — the wrong answer — is ~0.17.
    XCTAssertTrue(
      hue < 0.06 || hue > 0.94,
      "expected the dominant red, got hue \(hue) — that is the circular-mean bug")
  }

  func testDominantHueWins() {
    let ground = MeetingBannerPalette.ground(
      fromRGBA: rgba([(40, 90, 210)], each: 90) + rgba([(210, 90, 40)], each: 10))
    XCTAssertFalse(ground.isNeutral)
    // Blue sits around 0.6.
    XCTAssertEqual(ground.stops[0].hue, 0.61, accuracy: 0.06)
  }

  // MARK: - Contrast

  func testEveryHueYieldsAGroundWhiteTextCanBeReadOn() {
    // Yellow and cyan are far brighter than blue at the same nominal HSB brightness, so a constant
    // brightness is not safe. Walk the wheel and assert the measured contrast, not the intent.
    for step in 0..<36 {
      let hue = Double(step) / 36
      let stops = MeetingBannerPalette.stops(forHue: hue)
      let contrast = MeetingBannerPalette.contrastWithWhite(
        hue: stops[0].hue, saturation: stops[0].saturation, brightness: stops[0].brightness)
      XCTAssertGreaterThanOrEqual(
        contrast, MeetingBannerPalette.minimumContrastForWhite,
        "white title fails AA contrast over hue \(hue) (measured \(contrast))")
    }
  }

  /// The neutral ground exists in three languages and nothing else guards their agreement.
  ///
  /// The server emits `ground` on every frame it approves, so clients normally draw what they are
  /// given. A record persisted before `ground` existed has none, so each surface carries its own
  /// copy of the fallback:
  ///
  ///   - here (`MeetingBannerPalette.neutral`)
  ///   - `backend/utils/screen_frames/palette.py` (`_neutral_ground`)
  ///   - `web/app/src/components/conversations/ConversationScreenFrameBanner.tsx`
  ///     (`NEUTRAL_GROUND_STOPS`)
  ///
  /// Three copies of one constant drift silently, and the symptom would be a banner that is a
  /// different colour on web than on macOS for exactly the oldest records — the ones least likely
  /// to be opened during review. Pinning the hex here means changing the hue or either stop breaks
  /// a test on every surface at once.
  func testNeutralGroundMatchesTheOtherTwoSurfaces() {
    let stops = MeetingBannerPalette.neutral.stops
    func hex(_ stop: MeetingBannerGround.HSB) -> String {
      let (r, g, b) = MeetingBannerPalette.rgb(h: stop.hue, s: stop.saturation, v: stop.brightness)
      return String(
        format: "#%02X%02X%02X",
        Int((r * 255).rounded()), Int((g * 255).rounded()), Int((b * 255).rounded()))
    }
    XCTAssertEqual(hex(stops[0]), "#5A5D66")
    XCTAssertEqual(hex(stops[1]), "#33363D")
  }

  func testNeutralGroundAlsoClearsContrast() {
    let stop = MeetingBannerPalette.neutral.stops[0]
    XCTAssertGreaterThanOrEqual(
      MeetingBannerPalette.contrastWithWhite(
        hue: stop.hue, saturation: stop.saturation, brightness: stop.brightness),
      MeetingBannerPalette.minimumContrastForWhite)
  }

  func testSecondStopIsAlwaysDarkerThanTheFirst() {
    for step in 0..<12 {
      let stops = MeetingBannerPalette.stops(forHue: Double(step) / 12)
      XCTAssertLessThan(
        stops[1].brightness, stops[0].brightness,
        "the gradient must run light-to-dark so the inset's shadow reads")
    }
  }

  // MARK: - Colour arithmetic round-trip

  func testHSBRoundTrips() {
    for (r, g, b) in [(0.8, 0.2, 0.2), (0.2, 0.8, 0.4), (0.3, 0.4, 0.9), (0.5, 0.5, 0.5)] {
      let (h, s, v) = MeetingBannerPalette.hsb(r: r, g: g, b: b)
      let (r2, g2, b2) = MeetingBannerPalette.rgb(h: h, s: s, v: v)
      XCTAssertEqual(r, r2, accuracy: 0.001)
      XCTAssertEqual(g, g2, accuracy: 0.001)
      XCTAssertEqual(b, b2, accuracy: 0.001)
    }
  }
}
