import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

/// Behavioural guards on `RewindPalette`.
///
/// Every assertion here runs over the palette's **whole output domain** — all `hueBuckets` values
/// it can ever emit — rather than over a handful of sampled app names. That is the difference
/// between "we did not find an off-brand colour" and "one cannot exist", and the domain is 2 503
/// entries, so there is no reason to settle for the weaker claim.
///
/// The brand assertions deliberately measure the **rendered** colour (`NSColor` in device RGB, and
/// the `SwiftUI.Color` bridged back through `NSColor`) instead of the palette's own constants. A
/// guard that only reads `bands` proves the table matches itself; it would not have caught a
/// renderer that shifted hue on the way to the screen, which is where the shipped regression this
/// ceiling exists for actually lived.
final class RewindPaletteTests: XCTestCase {

  // MARK: - Determinism

  /// FNV-1a's published 64-bit vectors. If a refactor reaches for `String.hashValue` or a different
  /// prime, these fail — and the symptom in the product would be an app changing colour on every
  /// relaunch, which is the one thing a per-app colour must never do.
  func testStableHashMatchesPublishedFNV1aVectors() {
    XCTAssertEqual(RewindPalette.stableHash(""), 0xcbf2_9ce4_8422_2325)
    XCTAssertEqual(RewindPalette.stableHash("a"), 0xaf63_dc4c_8601_ec8c)
    XCTAssertEqual(RewindPalette.stableHash("foobar"), 0x8594_4171_f739_67e8)
  }

  /// Same input, same colour — the property the whole type exists for.
  func testSameAppNameAlwaysYieldsTheSameColour() {
    for name in Self.sampleApps {
      let first = RewindPalette.swatch(forApp: name)
      XCTAssertEqual(first, RewindPalette.swatch(forApp: name), "\(name) is not deterministic")
      XCTAssertEqual(
        RewindPalette.nsColor(forApp: name), RewindPalette.nsColor(forApp: name),
        "\(name) renders two different colours")
    }
  }

  /// Case and surrounding whitespace are not identity: one app must not split a day's timeline into
  /// two colours because one capture recorded a trailing space.
  func testAppNameKeyIsCaseAndWhitespaceFolded() {
    let canonical = RewindPalette.swatch(forApp: "Google Chrome")
    XCTAssertEqual(canonical, RewindPalette.swatch(forApp: "google chrome"))
    XCTAssertEqual(canonical, RewindPalette.swatch(forApp: "  Google Chrome  "))
    XCTAssertEqual(canonical, RewindPalette.swatch(forApp: "GOOGLE CHROME\n"))
  }

  /// Different apps must not collapse onto one colour. Not a uniqueness claim — 2 503 buckets over
  /// an unbounded name space cannot promise that — but the everyday set a user actually sees must
  /// spread, because the previous sweep's failure was visual sameness, not collisions.
  func testCommonAppsSpreadAcrossMostBands() {
    let families = Set(Self.sampleApps.map { RewindPalette.band(forApp: $0).name })
    XCTAssertGreaterThanOrEqual(
      families.count, 5,
      "\(Self.sampleApps.count) everyday apps landed in only \(families.count) families: \(families.sorted())")
  }

  // MARK: - Brand: the hue ceiling holds on the rendered colour

  /// No colour this palette can emit reaches `hueCeiling`, measured after rendering.
  ///
  /// The 250° ceiling this replaces shipped a real off-brand disc at 249.9°, so the interesting
  /// assertion is not "below the constant" but "below the constant *and* a clear distance from
  /// where that family begins".
  func testNoEmittableColourReachesTheHueCeiling() {
    var worstHue = 0.0
    var worstBucket: UInt64 = 0
    for bucket in 0..<RewindPalette.hueBuckets {
      let swatch = RewindPalette.swatch(bucket: bucket)
      let band = RewindPalette.band(bucket: bucket)
      let label = "bucket \(bucket), \(band.name) at \(swatch.hue)°"

      XCTAssertLessThan(swatch.hue, RewindPalette.hueCeiling, "\(label) exceeds the ceiling")

      // Both renderers, because the product uses both: AppKit draws the timeline track, SwiftUI
      // draws the monogram disc.
      assertOnBrand(RewindPalette.nsColor(swatch), "\(label), AppKit")
      assertOnBrand(NSColor(RewindPalette.color(swatch)), "\(label), SwiftUI")

      if swatch.hue > worstHue {
        worstHue = swatch.hue
        worstBucket = bucket
      }
    }
    XCTAssertLessThan(worstHue, RewindPalette.hueCeiling, "bucket \(worstBucket) is the highest hue emitted")
    // The blue band stops at 218°, and buckets sample the band's span half-open, so the measured
    // maximum must sit inside it rather than on the wall.
    XCTAssertLessThan(worstHue, 218.0)
  }

  /// The constants themselves, so a failure says *which entry to edit* rather than only that some
  /// bucket went out of range.
  func testEveryBandIsOrderedAndStopsShortOfTheCeiling() {
    XCTAssertFalse(RewindPalette.bands.isEmpty)
    for band in RewindPalette.bands {
      XCTAssertLessThan(band.hueStart, band.hueEnd, "\(band.name) is empty or inverted")
      XCTAssertGreaterThanOrEqual(band.hueStart, 0, "\(band.name) starts below the wheel")
      XCTAssertLessThan(band.hueEnd, RewindPalette.hueCeiling, "\(band.name) reaches the wall")
      XCTAssertGreaterThan(band.brightness, 0, "\(band.name) is black")
      XCTAssertLessThanOrEqual(band.brightness, 1, "\(band.name) is out of range")
    }
    XCTAssertEqual(RewindPalette.saturation, 0.92, accuracy: 0.0001)
    XCTAssertEqual(RewindPalette.hueCeiling, 220, accuracy: 0.0001)
  }

  /// Bands never touch. A gap the palette cannot emit from is what makes two adjacent segments
  /// *nameably* different rather than 8° apart, so a retune that closes one silently reintroduces
  /// the sameness the bands were built to fix.
  func testBandsAreSeparatedByGapsThePaletteNeverEmitsFrom() {
    for (lower, upper) in zip(RewindPalette.bands, RewindPalette.bands.dropFirst()) {
      XCTAssertLessThan(
        lower.hueEnd, upper.hueStart,
        "\(lower.name) and \(upper.name) are adjacent — there is no gap between them")
      // 6° is the narrowest gap the table holds (cyan → blue), and it is deliberate: those two
      // families are already separated by a large brightness step. Anything under it means a band
      // grew into its neighbour.
      XCTAssertGreaterThanOrEqual(
        upper.hueStart - lower.hueEnd, 6,
        "the gap between \(lower.name) and \(upper.name) is too narrow to read as a difference")
    }
  }

  /// The deliberate 54° skip. There is no vivid yellow under the luminance cap the white monogram
  /// imposes, so the palette does not have a band there — and no bucket may land inside it.
  func testTheSkippedStretchStaysEmptyAcrossTheWholeDomain() {
    guard let orange = RewindPalette.bands.first(where: { $0.name == "orange" }),
      let lime = RewindPalette.bands.first(where: { $0.name == "lime" })
    else { return XCTFail("the orange → lime skip is the palette's most load-bearing gap") }

    XCTAssertEqual(lime.hueStart - orange.hueEnd, 54, accuracy: 0.0001, "the skip changed width")

    for bucket in 0..<RewindPalette.hueBuckets {
      let hue = RewindPalette.swatch(bucket: bucket).hue
      XCTAssertFalse(
        hue > orange.hueEnd && hue < lime.hueStart,
        "bucket \(bucket) emitted \(hue)°, inside the stretch no band may cover")
    }

    // And the constants agree: no band overlaps the middle of the skip.
    for muddy in stride(from: orange.hueEnd + 1, to: lime.hueStart, by: 1.0) {
      XCTAssertFalse(
        RewindPalette.bands.contains { muddy >= $0.hueStart && muddy < $0.hueEnd },
        "a band now covers \(muddy)°")
    }
  }

  // MARK: - Legibility: white type on every swatch

  /// White monogram type at ~10 pt semibold needs 3:1. That requirement — not taste — is what sets
  /// every band's brightness, so it is asserted over the whole domain rather than spot-checked.
  func testWhiteTypeClearsThreeToOneOnEverySwatch() {
    var worstContrast = Double.greatestFiniteMagnitude
    var worstLabel = ""
    var lowestLuminance = Double.greatestFiniteMagnitude
    var highestLuminance = 0.0

    for bucket in 0..<RewindPalette.hueBuckets {
      let swatch = RewindPalette.swatch(bucket: bucket)
      let colour = RewindPalette.nsColor(swatch)
      let luminance = Self.relativeLuminance(colour)
      let contrast = Self.contrast(colour, .white)

      XCTAssertLessThanOrEqual(
        luminance, Self.luminanceCap,
        "\(RewindPalette.band(bucket: bucket).name) at \(swatch.hue)° is lighter than white type allows")

      if contrast < worstContrast {
        worstContrast = contrast
        worstLabel = "\(RewindPalette.band(bucket: bucket).name) at \(swatch.hue)°"
      }
      lowestLuminance = min(lowestLuminance, luminance)
      highestLuminance = max(highestLuminance, luminance)
    }

    XCTAssertGreaterThanOrEqual(
      worstContrast, 3.0, "worst swatch for white type is \(worstLabel) at \(worstContrast):1")
    // The measured window the doc comment on `bands` quotes. Pinned so a retune that quietly widens
    // it has to say so here.
    XCTAssertGreaterThan(lowestLuminance, 0.14)
    XCTAssertLessThan(highestLuminance, 0.30)
  }

  /// The reason there is no yellow band, stated as a measurement rather than as prose: a yellow dark
  /// enough for white type is olive, and a yellow vivid enough to be gold fails white type outright.
  func testYellowCannotSatisfyBothVividnessAndWhiteType() {
    let olive = RewindPalette.Swatch(hue: 49, saturation: RewindPalette.saturation, brightness: 0.64)
    XCTAssertLessThanOrEqual(
      Self.relativeLuminance(RewindPalette.nsColor(olive)), Self.luminanceCap,
      "a yellow dark enough for white type is this olive")

    let gold = RewindPalette.Swatch(hue: 50, saturation: RewindPalette.saturation, brightness: 0.90)
    XCTAssertLessThan(
      Self.contrast(RewindPalette.nsColor(gold), .white), 3.0,
      "a yellow vivid enough to read as gold cannot carry white type")
  }

  // MARK: - Renderers agree

  /// AppKit draws the timeline; SwiftUI draws the disc. If the two disagree, one app has two
  /// colours on one screen, which is worse than having no colour at all.
  func testAppKitAndSwiftUIRenderTheSameColour() {
    for name in Self.sampleApps {
      let appKit = RewindPalette.nsColor(forApp: name).usingColorSpace(.deviceRGB)
      let swiftUI = NSColor(RewindPalette.color(forApp: name)).usingColorSpace(.deviceRGB)
      guard let appKit, let swiftUI else { return XCTFail("\(name) did not convert to device RGB") }
      XCTAssertEqual(appKit.redComponent, swiftUI.redComponent, accuracy: 0.01, "\(name) red")
      XCTAssertEqual(appKit.greenComponent, swiftUI.greenComponent, accuracy: 0.01, "\(name) green")
      XCTAssertEqual(appKit.blueComponent, swiftUI.blueComponent, accuracy: 0.01, "\(name) blue")
    }
  }

  // MARK: - Helpers

  /// White monogram type at ~10 pt semibold needs 3:1, which caps relative luminance here.
  private static let luminanceCap = 0.30

  private static let sampleApps = [
    "Google Chrome", "Safari", "Xcode", "Terminal", "Slack", "Notion", "Figma",
    "Cursor", "Finder", "Mail", "Messages", "Music", "Zoom", "Visual Studio Code",
  ]

  /// A rendered colour is on brand when its measured hue stays clear of the family `INV-UI-1`
  /// forbids. Measured, not asserted from constants — see the note on this class.
  private func assertOnBrand(_ colour: NSColor, _ label: String, file: StaticString = #filePath, line: UInt = #line) {
    guard let rgb = colour.usingColorSpace(.deviceRGB) else {
      return XCTFail("\(label) did not convert to device RGB", file: file, line: line)
    }
    let hue = rgb.hueComponent * 360

    // The forbidden family is a structure in RGB — red and blue both above green. Asserting on that
    // structure rather than on a degree range is what makes this independent of the constants the
    // palette happens to hold.
    let isOffBrandStructure = rgb.redComponent > rgb.greenComponent && rgb.blueComponent > rgb.greenComponent
    XCTAssertFalse(
      isOffBrandStructure && rgb.saturationComponent > 0.1,
      "\(label) renders sRGB (\(Int(rgb.redComponent * 255)), \(Int(rgb.greenComponent * 255)), "
        + "\(Int(rgb.blueComponent * 255))) at \(hue)° — red and blue both above green",
      file: file, line: line)

    XCTAssertLessThan(
      hue, 225.0, "\(label) rendered at \(hue)°, past where blue stops reading as blue",
      file: file, line: line)
  }

  private static func relativeLuminance(_ colour: NSColor) -> Double {
    guard let rgb = colour.usingColorSpace(.sRGB) else { return 1 }
    func linear(_ channel: CGFloat) -> Double {
      let value = Double(channel)
      return value <= 0.03928 ? value / 12.92 : pow((value + 0.055) / 1.055, 2.4)
    }
    return 0.2126 * linear(rgb.redComponent) + 0.7152 * linear(rgb.greenComponent)
      + 0.0722 * linear(rgb.blueComponent)
  }

  private static func contrast(_ lhs: NSColor, _ rhs: NSColor) -> Double {
    let a = relativeLuminance(lhs)
    let b = relativeLuminance(rhs)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)
  }
}
