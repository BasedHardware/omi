//
//  Ink.swift — the shared visual vocabulary for the onboarding window and the menu bar popover.
//
//  Every colour here is a macOS semantic colour or a fixed alpha on one, and the single accent is
//  `NSColor.systemBlue` — a *named* system colour, chosen here rather than read off the machine.
//  No hue is hand-mixed, so there is exactly one palette in the product and it follows the system's
//  appearance for free: no `NSApp.appearance` override, no light-only assumption, no second set of
//  values for dark mode. The palette this replaces was Anthropic's own (ivory paper, clay accent),
//  which made the app read as a piece of someone else's brand pasted into the menu bar.
//
//  Display type is Open Runde, bundled at `Resources/Fonts/OpenRunde-*.otf` and registered at
//  launch by `ContextAppDelegate.registerBundledFonts()`. It is geometric and distinctive and it is
//  ours; reading type stays SF Pro, which is what a native macOS app should be setting body copy
//  in. One threshold (`Font.inkDisplayThreshold`) decides which is which, and a face that fails to
//  register degrades to SF Pro rather than crashing.
//
//  Roles are exposed as whole styles rather than loose numbers because the character of the type
//  lives in the tracking as much as the point size — a caller that hand-assembles
//  `.font(.openRunde(34, .semiBold))` and forgets `.tracking(-1.19)` has quietly shipped a
//  different product. And because tracking is derived from the size (`em × size`, see `InkType`),
//  loose numbers also mean the two drift apart the first time a role is resized.
//  `Text.inkStyle(_:)` makes both mistakes unavailable.
//
//  Brand: system semantics and neutrals only. Never purple, anywhere (INV-UI-1) — and note that
//  the accent is a value *this file picks*, not the one the machine reports. See `Ink.accent`: an
//  accent read off the machine is a hue this app cannot be held to, which is the one thing
//  INV-UI-1 does not allow.
//
//  The full spec, including every value below, is docs/design-system.md.
//

import AppKit
import SwiftUI

// MARK: - Colour

/// The whole palette. Twelve roles, every one of them a system semantic colour or a fixed alpha on
/// one — a colour literal anywhere else in the app is a bug.
enum Ink {
    // Surfaces.

    /// Every surface the app draws: the onboarding sheet, the popover ground.
    ///
    /// `controlBackgroundColor` rather than `windowBackgroundColor`: this is the ground *content*
    /// sits on, which is white in Light and near-black in Dark — a sheet, in both appearances.
    static let surface = Color(nsColor: .controlBackgroundColor)

    // Type, in three steps and no fourth. Which step a run gets is decided by what the reader has
    // to do with it, not by how deep it sits in a stack.
    //
    // The lower two steps are an alpha on `labelColor` and *not* `secondaryLabelColor` /
    // `tertiaryLabelColor`, which is a legibility decision with measurements behind it. The system's
    // own steps are 50% and 26% black in Light, tuned for dense system chrome — an inspector row, a
    // table cell, a menu — where the reader glances at a word beside its subject. Composited over
    // `surface` they measure **3.95:1** and **1.88:1**, so the step that carries whole sentences
    // failed WCAG AA for body text (4.5:1) and the glance step was barely a shade of grey. That is
    // the "greyish hue" onboarding was reported as being hard to read in, and onboarding is the one
    // screen in this app that asks for sustained reading rather than a glance.
    //
    // Alpha on `labelColor` keeps every property this file already relies on: `labelColor` is
    // near-black in Light and near-white in Dark, so one value darkens a light sheet and lightens a
    // dark one — no hardcoded grey, no second set of values for Dark, and it still composites
    // correctly over the popover's vibrant material.
    //
    // The hierarchy survives because it is a hierarchy of *lightness*, not of washing-out. Over
    // `surface` the three steps land at L* 15.6 / 35.0 / 47.4 in Light and 88.0 / 74.2 / 64.3 in
    // Dark — roughly even rungs, and an order of magnitude more separation than the eye needs to
    // read them as three.
    //
    // **There are three rungs, but glass only gets two.** `primary` and `secondary` may go on any
    // surface in the app; `tertiary` may only go on an *opaque* one, which in practice means the
    // menu bar popover. This is not a style preference — it is arithmetic, and it is the single
    // thing that decides how see-through every panel in this app is. See `tertiary`.

    /// Headlines, row copy, the primary button's fill, the granted checkbox — and any state with
    /// something to do about it.
    static let primary = Color(nsColor: .labelColor)
    /// A sentence someone reads: prose, a status line, an upload note — **and, on glass, everything
    /// that is not `primary`.**
    ///
    /// `labelColor` at 0.80 — 7.8:1 over `surface` in Light and 8.3:1 in Dark. AAA (7:1), which is
    /// the right target for the only step that carries whole sentences.
    ///
    /// Most of this app's surfaces are glass, so `surface` is no longer the whole ground: it is
    /// `InkGlass.scrim` of `surface` over a light-pinned blurred desktop. Because the glass pins its
    /// appearance, that ground does not depend on the machine's. **This is now the bottom rung on
    /// glass, so it is the rung that sets how see-through those panels are allowed to be**, and it is
    /// therefore measured rather than assumed: through the real material over the two desktops that
    /// can exist, it lands at **4.58:1 over a solid black desktop and 7.46:1 over a solid white
    /// one**, in both system appearances. Eight hundredths above AA on the worst desktop there is —
    /// this rung is spent, and `InkGlass.scrim` is what spent it.
    ///
    /// It cannot be thinned. It is deliberately not *thickened* either: contrast this rung does not
    /// need is contrast the panel paid for in opacity, which is exactly what an opaque-looking panel
    /// is made of.
    static let secondary = Color(nsColor: .labelColor).opacity(0.80)
    /// A word someone glances at: `Granted`, `Quit`, `Sign out`. Never a whole sentence — **and
    /// never on glass.**
    ///
    /// `labelColor` at 0.68 — 5.2:1 over `surface` in Light, 6.3:1 in Dark, which is a comfortable
    /// glance step on an *opaque* sheet. Its one remaining surface is the menu bar popover, which is
    /// AppKit's own chrome and not `InkGlassView`.
    ///
    /// **The rule "never on glass" is the whole of why those panels are see-through, and it was
    /// arrived at the hard way.** The ground under dark type has to stay light enough for the
    /// *faintest* rung set on it, so whichever rung is at the bottom is what decides the ground, and
    /// the ground is what "glassmorphic" means. With this rung on the panel the floor was a ground of
    /// ≈203/255 and 17% passthrough — pale paper — and three separate retunes of the material and the
    /// scrim moved it by fourteen levels out of 255, correctly reported each time as no change at
    /// all. Dropping it moved the floor to 154/255 and **34.8% passthrough**, twice the desktop, at
    /// the same 4.5:1.
    ///
    /// **And it really is drop-or-nothing: there is no alpha that rescues it.** To clear AA on
    /// today's ground this rung would have to darken to ≈0.79, which *is* `secondary` to within a
    /// hundredth — a third step that measures as the second is not a ladder, it is the same colour
    /// twice with an extra token to keep true. Nor can it darken a little to buy the glass a little:
    /// at 0.69 it is already 7.8 L\* from `secondary` on a Dark sheet, under the 8 L\* the rungs are
    /// held apart by.
    ///
    /// So on a glass surface, promote to `secondary`. A run that was `tertiary` because it is a
    /// sentence rather than a glance word was on the wrong rung anyway; one that was genuinely a
    /// glance word loses a step of hierarchy, which is the price of the panel, paid deliberately.
    ///
    /// Held from three directions: `InkGlassTests.testTheBottomRungIsWhatPaysForTheGlass` asserts
    /// this rung is *under* AA on the shipped ground (so the ground cannot drift back up to where it
    /// would be legal), `InkGlassTests.testNoGlassSurfaceSetsTypeOnTheBottomRung` is a static
    /// tripwire over the glass-hosted sources, and
    /// `MenuBarPresentationTests.testTheLabelLadderKeepsVisibleStepsBetweenItsRungs` keeps it a
    /// distinct step on the opaque surface it still serves.
    static let tertiary = Color(nsColor: .labelColor).opacity(0.68)

    // Edges.

    /// A rule between blocks. The popover uses `Divider()` instead, which draws this itself.
    static let separator = Color(nsColor: .separatorColor)
    /// The edge of something you are meant to press: the secondary button, the empty checkbox.
    /// `separator` is right for a rule and too faint for a control's outline.
    static let hairline = Color(nsColor: .labelColor).opacity(0.22)
    /// The edge of a *panel*, which is a different job and a much fainter one.
    ///
    /// `hairline` outlines a control, where the border is the affordance. A floating glass panel is
    /// defined by its brightness and its shadow; at 0.22 the outline is the loudest thing on the
    /// surface and the panel reads as a drawn box rather than as a piece of glass. The value lives
    /// beside its sibling so the two cannot be confused at a call site — the whole reason the
    /// palette is named roles rather than numbers. See `InkGlass.edgeAlpha`, which is this value.
    static let glassEdge = Color(nsColor: .labelColor).opacity(InkGlass.edgeAlpha)

    /// The one accent, spent on the one thing that is actionable and is not already a button.
    ///
    /// `systemBlue`, and deliberately **not** `NSColor.controlAccentColor`. The accent the user
    /// picked in System Settings was the obvious choice and it is the wrong one: macOS ships Purple
    /// as an accent, so on that machine every selection ring, checkbox, toggle and link in this app
    /// renders purple — and purple is off-brand everywhere in this product (`INV-UI-1`,
    /// `docs/product/invariants/brand-ui.md`). Nothing here can fix that at the call site, because
    /// the hue is not knowable here; the only fix is to stop reading it. A colour that is on brand
    /// on most machines and off brand on the rest is not a palette, it is a coin flip.
    ///
    /// It stays a *named system colour* rather than a literal, so it still tracks the appearance and
    /// still brightens under Increase Contrast — everything `controlAccentColor` was picked for
    /// except the one property that made it unshippable. `SearchInk.chipTint` reached the same
    /// conclusion independently for the query chip.
    ///
    /// Enforced, not asserted: `InkAccentTests` reads this token's rendered pixel through the shared
    /// `BrandColour` predicate *and* asserts it is not the `controlAccentColor` catalog entry — the
    /// second check being the one that survives being run on a machine whose accent happens to be
    /// blue, which is every machine this has been developed on.
    static let accent = Color(nsColor: .systemBlue)

    /// The error colour: the only place the app ever raises its voice.
    static let errorRed = Color(nsColor: .systemRed)
    /// The live indicator. "On" has to read as on at 7 pt, and green is the only colour that says
    /// it without a label.
    static let listeningGreen = Color(nsColor: .systemGreen)

    // Fills. Alpha on `labelColor` rather than a named fill colour, because these have to composite
    // correctly over both the onboarding sheet and the popover's vibrant material: a wash that
    // darkens in Light and lightens in Dark does, and a fixed grey does not.

    /// Permission-row fill on the onboarding sheet. The menu bar popover has no row fill at all —
    /// a real macOS menu does not fill its rows.
    static let rowFill = Color(nsColor: .labelColor).opacity(0.045)
    /// The same row under the pointer. A tappable row has to say so, and macOS has no other
    /// affordance for it.
    static let rowFillHover = Color(nsColor: .labelColor).opacity(0.085)
    /// A *menu* row under the pointer, on the popover. Fainter than `rowFillHover` and over nothing
    /// at rest: the popover's material is already separating the panel from the window, so anything
    /// heavier reads as a second, competing background.
    ///
    /// Deliberately still `tertiaryLabelColor` and not the ladder's `tertiary`: this is a fill, it
    /// is meant to be barely there, and the legibility reason the type ladder moved does not apply
    /// to something nobody reads.
    static let rowHover = Color(nsColor: .tertiaryLabelColor).opacity(0.12)
    /// The pressed state of anything with no fill of its own.
    static let wash = Color(nsColor: .labelColor).opacity(0.06)

    /// The finale's overexposure, composited in `plusLighter`.
    ///
    /// Plain white and not `surface`: `plusLighter` only ever adds, so the exit has to be the
    /// brightest thing available or there is nothing to burn out to — over a dark sheet, adding a
    /// dark grey is invisible. White is also the neutral INV-UI-1 asks for.
    static let glow = Color.white

    // AppKit twins, for the layers SwiftUI cannot reach.

    static let nsSurface = NSColor.controlBackgroundColor
    static let nsPrimary = NSColor.labelColor
    // There is deliberately no `nsAccent`. It was `NSColor.controlAccentColor` and it had no callers
    // at all — the spotlight ring it was written for draws white over a dark halo instead, because
    // the menu bar is routinely dark *and* routinely light (see `SpotlightRingView`). Deleting it
    // rather than repointing it at `systemBlue` is the stronger move: an AppKit twin nothing uses is
    // a second definition of the accent waiting to drift from the first, and the accent is exactly
    // the token this app has already been bitten by having two opinions about. AppKit callers that
    // genuinely need it can say `NSColor(Ink.accent)`.
}

// MARK: - Layout

enum InkLayout {
    /// The reading column: a headline and the sentences under it, centred on the card.
    ///
    /// 488 pt is the width left inside a 560 pt card after the page padding, and it is also the
    /// measure `prose` was sized against — at 17 pt that is a little under 80 characters a line,
    /// which is the top of the range a paragraph stays readable across. Wider is not more generous
    /// here; it is a longer distance for the eye to travel back along.
    static let contentMaxWidth: CGFloat = 488
    /// The list column: the permissions step and the other left-aligned cards.
    ///
    /// Wider than the reading column, and this is what pays for the larger type. A permission row is
    /// not a paragraph — it is a first-person sentence with a checkbox before it and a status word
    /// after it, and those two fixtures take ~116 pt out of the row before the sentence starts. At
    /// 488 pt and 15 pt row copy every row wrapped to two lines and the setup preamble ran to five,
    /// which put the card 23 pt past the window; at 560 the preamble loses a line, a row or two come
    /// back to one, and the card fits with room to spare. Nothing about the measure argument applies
    /// to a list, so the list takes the width the reading column deliberately does not.
    ///
    /// 560 is the card's own width — the reading column plus both gutters — so the list spans the
    /// pane and the 36 pt page padding becomes its margin against the window rather than a second
    /// inset inside it. It is also as wide as the column should go: 560 plus its padding leaves 80 pt
    /// of glass either side, and content that runs closer than that to a rounded edge reads as
    /// content that did not fit.
    static let permissionsMaxWidth: CGFloat = 560
    static let pagePaddingHorizontal: CGFloat = 36
    /// The margin between the copy and the top and bottom edges of the glass. Deliberately *not* a
    /// place to find height for bigger type: it is the only thing keeping a 34 pt headline off a
    /// rounded corner. Width was the lever; this is not one.
    static let pagePaddingVertical: CGFloat = 34
    /// The vertical rhythm. Pick from this ladder rather than inventing a gap.
    static let rhythm: [CGFloat] = [28, 22, 18, 14, 12, 10, 8, 6]

    /// The strip at the foot of every card that the progress dots occupy.
    ///
    /// Reserved rather than drawn over. The dots used to be an `.overlay(alignment: .bottom)` with
    /// 62 pt of padding — a *position*, which is only a safe one while no card's content reaches
    /// that far down, and the permissions card does. Subtracting a band is the version of "clear of
    /// the content" that a longer sentence cannot invalidate. 40 pt is the 5 pt dots plus a rhythm
    /// step of air either side, rounded, which lands them at much the same optical distance from
    /// the rim as the padding did.
    static let progressBandHeight: CGFloat = 44

    /// Between the headline block, the rows, and whichever panel the permissions run has reached.
    static let permissionsBlockSpacing: CGFloat = 18
    /// Between two permission rows.
    static let permissionsRowSpacing: CGFloat = 8
}

// MARK: - Motion

/// Durations from the motion table, in seconds. Pass them through `InkReduceMotion` before use.
enum InkMotion {
    static let stepTransition: Double = 0.240
    static let wordReveal: Double = 1.200
    static let settle: Double = 0.280
    static let checkbox: Double = 0.180
    static let finaleGlow: Double = 0.550
    /// Not in the doc: button press feedback, fast enough to read as pressure rather than animation.
    static let press: Double = 0.090
}

/// Reduce Transparency in one place, for the same reason `InkReduceMotion` exists: the setting is
/// honoured by a call, not by a discipline nobody keeps.
///
/// It has exactly one customer today — the onboarding window's glass — and it lives here anyway,
/// beside the sibling setting and on the same notification, so the second translucent surface this
/// app grows cannot honour it a different way or forget to.
enum InkReduceTransparency {
    static var isEnabled: Bool {
        NSWorkspace.shared.accessibilityDisplayShouldReduceTransparency
    }

    /// Fires when the user flips the setting. The same notification `InkReduceMotion` watches —
    /// macOS posts one for the whole accessibility display group — so an observer has to re-read the
    /// setting it cares about rather than assume which one changed.
    static let didChangeNotification = NSWorkspace.accessibilityDisplayOptionsDidChangeNotification
}

/// Reduce Motion in one place. Every animation in the app goes through this, so honouring the
/// setting is a call rather than a discipline nobody keeps.
enum InkReduceMotion {
    static var isEnabled: Bool {
        NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
    }

    /// Fires when the user flips the setting; posted on `NSWorkspace.shared.notificationCenter`.
    static let didChangeNotification = NSWorkspace.accessibilityDisplayOptionsDidChangeNotification

    /// `nil` under Reduce Motion, which is how SwiftUI spells "apply the change instantly".
    static func animation(_ animation: Animation) -> Animation? {
        isEnabled ? nil : animation
    }

    /// Zero under Reduce Motion. For hand-rolled interpolation (word reveal, backdrop rise) where a
    /// zero duration means "jump to the end state".
    static func duration(_ seconds: Double) -> Double {
        isEnabled ? 0 : seconds
    }

    /// `withAnimation`, or a straight mutation under Reduce Motion.
    static func perform(_ animation: Animation, _ body: () -> Void) {
        if isEnabled {
            body()
        } else {
            withAnimation(animation) { body() }
        }
    }
}

// MARK: - Font resolution

/// The four bundled Open Runde faces. One family carries display, body and label — the site's
/// `--sans`, `--disp` and `--mono` all resolve to it, and so does everything here.
enum RundeWeight {
    case regular, medium, semiBold, bold

    /// PostScript names of the bundled faces. Note the lowercase `b` in `Semibold`: it is the name
    /// inside the `.otf`, and the family/weight route would not find it — the PostScript name is
    /// the only reliable handle.
    var fontName: String {
        switch self {
        case .regular: return "OpenRunde-Regular"
        case .medium: return "OpenRunde-Medium"
        case .semiBold: return "OpenRunde-Semibold"
        case .bold: return "OpenRunde-Bold"
        }
    }

    var swiftUIWeight: Font.Weight {
        switch self {
        case .regular: return .regular
        case .medium: return .medium
        case .semiBold: return .semibold
        case .bold: return .bold
        }
    }

    var appKitWeight: NSFont.Weight {
        switch self {
        case .regular: return .regular
        case .medium: return .medium
        case .semiBold: return .semibold
        case .bold: return .bold
        }
    }
}

/// Looks up a bundled face, falls back to the matching system font, and caches both the SwiftUI
/// font and its AppKit metrics (needed to turn a line-height multiple into `.lineSpacing`).
enum InkFonts {
    struct Resolved {
        let font: Font
        let metrics: NSFont
        /// False when the bundled face was missing and a system font stood in. A missing font file
        /// must degrade, never crash — the app is still usable in San Francisco.
        let isCustom: Bool
    }

    private struct Key: Hashable {
        let name: String
        let size: CGFloat
    }

    private static let lock = NSLock()
    nonisolated(unsafe) private static var cache: [Key: Resolved] = [:]

    /// The app shell registers the bundled faces before any view renders, so this is normally
    /// unnecessary. If a font ever resolves ahead of registration, calling this afterwards drops the
    /// system-font stand-ins that got cached.
    static func invalidate() {
        lock.lock()
        cache.removeAll()
        lock.unlock()
    }

    /// True when every bundled face resolved. Useful in a diagnostic line; never gate UI on it.
    static var bundledFacesAvailable: Bool {
        let names = [RundeWeight.regular, .medium, .semiBold, .bold].map(\.fontName)
        return names.allSatisfy { NSFont(name: $0, size: 12) != nil }
    }

    static func resolve(
        _ name: String,
        size: CGFloat,
        weight: Font.Weight,
        appKitWeight: NSFont.Weight
    ) -> Resolved {
        let key = Key(name: name, size: size)
        lock.lock()
        let cached = cache[key]
        lock.unlock()
        if let cached { return cached }

        let resolved: Resolved
        if let custom = NSFont(name: name, size: size) {
            // `fixedSize:` and not `size:` — this window is a fixed-metric design, not body text.
            resolved = Resolved(font: .custom(name, fixedSize: size), metrics: custom, isCustom: true)
        } else {
            resolved = Resolved(
                font: .system(size: size, weight: weight),
                metrics: NSFont.systemFont(ofSize: size, weight: appKitWeight),
                isCustom: false
            )
        }

        lock.lock()
        cache[key] = resolved
        lock.unlock()
        return resolved
    }

    /// The line box a font draws by default, which is what `.lineSpacing` adds to.
    static func naturalLineHeight(_ font: NSFont) -> CGFloat {
        font.ascender - font.descender + font.leading
    }

    /// The pairing every role resolves through: Open Runde for display, SF Pro for reading.
    ///
    /// Drawn face and measured face are produced together and from the same decision, because the
    /// two must never disagree — a headline whose line spacing was computed from a different face is
    /// the kind of bug that looks like bad taste rather than like a defect. `resolve` guarantees
    /// that: when the bundled face is missing it returns the SF Pro font *and* SF Pro's metrics.
    static func role(size: CGFloat, weight: RundeWeight) -> Resolved {
        guard size >= Font.inkDisplayThreshold else {
            return Resolved(
                font: .system(size: size, weight: weight.swiftUIWeight),
                metrics: NSFont.systemFont(ofSize: size, weight: weight.appKitWeight),
                isCustom: false)
        }
        return resolve(
            weight.fontName,
            size: size,
            weight: weight.swiftUIWeight,
            appKitWeight: weight.appKitWeight)
    }
}

extension Font {
    /// The size at or above which a run of text is display type rather than reading type.
    ///
    /// One threshold rather than a flag on every call site: the split is a fact about the role, and
    /// every role in this system already encodes its role in its size. A headline is never 15 pt
    /// here and body copy is never 24.
    static let inkDisplayThreshold: CGFloat = 22

    /// Our own pairing: bundled Open Runde at display size, SF Pro for reading.
    ///
    /// Open Runde is a geometric sans with rounded terminals — distinctive, and ours rather than
    /// borrowed. It replaces New York, which was reached for as a stand-in for Anthropic's editorial
    /// serif and therefore carried a brand this app has no business wearing. Below the display
    /// threshold the text is SF Pro, which is what a native macOS app should be setting body copy in
    /// anyway, and which is also where a bundled face buys the least.
    ///
    /// Goes through `InkFonts` rather than naming `.custom` directly, so an unregistered face falls
    /// back to SF Pro at the same size and weight instead of resolving to whatever SwiftUI picks for
    /// a font name it cannot find.
    static func openRunde(_ size: CGFloat, _ weight: RundeWeight = .regular) -> Font {
        InkFonts.role(size: size, weight: weight).font
    }
}

// MARK: - Type roles

/// A complete type role: face, size, tracking and leading travelling together so none of them can
/// be dropped at a call site.
struct InkTextStyle {
    /// Point size, before tracking or leading.
    let size: CGFloat
    let font: Font
    /// `.tracking` in points; 0 when the role has none. The site states tracking in `em`, so each
    /// role below carries the em value it was converted from.
    let tracking: CGFloat
    /// Target line box as a multiple of `size`; nil when the role uses the face's natural leading.
    let lineHeightMultiple: CGFloat?
    /// Extra leading that lands the line box on `lineHeightMultiple`.
    ///
    /// Clamped at zero: `NSParagraphStyle.lineSpacing` is defined as non-negative, so a multiple
    /// *tighter* than the face's own leading (the 1.10 hero, the 1.18 step headline) cannot be
    /// expressed with `.lineSpacing` and renders at the face's natural leading instead.
    let lineSpacing: CGFloat
    /// False when the bundled face was missing for this role.
    let usesBundledFace: Bool
    /// The line box the face draws by default.
    let naturalLineHeight: CGFloat

    /// The exact line box the design doc asks for, or the face's own when the role has no multiple.
    var lineHeight: CGFloat {
        guard let lineHeightMultiple else { return naturalLineHeight }
        return size * lineHeightMultiple
    }

    /// `lineHeight - naturalLineHeight`, and negative for the two headline roles.
    ///
    /// The escape hatch for exact leading: `.lineSpacing` cannot go below the face's own leading, so
    /// a caller that lays lines out itself (`VStack(spacing: style.leadingDelta)` over one `Text`
    /// per line — `VStack` does accept negative spacing) gets the doc's value where the modifier
    /// path clamps to the face's.
    var leadingDelta: CGFloat { lineHeight - naturalLineHeight }

    fileprivate init(
        size: CGFloat,
        resolved: InkFonts.Resolved,
        tracking: CGFloat = 0,
        lineHeightMultiple: CGFloat? = nil
    ) {
        self.size = size
        self.font = resolved.font
        self.tracking = tracking
        self.lineHeightMultiple = lineHeightMultiple
        self.usesBundledFace = resolved.isCustom
        let natural = InkFonts.naturalLineHeight(resolved.metrics)
        self.naturalLineHeight = natural
        if let lineHeightMultiple {
            self.lineSpacing = max(0, size * lineHeightMultiple - natural)
        } else {
            self.lineSpacing = 0
        }
    }
}

/// The scale, and the two rules that generate it.
///
/// **Sizes.** Every role is one step larger than the ladder that shipped — 32/25/15/13/11/14 became
/// 34/27/17/15/12/15 — because onboarding was reported as being set too small to read comfortably.
/// This is the whole of that fix: nothing here changes which face, which colour, or which leading
/// multiple a role has, so the card reads as the same design at a size that does not ask the reader
/// to lean in. The two step-defining thresholds still hold at the new sizes and are what bound the
/// change: every reading role stays under `Font.inkDisplayThreshold` (22 pt) so it is still SF Pro
/// and not Open Runde, and `prose` stays under 18 pt so it is still *normal* text under WCAG and
/// the label ladder's AA bar stays the 4.5:1 one rather than the 3:1 large-text allowance.
///
/// **Tracking.** Every value below is `em × size`, recomputed at the new size and never carried over
/// from the old one: tracking in points is a function of the size it was struck at, so a role that
/// grows and keeps its old point value has quietly loosened. The `em` ratios are the site's and are
/// the thing that is fixed — −0.035 at display, −0.03 at headline, −0.01 at reading size — and each
/// role names the one it was converted from.
enum InkType {
    /// Open Runde 34 / semibold / −1.19 (−0.035 em) / 1.10 — the site's `h1` (600, −0.035 em, 1.08),
    /// at the scale a 720 pt card can hold. The largest thing on screen, and the only reason the
    /// tracking is this tight: at display size a geometric sans falls apart if the words do not lock
    /// up. 0.07 pt tighter than the −1.12 it was struck at when this role was 32 pt, which is the two
    /// points of growth at −0.035 em and not a new decision.
    static var introHero: InkTextStyle {
        runde(34, .semiBold, tracking: -1.19, lineHeight: 1.10)
    }

    /// Open Runde 27 / semibold / −0.81 (−0.03 em) / 1.18.
    static var stepHeadline: InkTextStyle {
        runde(27, .semiBold, tracking: -0.81, lineHeight: 1.18)
    }

    /// The "First…" line. Same face, size and tracking as `stepHeadline` — one headline size, as on
    /// the site — and no leading multiple, because it is always a single line over a list.
    static var firstTitle: InkTextStyle {
        runde(27, .semiBold, tracking: -0.81)
    }

    /// SF Pro 17 / regular / −0.17 (−0.01 em) / 1.55 — the site's body (400 at 1.6), at the system's
    /// own body size. Pair with `Ink.secondary`.
    ///
    /// 17 and not 18: `NSFont.systemFontSize` is 13 and this is the one role that carries paragraphs
    /// on a card, so it wants to be visibly larger than a menu without becoming a headline — and at
    /// 18 pt WCAG reclassifies it as large text, which would drop the label ladder's contrast bar
    /// from 4.5:1 to 3:1 for the step that does the most reading. The bar should not get easier
    /// because the type got bigger.
    static var prose: InkTextStyle {
        runde(17, .regular, tracking: -0.17, lineHeight: 1.55)
    }

    /// SF Pro 15 / medium / −0.15 (−0.01 em) / 1.40. Row copy and the popover's headline state.
    /// Medium, not regular: on a card, a row's sentence sits beside a heavier headline and regular
    /// goes weedy next to it — as true at 15 pt as it was at 13. Pair with `Ink.primary`.
    static var rowCopy: InkTextStyle {
        runde(15, .medium, tracking: -0.15, lineHeight: 1.40)
    }

    /// SF Pro 12 / regular. Every small line in the popover and the status word in a permission row.
    /// Pair with `Ink.secondary` — and on the popover, and only there, `Ink.tertiary` for a single
    /// glanceable word. Small type on glass is exactly where the bottom rung disappears.
    ///
    /// No tracking, and now for a boundary rather than a margin: 12 pt is the floor the ladder
    /// tightens *above*. At this size and under, closing the counters costs more legibility than
    /// locking the words up buys — true of the SF Pro this role actually resolves to, and truer still
    /// of the geometric display face the ladder is derived from. This role sits exactly on the floor,
    /// where the −0.01 em the reading roles take would come to −0.12 pt: not a letterform decision,
    /// a rounding error with a legibility cost.
    static var statusLabel: InkTextStyle {
        runde(12, .regular)
    }

    /// SF Pro 15 / semibold / −0.15 (−0.01 em).
    static var buttonLabel: InkTextStyle {
        runde(15, .semiBold, tracking: -0.15)
    }

    /// The smallest size any role is allowed to resolve at.
    ///
    /// Not a style value — a floor, and the one the scale is guarded against sliding back under. It
    /// is also the size the tracking ladder stops at, so a role that ever lands below this has both
    /// gone under the legible minimum and left the part of the ladder where tracking is defined.
    static let minimumSize: CGFloat = 12

    /// The roles, in the order they appear in the design doc. Used by previews and by the
    /// completeness test that every role resolves to a real face.
    static let allRoles: [InkTextStyle] = [
        introHero, stepHeadline, firstTitle, prose, rowCopy, statusLabel, buttonLabel,
    ]

    private static func runde(
        _ size: CGFloat,
        _ weight: RundeWeight,
        tracking: CGFloat = 0,
        lineHeight: CGFloat? = nil
    ) -> InkTextStyle {
        InkTextStyle(
            size: size,
            resolved: InkFonts.role(size: size, weight: weight),
            tracking: tracking,
            lineHeightMultiple: lineHeight
        )
    }
}

/// The roles again, on the type they produce, so every call site can infer the base:
/// `.inkStyle(.introHero)` rather than `.inkStyle(InkType.introHero)`. `InkType` stays the place the
/// values are defined; this is only how they are spelled at the point of use.
extension InkTextStyle {
    static var introHero: InkTextStyle { InkType.introHero }
    static var stepHeadline: InkTextStyle { InkType.stepHeadline }
    static var firstTitle: InkTextStyle { InkType.firstTitle }
    static var prose: InkTextStyle { InkType.prose }
    static var rowCopy: InkTextStyle { InkType.rowCopy }
    static var statusLabel: InkTextStyle { InkType.statusLabel }
    static var buttonLabel: InkTextStyle { InkType.buttonLabel }
}

extension View {
    /// The role applied to a view whose text it cannot reach directly — a `Button` label, a `Label`,
    /// a stack of runs. Carries the face and the tracking, which propagate to descendant text; the
    /// leading is `Text`-level and stays with the `Text` overload below.
    @ViewBuilder
    func inkStyle(_ style: InkTextStyle, color: Color? = nil) -> some View {
        let styled = font(style.font).tracking(style.tracking)
        if let color {
            styled.foregroundStyle(color)
        } else {
            styled
        }
    }
}

extension Text {
    /// The whole role: face, size, tracking, leading, and optionally the colour.
    /// `Text("…").inkStyle(.introHero)` — there is no supported way to get the face without the
    /// tracking, which is the point.
    ///
    /// `color` is applied innermost so a caller's own `.foregroundStyle` further out cannot fight it;
    /// omit it to inherit from the environment.
    @ViewBuilder
    func inkStyle(_ style: InkTextStyle, color: Color? = nil) -> some View {
        Group {
            if let color {
                inkFont(style).foregroundStyle(color)
            } else {
                inkFont(style)
            }
        }
        .lineSpacing(style.lineSpacing)
    }

    /// Face + size + tracking only, still a `Text`, for the rare case that needs to concatenate or
    /// feed a `Label`. Loses the leading — prefer `inkStyle(_:)`.
    func inkFont(_ style: InkTextStyle) -> Text {
        font(style.font).tracking(style.tracking)
    }
}

// MARK: - Button

/// The only action shape in the app: a full stadium, never a rounded rectangle.
struct InkButton: View {
    enum Kind {
        /// `Ink.primary` fill, `Ink.surface` label — the label ladder inverted.
        case primary
        /// Clear fill, `Ink.primary` label, 1 pt `Ink.hairline`.
        case secondary
    }

    private let title: String
    private let kind: Kind
    private let action: () -> Void

    init(_ title: String, kind: Kind = .primary, action: @escaping () -> Void) {
        self.title = title
        self.kind = kind
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            Text(title).inkFont(InkType.buttonLabel)
        }
        .buttonStyle(InkButtonStyle(kind: kind))
    }
}

/// Exposed so a caller with a richer label (an icon, a progress ring) still gets the exact metrics.
struct InkButtonStyle: ButtonStyle {
    var kind: InkButton.Kind = .primary

    static let minHeight: CGFloat = 42
    static let horizontalPadding: CGFloat = 24

    func makeBody(configuration: Configuration) -> some View {
        // A nested view, not an inline body: `@Environment` only tracks changes inside a `View`.
        StyledLabel(kind: kind, configuration: configuration)
    }

    private struct StyledLabel: View {
        let kind: InkButton.Kind
        let configuration: Configuration
        @Environment(\.isEnabled) private var isEnabled

        private var pressed: Bool { configuration.isPressed }

        /// The primary button is deliberately *not* accent-filled. The accent is already spent on
        /// the one link in the popover, and a filled accent button owes a label colour legible on
        /// it in both appearances — one more contrast pair to keep true. Inverting the label ladder
        /// instead is high-contrast in both appearances by construction.
        private var fill: Color {
            switch kind {
            // Pressed drops opacity rather than darkening: letting the surface through is the only
            // direction that reads as give in both appearances.
            case .primary: return pressed ? Ink.primary.opacity(0.82) : Ink.primary
            case .secondary: return pressed ? Ink.wash : Color.clear
            }
        }

        private var label: Color {
            kind == .primary ? Ink.surface : Ink.primary
        }

        var body: some View {
            configuration.label
                // A caller-supplied label keeps its own font; `InkButton` has already set it.
                .font(InkType.buttonLabel.font)
                .foregroundStyle(label)
                .padding(.horizontal, InkButtonStyle.horizontalPadding)
                .frame(minHeight: InkButtonStyle.minHeight)
                .background(Capsule(style: .continuous).fill(fill))
                .overlay {
                    if kind == .secondary {
                        Capsule(style: .continuous).strokeBorder(Ink.hairline, lineWidth: 1)
                    }
                }
                .contentShape(Capsule(style: .continuous))
                .opacity(isEnabled ? 1 : 0.45)
                // Colour only, no scale: a pill this size bouncing reads as a toy.
                .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: pressed)
        }
    }
}

// MARK: - Permission row

/// One capability, asked for in the app's own voice. The whole row is the target — the state
/// readout is not a separate control.
///
/// The same row appears on two surfaces that must not look alike, which is what `native` selects
/// between:
///
/// - **Onboarding** is the app's own sheet, and it is *glass*. The row is a card: a wash, a
///   hairline, a drawn checkbox, the capability introduced as a first-person sentence, and the
///   status word in `secondary` — glass carries a two-rung ladder (see `Ink.tertiary`).
/// - **The menu bar popover** is a system surface sitting beside every other menu bar extra on the
///   machine, so the row is a *menu item*: 22 pt tall, one system-size label, the status trailing in
///   `tertiary` (this surface is opaque chrome, so it keeps all three rungs), no fill of its own, no
///   tracking, no border. A filled capsule with letter-spaced type is the single clearest tell that
///   a panel was drawn by a website rather than by macOS.
struct InkPermissionRow: View {
    private let title: String
    private let granted: Bool
    private let status: String
    private let native: Bool
    private let action: () -> Void

    @State private var isHovering = false

    /// - Parameters:
    ///   - title: the first-person sentence, e.g. "I would like to hear you"; the plain noun on the
    ///     native surface, where the user has already been introduced.
    ///   - granted: drives the state readout.
    ///   - status: one word — `Granted` / `Open` / `Checking` / `Action required`.
    ///   - native: renders the row as a macOS menu item instead of an onboarding card.
    init(title: String, granted: Bool, status: String, native: Bool = false, action: @escaping () -> Void) {
        self.native = native
        self.title = title
        self.granted = granted
        self.status = status
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            if native {
                menuRow
            } else {
                card
            }
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isHovering)
        .accessibilityLabel(Text("\(title). \(status)"))
    }

    // MARK: - The menu bar

    /// Menu metrics, not card metrics: `NSFont.systemFontSize` is the size AppKit sets a menu item
    /// in, and 22 pt is the height it gives one. No `.inkStyle` anywhere in here — the tracking that
    /// gives the onboarding sheet its character is exactly what makes a menu look counterfeit.
    private var menuRow: some View {
        HStack(spacing: 6) {
            // The checkmark column, held open whether or not it is filled, so the titles of a
            // granted and an ungranted row line up the way a menu's do.
            Image(systemName: "checkmark")
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(Ink.primary)
                .opacity(granted ? 1 : 0)
                .frame(width: 12, alignment: .leading)

            Text(title)
                .font(.system(size: NSFont.systemFontSize))
                .foregroundStyle(Ink.primary)
                .lineLimit(1)

            Spacer(minLength: 8)

            // The one `Ink.tertiary` left in this file, and it is on the *opaque* surface: this
            // branch only ever renders inside the menu bar popover, which is AppKit's own chrome
            // rather than `InkGlassView`. The card branch below sets the same word in `secondary`,
            // because glass carries a two-rung ladder — see `Ink.tertiary`.
            Text(status)
                .font(.system(size: NSFont.systemFontSize))
                .foregroundStyle(Ink.tertiary)
                .fixedSize()
        }
        .padding(.horizontal, 4)
        .frame(height: InkPermissionRow.menuRowHeight)
        .frame(maxWidth: .infinity, alignment: .leading)
        // Nothing at rest. The popover already has a vibrant material doing the work of separating
        // itself from the window behind it, and a menu row that is filled when it is not under the
        // pointer is not a menu row.
        .background(
            RoundedRectangle(cornerRadius: 4, style: .continuous)
                .fill(isHovering ? Ink.rowHover : Color.clear)
        )
        .contentShape(Rectangle())
    }

    /// The height AppKit gives a menu item set at `NSFont.systemFontSize`.
    static let menuRowHeight: CGFloat = 22

    // MARK: - Onboarding

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: 13, style: .continuous)
    }

    private var card: some View {
        HStack(spacing: 11) {
            InkCheckbox(granted: granted)
            Text(title)
                .inkStyle(InkType.rowCopy, color: Ink.primary)
                .multilineTextAlignment(.leading)
                // **The row wraps; it never truncates.** Without this the sentence is compressible,
                // and a `VStack` of four rows in a card that is a little too short pays for the
                // shortfall by squeezing them — which is not a squeeze, it is a `Text` given less
                // height than it needs, and a `Text` given less height than it needs ends in "…".
                // Three of these four sentences shipped cut off mid-word. Fixed vertically, the row
                // can only get taller, so too little room becomes a layout that fails a measurement
                // instead of copy that quietly disappears.
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
            // `secondary` and not the glance-word rung: this row is on the onboarding glass, which
            // carries two rungs. The status still reads as subordinate to the sentence beside it,
            // which is `primary`.
            Text(status)
                .inkStyle(InkType.statusLabel, color: Ink.secondary)
                .fixedSize()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
        .frame(maxWidth: .infinity, alignment: .leading)
        // A half-step of shading plus a hairline. A fill strong enough to read on its own would box
        // three sentences into three grey slabs.
        .background(shape.fill(isHovering ? Ink.rowFillHover : Ink.rowFill))
        .overlay(shape.strokeBorder(Ink.separator, lineWidth: 1))
        .contentShape(shape)
    }
}

/// 18 × 18, corner radius 6, `Ink.hairline`; fills `Ink.primary` with an `Ink.surface` checkmark
/// when granted. The onboarding surface only — the menu bar uses a plain menu checkmark.
struct InkCheckbox: View {
    let granted: Bool

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: 6, style: .continuous)
    }

    var body: some View {
        shape
            .fill(granted ? Ink.primary : Color.clear)
            .overlay(shape.strokeBorder(granted ? Color.clear : Ink.hairline, lineWidth: 1))
            .overlay(
                Image(systemName: "checkmark")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(Ink.surface)
                    .opacity(granted ? 1 : 0)
            )
            .frame(width: 18, height: 18)
            .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.checkbox)), value: granted)
    }
}

// MARK: - The mark

/// The eight-dot Omi mark. One geometry, drawn at 18 pt in the menu bar and 120 pt in onboarding.
struct OmiMark: View {
    /// The canvas the geometry was authored on; every value below is in this space and scales.
    static let canvas: CGFloat = 260
    static let centre: CGFloat = 129.5
    static let dotRadius: CGFloat = 17.2
    /// Dots 0/2/4/6 — N, E, S, W.
    static let axisRadius: CGFloat = 86.71
    /// Dots 1/3/5/7. Further out, so the mark reads as a ring rather than a square.
    static let diagonalRadius: CGFloat = 91.92
    static let glowBlur: CGFloat = 9
    static let glowOpacity: Double = 0.3
    static let dotCount = 8
    /// One full lap of the pulse.
    static let lapSeconds: Double = 0.9
    /// Not in the doc: how far a dot dims between pulses, and how wide the travelling bright spot is
    /// as a fraction of a lap. 0.18 against a 0.125 dot spacing gives a comet rather than a blink.
    static let idleBrightness: Double = 0.5
    static let pulseWidth: Double = 0.18

    var size: CGFloat
    /// Dots brighten in sequence while true. Stops dead when false, and under Reduce Motion.
    var pulsing: Bool = false
    var color: Color = Ink.primary

    init(size: CGFloat, pulsing: Bool = false, color: Color = Ink.primary) {
        self.size = size
        self.pulsing = pulsing
        self.color = color
    }

    /// Dot centres in canvas space. `angle(i) = i·π/4` clockwise from due north, and
    /// `direction(θ) = (sin θ, −cos θ)` — which lands correctly in SwiftUI's y-down space.
    static let dotCentres: [CGPoint] = (0..<dotCount).map { index in
        let theta = Double(index) * .pi / 4
        let radius = index.isMultiple(of: 2) ? axisRadius : diagonalRadius
        return CGPoint(
            x: centre + radius * CGFloat(sin(theta)),
            y: centre - radius * CGFloat(cos(theta))
        )
    }

    /// 1 when the mark is static; a travelling bump between `idleBrightness` and 1 while pulsing.
    static func brightness(index: Int, phase: Double?) -> Double {
        guard let phase else { return 1 }
        let peak = Double(index) / Double(dotCount)
        var distance = abs(phase - peak)
        if distance > 0.5 { distance = 1 - distance }
        let bump = max(0, 1 - distance / pulseWidth)
        return idleBrightness + (1 - idleBrightness) * bump
    }

    private var isPulsing: Bool { pulsing && !InkReduceMotion.isEnabled }

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0, paused: !isPulsing)) { timeline in
            Canvas { context, canvasSize in
                let phase: Double? = isPulsing
                    ? (timeline.date.timeIntervalSinceReferenceDate / Self.lapSeconds)
                        .truncatingRemainder(dividingBy: 1)
                    : nil
                Self.draw(in: &context, size: canvasSize, color: color, phase: phase)
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }

    private static func draw(in context: inout GraphicsContext, size: CGSize, color: Color, phase: Double?) {
        let scale = min(size.width, size.height) / canvas
        let radius = dotRadius * scale
        for (index, centre) in dotCentres.enumerated() {
            let box = CGRect(
                x: centre.x * scale - radius,
                y: centre.y * scale - radius,
                width: radius * 2,
                height: radius * 2
            )
            let circle = Path(ellipseIn: box)
            let level = brightness(index: index, phase: phase)

            var glow = context
            glow.addFilter(.blur(radius: glowBlur * scale))
            glow.opacity = glowOpacity * level
            glow.fill(circle, with: .color(color))

            var solid = context
            solid.opacity = level
            solid.fill(circle, with: .color(color))
        }
    }

    /// The same geometry as a template image, for `NSStatusItem` and anywhere else AppKit needs an
    /// `NSImage`. Template means the system tints it for the menu bar's own light/dark state, so the
    /// colour is discarded and only the alpha survives — the glow still softens the edge.
    static func templateImage(size: CGFloat) -> NSImage {
        let image = NSImage(size: NSSize(width: size, height: size), flipped: true) { rect in
            guard let context = NSGraphicsContext.current?.cgContext else { return false }
            let scale = min(rect.width, rect.height) / canvas
            let radius = dotRadius * scale
            for centre in dotCentres {
                let box = CGRect(
                    x: rect.minX + centre.x * scale - radius,
                    y: rect.minY + centre.y * scale - radius,
                    width: radius * 2,
                    height: radius * 2
                )
                context.saveGState()
                context.setShadow(
                    offset: .zero,
                    blur: glowBlur * scale,
                    color: NSColor.black.withAlphaComponent(glowOpacity).cgColor
                )
                context.setFillColor(NSColor.black.cgColor)
                context.fillEllipse(in: box)
                context.restoreGState()
            }
            return true
        }
        image.isTemplate = true
        return image
    }
}

// MARK: - Previews

#if DEBUG
#Preview("Type") {
    VStack(alignment: .leading, spacing: 26) {
        Text("i notice things").inkStyle(InkType.introHero, color: Ink.primary)
        Text("First, a few permissions").inkStyle(InkType.firstTitle, color: Ink.primary)
        Text("I listen, I watch, and I remember — all of it stays on this Mac.")
            .inkStyle(InkType.prose, color: Ink.secondary)
    }
    .padding(45)
    .background(Ink.surface)
}

#Preview("Components") {
    VStack(spacing: 18) {
        OmiMark(size: 120, pulsing: true)
        InkPermissionRow(title: "I would like to hear you", granted: true, status: "Granted") {}
        InkPermissionRow(title: "I would like to see your screen", granted: false, status: "Open") {}
        HStack(spacing: 16) {
            InkButton("Continue") {}
            InkButton("Not now", kind: .secondary) {}
        }
    }
    .frame(width: InkLayout.permissionsMaxWidth)
    .padding(45)
    .background(Ink.surface)
}
#endif
