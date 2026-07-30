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
/// **The hue range must skip purple.** A hash swept over all 360° emits purple for roughly one turn
/// in six, and purple is off-brand anywhere in the product (`INV-UI-1`,
/// `docs/product/invariants/brand-ui.md`). Excluding it after the fact — clamping, nudging, retrying
/// the hash — leaves the property untested and one refactor from returning. The range simply does
/// not contain it: hues are drawn from `[0°, 250°)`, which stops short of violet at 250° and never
/// reaches magenta, so no input can produce one. `RewindTests` asserts that over every app name in
/// the real database plus a large generated sweep.
enum RewindPalette {

    /// The hue arc app colours are drawn from, in degrees: red → orange → yellow → green → cyan →
    /// blue, stopping before violet.
    ///
    /// 250° is the ceiling because violet begins there and purple sits at 270–290°. The upper reach
    /// of the wheel (magenta and pink, 300–340°) is excluded too — not because those are purple, but
    /// because at the saturation and brightness below they are close enough to read as it, and a
    /// brand rule nobody can eyeball is a brand rule that erodes. 250° of arc separates the ~22
    /// distinct apps in a real database comfortably.
    static let hueCeiling: Double = 250

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
    private static let hueBuckets: UInt64 = 2_503

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

    /// The hue in degrees for an app name. Always in `[0, 250)`, so never purple.
    static func hue(forApp appName: String) -> Double {
        // Case- and whitespace-folded: "Google Chrome" and "google chrome " are one app on a
        // timeline, and giving them two colours would split one stretch of a day into two.
        let key = appName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let bucket = stableHash(key) % hueBuckets
        return Double(bucket) / Double(hueBuckets) * hueCeiling
    }

    /// The SwiftUI colour for an app.
    static func color(forApp appName: String) -> Color {
        Color(hue: hue(forApp: appName) / 360, saturation: saturation, brightness: brightness)
    }

    /// The same colour for the AppKit layers that draw the track.
    ///
    /// `NSColor(hue:saturation:brightness:alpha:)` is device RGB and appearance-independent, which is
    /// what is wanted here — see the note on `saturation`.
    static func nsColor(forApp appName: String) -> NSColor {
        NSColor(
            hue: CGFloat(hue(forApp: appName) / 360),
            saturation: CGFloat(saturation),
            brightness: CGFloat(brightness),
            alpha: 1)
    }
}
