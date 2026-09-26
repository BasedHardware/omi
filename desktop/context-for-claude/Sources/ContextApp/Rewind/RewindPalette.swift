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
/// Three things about their implementation had to change.
///
/// **The hash must be stable across launches.** `String.hashValue` is seeded per process in Swift,
/// so a track keyed on it draws Cursor blue this morning and orange after a relaunch — which
/// destroys the only thing the colour is for, since recognising the shape of a day depends on the
/// colours meaning the same thing tomorrow. FNV-1a is computed here, in full, over the name's UTF-8:
/// a fixed function with fixed constants cannot drift with a toolchain or a process.
///
/// **The output must never contain violet.** A hash swept over all 360° emits an off-brand hue for
/// roughly one turn in three, and that family is off-brand anywhere in the product (`INV-UI-1`,
/// `product/invariants/brand-ui.md`). Excluding it after the fact — clamping, nudging, retrying
/// the hash — leaves the property untested and one refactor from returning. The range simply does
/// not contain it: every band below ends at or under `hueCeiling`, which stops a clear distance
/// short of pure blue and never reaches magenta, so no input can produce one. `RewindTests` asserts
/// that on the *rendered colour* of every value this can emit, not on the constants.
///
/// **A continuous arc is not a palette; it is a gradient.** See `bands`.
enum RewindPalette {

    // MARK: - The bands

    /// One hue family, and the brightness at which that family is drawn.
    ///
    /// Brightness is per band rather than global because HSB brightness is not lightness: at one
    /// fixed value a yellow renders roughly three times as light as a blue, so a single constant
    /// either lets the yellows go pale or drags the blues to near-black. Each band therefore carries
    /// the brightness at which *its* hues land inside the legibility window described on `bands`.
    struct Band: Sendable, Equatable {
        /// Only ever used in test failure messages, which is worth a string: "bucket 1904 (hue
        /// 191.3)" says nothing, "cyan" says which entry below to go and edit.
        let name: String
        /// Inclusive at the start, exclusive at the end — the band owns `[hueStart, hueEnd)`.
        let hueStart: Double
        let hueEnd: Double
        let brightness: Double
    }

    /// A colour this palette can emit, as the three numbers that produce it.
    ///
    /// Returned instead of a `Color` so a guard can ask what a swatch *is* — how saturated, how
    /// light — rather than only what it looks like after two different frameworks have rendered it.
    struct Swatch: Sendable, Equatable {
        let hue: Double
        let saturation: Double
        let brightness: Double
    }

    /// The hue families app colours are drawn from, low to high.
    ///
    /// **Why a set of separated bands rather than one continuous arc, which is what this shipped
    /// with.** The old palette swept `[0°, 220°)` uniformly. Two things follow from that and both
    /// were visible on a real day's track:
    ///
    /// - *No variety.* Green occupies 70°–160° of the wheel, so 41% of every app landed in one
    ///   family, and the eye does not read 8° of hue as a difference. A day came out as long runs of
    ///   near-identical green with the occasional orange, and two adjacent segments were routinely
    ///   indistinguishable — which defeats the only thing a per-app colour is for.
    /// - *No solidity.* The sweep also crossed 60°–95°, the yellow-green transition, which at the
    ///   old fixed saturation of 0.52 renders khaki — sRGB (178, 163, 86) at 52°. Washed-out olive
    ///   is what the user reported, and it is what those two numbers make.
    ///
    /// The bands below fix both by construction. Hue is spent where it buys a *nameable* difference
    /// rather than in proportion to degrees: seven families, each 10°–16° wide, separated by gaps
    /// the palette never emits from.
    ///
    /// **The legibility window every band is tuned into, and what actually sets it.** The track is
    /// not a bare bar. Three things sit *on* a segment: the badge ring (`controlBackgroundColor`),
    /// the playhead (`labelColor`, which carries its own contrasting stroke and therefore always
    /// reads), and **white monogram type** — `RewindTrackView`'s fallback disc, `RewindAppIcon`'s,
    /// and the search panel's site discs, which are this same palette on another surface. The type is
    /// the binding one. White at ~10 pt semibold needs 3:1, which caps relative luminance at
    /// **0.30**, and no choice about the ring can move that: the ring is ours and could be flipped
    /// dark over a light segment, but the monogram is white at all three call sites and one of them
    /// is not this file's to change.
    ///
    /// Each band's brightness is the largest value keeping its whole span under that cap, so the
    /// colours are as vivid as the type on them allows and no more. Measured over all 2 503 emittable
    /// swatches: luminance 0.151–0.296, chroma 0.92 throughout, worst contrast against white type or
    /// a light ring **3.03:1**, against a dark ring **3.19:1**. The arc this replaces measured
    /// 0.168–0.422 at chroma 0.52 and **2.22:1** — so this is far more saturated *and* strictly more
    /// legible, which was never a trade-off anyone had to make; it was just never measured.
    /// `RewindTests` pins every one of those floors over the whole domain.
    ///
    /// **Why there is no yellow band — the one thing here somebody will want to add back.** The
    /// 40°–90° family has no vivid form under that cap. At luminance 0.30 the best a yellow can do is
    /// sRGB (166, 138, 13): fully saturated and still, unmistakably, olive. It shipped once as
    /// exactly that and was reported as exactly that. Brightening it to a real gold (230, 194, 18)
    /// leaves white type on it at **1.74:1** — illegible, on a surface this file does not own. So the
    /// stretch is skipped outright: `orange → lime` is a 54° gap, and every colour inside it is one
    /// this palette has decided it cannot draw well. Seven vivid families beat eight with a muddy
    /// one. A yellow band comes back only together with a monogram ink that adapts to its own ground
    /// at all three call sites; until then `RewindTests` fails the moment one is emitted.
    /// **Brightness alternates deliberately, and that is the second axis of variety.** Pinning every
    /// band to the same luminance was the first cut and it made hue-neighbours hard to tell apart on
    /// a real track: `lime` and `green` at the same lightness read as one green run. So the families
    /// alternate bright / deep along the wheel — a bright band takes the largest brightness its whole
    /// span can hold under the type cap, a deep band the smallest its span can hold above the
    /// dark-ring floor. Two segments now differ in *lightness as well as hue* whichever pair of apps
    /// happen to sit next to each other, which is what the eye actually reads at 4 pt wide. The
    /// closest pair went from lime/green to teal/cyan and its sRGB separation nearly doubled.
    static let bands: [Band] = [
        Band(name: "red", hueStart: 2, hueEnd: 16, brightness: 1.00),  // bright
        Band(name: "orange", hueStart: 26, hueEnd: 36, brightness: 0.68),  // deep
        Band(name: "lime", hueStart: 90, hueEnd: 104, brightness: 0.65),  // bright
        Band(name: "green", hueStart: 126, hueEnd: 142, brightness: 0.50),  // deep
        Band(name: "teal", hueStart: 156, hueEnd: 170, brightness: 0.65),  // bright
        Band(name: "cyan", hueStart: 188, hueEnd: 200, brightness: 0.65),  // deep
        Band(name: "blue", hueStart: 206, hueEnd: 218, brightness: 0.99),  // bright
    ]

    /// The wall no band may reach, in degrees.
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
    /// 240° is the wall. 225° is where a colour at these saturations and brightnesses still reads
    /// unambiguously blue rather than indigo — it is `royalblue`'s hue, and equivalently it is the
    /// point that keeps a quarter of the cyan→blue sector's green lift. 220° sits 5° inside that, so
    /// bucket quantisation, a colour-space round trip, or a future retune of a band cannot walk an
    /// emitted colour onto the boundary. The blue band stops at 218°, another 2° inside that again.
    static let hueCeiling: Double = 220

    /// One saturation for every band, and deliberately not appearance-dependent.
    ///
    /// An app's colour is its identity, so it must not change when the user switches to Dark — a
    /// segment that inverts is a segment whose colour means nothing. 0.92 is the "solid" the report
    /// asked for: it is *perceptual* chroma too, since these bands never clip a channel, so every
    /// swatch measures 0.92 chroma-over-max rather than the 0.52 the previous fixed pair produced.
    /// Held below 1.0 so a band is a colour rather than a primary — a track of eight pure hues reads
    /// as a test card.
    static let saturation: Double = 0.92

    /// A prime modulus finer than the bands, so two names that differ only slightly still land on
    /// visibly different hues rather than colliding into the same integer degree.
    ///
    /// Internal rather than private because it is the size of this type's entire output domain: every
    /// colour it can ever produce is `swatch(bucket:)` for some bucket below this, which is what lets
    /// the brand guard check all of them instead of sampling names and hoping.
    static let hueBuckets: UInt64 = 2_503

    // MARK: - Name → colour

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

    /// The swatch for an app name.
    static func swatch(forApp appName: String) -> Swatch {
        // Case- and whitespace-folded: "Google Chrome" and "google chrome " are one app on a
        // timeline, and giving them two colours would split one stretch of a day into two.
        let key = appName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return swatch(bucket: stableHash(key) % hueBuckets)
    }

    /// Where one bucket lands, as a colour rather than only a hue.
    ///
    /// Split out from `swatch(forApp:)` so the output domain is enumerable. A brand rule sampled over
    /// names is a statistical argument; over `0..<hueBuckets` it is a complete one, and this palette
    /// is small enough that there is no reason to settle for the weaker kind.
    ///
    /// Buckets are spread across the bands rather than across the *degrees* the bands cover, so each
    /// family gets an equal share of apps. Weighting by width would hand the 20°-wide red band
    /// two-thirds more apps than the 12°-wide cyan one for no reason a person looking at the track
    /// could name.
    static func swatch(bucket: UInt64) -> Swatch {
        let position = Double(bucket % hueBuckets) / Double(hueBuckets) * Double(bands.count)
        // `min` rather than a wrap: `position` is below `bands.count` for every valid bucket, and the
        // clamp exists only so a future `hueBuckets` that divides badly cannot index past the end.
        let index = min(bands.count - 1, Int(position))
        let band = bands[index]
        return Swatch(
            hue: band.hueStart + (position - Double(index)) * (band.hueEnd - band.hueStart),
            saturation: saturation,
            brightness: band.brightness)
    }

    /// The band a bucket belongs to. Only the guards ask, but they ask by name, and reconstructing
    /// the answer from a hue at the call site is how two definitions of "which band" get to disagree.
    static func band(bucket: UInt64) -> Band {
        let position = Double(bucket % hueBuckets) / Double(hueBuckets) * Double(bands.count)
        return bands[min(bands.count - 1, Int(position))]
    }

    /// The hue in degrees for an app name. Always below `hueCeiling`, so never in the violet family.
    static func hue(forApp appName: String) -> Double { swatch(forApp: appName).hue }

    /// Which family an app landed in. Only the guards ask, and they ask through here rather than
    /// re-folding the name themselves — a second copy of the key normalisation is a second answer to
    /// "which band is Chrome in", and the two would drift.
    static func band(forApp appName: String) -> Band {
        let key = appName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return band(bucket: stableHash(key) % hueBuckets)
    }

    // MARK: - Rendering

    /// The SwiftUI colour for an app. Draws the search panel's site discs and the frame border.
    static func color(forApp appName: String) -> Color { color(swatch(forApp: appName)) }

    /// The same colour for the AppKit layers that draw the track.
    static func nsColor(forApp appName: String) -> NSColor { nsColor(swatch(forApp: appName)) }

    /// Both renderers, keyed on a swatch rather than on a name, so the guard can render a colour it
    /// chose rather than hunting for a name that hashes to one.
    static func color(_ swatch: Swatch) -> Color {
        Color(hue: swatch.hue / 360, saturation: swatch.saturation, brightness: swatch.brightness)
    }

    /// `NSColor(hue:saturation:brightness:alpha:)` is device RGB and appearance-independent, which is
    /// what is wanted here — see the note on `saturation`.
    static func nsColor(_ swatch: Swatch) -> NSColor {
        NSColor(
            hue: CGFloat(swatch.hue / 360),
            saturation: CGFloat(swatch.saturation),
            brightness: CGFloat(swatch.brightness),
            alpha: 1)
    }
}
