//
//  Ink.swift — the shared visual vocabulary for the onboarding window and the menu bar popover.
//
//  Every colour here is a macOS semantic colour, and the single accent is
//  `NSColor.controlAccentColor` — the accent the user picked in System Settings. Nothing is
//  hand-mixed, so there is exactly one palette in the product and it follows the system's
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
//  `.font(.openRunde(32, .semiBold))` and forgets `.tracking(-1.12)` has quietly shipped a
//  different product. `Text.inkStyle(_:)` makes that mistake unavailable.
//
//  Brand: system semantics and neutrals only. Never purple, anywhere (INV-UI-1) — and note that
//  the accent is the *user's* choice rather than a value this file picks, which is the only way an
//  accent can be native.
//
//  The full spec, including every value below, is docs/design-system.md.
//

import AppKit
import SwiftUI

// MARK: - Colour

/// The whole palette. Twelve roles, every one of them a system semantic colour — a colour literal
/// anywhere else in the app is a bug.
enum Ink {
    // Surfaces.

    /// Every surface the app draws: the onboarding sheet, the popover ground.
    ///
    /// `controlBackgroundColor` rather than `windowBackgroundColor`: this is the ground *content*
    /// sits on, which is white in Light and near-black in Dark — a sheet, in both appearances.
    static let surface = Color(nsColor: .controlBackgroundColor)

    // Type, in three steps and no fourth. Which step a run gets is decided by what the reader has
    // to do with it, not by how deep it sits in a stack.

    /// Headlines, row copy, the primary button's fill, the granted checkbox — and any state with
    /// something to do about it.
    static let primary = Color(nsColor: .labelColor)
    /// A sentence someone reads: prose, a status line, an upload note.
    static let secondary = Color(nsColor: .secondaryLabelColor)
    /// A word someone glances at: `Granted`, `Quit`, `Sign out`. Never a whole sentence.
    static let tertiary = Color(nsColor: .tertiaryLabelColor)

    // Edges.

    /// A rule between blocks. The popover uses `Divider()` instead, which draws this itself.
    static let separator = Color(nsColor: .separatorColor)
    /// The edge of something you are meant to press: the secondary button, the empty checkbox.
    /// `separator` is right for a rule and too faint for a control's outline.
    static let hairline = Color(nsColor: .labelColor).opacity(0.22)

    /// The one accent, spent on the one thing that is actionable and is not already a button.
    ///
    /// The user's own accent colour, so it can never be a borrowed brand — and it is not this
    /// file's decision to make, which is the point. Anything relying on it for contrast has to earn
    /// that with weight or size rather than with hue, because the value is not knowable here.
    static let accent = Color(nsColor: .controlAccentColor)

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
    /// The onboarding spotlight ring. Drawn in the accent because it lands on the *menu bar* — the
    /// system's own surface, which is routinely dark and routinely light, so neither end of the
    /// label ladder can be relied on to show up there.
    static let nsAccent = NSColor.controlAccentColor
}

/// One backdrop blob: a unit position relative to the frame, and its colour.
/// Positions are in frame units, so `x = -1.25` means one and a quarter frame widths off the
/// leading edge — the blobs sit outside the frame and only their falloff is visible.
struct InkBlob: Equatable {
    let x: CGFloat
    let y: CGFloat
    let color: Color
}

extension Ink {
    /// The nine backdrop blobs, in paint order. The geometry has never changed; the colour has, and
    /// this is the third palette it has worn.
    ///
    /// Every blob is now the *same* colour — `labelColor` — and differs only in alpha, which is what
    /// makes the field neutral rather than the warm clay wash it replaces. This is not a shortcut:
    /// `labelColor` is near-black in Light and near-white in Dark, so a low-alpha wash of it darkens
    /// a light sheet and lightens a dark one. Both directions read as *shading across a sheet*,
    /// which is the whole intent of the field. Nine distinct hues could not do that — a fixed tone
    /// tuned to look like light on paper looks like dirt on a dark ground.
    ///
    /// The alphas keep the old field's relative intensity (its tones sat 5–9% off `paper`, blurred
    /// 24σ and composited at 0.55) and are nudged up a little, because a 3% wash that is legible as
    /// shading on white is invisible as light on near-black.
    ///
    /// Saturated colour here would read as nine coloured lights, which is a bug and not a backdrop.
    static let backdropBlobs: [InkBlob] = [
        InkBlob(x: -1.25, y: -1.20, color: primary.opacity(0.16)),
        InkBlob(x: -0.25, y: -1.25, color: primary.opacity(0.11)),
        InkBlob(x: 0.35, y: -1.25, color: primary.opacity(0.08)),
        InkBlob(x: 1.20, y: -1.05, color: primary.opacity(0.15)),
        InkBlob(x: 1.25, y: 0.05, color: primary.opacity(0.12)),
        InkBlob(x: 1.20, y: 1.15, color: primary.opacity(0.14)),
        InkBlob(x: 0.05, y: 1.25, color: primary.opacity(0.13)),
        InkBlob(x: -0.75, y: 1.20, color: primary.opacity(0.17)),
        InkBlob(x: -1.25, y: 0.45, color: primary.opacity(0.10)),
    ]
}

// MARK: - Layout

enum InkLayout {
    /// Content column ceiling for every step. The card is 560 pt wide, so this is the width left
    /// after the page padding — the column never has to compete with the window edge.
    static let contentMaxWidth: CGFloat = 488
    /// The permissions step uses the full column: three rows read as a list at any narrower width.
    static let permissionsMaxWidth: CGFloat = 488
    static let pagePaddingHorizontal: CGFloat = 36
    static let pagePaddingVertical: CGFloat = 34
    /// The vertical rhythm. Pick from this ladder rather than inventing a gap.
    static let rhythm: [CGFloat] = [28, 22, 18, 14, 12, 10, 8, 6]
}

// MARK: - Motion

/// Durations from the motion table, in seconds. Pass them through `InkReduceMotion` before use.
enum InkMotion {
    static let stepTransition: Double = 0.240
    static let wordReveal: Double = 1.200
    static let backdropFadeIn: Double = 0.900
    static let backdropRise: Double = 1.800
    static let backdropDrift: Double = 14.0
    static let settle: Double = 0.280
    static let checkbox: Double = 0.180
    static let finaleGlow: Double = 0.550
    /// Not in the doc: button press feedback, fast enough to read as pressure rather than animation.
    static let press: Double = 0.090
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

enum InkType {
    /// Open Runde 32 / semibold / −1.12 / 1.10 — the site's `h1` (600, −0.035 em, 1.08), at the
    /// scale a 720 pt card can hold. The largest thing on screen, and the only reason the tracking
    /// is this tight: at display size a geometric sans falls apart if the words do not lock up.
    static var introHero: InkTextStyle {
        runde(32, .semiBold, tracking: -1.12, lineHeight: 1.10)
    }

    /// Open Runde 25 / semibold / −0.75 (−0.03 em) / 1.18.
    static var stepHeadline: InkTextStyle {
        runde(25, .semiBold, tracking: -0.75, lineHeight: 1.18)
    }

    /// The "First…" line. Same face, size and tracking as `stepHeadline` — one headline size, as on
    /// the site — and no leading multiple, because it is always a single line over a list.
    static var firstTitle: InkTextStyle {
        runde(25, .semiBold, tracking: -0.75)
    }

    /// Open Runde 15 / regular / −0.15 (−0.01 em) / 1.55 — the site's body (400 at 1.6). Pair with
    /// `Ink.secondary`.
    static var prose: InkTextStyle {
        runde(15, .regular, tracking: -0.15, lineHeight: 1.55)
    }

    /// Open Runde 13 / medium / −0.13 / 1.40. Row copy and the popover's headline state. Medium,
    /// not regular: at 13 pt on a card, regular goes weedy. Pair with `Ink.primary`.
    static var rowCopy: InkTextStyle {
        runde(13, .medium, tracking: -0.13, lineHeight: 1.40)
    }

    /// Open Runde 11 / regular. Every small line in the popover and the status word in a permission
    /// row. No tracking: below 12 pt, tightening a geometric sans only closes the counters. Pair
    /// with `Ink.secondary`, or `Ink.tertiary` for a single glanceable word.
    static var statusLabel: InkTextStyle {
        runde(11, .regular)
    }

    /// Open Runde 14 / semibold / −0.14 (−0.01 em).
    static var buttonLabel: InkTextStyle {
        runde(14, .semiBold, tracking: -0.14)
    }

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

        /// The primary button is deliberately *not* accent-filled. `controlAccentColor` is the
        /// user's choice, so its luminance is unknowable here and no single label colour is legible
        /// against all of them — and the accent is already spent on the one link in the popover.
        /// Inverting the label ladder instead is high-contrast in both appearances by construction.
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
/// - **Onboarding** is the app's own sheet. The row is a card: a wash, a hairline, a drawn checkbox,
///   the capability introduced as a first-person sentence.
/// - **The menu bar popover** is a system surface sitting beside every other menu bar extra on the
///   machine, so the row is a *menu item*: 22 pt tall, one system-size label, the status trailing in
///   secondary, no fill of its own, no tracking, no border. A filled capsule with letter-spaced type
///   is the single clearest tell that a panel was drawn by a website rather than by macOS.
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
                .frame(maxWidth: .infinity, alignment: .leading)
            Text(status)
                .inkStyle(InkType.statusLabel, color: Ink.tertiary)
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
