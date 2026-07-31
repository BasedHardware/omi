import AppKit
import XCTest

/// The one definition of "reads violet" this app's tests use, and the reason it is a predicate on a
/// rendered pixel rather than a range of hue degrees.
///
/// Two brand guards were written independently — `RewindTests` over the timeline palette,
/// `SettingsTests` over the accent list — and both stated `INV-UI-1` as a band of hue numbers. Both
/// were wrong the same way, because a band's boundaries are an *opinion* about where a colour stops
/// looking violet, and an opinion written as a constant cannot be checked by a test whose only
/// vocabulary is that constant:
///
/// - the palette's `hue < 250 && !(250...330).contains(hue)` passed 249.9°, and that colour shipped:
///   a lavender site disc in the search panel, sRGB (101, 86, 179);
/// - the accent list's `hue >= 250 && hue <= 345` passes `systemIndigo` (233.8°) *and* `systemPink`
///   (348.0°) — it escaped notice only because `AccentChoice` ships neither, i.e. it was
///   documentation wearing a test's clothes.
///
/// So the rule is stated once, structurally, and both guards call it.
///
/// ## The structure
///
/// Violet is the one hue family the eye reads as a *mixture of the spectrum's two ends*: red **and**
/// blue above green, i.e. `min(R, B) > G`. That is the arc from pure blue (240°) through magenta
/// (300°) to pure red (360°) — violet, purple, magenta, pink, all of it. It is a fact about the
/// channels rather than a numbering convention, which is why it survives a retune of saturation,
/// brightness, or whatever generator produced the colour.
enum BrandColour {

    /// The margin a blue-dominant colour must keep from the wedge, in units of its own chroma.
    ///
    /// 0.25 of chroma is 15° of hue: from pure blue (240°) down to 225°, which is `royalblue`'s hue
    /// and the last hue that still reads blue rather than indigo when rendered at the timeline
    /// palette's saturation and brightness. Below that the swatches turn — 230° is indigo, and 240°,
    /// still "pure blue" by the numbers, reads violet on a dark ground.
    static let blueMargin = 0.25

    /// The slack allowed at the wedge's *other* edge, pure red, whose neighbours are crimson and
    /// scarlet rather than violet.
    ///
    /// This is the only tolerance in the rule and it exists for one measured colour: `systemRed`
    /// renders at hue 359.0°, a degree onto the magenta side of pure red, clearance −0.016. 0.05 of
    /// chroma is 3° of hue — enough for a red that is a hair off, nowhere near enough for something
    /// anyone would call pink, which `systemPink` (348.0°, clearance −0.200) demonstrates by being
    /// rejected.
    static let redEdgeTolerance = 0.05

    /// Below this saturation a colour has no hue to be wrong about. Graphite (`systemGray`,
    /// saturation 0.03) is the one shipped choice that lands here.
    static let neutralSaturation = 0.15

    /// A rendered colour reduced to what INV-UI-1 turns on.
    struct Reading {
        /// How far the colour sits clear of the red↔blue wedge, in units of its own chroma: `+1` at
        /// cyan and at yellow, `0` on the wedge's two edges (pure blue 240°, pure red 0°), negative
        /// inside it.
        ///
        /// Scale-free on purpose, which makes it **blend-invariant**: compositing over any neutral
        /// ground adds the same amount to all three channels and scales chroma, so the ratio is
        /// unchanged. The violet that shipped was measured on screen as (134, 121, 191) — the
        /// palette's (101, 86, 179) after the app's own compositing — and a guard that recognised
        /// only the un-composited value would have let the screenshot argue with it.
        let clearance: Double
        /// Violet lives on the *blue* side of the wedge, so only blue-dominant colours owe the
        /// margin.
        let isBlueDominant: Bool
        let saturation: Double
        let hue: Double

        var isNeutral: Bool { saturation < BrandColour.neutralSaturation }

        /// Nil when the colour is on brand; otherwise what is wrong with it, in the terms above.
        var complaint: String? {
            guard !isNeutral else { return nil }
            let floor = isBlueDominant ? 0 : -BrandColour.redEdgeTolerance
            if clearance < floor {
                return "renders inside the red↔blue wedge — hue \(hue), clearance \(clearance)"
            }
            if isBlueDominant, clearance < BrandColour.blueMargin {
                return "renders \(clearance) from the red↔blue wedge, inside the "
                    + "\(BrandColour.blueMargin) margin a blue must keep — hue \(hue), it reads "
                    + "indigo/violet"
            }
            return nil
        }
    }

    /// Nil only when the colour has no sRGB representation at all, which is a failure in itself.
    static func read(_ color: NSColor) -> Reading? {
        guard let rgb = color.usingColorSpace(.sRGB) else { return nil }
        let r = Double(rgb.redComponent)
        let g = Double(rgb.greenComponent)
        let b = Double(rgb.blueComponent)
        let high = max(r, max(g, b))
        let chroma = high - min(r, min(g, b))
        return Reading(
            clearance: chroma > 0 ? (g - min(r, b)) / chroma : 1,
            isBlueDominant: b >= max(r, g),
            saturation: high > 0 ? chroma / high : 0,
            hue: Double(rgb.hueComponent) * 360)
    }
}

extension XCTestCase {

    /// INV-UI-1, asserted on the rendered pixel rather than on the number that produced it.
    func assertReadsOnBrand(
        _ color: NSColor, _ context: @autoclosure () -> String,
        file: StaticString = #filePath, line: UInt = #line
    ) {
        guard let reading = BrandColour.read(color) else {
            return XCTFail("\(context()) has no sRGB representation", file: file, line: line)
        }
        if let complaint = reading.complaint {
            XCTFail("\(context()) \(complaint) (INV-UI-1)", file: file, line: line)
        }
    }

    /// The other direction, which is what keeps a guard honest: a clean palette and a blind guard
    /// look identical until something known-violet is put in front of it.
    func assertReadsOffBrand(
        _ color: NSColor, _ context: @autoclosure () -> String,
        file: StaticString = #filePath, line: UInt = #line
    ) {
        guard let reading = BrandColour.read(color) else {
            return XCTFail("\(context()) has no sRGB representation", file: file, line: line)
        }
        XCTAssertNotNil(
            reading.complaint,
            "\(context()) was accepted by the brand guard and must not be — hue \(reading.hue), "
                + "clearance \(reading.clearance)",
            file: file, line: line)
    }
}
