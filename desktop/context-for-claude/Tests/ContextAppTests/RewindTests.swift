import AppKit
import ContextCore
import XCTest

@testable import ContextApp

/// The Rewind window's pure decisions, tested where they are decidable without a screen: the brand
/// rule on segment colour, the Vision coordinate flip, and the honest-resolution rule behind the
/// "open externally" button.
final class RewindTests: XCTestCase {

    // MARK: - Segment colour

    /// The reason the palette computes FNV-1a itself instead of using `String.hashValue`.
    ///
    /// Swift seeds `hashValue` per process, so the implementation this was ported from redraws every
    /// app in a different colour on every launch — which destroys the only thing a per-app colour is
    /// for. This asserts the hash is a fixed function of its input by pinning known values; if
    /// somebody swaps it back to `hashValue`, these constants stop matching.
    func testStableHashIsPinnedAndNotProcessSeeded() {
        // FNV-1a 64-bit offset basis, i.e. the empty string.
        XCTAssertEqual(RewindPalette.stableHash(""), 0xcbf2_9ce4_8422_2325)
        // Standard FNV-1a test vectors.
        XCTAssertEqual(RewindPalette.stableHash("a"), 0xaf63_dc4c_8601_ec8c)
        XCTAssertEqual(RewindPalette.stableHash("foobar"), 0x85944_171_f73967e8 & 0xffff_ffff_ffff_ffff)
    }

    func testHueIsStableAcrossCallsAndCaseInsensitive() {
        let first = RewindPalette.hue(forApp: "Google Chrome")
        XCTAssertEqual(first, RewindPalette.hue(forApp: "Google Chrome"))
        // One app, one colour: a stretch of a day must not split in two because a title was cased
        // differently.
        XCTAssertEqual(first, RewindPalette.hue(forApp: "google chrome "))
    }

    // MARK: - INV-UI-1, decided on the pixel
    //
    // ## Why the assertions this replaces passed a violet disc
    //
    // They were `hue < RewindPalette.hueCeiling` (250) and `!(250...330).contains(hue)`. The second
    // was written to be a second opinion — "stated independently of the ceiling constant" — but it
    // took the *same* boundary as its lower bound, so it was the same opinion twice, and 249.9°
    // satisfied both. That is the colour that shipped: sRGB (101, 86, 179), a lavender site disc in
    // the search panel, measured on screen at (134, 121, 191) after compositing. A hue in degrees is
    // a number; "looks violet" is a property of the pixel, and no inequality between two constants
    // can stand in for it — a wrong constant is invisible to a test whose only vocabulary is that
    // constant. So the guard below renders the colour and asks the pixel.
    //
    // ## What "looks violet" is, structurally
    //
    // Stated once, in `BrandColourGuard.swift`, and shared with the accent guard in `SettingsTests`
    // — which had the same defect with different constants. Short version: violet is the hue family
    // the eye reads as a mixture of the spectrum's two ends, `min(R, B) > G`, and `BrandColour`
    // measures how far a rendered pixel sits clear of it.

    /// The guard, over the palette's **entire** output domain rather than a sample of it.
    ///
    /// Both rendering paths are checked because both ship: `nsColor` draws the timeline segments and
    /// their badges, `color` draws the search panel's site discs — which is the surface the violet
    /// was seen on — and the frame border. They are separate constructors in separate colour spaces,
    /// so agreeing about one of them is not evidence about the other.
    func testEveryColourThePaletteCanEmitReadsAsBlueNotViolet() {
        // `BrandColour` skips near-greys, which have no hue to be wrong about. A palette that went
        // grey would therefore be *skipped* rather than checked, so the rule below would stop being
        // a rule silently. It cannot: this palette's saturation is fixed and well above the line.
        XCTAssertGreaterThan(
            RewindPalette.saturation, BrandColour.neutralSaturation,
            "a palette this desaturated would be waved through as neutral, not checked")

        var maxHue = 0.0
        for bucket in 0..<RewindPalette.hueBuckets {
            let swatch = RewindPalette.swatch(bucket: bucket)
            let band = RewindPalette.band(bucket: bucket)
            maxHue = max(maxHue, swatch.hue)
            assertReadsOnBrand(
                RewindPalette.nsColor(swatch), "bucket \(bucket), \(band.name) \(swatch.hue)°, AppKit")
            assertReadsOnBrand(
                NSColor(RewindPalette.color(swatch)),
                "bucket \(bucket), \(band.name) \(swatch.hue)°, SwiftUI")
        }
        // Reported rather than asserted as a bound: the property above is the rule, this is what the
        // bands actually reached while satisfying it.
        XCTAssertLessThan(maxHue, RewindPalette.hueCeiling)
        XCTAssertGreaterThan(
            maxHue, RewindPalette.bands[RewindPalette.bands.count - 1].hueEnd - 1,
            "the top band must actually be used")
    }

    /// The bands are a partition with gaps, and the gaps are the feature.
    ///
    /// Ascending, non-overlapping, non-empty, and every one of them stopping short of the wall. This
    /// is structure rather than appearance — the rendered-pixel guard above is what proves the brand
    /// rule — but a band table that silently overlapped or ran backwards would still hash apps into
    /// colours that are not the families the header says they are.
    func testTheBandsAreOrderedSeparatedAndStopShortOfTheWall() {
        XCTAssertFalse(RewindPalette.bands.isEmpty)
        for band in RewindPalette.bands {
            XCTAssertLessThan(band.hueStart, band.hueEnd, "\(band.name) is empty or inverted")
            XCTAssertGreaterThanOrEqual(band.hueStart, 0, "\(band.name) starts below the wheel")
            XCTAssertLessThan(band.hueEnd, RewindPalette.hueCeiling, "\(band.name) reaches the wall")
            XCTAssertGreaterThan(band.brightness, 0)
            XCTAssertLessThanOrEqual(band.brightness, 1)
        }
        for (lower, upper) in zip(RewindPalette.bands, RewindPalette.bands.dropFirst()) {
            // A strict gap, not merely "does not overlap": two bands that met would be one band, and
            // the whole point of the table is that the muddy stretches between families are never
            // emitted from.
            XCTAssertLessThan(
                lower.hueEnd, upper.hueStart,
                "\(lower.name) and \(upper.name) run together; the gap between families is the point")
        }
        // The yellow family, which has no vivid form under the cap the white monogram sets — see
        // `testNoColourLandsInTheYellowFamilyThatHasNoVividForm` — plus the lime→green transition.
        // Named so the case is a fixture rather than a memory.
        for muddy in [44.0, 50.0, 54.0, 60.0, 70.0, 80.0, 112.0, 120.0] {
            XCTAssertFalse(
                RewindPalette.bands.contains { muddy >= $0.hueStart && muddy < $0.hueEnd },
                "\(muddy)° is inside a band; that is mud this table exists to skip")
        }
    }

    /// The amber band that shipped in the first cut of this table, and must not come back on its own.
    ///
    /// It was reported exactly as the arc before it was — still olive — and the measurement says why:
    /// at the luminance the white monogram allows, the best a yellow-family hue can do is sRGB
    /// (166, 138, 13). Asserted on the *emitted hue* over the whole domain rather than on the band
    /// table, so a yellow reintroduced by widening a neighbour or retuning a brightness is caught the
    /// same way a new band would be.
    ///
    /// The escape hatch is deliberate and is named in the failure message: a yellow may return once
    /// the monogram ink adapts to its own ground at all three call sites — `RewindTrackView`'s
    /// fallback disc, `RewindAppIcon`, and `SearchFavicon` — because white type is the whole of the
    /// cap. Adapting only the badge *ring* does not buy it, which is the trap this test exists to
    /// stop the next person walking into.
    func testNoColourLandsInTheYellowFamilyThatHasNoVividForm() {
        for bucket in 0..<RewindPalette.hueBuckets {
            let hue = RewindPalette.swatch(bucket: bucket).hue
            XCTAssertFalse(
                (38.0..<88.0).contains(hue),
                "bucket \(bucket) emits \(hue)° — the yellow family, which under this palette's "
                    + "luminance cap can only render olive. It returns with an adaptive monogram "
                    + "ink at all three call sites, not before")
        }

        // The guard's own two-sided check. The reported olive sits *inside* the cap, which is the
        // whole point: the cap is not what made it olive, the hue family is — so raising the cap
        // (by adapting the ring, say) would not have rescued it, and only skipping the family does.
        let olive = RewindPalette.Swatch(
            hue: 49, saturation: RewindPalette.saturation, brightness: 0.64)
        XCTAssertTrue((38.0..<88.0).contains(olive.hue))
        XCTAssertLessThanOrEqual(Self.relativeLuminance(RewindPalette.nsColor(olive)), Self.luminanceCap)
        // And a yellow bright enough to actually read as gold puts white type at 1.74:1 — under the
        // 3:1 floor, on `SearchFavicon`'s disc as much as on the track's.
        let gold = RewindPalette.Swatch(hue: 50, saturation: RewindPalette.saturation, brightness: 0.90)
        XCTAssertLessThan(
            Self.contrast(RewindPalette.nsColor(gold), .white), 3.0,
            "a gold that reads gold must be recognised as illegible under white monogram type")
    }

    // MARK: - Solid, and still legible under everything drawn on top
    //
    // The report was "the colours need to be more solid, more vibrant, more variety", and it pulls
    // against what sits on a segment. Three things do: the badge ring (`controlBackgroundColor`), the
    // playhead (`labelColor`, which carries a contrasting stroke and so always reads), and white
    // monogram type — `RewindTrackView`'s fallback disc, `RewindAppIcon`'s, and `SearchFavicon`'s.
    //
    // **Which of them is binding is the thing to get right, and it is the type, not the ring.** The
    // ring is ours: it could be flipped dark over a light segment and stop constraining anything. The
    // monogram is white at all three call sites and one of them is outside this file, so the cap it
    // sets — relative luminance 0.30 for 3:1 — stands whatever the ring does. Both floors are
    // asserted below, separately, so a future change that makes the ring adaptive can see at a glance
    // that it has not moved the other one.

    /// Highest relative luminance at which white ~10 pt semibold type still clears 3:1.
    private static let luminanceCap = 0.30

    /// The chroma floor, the white-type floor, and the ring floor, over every colour this can emit.
    func testEveryColourIsSolidAndStaysLegibleUnderTypeAndRing() {
        // Well above the 0.52 the fixed pair produced, and stated as a floor rather than as equality
        // with `RewindPalette.saturation` — HSB saturation and the chroma the eye reads are only the
        // same number while no channel clips, which is a property of the bands and not a given.
        let chromaFloor = 0.85
        let contrastFloor = 3.0

        var worstChroma = 1.0
        var worstType = 99.0
        var worstLight = 99.0
        var worstDark = 99.0
        var worstCase = ""
        for bucket in 0..<RewindPalette.hueBuckets {
            let swatch = RewindPalette.swatch(bucket: bucket)
            let colour = RewindPalette.nsColor(swatch)
            worstChroma = min(worstChroma, BrandColour.read(colour)?.saturation ?? 0)

            let type = Self.contrast(colour, .white)
            if type < worstType { worstCase = "\(RewindPalette.band(bucket: bucket).name) \(swatch.hue)°" }
            worstType = min(worstType, type)
            worstLight = min(worstLight, Self.contrast(colour, Self.ring(.aqua)))
            worstDark = min(worstDark, Self.contrast(colour, Self.ring(.darkAqua)))
            XCTAssertLessThanOrEqual(
                Self.relativeLuminance(colour), Self.luminanceCap,
                "\(RewindPalette.band(bucket: bucket).name) \(swatch.hue)° is lighter than white "
                    + "monogram type can sit on")
        }

        XCTAssertGreaterThanOrEqual(
            worstChroma, chromaFloor,
            "a segment measured only \(worstChroma) chroma — the report was that these read washed out")
        XCTAssertGreaterThanOrEqual(
            worstType, contrastFloor,
            "\(worstCase) leaves the white monogram at \(worstType):1 — this is the binding floor, "
                + "and it is set by type at three call sites rather than by the ring")
        XCTAssertGreaterThanOrEqual(
            worstLight, contrastFloor,
            "\(worstCase) leaves the badge ring at \(worstLight):1 on a light window")
        XCTAssertGreaterThanOrEqual(
            worstDark, contrastFloor,
            "\(worstCase) leaves the badge ring at \(worstDark):1 on a dark window")
    }

    /// The guard's own regression test: the palette this replaces has to fail it.
    ///
    /// Without this, "the bands are solid" and "the guard cannot tell solid from washed out" look
    /// identical — which is exactly how a fixed saturation of 0.52 stayed in the product long enough
    /// to be reported by a user rather than by a test.
    func testTheSolidityGuardRejectsThePaletteThisReplaced() {
        // The retired constants, verbatim: one saturation and one brightness for the whole 0°–220°
        // sweep. 52° is the khaki that was actually on screen.
        let retired = { (hue: Double) in
            NSColor(hue: hue / 360, saturation: 0.52, brightness: 0.70, alpha: 1)
        }
        XCTAssertLessThan(
            BrandColour.read(retired(52))?.saturation ?? 1, 0.85,
            "0.52 saturation must be recognised as washed out")
        // sRGB (178, 163, 86): the khaki, and it leaves white monogram type — and the light badge
        // ring — at 2.22:1, under the 3:1 the guard above requires.
        XCTAssertLessThan(
            Self.contrast(retired(52), .white), 3.0,
            "the old arc's yellow-green must be recognised as too light for white type")
        XCTAssertLessThan(Self.contrast(retired(52), Self.ring(.aqua)), 3.0)
        // The same measurement on today's worst case, so the improvement is a number in the record
        // rather than a claim in a comment.
        let worst = (0..<RewindPalette.hueBuckets)
            .map { Self.contrast(RewindPalette.nsColor(RewindPalette.swatch(bucket: $0)), .white) }
            .min() ?? 0
        XCTAssertGreaterThan(worst, Self.contrast(retired(52), .white))
    }

    /// `controlBackgroundColor` — the badge ring's own colour — resolved in a named appearance.
    ///
    /// Resolved rather than hardcoded: the ring is drawn with that semantic, so a test that assumed
    /// "white" and "#1E1E1E" would be measuring against a guess that the next macOS release is free
    /// to invalidate.
    private static func ring(_ appearance: NSAppearance.Name) -> NSColor {
        var resolved = NSColor.controlBackgroundColor
        NSAppearance(named: appearance)?.performAsCurrentDrawingAppearance {
            resolved = NSColor.controlBackgroundColor.usingColorSpace(.sRGB) ?? resolved
        }
        return resolved
    }

    /// WCAG relative luminance, over sRGB.
    private static func relativeLuminance(_ color: NSColor) -> Double {
        guard let rgb = color.usingColorSpace(.sRGB) else { return 0 }
        let linear = [rgb.redComponent, rgb.greenComponent, rgb.blueComponent].map { component -> Double in
            let value = Double(component)
            return value <= 0.03928 ? value / 12.92 : pow((value + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    }

    private static func contrast(_ first: NSColor, _ second: NSColor) -> Double {
        let a = relativeLuminance(first)
        let b = relativeLuminance(second)
        return (max(a, b) + 0.05) / (min(a, b) + 0.05)
    }

    /// The guard's own regression test: it must reject the colour that shipped.
    ///
    /// Without this, "the palette is clean" and "the guard cannot see violet" are indistinguishable —
    /// which is precisely how the old assertion looked healthy for as long as it did.
    func testTheGuardRejectsTheVioletThatShipped() {
        // 249.9° is what the 250° ceiling could emit, and did — on both rendering paths. Rendered at
        // the bands' own saturation, so what is on trial is the hue rather than a second retune.
        let violet = RewindPalette.Swatch(
            hue: 249.9, saturation: RewindPalette.saturation, brightness: 0.70)
        assertReadsOffBrand(RewindPalette.nsColor(violet), "the shipped violet, AppKit")
        assertReadsOffBrand(NSColor(RewindPalette.color(violet)), "the shipped violet, SwiftUI")

        // The pixel as measured on screen: the same colour after compositing, which is what a
        // screenshot of the search panel gives you.
        assertReadsOffBrand(
            NSColor(srgbRed: 134 / 255, green: 121 / 255, blue: 191 / 255, alpha: 1),
            "the measured on-screen pixel")

        // Blend invariance, stated as a test rather than as a claim: the same colour at 45% over a
        // white ground is a much paler lavender and is still caught.
        assertReadsOffBrand(
            NSColor(
                srgbRed: 0.45 * 101 / 255 + 0.55, green: 0.45 * 86 / 255 + 0.55,
                blue: 0.45 * 179 / 255 + 0.55, alpha: 1),
            "a washed-out lavender")

        // The margin's boundary, pinned from both sides. 226° is *outside* the wedge — the old
        // test's vocabulary could not object to it — and is rejected anyway, because it reads indigo.
        let indigo = RewindPalette.Swatch(
            hue: 226, saturation: RewindPalette.saturation, brightness: 0.70)
        XCTAssertGreaterThan(
            BrandColour.read(RewindPalette.nsColor(indigo))?.clearance ?? -1, 0,
            "226° is outside the wedge")
        assertReadsOffBrand(
            RewindPalette.nsColor(indigo), "226°, outside the wedge but hugging it")

        // And the real top of the palette — the last colour the blue band can actually emit — clears
        // the margin rather than sitting on it. Taken from the band table rather than written as a
        // literal, so narrowing or widening that band re-runs the check instead of dodging it.
        let top = RewindPalette.bands[RewindPalette.bands.count - 1]
        let topSwatch = RewindPalette.Swatch(
            hue: top.hueEnd, saturation: RewindPalette.saturation, brightness: top.brightness)
        XCTAssertGreaterThanOrEqual(
            BrandColour.read(RewindPalette.nsColor(topSwatch))?.clearance ?? 0,
            BrandColour.blueMargin,
            "the top of the \(top.name) band must clear the margin, not sit on it")
    }

    /// The names side: every real app name and every host the search panel can be asked for lands
    /// inside that domain. The colours are already proven safe above; what this pins is that the
    /// mapping from a name cannot escape the arc.
    ///
    /// Hosts are here because `SearchFavicon` feeds this palette a domain, not an app name, and the
    /// violet disc was a domain's.
    func testEveryNameAndHostMapsIntoTheSafeArc() {
        let realAppNames = [
            "Arc", "Cursor", "Warp", "QuickTime Player", "Preview", "Google Chrome", "Telegram",
            "ChatGPT Atlas", "Claude", "Messages", "Finder", "omi-people-intel", "Notes",
            "System Settings", "Terminal", "Xcode", "Slack", "Safari", "Mail", "Music",
            "Activity Monitor", "Unknown", "Figma", "iTerm2",
        ]
        // Hosts that landed in the wedge under the 250° arc: gitlab.com was 244.7°, reddit.com
        // 242.9°, bsky.app 240.8°. They are named here so the case is a fixture, not a memory.
        let realHosts = [
            "github.com", "gitlab.com", "reddit.com", "bsky.app", "anthropic.com", "claude.ai",
            "news.ycombinator.com", "figma.com", "linear.app", "medium.com", "x.com", "google.com",
        ]
        var names = realAppNames + realHosts
        for index in 0..<20_000 { names.append("generated-app-\(index)") }

        for name in names {
            let hue = RewindPalette.hue(forApp: name)
            XCTAssertGreaterThanOrEqual(hue, 0, "hue below the wheel for \(name)")
            XCTAssertLessThan(hue, RewindPalette.hueCeiling, "\(name) escaped the arc at \(hue)")
        }
        // Spot-check the whole pipeline on the real names rather than trusting the arc alone.
        for name in realAppNames + realHosts {
            assertReadsOnBrand(RewindPalette.nsColor(forApp: name), name)
            assertReadsOnBrand(NSColor(RewindPalette.color(forApp: name)), "\(name), SwiftUI")
        }
    }

    /// The colour is a real colour rather than a semantic that would collapse to the same value for
    /// every app — and two different apps must actually differ.
    ///
    /// The second half is what keeps narrowing the arc honest: a ceiling low enough to satisfy the
    /// brand rule by squeezing every app into one blue would satisfy the guard above and destroy the
    /// only thing the palette is for.
    func testDifferentAppsGetDifferentHues() {
        let hues = ["Arc", "Cursor", "Warp", "Messages", "Finder"].map(RewindPalette.hue(forApp:))
        XCTAssertEqual(Set(hues).count, hues.count, "distinct apps must be distinguishable")

        let spread = Self.aRealDaysApps.map(RewindPalette.hue(forApp:))
        XCTAssertGreaterThan(
            (spread.max() ?? 0) - (spread.min() ?? 0), 150,
            "a real day's apps must still span the arc, not cluster into one colour")
    }

    /// The variety property, which the spread above cannot state.
    ///
    /// A spread of 150° is satisfied by thirteen apps in one green and one app in blue, and that is
    /// close to what the continuous arc actually produced: uniform over `[0°, 220°)` it put 41% of
    /// every app into green alone, so a day read as long runs of the same colour with the occasional
    /// orange. What a person needs from the track is that the *next* segment looks different from
    /// this one, which is a statement about how many families are in play, not about their range.
    func testARealDaysAppsSpreadAcrossHueFamiliesRatherThanCrowdingOne() {
        let families = Dictionary(grouping: Self.aRealDaysApps, by: { RewindPalette.band(forApp: $0).name })

        XCTAssertGreaterThanOrEqual(
            families.count, RewindPalette.bands.count - 1,
            "a real day must reach almost every family; it reached \(families.keys.sorted())")
        let crowded = families.max { $0.value.count < $1.value.count }
        XCTAssertLessThanOrEqual(
            crowded?.value.count ?? 0, Self.aRealDaysApps.count / 3,
            "\(crowded?.key ?? "one family") took \(crowded?.value.count ?? 0) of "
                + "\(Self.aRealDaysApps.count) apps — that is the green sea this table replaced")
    }

    /// The apps on this machine's own database, which is what the palette is actually judged on.
    private static let aRealDaysApps = [
        "Arc", "Cursor", "Warp", "QuickTime Player", "Google Chrome", "Claude", "Messages",
        "Finder", "Notes", "Terminal", "Xcode", "Slack", "Safari", "Music", "Photos", "Mail",
        "Preview", "Telegram", "ChatGPT Atlas", "Figma", "iTerm2", "Activity Monitor",
    ]

    // MARK: - Badge artwork
    //
    // The reported defect: "the logos in timeline appear inverted". They were — mirrored about their
    // horizontal axis, every one of them.
    //
    // `RewindTrackView` is `isFlipped`, and the badge was drawn with
    // `NSImage.draw(in:from:operation:fraction:)`, which Apple documents as behaving like the
    // six-argument form with `respectFlipped: false`: it ignores the flipped state of the current
    // context and lays the image out in AppKit's bottom-left orientation regardless. So Finder's face
    // came out upside down and Safari's needle pointed the wrong way, while the handful of icons that
    // are vertically symmetric looked fine — which is why it survived being looked at.
    //
    // These render the real view through `cacheDisplay(in:to:)` and read the pixels back. Nothing
    // here restates the fix: an assertion about `respectFlipped` appearing in the source would pass
    // for a call that passed `false`.

    /// An unmistakably asymmetric stand-in for an app icon: red across the top half, blue across the
    /// bottom, drawn in the image's own (unflipped) space so "top" means what it means on screen.
    @MainActor
    private static func halfAndHalfIcon() -> NSImage {
        let icon = NSImage(size: NSSize(width: 32, height: 32))
        icon.lockFocus()
        NSColor.red.setFill()
        NSRect(x: 0, y: 16, width: 32, height: 16).fill()
        NSColor.blue.setFill()
        NSRect(x: 0, y: 0, width: 32, height: 16).fill()
        icon.unlockFocus()
        return icon
    }

    /// Wide enough that the single block's badge is clamped to nothing and lands dead centre.
    private static let trackWidth: CGFloat = 200

    /// A track showing one hour of one app, wide enough that its badge lands dead centre.
    ///
    /// The appearance is pinned rather than inherited: the badge ring is `controlBackgroundColor` and
    /// a tinted stencil is `labelColor`, so a test that took whatever the runner happened to be in
    /// would be reading a different pixel on a developer's machine than in CI. `.aqua` is the
    /// timeline window's own — it is glass, and `InkGlass.appearanceName` pins it.
    @MainActor
    private static func trackShowing(_ app: String, in appearance: NSAppearance.Name = .aqua)
        -> RewindTrackView
    {
        let start = 1_785_000_000.0
        let span = 3_600.0
        let view = RewindTrackView(
            frame: NSRect(x: 0, y: 0, width: trackWidth, height: RewindTrackView.height))
        view.appearance = NSAppearance(named: appearance)
        view.apply(
            blocks: [
                ActivityBlock(
                    app: app, window: nil, startedAt: start, endedAt: start + span, sampleText: nil)
            ],
            frames: [],
            trackStart: start,
            trackSpan: span,
            // No playhead: it is drawn last and full height, and it would sit over the one column
            // of pixels these assertions read.
            playheadAt: nil)
        return view
    }

    @MainActor
    private static func render(_ view: RewindTrackView) throws -> NSBitmapImageRep {
        let rep = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: rep)
        return rep
    }

    /// One pixel of a render, addressed in **points**.
    ///
    /// `bitmapImageRepForCachingDisplay(in:)` sizes itself for the backing store, so on a Retina
    /// machine the rep is twice the view in each direction while `NSBitmapImageRep.colorAt(x:y:)`
    /// indexes pixels. Reading a point coordinate straight out of it therefore samples a quarter of
    /// the way into the picture — which on the first run of this guard landed above the bar entirely
    /// and read the sheet, i.e. the assertion was measuring nothing. The scale is taken from the rep
    /// rather than from `NSScreen`, so this reads the same on a laptop and on a headless runner.
    private static func colour(_ rep: NSBitmapImageRep, atPoint point: NSPoint) throws -> NSColor {
        let scale = Double(rep.pixelsWide) / Double(trackWidth)
        let sampled = rep.colorAt(x: Int(Double(point.x) * scale), y: Int(Double(point.y) * scale))
        return try XCTUnwrap(sampled?.usingColorSpace(.sRGB))
    }

    /// The badge's vertical extent in points: 18 pt centred on the bar's midline, which
    /// `RewindTrackView.barRect` puts at y = 22 in this view's flipped space. Sampled a few points
    /// either side of that midline so both reads are well inside the circular clip.
    private static let badgeTop = NSPoint(x: 100, y: 17)
    private static let badgeBottom = NSPoint(x: 100, y: 27)
    /// Inside the disc but above the monogram glyph, which is the one part of the badge the letter
    /// never reaches: the disc spans y 13–31 and a capital at 9.9 pt semibold sits about y 18–26.
    /// Kept off the disc's rim too, so the read is the fill rather than its antialiased edge.
    private static let badgeAboveGlyph = NSPoint(x: 100, y: 16)

    @MainActor
    func testABadgeDrawsItsIconTheRightWayUpInTheFlippedTrack() throws {
        let app = "orientation-fixture-\(UUID().uuidString)"
        AppIconCache.shared.seed(Self.halfAndHalfIcon(), forApp: app)

        let rep = try Self.render(Self.trackShowing(app))

        // The badge is `badgeSize` (18 pt) centred on the bar's midline, and the bar's midline is at
        // y = 22 in this view's flipped space — which is also the bitmap's, since both measure down
        // from the top. 17 and 27 are a few points either side of it, inside the circular clip.
        let top = try Self.colour(rep, atPoint: Self.badgeTop)
        let bottom = try Self.colour(rep, atPoint: Self.badgeBottom)

        XCTAssertGreaterThan(
            top.redComponent, top.blueComponent,
            "the top of the badge is drawing the bottom of the icon — the logo is upside down")
        XCTAssertGreaterThan(
            bottom.blueComponent, bottom.redComponent,
            "the bottom of the badge is drawing the top of the icon — the logo is upside down")
    }

    /// The other direction, which is what keeps the test above from being satisfied by a blank badge:
    /// the two sampled points must genuinely disagree, and they must be the icon's colours rather
    /// than the monogram fallback's.
    @MainActor
    func testTheOrientationGuardIsLookingAtTheIconAndNotAnEmptyBadge() throws {
        let app = "orientation-fixture-\(UUID().uuidString)"
        AppIconCache.shared.seed(Self.halfAndHalfIcon(), forApp: app)

        let rep = try Self.render(Self.trackShowing(app))
        let top = try Self.colour(rep, atPoint: Self.badgeTop)
        let bottom = try Self.colour(rep, atPoint: Self.badgeBottom)

        XCTAssertGreaterThan(top.redComponent, 0.5, "the badge is not showing the icon at all")
        XCTAssertGreaterThan(bottom.blueComponent, 0.5, "the badge is not showing the icon at all")
        XCTAssertNotEqual(top.redComponent, bottom.redComponent, accuracy: 0.001)

        // And an app with no icon anywhere on this machine still gets a badge — the monogram disc, in
        // its own segment colour. Without this, "the icon drew" and "the fallback drew" are the same
        // observation.
        //
        // **The name is fixed, and a random one is what made this test flaky.** `RewindPalette`
        // derives hue and brightness from the string, so a fresh `UUID()` each run drew the disc in a
        // different colour every time — while `badgeAboveGlyph` samples three points inside a disc
        // spanning y 13–31, close enough that a constant sliver of antialiased rim blends the read
        // toward the ground beneath it. The *absolute* error that blend produces scales with how far
        // the chosen colour sits from that ground, so the tolerance below was a lottery over the
        // palette rather than a statement about the drawing: observed passing 38 runs and then
        // failing at 0.148 against 0.116. A fixed name makes the blend a constant, so this assertion
        // now either holds or does not, reproducibly — which is the only thing a guard is worth.
        // The name still matches no real app, which is the property the case is about.
        let unknown = "no-such-app-orientation-fixture"
        let fallback = try Self.render(Self.trackShowing(unknown))
        let disc = try Self.colour(fallback, atPoint: Self.badgeAboveGlyph)
        let expected = try XCTUnwrap(RewindPalette.nsColor(forApp: unknown).usingColorSpace(.sRGB))
        XCTAssertEqual(disc.redComponent, expected.redComponent, accuracy: 0.03)
        XCTAssertEqual(disc.greenComponent, expected.greenComponent, accuracy: 0.03)
        XCTAssertEqual(
            disc.blueComponent, expected.blueComponent, accuracy: 0.03,
            "the monogram disc must be drawn in the app's own segment colour")
    }

    /// Full-colour artwork is never tinted; a genuine stencil always is.
    ///
    /// The two halves are one rule — the image's `isTemplate` flag decides, and nothing at the call
    /// site does — and they fail in opposite directions: templating a real icon flattens a logo into
    /// a silhouette nobody can recognise, and *not* honouring a real stencil leaves opaque black
    /// artwork inside a dark badge ring.
    ///
    /// Rendered in Dark on purpose. A stencil is black-with-alpha by construction, so "was it tinted"
    /// is only a visible question where the label colour is *not* black — and it is the appearance
    /// where getting it wrong costs something, since untinted black artwork inside a dark badge ring
    /// is a badge with nothing in it.
    @MainActor
    func testTemplateIconsAreTintedAndRealArtworkIsLeftAlone() throws {
        // A real template image: opaque black where the mark is, transparent everywhere else.
        let stencilImage = NSImage(size: NSSize(width: 32, height: 32))
        stencilImage.lockFocus()
        NSColor.black.setFill()
        NSRect(x: 0, y: 16, width: 32, height: 16).fill()
        stencilImage.unlockFocus()

        // The same pixels twice, and only the flag differs — which is what makes this a test of the
        // flag rather than of two unrelated pictures.
        let untinted = stencilImage.copy() as! NSImage
        stencilImage.isTemplate = true

        let stencil = "stencil-\(UUID().uuidString)"
        let plain = "plain-\(UUID().uuidString)"
        let artwork = "artwork-\(UUID().uuidString)"
        AppIconCache.shared.seed(stencilImage, forApp: stencil)
        AppIconCache.shared.seed(untinted, forApp: plain)
        AppIconCache.shared.seed(Self.halfAndHalfIcon(), forApp: artwork)

        let tintedTop = try Self.colour(
            Self.render(Self.trackShowing(stencil, in: .darkAqua)), atPoint: Self.badgeTop)
        let plainTop = try Self.colour(
            Self.render(Self.trackShowing(plain, in: .darkAqua)), atPoint: Self.badgeTop)
        let artworkTop = try Self.colour(
            Self.render(Self.trackShowing(artwork, in: .darkAqua)), atPoint: Self.badgeTop)

        // Black artwork, not declared a stencil: it stays black, which is the whole reason the
        // declared one has to be tinted.
        XCTAssertLessThan(plainTop.redComponent, 0.2, "undeclared artwork must not be tinted")
        // Declared a stencil: it takes the label colour, which in Dark is light.
        XCTAssertGreaterThan(
            tintedTop.redComponent, 0.6,
            "a template image must take the label colour — untinted it is black in a dark badge")
        XCTAssertGreaterThan(tintedTop.greenComponent, 0.6)
        XCTAssertGreaterThan(tintedTop.blueComponent, 0.6)
        // And full-colour artwork keeps its own colour in the same appearance.
        XCTAssertGreaterThan(
            artworkTop.redComponent, 0.5,
            "a full-colour app icon was tinted; it must ship as its author drew it")
        XCTAssertGreaterThan(artworkTop.redComponent, artworkTop.blueComponent + 0.3)
    }

    // MARK: - Live Text geometry

    /// Vision measures from the bottom-left; every drawing system here measures from the top-left.
    /// The flip is `1 - y - height`, and the classic bug is writing `1 - y`, which puts every
    /// highlight exactly one box-height too high.
    func testScreenRectFlipsVisionsBottomLeftOrigin() {
        // A box occupying the bottom-left tenth of the image.
        let block = LiveTextBlock(
            id: 0, text: "hi", boundingBox: CGRect(x: 0, y: 0, width: 0.1, height: 0.1))
        let rect = block.screenRect(for: CGSize(width: 1000, height: 1000))

        XCTAssertEqual(rect.minX, 0, accuracy: 0.001)
        // Bottom in Vision space becomes bottom in top-left space: y = 1 - 0 - 0.1 = 0.9.
        XCTAssertEqual(rect.minY, 900, accuracy: 0.001)
        XCTAssertEqual(rect.width, 100, accuracy: 0.001)
        XCTAssertEqual(rect.height, 100, accuracy: 0.001)
    }

    func testScreenRectPlacesATopBoxAtTheTop() {
        let block = LiveTextBlock(
            id: 0, text: "title", boundingBox: CGRect(x: 0, y: 0.9, width: 1, height: 0.1))
        let rect = block.screenRect(for: CGSize(width: 800, height: 600))

        // y = 1 - 0.9 - 0.1 = 0, i.e. flush with the top edge.
        XCTAssertEqual(rect.minY, 0, accuracy: 0.001)
        XCTAssertEqual(rect.height, 60, accuracy: 0.001)
    }

    /// The wrong flip and the right one disagree for any box that is not vertically centred, which is
    /// what makes this worth pinning rather than eyeballing.
    func testFlipIsNotTheNaiveOneMinusY() {
        let block = LiveTextBlock(
            id: 0, text: "x", boundingBox: CGRect(x: 0, y: 0.2, width: 0.5, height: 0.3))
        let correct = block.screenRect(for: CGSize(width: 100, height: 100)).minY
        let naive = (1.0 - 0.2) * 100

        XCTAssertEqual(correct, 50, accuracy: 0.001)
        XCTAssertNotEqual(correct, naive, accuracy: 0.001)
    }

    // MARK: - Open externally

    private func frame(title: String?, app: String = "Warp") -> RewindFrame {
        RewindFrame(
            id: 1, capturedAt: 0, appName: app, windowTitle: title,
            imagePath: "/tmp/frame.heic")
    }

    /// The button must be **absent**, not disabled, for a frame that resolves to nothing — which on
    /// the real database is 99.9% of them.
    func testOrdinaryWindowTitleResolvesToNothing() {
        XCTAssertNil(OpenExternally.target(for: frame(title: "zsh")))
        XCTAssertNil(OpenExternally.target(for: frame(title: nil)))
        XCTAssertNil(OpenExternally.target(for: frame(title: "✳ Claude Code")))
        XCTAssertNil(OpenExternally.target(for: frame(title: "/nonexistent/path/for/tests")))
    }

    /// The regression this file exists for. Arc's window title is the *page* title, and on this
    /// machine 73 frames carry a `t.co` link quoted inside a tweet's text. Resolving that URL and
    /// opening it navigates somewhere the user never went — a confidently wrong answer, which is
    /// worse than a hidden button. No URL in a title may ever produce a target.
    func testAUrlQuotedInsideAPageTitleIsNeverOpened() {
        let realTitle = """
            Aidan Guo on X: "A billion people produce the most valuable dataset in the world every \
            day – and delete it every night. We're recording it. Introducing @AttentionInc \
            https://t.co/wT0pLYHt01" / X
            """
        XCTAssertNil(
            OpenExternally.target(for: frame(title: realTitle, app: "Arc")),
            "a link drawn inside a page is not that page's address")
        XCTAssertNil(OpenExternally.target(for: frame(title: "https://example.com", app: "Arc")))
    }

    /// What genuinely does resolve: a terminal whose title is its working directory. This is the app
    /// declaring the window's subject rather than text that happened to be on screen.
    func testATitleThatIsAnExistingDirectoryResolvesToThatFolder() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("rewind-open-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let target = OpenExternally.target(for: frame(title: directory.path))

        XCTAssertEqual(target, .folder(directory))
        XCTAssertEqual(target?.symbolName, "folder")
    }

    func testATitleThatIsAnExistingFileResolvesToThatFile() throws {
        let file = FileManager.default.temporaryDirectory
            .appendingPathComponent("rewind-open-\(UUID().uuidString).txt")
        try Data("x".utf8).write(to: file)
        defer { try? FileManager.default.removeItem(at: file) }

        let target = OpenExternally.target(for: frame(title: file.path))

        XCTAssertEqual(target, .file(file))
        XCTAssertEqual(target?.symbolName, "doc")
    }

    /// `~` and `~/…` are how shells write a home-relative directory, and Warp's real titles use them.
    func testHomeRelativeTitleIsExpanded() {
        let target = OpenExternally.target(for: frame(title: "~"))
        XCTAssertEqual(target, .folder(URL(fileURLWithPath: NSHomeDirectory())))
    }

    /// A path mentioned inside a sentence is not a window showing that path. Only whole
    /// separator-delimited segments count, which is exactly what keeps the URL-in-a-title case out.
    func testAPathEmbeddedInProseIsNotResolved() {
        XCTAssertNil(
            OpenExternally.target(
                for: frame(title: "I was reading \(NSHomeDirectory()) earlier today")))
    }

    /// Editors title windows "file — project"; both sides are tried, so the real path is found
    /// wherever the app put it.
    func testEitherSideOfASeparatorIsTried() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("rewind-open-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        XCTAssertEqual(
            OpenExternally.target(for: frame(title: "main.swift — \(directory.path)")),
            .folder(directory))
        XCTAssertEqual(
            OpenExternally.target(for: frame(title: "\(directory.path) — main.swift")),
            .folder(directory))
    }

    // MARK: - Brand: no hardcoded light-only colours
    //
    // A static tripwire, not behavioural coverage — labelled as such. It guards a property that is
    // invisible in the appearance a developer happens to be running: the implementation this was
    // ported from is hardcoded dark, with dozens of `Color.white.opacity(…)` and `NSColor(white:…)`
    // values that vanish on a light window. Catching a reintroduced one needs a source scan, because
    // rendering in one appearance cannot see it.

    func testRewindSourcesUseNoLightOnlyColourLiterals() throws {
        let directory = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // ContextAppTests
            .deletingLastPathComponent()  // Tests
            .deletingLastPathComponent()  // package root
            .appendingPathComponent("Sources/ContextApp/Rewind", isDirectory: true)

        let files = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
            .filter { $0.pathExtension == "swift" }
        XCTAssertFalse(files.isEmpty, "the Rewind sources moved; update this scan")

        for file in files {
            let source = try String(contentsOf: file, encoding: .utf8)
            for (number, line) in source.split(separator: "\n", omittingEmptySubsequences: false).enumerated() {
                // Comments explain *why* the two intentional cases are correct, so they are not code.
                let code = line.trimmingCharacters(in: .whitespaces)
                guard !code.hasPrefix("//"), !code.hasPrefix("///") else { continue }

                XCTAssertFalse(
                    code.contains("NSColor(white:"),
                    "\(file.lastPathComponent):\(number + 1) uses NSColor(white:), which is light-only")
                XCTAssertFalse(
                    code.contains("Color.white.opacity") || code.contains(".white.opacity"),
                    "\(file.lastPathComponent):\(number + 1) uses a white opacity wash, which is light-only")
                XCTAssertFalse(
                    code.lowercased().contains("purple"),
                    "\(file.lastPathComponent):\(number + 1) mentions purple (INV-UI-1)")
                XCTAssertFalse(
                    code.contains("preferredColorScheme(.dark)"),
                    "\(file.lastPathComponent):\(number + 1) forces dark; the window must follow the system")
            }
        }
    }
}

// MARK: - The timeline does not stand aside

/// **The timeline stays where it is while the search window is up, and a closed one stays closed.**
///
/// The repealed behaviour: the timeline used to order itself out on `SearchPanelEvent.opened` and
/// come back on `.closed`, because the search surface was a borderless slab summoned from the
/// timeline's own header that landed over the very window it was summoned from. That yield is a dead
/// end against a persistent main window — open the timeline, press its own "Search All" pill,
/// `.opened` fires, the timeline is ordered off screen, `.closed` never arrives, and there is nothing
/// left to bring it back.
///
/// These put a real window on screen, which the old tests did not have to: the yield was observable
/// as an *intent* flag, and there is no flag any more precisely because there is no yield. What
/// replaced it is only observable as the window's own visibility, so that is what is asserted.
@MainActor
final class RewindVisibilityTests: XCTestCase {

    private var root: URL!

    override func setUpWithError() throws {
        try super.setUpWithError()
        root = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("rewind-visibility-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDown() {
        RewindWindow.dismiss()
        if let root { try? FileManager.default.removeItem(at: root) }
        super.tearDown()
    }

    /// A timeline over an empty capture database. Enough to have a real window: what is being
    /// asserted is where the window is, not what is in it.
    private func presentTheTimeline() throws {
        let store = try ContextStore(url: root.appendingPathComponent("context.db"))
        RewindWindow.present(store: store, via: .menuBarRow)
    }

    /// The search surface being asked for, and going away again, leaves the timeline alone.
    ///
    /// Both halves matter. `.opened` not hiding it is the repeal; `.closed` not *showing* it is the
    /// other half of the same statement — a window that reappears because something else went away is
    /// a window the user cannot get rid of.
    func testTheTimelineDoesNotYieldToTheSearchWindow() throws {
        try presentTheTimeline()
        XCTAssertTrue(RewindWindow.isVisible, "the timeline never came up, so nothing here is measured")

        SearchPanelWatch.report(.opened)
        XCTAssertTrue(RewindWindow.isVisible, "the timeline stood aside for the main window")

        SearchPanelWatch.report(.closed)
        XCTAssertTrue(RewindWindow.isVisible)
    }

    /// Everything else the search surface reports leaves it alone too.
    func testAskingAndAnsweringDoNotMoveTheTimeline() throws {
        try presentTheTimeline()

        SearchPanelWatch.report(.answered(query: "invoice", results: 4))
        SearchPanelWatch.report(.openedMoment(at: 1_699_998_888, hasPicture: true))

        XCTAssertTrue(RewindWindow.isVisible)
    }

    /// **A timeline the user closed stays closed.** This is the dead end the yield produced, stated
    /// as the contract that replaced it: nothing the search surface announces may put the timeline
    /// back on screen, because the only thing that closed it was the user.
    func testATimelineTheUserClosedStaysClosed() throws {
        try presentTheTimeline()
        RewindWindow.dismiss()
        XCTAssertFalse(RewindWindow.isVisible)

        SearchPanelWatch.report(.opened)
        SearchPanelWatch.report(.closed)

        XCTAssertFalse(RewindWindow.isVisible, "something brought the timeline back that the user did not")
    }

    /// …and an explicit ask still brings it back, which is what makes the close recoverable rather
    /// than final.
    func testPresentingAgainBringsAClosedTimelineBack() throws {
        try presentTheTimeline()
        RewindWindow.dismiss()
        XCTAssertFalse(RewindWindow.isVisible)

        try presentTheTimeline()
        XCTAssertTrue(RewindWindow.isVisible)
    }
}

/// **The timeline draws all four of its controls, and nothing may take one away again.**
///
/// The Appearance pane offered four switches to hide them. They were written, persisted and drawn as
/// a live preview beside the switches while `RewindView` drew all four unconditionally — four
/// switches that changed only the picture next to them. They were wired up, and then the pane was
/// removed along with the rest of Appearance, so the end state is the window having its controls
/// unconditionally again.
///
/// A static checker, and labelled as one: the honest behavioural test is that the buttons are in the
/// window, and asserting that means rendering the real `RewindView`, which needs a store, a frame
/// loader and a window on screen. What this catches is the specific way this went wrong twice — a
/// preference gate reappearing over a control — which is invisible to every other test in this file.
final class TimelineControlVisibilityWiringTests: XCTestCase {

    func testNoTimelineControlIsGatedOnAPreference() throws {
        let source = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
                .appendingPathComponent("Sources/ContextApp/Rewind/RewindView.swift"),
            encoding: .utf8)

        XCTAssertFalse(
            source.contains("timelineControls"),
            "a preference is deciding again whether a timeline control is drawn")
        for control in ["openExternallyButton", "liveTextButton", "segmentChevron", "zoomTrack"] {
            XCTAssertTrue(source.contains(control), "the timeline no longer draws \(control)")
        }
    }
}
