import AppKit
import SwiftUI

/// The one place a per-app colour is decided, and the only colour in the app that is not a system
/// semantic.
///
/// The exception is earned rather than convenient: a track segment's colour *is* its content. It is
/// how a day reads as a shape at a glance — this stretch was the browser, that one the editor — and
/// a semantic label colour cannot say that because every app would get the same one. Everything
/// else in the timeline window goes through `Ink`.
///
/// Two things about their implementation had to change.
///
/// **The hash must be stable across launches.** `String.hashValue` is seeded per process in Swift,
/// so a track keyed on it draws Cursor blue this morning and orange after a relaunch — which
/// destroys the only thing the colour is for, since recognising the shape of a day depends on the
/// colours meaning the same thing tomorrow. FNV-1a is computed here, in full, over the name's UTF-8:
/// a fixed function with fixed constants cannot drift with a toolchain or a process.
///
/// **The hue range must skip violet.** A hash swept over all 360° emits an off-brand hue for
/// roughly one turn in three, and that family is off-brand anywhere in the product (`INV-UI-1`,
/// `docs/product/invariants/brand-ui.md`). Excluding it after the fact — clamping, nudging, retrying
/// the hash — leaves the property untested and one refactor from returning. The range simply does
/// not contain it: hues are drawn from `[0°, 220°)`, which stops a clear distance below pure blue
/// and never reaches magenta, so no input can produce one. `RewindTests` asserts that on the
/// *rendered colour* of every value this can emit, not on the constant.
enum RewindPalette {

    /// The hue arc app colours are drawn from, in degrees: red → orange → yellow → green → cyan →
    /// blue, stopping well short of violet.
    ///
    /// **Why 220°, and why the 250° this shipped with was wrong.** The forbidden family is not a
    /// stretch of wheel somebody agreed on; in RGB it is a structure — red *and* blue both above
    /// green, the eye reading a mixture of the spectrum's two ends. That structure begins the
    /// instant a hue passes pure blue at 240°, so everything in `[240°, 360°)` is in it. A 250°
    /// ceiling put 4% of this palette's output literally inside that wedge, and 10% of it inside or
    /// hugging the edge — Figma landed on 244.1°, gitlab.com on 244.7°. It shipped: a monogram disc in
    /// the search panel rendered sRGB (101, 86, 179) — a lavender — from a hue of 249.9°, and the
    /// guard passed it because 249.9 is less than 250.
    ///
    /// 240° is the wall. 225° is where a colour at the saturation and brightness below still reads
    /// unambiguously blue rather than indigo — it is `royalblue`'s hue, and equivalently it is the
    /// point that keeps a quarter of the cyan→blue sector's green lift. 220° sits 5° inside that, so
    /// bucket quantisation, a colour-space round trip, or a future retune of `saturation` /
    /// `brightness` cannot walk an emitted colour onto the boundary. The cost is 12% of the arc: 220°
    /// still separates the ~22 distinct apps in a real database by a median 8°.
    static let hueCeiling: Double = 220

    /// Fixed saturation and brightness, deliberately not appearance-dependent.
    ///
    /// An app's colour is its identity, so it must not change when the user switches to Dark — a
    /// segment that inverts is a segment whose colour means nothing. These two values are instead
    /// chosen to hold up against *both* grounds: bright enough to separate from a near-black window
    /// in Dark, saturated and dark enough to separate from a white one in Light. Their original
    /// values (0.3 / 0.5) were tuned against a hardcoded dark background and go muddy on a light one.
    static let saturation: Double = 0.52
    static let brightness: Double = 0.70

    /// A prime modulus finer than the arc, so two names that differ only slightly still land on
    /// visibly different hues rather than colliding into the same integer degree.
    ///
    /// Internal rather than private because it is the size of this type's entire output domain: every
    /// colour it can ever produce is `hue(bucket:)` for some bucket below this, which is what lets the
    /// brand guard check all of them instead of sampling names and hoping.
    static let hueBuckets: UInt64 = 2_503

    /// FNV-1a, 64-bit. Written out rather than reached for so the constants are visible and the
    /// result is pinned to this source rather than to the standard library's seed.
    static func stableHash(_ text: String) -> UInt64 {
        var hash: UInt64 = 0xcbf2_9ce4_8422_2325
        for byte in text.utf8 {
            hash ^= UInt64(byte)
            hash = hash &* 0x0000_0100_0000_01b3
        }
        return hash
    }

    /// The hue in degrees for an app name. Always in `[0, hueCeiling)`, so never in the violet family.
    static func hue(forApp appName: String) -> Double {
        // Case- and whitespace-folded: "Google Chrome" and "google chrome " are one app on a
        // timeline, and giving them two colours would split one stretch of a day into two.
        let key = appName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return hue(bucket: stableHash(key) % hueBuckets)
    }

    /// Where one bucket lands on the arc, in degrees.
    ///
    /// Split out from `hue(forApp:)` so the output domain is enumerable. A brand rule sampled over
    /// names is a statistical argument; over `0..<hueBuckets` it is a complete one, and this palette
    /// is small enough that there is no reason to settle for the weaker kind.
    static func hue(bucket: UInt64) -> Double {
        Double(bucket % hueBuckets) / Double(hueBuckets) * hueCeiling
    }

    /// The SwiftUI colour for an app. Draws the search panel's site discs and the frame border.
    static func color(forApp appName: String) -> Color {
        color(hue: hue(forApp: appName))
    }

    /// The same colour for the AppKit layers that draw the track.
    ///
    /// `NSColor(hue:saturation:brightness:alpha:)` is device RGB and appearance-independent, which is
    /// what is wanted here — see the note on `saturation`.
    static func nsColor(forApp appName: String) -> NSColor {
        nsColor(hue: hue(forApp: appName))
    }

    /// Both renderers, keyed on the arc rather than on a name, so the guard can render a hue it
    /// chose rather than hunting for a name that hashes to one.
    static func color(hue: Double) -> Color {
        Color(hue: hue / 360, saturation: saturation, brightness: brightness)
    }

    static func nsColor(hue: Double) -> NSColor {
        NSColor(
            hue: CGFloat(hue / 360),
            saturation: CGFloat(saturation),
            brightness: CGFloat(brightness),
            alpha: 1)
    }
}
