import AppKit
import SwiftUI
import XCTest

@testable import ContextApp

/// The app's one piece of glass — the surface the onboarding card, the timeline, settings, the menu
/// bar popover, the search panels and the tutorial's coach marks are all built on.
///
/// Every claim here is about what the *type* ends up sitting on, because that is the only thing a
/// translucent surface can get wrong in a way that matters. The material's own blur is not asserted
/// and cannot be: an `NSVisualEffectView` set to `.behindWindow` samples the desktop, and in a test
/// process there is no desktop behind it. What is asserted is the part this code owns — the pinned
/// appearance, the scrim, the ladder on the resulting ground, the shadow, and what the accessibility
/// setting does to all of it.
final class InkGlassTests: XCTestCase {

    // MARK: - The pin

    /// **The panel is light, and it is light because it says so — not because the machine is.**
    ///
    /// This is the whole mechanism. `NSVisualEffectView` renders a *different, dark* material in
    /// `.darkAqua`, and `controlBackgroundColor` resolves near-black there, which is how this surface
    /// shipped as a black slab. A test host runs in whatever appearance it happens to be in, so the
    /// claim is asserted the hard way: the panel is put inside a view hierarchy explicitly pinned to
    /// Dark, and it still has to come out Aqua.
    @MainActor
    func testTheGlassStaysLightInsideADarkHost() {
        let host = NSView(frame: NSRect(x: 0, y: 0, width: 400, height: 300))
        host.appearance = NSAppearance(named: .darkAqua)
        let glass = InkGlassView(frame: host.bounds)
        host.addSubview(glass)

        XCTAssertEqual(
            glass.panel.effectiveAppearance.name, .aqua,
            "the glass resolved \(glass.panel.effectiveAppearance.name.rawValue) inside a Dark host — "
                + "the pin is what makes this surface light, and it is not holding")
    }

    /// **…and the type on it flips dark with it.**
    ///
    /// The failure this guards against is not subtle-looking, it is invisible: `Ink`'s whole ladder
    /// is an alpha on `labelColor`, which is near-*white* in Dark. A panel forced light whose text
    /// did not follow is white-on-white — nothing on screen at all. Asserted as luminance rather than
    /// as a colour value so it keeps meaning something if the palette is ever re-based.
    @MainActor
    func testTheTypeResolvesDarkOnTheLightGlass() {
        for (name, step) in [("primary", Ink.primary), ("secondary", Ink.secondary), ("tertiary", Ink.tertiary)] {
            XCTAssertLessThan(
                InkContrastProbe.glassLuminance(step), 0.2,
                "\(name) resolves light on the light glass, which is text nobody can see")
        }
        XCTAssertGreaterThan(
            InkContrastProbe.glassLuminance(Ink.surface), 0.8,
            "the scrim colour has to be near-white on the light glass, or the panel is not light")
    }

    // MARK: - Contrast

    /// **The ladder on glass is two rungs, and both of them clear WCAG AA** — in both system
    /// appearances, over both of the two desktops that can be behind the panel.
    ///
    /// Four combinations, and all four have to hold. `Ink`'s alphas were tuned against an opaque
    /// `surface`, and `MenuBarPresentationTests` still asserts them there; that assertion does not
    /// cover any of these windows, because the ground is `surface` at `InkGlass.scrim`, over the
    /// material, over whatever the user has on screen. So the ladder is measured again against
    /// *that* ground, at both extremes — a solid black desktop and a solid white one.
    ///
    /// **`tertiary` is deliberately not asserted here and is asserted to fail below.** The ground is
    /// tuned to the faintest rung the panel carries, so which rungs the panel carries *is* the
    /// design: three rungs bought a ground of 205.5/255 and 17% passthrough, which was reported as an
    /// opaque slab three times. Two rungs buy 154.1/255 and 34.8%. See `Ink.tertiary`.
    ///
    /// The system appearance is varied and is expected to make no difference at all. That is the
    /// point: it is the assertion that the pin, and not the machine, decides what this surface is.
    @MainActor
    func testTheLadderClearsWCAGAAOnTheGlassOnEveryDesktopAndEverySystemAppearance() {
        var readings: [Double] = []
        for system in [NSAppearance.Name.aqua, .darkAqua] {
            for (desktop, label) in [(Color.black, "black desktop"), (Color.white, "white desktop")] {
                let ladder = InkContrastProbe.glassLadder(system: system, over: desktop)
                let where_ = "\(label), system \(system.rawValue)"

                // Both steps carry text under 18 pt, so the bar is AA's 4.5:1 for normal text and not
                // the 3:1 large-text allowance. `secondary` is the binding one: the search results
                // panel sets dense small copy on this glass, so a floor that only held for headlines
                // would be no floor at all.
                XCTAssertGreaterThanOrEqual(
                    ladder.primary, 4.5, "primary is \(ladder.primary):1 on the glass — \(where_)")
                XCTAssertGreaterThanOrEqual(
                    ladder.secondary, 4.5, "secondary is \(ladder.secondary):1 on the glass — \(where_)")

                // …and it is still a ladder on glass, not one colour twice.
                XCTAssertGreaterThan(ladder.primary, ladder.secondary, where_)

                readings.append(ladder.secondary)
            }
        }

        // The two system appearances must produce *identical* readings, not merely passing ones. A
        // difference here means something in the chain is still reading the machine's appearance.
        XCTAssertEqual(readings[0], readings[2], accuracy: 1e-9, "system appearance changed the glass")
        XCTAssertEqual(readings[1], readings[3], accuracy: 1e-9, "system appearance changed the glass")
    }

    /// **Whatever rung sits at the bottom is what pays for the glass, and the ground sits directly on
    /// that rung's floor.**
    ///
    /// This assertion has three times been right about the wrong number, and the shape of the mistake
    /// is worth keeping in front of whoever tunes this next. It first held the *scrim* to a maximum,
    /// then held the scrim to a fraction of `1 − measuredMaterialOpacity` — both quantities of the
    /// scrim, which was never what the desktop had to survive. Then it held the **ground**, which is
    /// the right quantity, but held it against `tertiary`, which is the wrong rung: the ground can
    /// only be as thin as the *faintest thing anyone sets on it*, so the real lever was never a
    /// number in `InkGlass` at all. It was the ladder.
    ///
    /// So the claim is made about the ground, against **the bottom rung the panel actually carries**,
    /// which on glass is `Ink.secondary`. Three boundaries:
    ///
    /// - the ground is light enough that `secondary` clears AA (or the panel is illegible), and
    /// - the ground is *no lighter than it has to be* (or the panel is paper, which is the complaint
    ///   that was made three times), and
    /// - `tertiary` **fails** on this ground, which is what makes "never on glass" a fact about the
    ///   product rather than a convention someone can forget.
    ///
    /// The second is a ratchet rather than a floor: it fails if someone thickens the ground for
    /// comfort, which is the direction every previous retune drifted. The third is the one that
    /// cannot be satisfied by drifting in either direction — lighten the ground far enough to make
    /// `tertiary` legal again and it fails, which is precisely the regression it exists to catch.
    @MainActor
    func testTheBottomRungIsWhatPaysForTheGlass() {
        let shipped = InkContrastProbe.glassLadder(system: .aqua, over: .black)
        XCTAssertGreaterThanOrEqual(shipped.secondary, 4.5)

        // **The ground is on the floor, not above it.** Measured on the real material over a real
        // banded desktop: at scrim 0.14 the ground is 154.1/255 and `secondary` is 4.58:1; at 0.115
        // it is 151.2/255 and 4.48:1 — under AA. The whole remaining budget is under three points of
        // ground, so anything more than a rounding error of headroom here means the ground drifted.
        let headroom = shipped.secondary - 4.5
        XCTAssertLessThan(
            headroom, 0.30,
            "the bottom rung on glass clears AA by \(headroom). That is contrast the panel bought "
                + "with opacity nobody asked for: this surface has been reported as an opaque slab "
                + "three times, and spare contrast on the bottom rung is precisely what that is made "
                + "of. Thin the ground until this rung is just over 4.5.")

        // **And the rung below it does not fit on this ground.** This is the arithmetic behind
        // `Ink.tertiary`'s "never on glass": it is not a taste rule, it is that at 0.68 the glance
        // rung measures 3.60:1 here. Two things fail this line — putting the ground back up where
        // `tertiary` is legal (the panel becomes paper again), or quietly darkening `tertiary` to fit
        // (at which point it is `secondary` with a different name, see that token).
        XCTAssertLessThan(
            shipped.tertiary, 4.5,
            "tertiary clears AA on the shipped glass ground (\(shipped.tertiary):1), which means the "
                + "ground has drifted back up to where a three-rung ladder fits — and a three-rung "
                + "ladder is a 17%-passthrough panel. See Ink.tertiary and InkGlass.scrim.")

        // The negative control for the sweep below: the rule only means anything if the two rungs are
        // genuinely different colours on this ground.
        XCTAssertGreaterThan(
            shipped.secondary - shipped.tertiary, 0.5,
            "secondary and tertiary measure the same on the glass, so promoting a call site from one "
                + "to the other changes nothing and this whole rule is decoration")

        // **And there is no alpha that rescues a third rung on this ground.** The faintest alpha on
        // `labelColor` that still clears AA here is `secondary`'s own, to within a hundredth — so a
        // "darker tertiary for glass" is `secondary` with a second name and a second value to keep
        // true. This is the arithmetic that makes the answer *drop the rung* rather than retune it,
        // and it is asserted rather than written down because it is the step every retune skipped.
        let rescued = InkGlassTests.faintestRungClearingAA(scrim: InkGlass.scrim)
        XCTAssertEqual(
            rescued, 0.80, accuracy: 0.02,
            "the faintest rung this ground supports is \(rescued), which is no longer secondary's "
                + "0.80 — if these have genuinely come apart there may be room for a third rung on "
                + "glass again, and the two-rung rule should be re-derived rather than assumed")
    }

    /// **The panel passes materially more of the desktop than it did, and the number is measured.**
    ///
    /// Held as passthrough — the fraction of the desktop's own luminance that survives to the eye —
    /// because that, and not any alpha, is what "see-through" means. It is derived from the sampled
    /// material constants rather than from the scrim, so a future change that thins the scrim while
    /// swapping in a denser material cannot pass this by moving one number.
    ///
    /// The value asserted is the one taken off the real material on a real desktop (see
    /// `GlassRenderHarness` and the header of `InkGlass.swift`): `.hudWindow` at this scrim measures
    /// **34.8%**, against **17.0%** for the three-rung recipe this replaces and **14.5%** for the
    /// `.headerView` recipe before that. The floor is set below the measurement rather than at it
    /// because the two-layer model reproduces the sampled composite to about 3/255, and a bound tuned
    /// tighter than the model's own error is a flake.
    @MainActor
    func testThePanelPassesMoreOfTheDesktopThanTheRecipeItReplaced() {
        let opacity = Double(InkGlass.measuredMaterialOpacity)
        let passthrough = (1 - opacity) * (1 - Double(InkGlass.scrim))

        XCTAssertGreaterThan(
            passthrough, 0.30,
            "the glass passes \(passthrough) of the desktop. Both previous recipes sat at 14.5% and "
                + "17.0% and both were reported as an opaque slab; the two-rung ladder is what buys "
                + "the difference, so a number back down there means the ground crept up again")
        // …and the material really is a thin one. `.headerView` could not reach the contrast floor at
        // any scrim because its own opacity held the ground above it; a material denser than this
        // puts the surface straight back into that trap.
        XCTAssertLessThan(
            opacity, 0.70,
            "a material \(opacity) opaque owns the ground before the scrim is applied at all, so the "
                + "scrim can no longer reach the contrast floor — which is the defect this recipe fixes")
    }

    /// **The timeline's hour labels clear AA on the glass**, measured on the colour the view actually
    /// hands AppKit.
    ///
    /// The one call site that proved the sweep below is not enough on its own. `RewindTrackView` draws
    /// the 9 pt hour marks with an `NSAttributedString`, and it set them in `NSColor
    /// .tertiaryLabelColor` — never `Ink.tertiary`, so the token sweep was blind to it, and never a
    /// rung anyone had measured. On the ground this window ships with, that is **1.70:1**: not merely
    /// under AA but roughly half as legible as the rung the two-rung rule exists to ban, on the axis
    /// `drawHourTicks` itself calls "what makes the time-linearity legible".
    ///
    /// Asserted on `RewindTrackView.hourLabelAttributes` rather than on a rendered bitmap. That
    /// dictionary is the object AppKit is handed — a real seam through production code, not a
    /// restatement of it — and it is stable, where reading a 9 pt glyph's darkest pixel out of a
    /// render would depend on font rasterisation and would be the sort of test people learn to
    /// re-run.
    @MainActor
    func testTheTimelinesHourLabelsClearWCAGAAOnTheGlass() throws {
        let attributes = RewindTrackView.hourLabelAttributes

        let font = try XCTUnwrap(attributes[.font] as? NSFont, "the hour labels name no font")
        XCTAssertLessThan(
            font.pointSize, 18,
            "the hour labels are large text now, which would move the applicable WCAG bar from 4.5:1 "
                + "to 3:1 — re-derive this assertion rather than letting the bar fall by accident")

        let colour = try XCTUnwrap(
            attributes[.foregroundColor] as? NSColor,
            "the hour labels no longer name a foreground colour, so AppKit draws them in its own "
                + "default and nothing measured here describes what is on screen")
        let ratio = Self.contrastOnGlass(colour)
        XCTAssertGreaterThanOrEqual(
            ratio, 4.5,
            "the timeline's hour labels measure \(ratio):1 on the shipped glass ground over a black "
                + "desktop, under WCAG AA for text this size. The timeline window is glass "
                + "(`RewindWindow` hosts `RewindView` on `InkGlassView`), so these labels sit on the "
                + "panel's ground — use Ink.secondary, which is the bottom rung glass carries.")

        // The negative control, and the exact colour that shipped here. Without it a ground that had
        // drifted light enough to rescue anything would pass the line above and mean nothing.
        let was = Self.contrastOnGlass(.tertiaryLabelColor)
        XCTAssertLessThan(
            was, 2.0,
            "NSColor.tertiaryLabelColor now measures \(was):1 on this ground, which is not the "
                + "invisible it was (1.70:1) — the ground has drifted light and every claim in this "
                + "file about what glass can carry needs re-deriving")
    }

    // MARK: - Static tripwire

    /// **STATIC TRIPWIRE — not behavioural coverage.**
    ///
    /// This test reads source text. It cannot tell you what any view draws, and it must never be
    /// counted as evidence that the app is legible; `testTheBottomRungIsWhatPaysForTheGlass` is the
    /// test that measures the rungs, `testTheTimelinesHourLabelsClearWCAGAAOnTheGlass` measures the
    /// one call site this sweep was blind to, and `SearchSurfaceTests` measures the one panel that
    /// puts type on something other than the ground. What no assertion over a token can cover is a
    /// *new call site* setting faint type on a glass surface — a file no guard has heard of,
    /// rendering 3.6:1 or worse over someone's dark wallpaper. That is a question about the source,
    /// so it is answered with a check on the source, labelled as one.
    ///
    /// **It sweeps for more than `Ink.tertiary`, because the token spelling was never the whole
    /// rule.** The rule is *no faint type on glass*, and the way it was actually broken had nothing
    /// to do with the token: `RewindTrack` set the timeline's hour labels straight in
    /// `NSColor.tertiaryLabelColor` — 1.70:1 on the shipped ground, about half as legible as the rung
    /// this rule exists to ban — and a check that greps one string could not see it. So every faint
    /// spelling a call site can reach for is swept (see `faintTypeOnGlass`), and the app's own token
    /// is one entry in that list rather than the subject of the test.
    ///
    /// Every surface in this app is glass except the menu bar popover (`StatusView`, which is
    /// AppKit's own popover chrome — see the note at the top of that file), so the sweep's default is
    /// "this is glass, faint type is not allowed" and every exception is declared below with its
    /// reason.
    ///
    /// **The declarations are exact counts, not ceilings, and that is the entire ratchet.** The
    /// version this replaces compared `uses > allowed`, which is a ceiling: a file declared at 4
    /// could be migrated to 0 and then grow all four back without the test noticing, and its
    /// companion assertion (`outstanding <= debt`, both derived from the same declaration) could not
    /// fail on a *decrease* at all. That is exactly what happened — nineteen call sites were paid off
    /// in parallel and the list sat there licensing their return. An equality means a re-addition
    /// fails and paying one off *also* fails, with the new number in the message, so the declaration
    /// cannot stay stale in either direction.
    func testNoGlassSurfaceSetsTypeOnTheBottomRung() {
        let root = InkSourceSweep.uiSourceRoot
        var scanned = 0
        var counts: [String: [String: Int]] = [:]

        let files = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)
        while let url = files?.nextObject() as? URL {
            guard url.pathExtension == "swift" else { continue }
            guard let text = try? String(contentsOf: url, encoding: .utf8) else {
                return XCTFail("could not read \(url.path)")
            }
            scanned += 1
            let relative = url.path.replacingOccurrences(of: root.path + "/", with: "")
            // Comments stripped, deliberately: the files that explain *why* the rule exists all name
            // the tokens, and a check that punished them would delete its own reasoning.
            let lines = InkSourceSweep.strippingComments(from: text).components(separatedBy: "\n")
            for spelling in Self.faintTypeOnGlass {
                let uses = lines.filter { $0.contains(spelling) }.count
                if uses > 0 { counts[relative, default: [:]][spelling] = uses }
            }
        }

        // A scan that found nothing because it looked nowhere passes silently, which is the failure
        // mode of every check like this one.
        XCTAssertGreaterThan(scanned, 40, "the sweep found almost no Swift files — check \(root.path)")

        // A declaration naming a spelling the sweep does not look for is a hole that reads like a
        // rule, so the two lists are held together rather than merely written next to each other.
        for (file, spellings) in Self.declaredFaintType {
            for spelling in spellings.keys {
                XCTAssertTrue(
                    Self.faintTypeOnGlass.contains(spelling),
                    "\(file) declares \"\(spelling)\", which is not a spelling this sweep looks for — "
                        + "the entry allows nothing and hides that it allows nothing")
            }
        }

        var added: [String] = []
        var paid: [String] = []
        for file in Set(counts.keys).union(Self.declaredFaintType.keys).sorted() {
            for spelling in Self.faintTypeOnGlass {
                let uses = counts[file]?[spelling] ?? 0
                let allowed = Self.declaredFaintType[file]?[spelling] ?? 0
                guard uses != allowed else { continue }
                let entry = "\(file): \(spelling) — \(uses) uses, \(allowed) declared"
                if uses > allowed { added.append(entry) } else { paid.append(entry) }
            }
        }

        XCTAssertEqual(
            added, [],
            "these set faint type on a surface that is glass. On the shipped ground Ink.tertiary "
                + "measures 3.60:1 and the system's own faint label steps are far worse "
                + "(secondaryLabelColor 2.98:1, tertiaryLabelColor 1.70:1, quaternaryLabelColor "
                + "1.21:1, all over a solid black desktop) — text a user cannot read over a dark "
                + "wallpaper. Use Ink.secondary; glass carries two rungs (see Ink.tertiary). If the "
                + "call site is a *fill* rather than type, declare it in `declaredFaintType` with "
                + "that reason, the way Ink.rowHover and the timeline's empty channel are.")

        XCTAssertEqual(
            paid, [],
            "these are declared above the number of uses actually in the file. That is a stale "
                + "allowance — it is what let a nineteen-entry migration debt sit here after the "
                + "debt was paid, licensing every one of those call sites to come back. Lower each "
                + "count to the number reported here, or delete the entry when it reaches zero.")
    }

    /// **The spellings a glass surface may not set type in**, and what each measures on the shipped
    /// ground over a solid black desktop — the worst desktop a translucent panel can be over.
    ///
    /// | spelling | resolved in `.aqua` | on the glass |
    /// |---|---|---|
    /// | `Ink.tertiary` | `labelColor` @ 0.68 → black @ 0.576 | 3.60:1 |
    /// | `secondaryLabelColor` | black @ 0.498 | 2.98:1 |
    /// | `tertiaryLabelColor` | black @ 0.259 | 1.70:1 |
    /// | `quaternaryLabelColor` | black @ 0.098 | 1.21:1 |
    ///
    /// The SwiftUI hierarchical styles are the same three steps reached by another name, and they are
    /// swept even though the app currently uses none: a rule with a spelling nobody has used yet is
    /// precisely where the next instance lands, and an entry that matches nothing costs nothing.
    /// `placeholderTextColor` (2.98:1 here) and `disabledControlTextColor` (1.66:1) are on the list
    /// for the same reason — both are unused today, both are far under AA on this ground, and both
    /// are what a call site reaches for when it wants "quieter" and has no rung left to drop to.
    ///
    /// Not on the list, deliberately: `Ink.secondary`, which *is* the bottom rung on glass, and
    /// `NSColor.separatorColor`, which is not type — it draws rules and tick marks, where the
    /// applicable floor is WCAG's 3:1 for graphical objects rather than 4.5:1 for text, and where a
    /// blanket ban would be a different rule than the one this file states.
    private static let faintTypeOnGlass: [String] = [
        "Ink.tertiary",
        "secondaryLabelColor",
        "tertiaryLabelColor",
        "quaternaryLabelColor",
        "placeholderTextColor",
        "disabledControlTextColor",
        "foregroundStyle(.secondary)",
        "foregroundStyle(.tertiary)",
        "foregroundStyle(.quaternary)",
        "foregroundColor(.secondary)",
        "foregroundColor(.tertiary)",
    ]

    /// **Every exception, per file and per spelling, with the reason it is one.**
    ///
    /// Per *spelling* and not per file: a single number for a file lets one exception be spent on a
    /// different and worse colour — swap `Ink.tertiary` (5.24:1 on the popover) for
    /// `tertiaryLabelColor` (1.88:1 there) and a per-file count would not move.
    ///
    /// **There is no migration debt here any more.** There was: six glass files carrying nineteen
    /// `Ink.tertiary` call sites, excluded because the two-rung change landed while they were being
    /// edited elsewhere. All six are at zero, so the entries are gone rather than kept at their old
    /// numbers — which is the whole point, because a stale entry is an allowance to put them back.
    private static let declaredFaintType: [String: [String: Int]] = [
        // **Not glass.** The deliberate exception documented at the top of `StatusView`: an
        // `NSPopover` brings its own frosted chrome from a window this process does not own, so the
        // app does not put `InkGlassView` inside it. Its ground is AppKit's, not `InkGlass.scrim`,
        // and the ladder on it is measured against opaque `Ink.surface` by `MenuBarPresentationTests`
        // rather than here.
        "MenuBar/StatusView.swift": ["Ink.tertiary": 2],
        "Onboarding/Ink.swift": [
            // `InkPermissionRow` renders on both surfaces, and its `native` branch — the menu row —
            // only ever appears inside that popover.
            "Ink.tertiary": 1,
            // `Ink.rowHover`. A **fill**, not type: a menu row under the pointer, deliberately barely
            // there. The legibility argument that moved the type ladder does not apply to something
            // nobody reads, and it is on the popover in any case.
            "tertiaryLabelColor": 1,
        ],
        // The timeline track's empty channel — also a **fill**, and one whose whole job is to read as
        // absence. See the note at `RewindTrackView.draw`.
        "Rewind/RewindTrack.swift": ["quaternaryLabelColor": 1],
    ]

    // MARK: - Contrast helpers

    /// The faintest alpha on `labelColor` that still clears AA on the glass at this scrim.
    ///
    /// Scanned rather than solved: the inverse of the sRGB transfer function is easy to get subtly
    /// wrong, and a 0.001 sweep of the same forward model the guard uses cannot disagree with it.
    @MainActor
    private static func faintestRungClearingAA(scrim: CGFloat) -> CGFloat {
        var alpha: CGFloat = 0.50
        while alpha < 1.0 {
            if rungOnGlass(scrim: scrim, alpha: alpha) >= 4.5 { return alpha }
            alpha += 0.001
        }
        return 1.0
    }

    /// The WCAG contrast of an **arbitrary colour** on the shipped glass ground, over a solid black
    /// desktop — the worst ground a translucent panel can have.
    ///
    /// `InkContrastProbe.glassLadder` measures the same ground but only knows the three `Ink` tokens,
    /// and the defect this was written for was a call site that never touched them: AppKit views hand
    /// `NSColor` straight to an `NSAttributedString`, so a guard that can only ask about tokens
    /// cannot see the type they draw. Same two-layer model, same constants, one colour at a time.
    @MainActor
    static func contrastOnGlass(_ colour: NSColor) -> Double {
        var value = 0.0
        NSAppearance(named: InkGlass.appearanceName)!.performAsCurrentDrawingAppearance {
            func linear(_ c: Double) -> Double {
                c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
            }
            func luminance(_ r: Double, _ g: Double, _ b: Double) -> Double {
                0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)
            }
            // The ground is neutral — grey material tint, white scrim, black desktop — so one channel
            // describes it. The *colour* being measured is not assumed neutral.
            let material = Double(InkGlass.measuredMaterialOpacity)
            let tint = Double(InkGlass.measuredMaterialTint)
            let frosted = tint * material  // over a black desktop
            let scrim = Double(InkGlass.groundAlpha(reduceTransparency: false))
            let ground = 1.0 * scrim + frosted * (1 - scrim)

            guard let sRGB = colour.usingColorSpace(.sRGB) else { return }
            let alpha = Double(sRGB.alphaComponent)
            func over(_ channel: CGFloat) -> Double {
                Double(channel) * alpha + ground * (1 - alpha)
            }
            let text = luminance(over(sRGB.redComponent), over(sRGB.greenComponent), over(sRGB.blueComponent))
            let back = luminance(ground, ground, ground)
            value = (max(text, back) + 0.05) / (min(text, back) + 0.05)
        }
        return value
    }

    /// The same model as `InkContrastProbe.glassLadder`, at an arbitrary scrim and an arbitrary alpha
    /// on `labelColor`, so the floors above can be shown to be ones.
    ///
    /// `alpha` is a multiplier on `labelColor`'s own alpha, exactly as `Ink.secondary` and
    /// `Ink.tertiary` are: a raw number here would be a second definition of what the tokens mean.
    @MainActor
    private static func rungOnGlass(scrim: CGFloat, alpha: CGFloat) -> Double {
        var value = 0.0
        NSAppearance(named: InkGlass.appearanceName)!.performAsCurrentDrawingAppearance {
            func linear(_ c: Double) -> Double {
                c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
            }
            // Grey throughout: the material measures neutral and both extreme desktops are neutral.
            let material = Double(InkGlass.measuredMaterialOpacity)
            let tint = Double(InkGlass.measuredMaterialTint)
            let frosted = tint * material  // over a black desktop
            let ground = 1.0 * Double(scrim) + frosted * (1 - Double(scrim))
            let label = Double(NSColor(Ink.primary).usingColorSpace(.sRGB)!.alphaComponent)
            let text = ground * (1 - label * Double(alpha))
            value = (linear(ground) + 0.05) / (linear(text) + 0.05)
        }
        return value
    }

    // MARK: - Reduce Transparency

    /// **Reduce Transparency really produces an opaque background.**
    ///
    /// The whole promise of the setting, in the two values that carry it. A user who has asked macOS
    /// to stop making surfaces see-through gets a solid sheet and no material at all — not a thicker
    /// scrim, not a slower blur. Shipping glass that ignores this is an accessibility defect and not
    /// a rough edge, which is why it is a value a test can hold rather than an `if` inside a view.
    func testReduceTransparencyGivesAnOpaqueGroundAndNoMaterial() {
        XCTAssertEqual(
            InkGlass.groundAlpha(reduceTransparency: true), 1,
            "the ground has to be fully opaque when the user has asked for reduced transparency")
        XCTAssertFalse(
            InkGlass.showsMaterial(reduceTransparency: true),
            "and the blurred material has to be gone, not merely covered")
    }

    /// …and with the setting off it is genuinely glass, so the test above cannot pass by the
    /// translucency having quietly been dropped everywhere.
    func testTheDefaultGroundIsTranslucentAndKeepsItsMaterial() {
        let alpha = InkGlass.groundAlpha(reduceTransparency: false)
        XCTAssertEqual(alpha, InkGlass.scrim)
        XCTAssertLessThan(alpha, 1, "the default ground has to let the desktop through")
        XCTAssertTrue(InkGlass.showsMaterial(reduceTransparency: false))

        // **Deliberately no bound on this alpha.** There used to be one — `alpha <= 0.16` — and it is
        // removed rather than retuned, because it measured the wrong thing and reading it as a
        // translucency guarantee is what let three retunes ship without changing what anyone saw. The
        // scrim is a fraction of *whatever the material left*, so it is only comparable between two
        // recipes with the same material: 0.56 of white over `.hudWindow` is a thinner ground than
        // 0.10 of white over `.headerView` was. What the surface has to be is asserted on the ground
        // and on passthrough instead — see `testThePanelPassesMoreOfTheDesktopThanTheRecipeItReplaced`
        // and `testTheBottomRungIsWhatPaysForTheGlass`.
    }

    /// …and the panel the app actually installs really does what those two values say, in **every**
    /// style it is used in.
    ///
    /// The values above are a policy; this is the wiring. Asserted on the real `NSView` because the
    /// defect being guarded against is not "the policy is wrong", it is "the policy is right and
    /// nothing reads it", which is what shipping a glass window that ignores the setting looks like
    /// from the inside. Both styles, because they are used by different windows and a branch that
    /// only fires for one of them is the shape this defect takes next time.
    @MainActor
    func testEveryStyleOfPanelGoesOpaqueWhenTransparencyIsReduced() throws {
        for (name, style) in [
            ("floating", InkGlassStyle.floating),
            ("fullBleed", InkGlassStyle.fullBleed),
            ("panel", InkGlassStyle.panel()),
        ] {
            let glass = InkGlassView(frame: NSRect(x: 0, y: 0, width: 720, height: 520), style: style)
            glass.layoutSubtreeIfNeeded()

            glass.apply(reduceTransparency: true)
            XCTAssertTrue(glass.material.isHidden, "\(name): the blurred material is still being drawn")
            let opaque = try XCTUnwrap(glass.ground.layer?.backgroundColor)
            XCTAssertEqual(
                opaque.alpha, 1, accuracy: 1e-9, "\(name): the ground is still letting the desktop in")

            XCTAssertTrue(
                glass.sheen.isHidden,
                "\(name): the specular highlight is still drawn on a surface that is no longer glass")

            glass.apply(reduceTransparency: false)
            XCTAssertFalse(glass.material.isHidden, "\(name): the material never came back")
            XCTAssertFalse(glass.sheen.isHidden, "\(name): the highlight never came back")
            let glassy = try XCTUnwrap(glass.ground.layer?.backgroundColor)
            XCTAssertEqual(glassy.alpha, InkGlass.scrim, accuracy: 1e-6, name)
        }
    }

    // MARK: - The specular edge

    /// **The highlight is a line along the top, and it stays there when the panel resizes.**
    ///
    /// It exists because the ground is pinned to the contrast floor and cannot be thinned, so every
    /// remaining bit of "this is glass rather than paper" has to come from cues that spend no
    /// contrast. Two things can go wrong with it and both look like a rendering bug rather than a
    /// tuning one: it grows into a band (a second, lighter panel stacked on the first), or it stops
    /// tracking the top edge on a resize — which is not hypothetical, because the onboarding window
    /// resizes from full screen down to the card when the cinematic lands.
    @MainActor
    func testTheSpecularEdgeIsAHairlineOnTheTopEdgeAtEverySize() {
        let glass = InkGlassView(frame: NSRect(x: 0, y: 0, width: 832, height: 752), style: .floating)
        glass.layoutSubtreeIfNeeded()

        func check(_ label: String) {
            let panel = glass.panel.bounds
            XCTAssertEqual(
                glass.sheen.frame.maxY, panel.maxY, accuracy: 0.5,
                "\(label): the highlight is not on the panel's top edge — a glass panel lit from "
                    + "somewhere other than above reads as a rendering fault")
            XCTAssertEqual(glass.sheen.frame.width, panel.width, accuracy: 0.5, label)
            XCTAssertEqual(
                glass.sheen.frame.height, InkGlassView.sheenHeight, accuracy: 0.01,
                "\(label): a highlight with height is a gradient band, which reads as a second panel")
        }
        check("at the size it was built")

        // The cinematic's landing: the same view, resized under the window.
        glass.setFrameSize(NSSize(width: 500, height: 400))
        glass.layoutSubtreeIfNeeded()
        check("after a resize")
    }

    /// The highlight is **white**, not a palette colour — it is a light source reflecting off the
    /// panel, and INV-UI-1 wants that light neutral.
    @MainActor
    func testTheSpecularEdgeIsNeutralWhiteAndNotAPaletteColour() throws {
        let glass = InkGlassView(frame: NSRect(x: 0, y: 0, width: 400, height: 300))
        glass.layoutSubtreeIfNeeded()
        glass.apply(reduceTransparency: false)

        let colour = try XCTUnwrap(glass.sheen.layer?.backgroundColor)
        let sampled = try XCTUnwrap(NSColor(cgColor: colour)?.usingColorSpace(.sRGB))
        XCTAssertEqual(sampled.redComponent, 1, accuracy: 1e-6)
        XCTAssertEqual(sampled.greenComponent, 1, accuracy: 1e-6)
        XCTAssertEqual(sampled.blueComponent, 1, accuracy: 1e-6)
        XCTAssertEqual(sampled.alphaComponent, InkGlass.sheenAlpha, accuracy: 1e-6)
    }

    // MARK: - The shape and the shadow

    /// One corner for every panel, and it is the rounder one.
    ///
    /// Two things floating over the same desktop rounded to two different radii is the tell that
    /// neither was decided. The floor is the part worth holding: at 16 — where this app was — a large
    /// panel reads as a dialog rather than as a floating object.
    func testEveryFloatingPanelIsCutToOneGenerousCorner() {
        XCTAssertEqual(InkGlass.cornerRadius, 22)
        XCTAssertGreaterThanOrEqual(
            InkGlass.cornerRadius, 20, "a panel cut tighter than this reads as a dialog, not as glass")
        XCTAssertEqual(InkGlassStyle.floating.cornerRadius, InkGlass.cornerRadius)
        XCTAssertEqual(InkGlassStyle.panel().cornerRadius, InkGlass.cornerRadius)
        // The inside of an ordinary titled window is the one surface that is not rounded: the window
        // frame already is, and rounding twice draws a corner inside a corner.
        XCTAssertEqual(InkGlassStyle.fullBleed.cornerRadius, 0)
    }

    /// The shadow is **broad and faint**, which is the whole of why a panel reads as floating.
    ///
    /// The wrong shadow here is not a missing one, it is a tight dark one: an 18 pt radius at 0.22 —
    /// what the tutorial card shipped with — reads as a sticker rather than as an object with air
    /// under it. Held as a shape (wide, low-opacity, offset downward) rather than as three numbers,
    /// so it can be retuned but not turned back into a drop shadow.
    func testTheAmbientShadowIsWideAndFaintRatherThanATightDrop() {
        let shadow = InkGlassShadow.ambient
        XCTAssertGreaterThanOrEqual(shadow.radius, 24, "a \(shadow.radius) pt shadow is a drop shadow")
        XCTAssertLessThanOrEqual(shadow.opacity, 0.35, "a shadow this dark reads as a border")
        XCTAssertGreaterThan(shadow.opacity, 0, "no shadow at all is not the design either")
        XCTAssertLessThan(shadow.offsetY, 0, "the light is above; the shadow falls below the panel")

        // And the window has to leave it somewhere to fall. A borderless window clips at its own
        // bounds, so a panel drawn edge to edge simply has no shadow — which is the same bug as not
        // having one, arrived at from the other direction.
        XCTAssertGreaterThan(shadow.padding, shadow.radius, "the margin cannot be narrower than the blur")
        XCTAssertEqual(InkGlassStyle.floating.inset, shadow.padding)
        XCTAssertEqual(InkGlassStyle.fullBleed.inset, 0, "a window-filling surface must not be inset")
    }

    /// The panel really is inset inside its host, at every size — a 56 pt bar and a 760 pt panel both
    /// have to leave the same room, because the shadow is one value for all of them.
    @MainActor
    func testThePanelLeavesRoomForItsShadowAtEverySize() {
        for size in [NSSize(width: 660, height: 56), NSSize(width: 1180, height: 760)] {
            let outer = NSSize(
                width: size.width + InkGlassStyle.floating.inset * 2,
                height: size.height + InkGlassStyle.floating.inset * 2)
            let glass = InkGlassView(frame: NSRect(origin: .zero, size: outer), style: .floating)
            glass.layoutSubtreeIfNeeded()

            XCTAssertEqual(glass.panel.frame.width, size.width, accuracy: 0.5, "\(size)")
            XCTAssertEqual(glass.panel.frame.height, size.height, accuracy: 0.5, "\(size)")
            XCTAssertEqual(glass.panel.layer?.cornerRadius, InkGlass.cornerRadius, "\(size)")
        }
    }

    /// Content handed to the panel fills the *panel*, not the host — otherwise the card's copy is
    /// drawn out in the transparent shadow margin, which looks exactly like a layout bug because it
    /// is one.
    @MainActor
    func testContentIsLaidOutInsideTheGlassAndNotInTheShadowMargin() {
        let glass = InkGlassView(frame: NSRect(x: 0, y: 0, width: 832, height: 632), style: .floating)
        glass.layoutSubtreeIfNeeded()
        let content = NSView()
        glass.setContent(content)

        XCTAssertTrue(content.isDescendant(of: glass.panel), "content was not hosted inside the glass")
        XCTAssertEqual(content.frame.size, glass.panel.bounds.size)
    }

    // MARK: - The onboarding window

    /// The onboarding window is sized to the card *plus* the shadow's margin, and the card keeps the
    /// size it always had.
    ///
    /// The failure this catches is the one that makes the whole component look broken: sizing the
    /// window to the card, so the panel is inset inside it and the card silently shrinks by 112 pt.
    @MainActor
    func testTheOnboardingWindowIsTheCardPlusTheRoomItsShadowNeeds() {
        let pad = InkGlassStyle.floating.inset
        let card = OnboardingWindow.cardSize
        let window = OnboardingWindow.windowSize
        XCTAssertEqual(card.width, 720, "the reading column plus both gutters")
        // The height is not a free choice and is no longer 520: it is what the permissions card's
        // tallest state measures, plus the page margins and the band the progress dots are
        // reserved. `PermissionsCardLayoutTests` derives and enforces it; restated here only so a
        // change to the pane is a deliberate one rather than a side effect.
        XCTAssertEqual(card.height, 640)
        XCTAssertEqual(
            card.height,
            OnboardingWindow.cardContentHeight + 2 * InkLayout.pagePaddingVertical
                + InkLayout.progressBandHeight,
            "the budget the card is laid out against has to describe the card")
        XCTAssertEqual(window.width, card.width + pad * 2)
        XCTAssertEqual(window.height, card.height + pad * 2)
    }

    // MARK: - Yielding the screen

    /// A show that arrives while the card is still fading out must cancel the `orderOut`.
    ///
    /// The card yields the screen whenever the next thing to click belongs to another app, and on the
    /// permissions run that is three times per grant — so a hide and a show overlapping is the normal
    /// case, not the edge one. The fade made it possible for the two to cross: `orderOut` now runs in
    /// a completion handler, and a completion handler that fires after the user has been sent back to
    /// the card takes the window off screen behind them.
    ///
    /// There is no recovering from that. The app is `LSUIElement` — no Dock icon, no window menu,
    /// nothing to click — so a first-run window ordered out with no path back is a dead install. The
    /// rule is a value precisely so it can be asserted rather than reasoned about in a closure.
    func testAShowArrivingMidFadeCancelsTheHide() {
        // The ordinary case: a hide runs to completion undisturbed.
        XCTAssertTrue(
            OnboardingWindow.hideMayComplete(startedAt: 4, current: 4, stillHidden: true))

        // A show landed while the fade was running — the intent is no longer "hidden".
        XCTAssertFalse(
            OnboardingWindow.hideMayComplete(startedAt: 4, current: 5, stillHidden: false),
            "a fade that has been overtaken by a show must not order the window out")
        // …and even a hide → show → hide round trip must not let the *first* fade do the ordering:
        // the second one owns it, and the first one's completion is stale.
        XCTAssertFalse(
            OnboardingWindow.hideMayComplete(startedAt: 4, current: 6, stillHidden: true),
            "a stale fade must not order the window out on a newer request's behalf")
    }
}

// MARK: - Sweeping the UI sources

/// The plumbing the two static tripwires over `Sources/ContextApp` share — this file's "no bottom
/// rung on glass" and `InkAccentTests`'s "no view reads the machine's accent".
///
/// One copy, for the same reason the palette is one file: two sweeps that disagree about what counts
/// as a comment would report different offenders for the same source, and the one that under-reports
/// is the one nobody notices. Lives beside a test rather than in the package because it exists only
/// to check the package's own source text, exactly as `InkContrastProbe` lives beside
/// `MenuBarPresentationTests`.
enum InkSourceSweep {

    /// `Sources/ContextApp`, found from this file rather than from the working directory, which is
    /// not the package root under every runner.
    static var uiSourceRoot: URL {
        URL(fileURLWithPath: #filePath)  // Tests/ContextAppTests/InkGlassTests.swift
            .deletingLastPathComponent()  // Tests/ContextAppTests
            .deletingLastPathComponent()  // Tests
            .deletingLastPathComponent()  // package root
            .appendingPathComponent("Sources/ContextApp")
    }

    /// Swift source with `//` and `/* */` comments removed, quote-aware so a `//` inside a string
    /// literal does not truncate the line it is on. Line numbering is preserved, so an offender's
    /// reported line is the one a person can open.
    static func strippingComments(from source: String) -> String {
        var out = ""
        var inString = false
        var inLineComment = false
        var inBlockComment = false
        var escaped = false
        var iterator = source.startIndex

        while iterator < source.endIndex {
            let c = source[iterator]
            let next = source.index(after: iterator) < source.endIndex ? source[source.index(after: iterator)] : nil

            if inLineComment {
                if c == "\n" {
                    inLineComment = false
                    out.append(c)
                }
            } else if inBlockComment {
                if c == "*", next == "/" {
                    inBlockComment = false
                    iterator = source.index(after: iterator)
                } else if c == "\n" {
                    out.append(c)  // keep line numbers honest
                }
            } else if inString {
                if escaped {
                    escaped = false
                } else if c == "\\" {
                    escaped = true
                } else if c == "\"" || c == "\n" {
                    inString = false
                }
                out.append(c)
            } else if c == "/", next == "/" {
                inLineComment = true
            } else if c == "/", next == "*" {
                inBlockComment = true
                iterator = source.index(after: iterator)
            } else {
                if c == "\"" { inString = true }
                out.append(c)
            }

            iterator = source.index(after: iterator)
        }
        return out
    }
}
