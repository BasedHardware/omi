//
//  Ink.swift — the shared visual vocabulary for the onboarding window and the menu bar popover.
//
//  The palette is Anthropic's: ivory paper (#FAF9F5), near-black ink (#141413), and clay (#D97757)
//  as the single accent, with the backdrop washed in the same clay/manilla/kraft neutrals. Type is
//  Open Runde at 400/500/600, carried over from the product site — the one part of this system not
//  yet on brand, because changing it means shipping different font files rather than different
//  numbers.
//
//  The rest of the structure — role names, tracking, the rhythm ladder — still comes from
//  docs/design-system.md, which reads the product site (archit-lal.github.io/Periphery) as CSS
//  custom properties. What changed is which brand the values belong to: this app sits beside Claude
//  in the same menu bar and hands its output to the same model, so it should look like it belongs
//  there rather than like a separate product that integrates with it.
//
//  Roles are exposed as whole styles rather than loose numbers because the character of the type
//  lives in the tracking as much as the point size — a caller that hand-assembles
//  `.font(.openRunde(32, .semiBold))` and forgets `.tracking(-1.12)` has quietly shipped a
//  different product. `Text.inkStyle(_:)` makes that mistake unavailable.
//
//  Brand: warm neutrals and bronze only (INV-UI-1) — nothing off-brand anywhere in this file.
//

import AppKit
import SwiftUI

// MARK: - Hex literals

extension Color {
    /// `Color(hex: 0xFBF8F4)` — sRGB, the space the design values were picked in.
    init(hex: UInt32, opacity: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: opacity
        )
    }
}

extension NSColor {
    /// AppKit twin of `Color(hex:)`, for the layers SwiftUI cannot reach: the window's root
    /// `contentView.layer.backgroundColor`, the menu bar spotlight ring, the status item.
    convenience init(hex: UInt32, alpha: CGFloat = 1) {
        self.init(
            srgbRed: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: alpha
        )
    }
}

// MARK: - Colour

enum Ink {
    // The site's seven variables, spelled the same way they are spelled in its `:root`.

    /// `--paper`. Every surface in the app: the onboarding oval, the popover.
    ///
    /// Anthropic's ivory rather than the site's slightly pinker cream. This app sits beside Claude
    /// in the same menu bar and hands its output to the same model, so reading as part of that
    /// family is worth more than matching a marketing page — and the two were a hair apart anyway.
    static let paper = Color(hex: 0xFAF9F5)
    /// `--ink`. Primary type, the primary button's fill, the granted checkbox.
    static let ink = Color(hex: 0x141413)
    /// `--mid`. Secondary type: prose under a headline, the popover's status lines.
    static let mid = Color(hex: 0x6B625B)
    /// `--faint`. Tertiary type: a status word, a count, "Quit". Never a whole sentence someone
    /// has to read — at 2.6:1 on paper this is a colour for glancing at.
    static let faint = Color(hex: 0xA39A92)
    /// `--line`. Rules and card hairlines. Barely there on purpose.
    static let line = Color(hex: 0xE6DFD6)
    /// `--bronze`. The one accent: an actionable link, and nothing else.
    ///
    /// Anthropic's clay. Kept under the old name because it is still the same role — one accent,
    /// spent on the one thing that is actionable — and renaming it would touch every call site to
    /// say nothing new. Warmer and lighter than the bronze it replaces, so anything relying on it
    /// for contrast against paper has to earn that with weight or size rather than with hue.
    static let bronze = Color(hex: 0xD97757)
    /// `--red`. The site draws its card outline in this; here it is the error colour, which is the
    /// only place the app ever needs to raise its voice.
    static let errorRed = Color(hex: 0xC9352B)

    /// The live indicator. The one hue outside the site palette, because "on" has to read as on at
    /// 7 pt and the site never had to say it. Muted enough to sit on paper without shouting.
    static let listeningGreen = Color(hex: 0x2E8B57)

    // Paper on paper. The site has no card fill, so these are derived: two steps of warm shading
    // between `paper` and `line`, which is what lets a permission row read as a card without a
    // border heavy enough to box it in.
    /// Permission-row fill.
    static let surface = Color(hex: 0xF0EEE6)
    /// The same row under the pointer. A tappable row has to say so, and macOS has no other
    /// affordance for it.
    static let surfaceHover = Color(hex: 0xE8E5DA)

    /// A drawn hairline: the secondary button's outline, the empty checkbox. `line` is right for a
    /// rule between blocks and too faint for the edge of something you are meant to press.
    static let inkHairline = Color(hex: 0x141413, opacity: 0.28)
    /// The pressed state of anything with no fill of its own.
    static let inkWash = Color(hex: 0x141413, opacity: 0.06)

    // AppKit twins for the layers below SwiftUI.
    static let nsPaper = NSColor(hex: 0xFAF9F5)
    static let nsInk = NSColor(hex: 0x141413)
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
    /// The nine backdrop blobs, in paint order. Geometry is unchanged from the dark system; the
    /// colour is not. Every tone here is a warm neutral a step or two below `paper`, so blurred and
    /// composited over the paper scrim the field reads as shading on a sheet — a faint warm wash —
    /// rather than as nine coloured lights. Saturated colour on paper reads as a bug.
    ///
    /// Each is now a wash of Anthropic's own warm neutrals — clay, manilla, kraft — rather than the
    /// bronze family the site used. This field is the largest coloured surface in the product, so
    /// leaving it on the old palette while the accent moved would have made the window read as two
    /// designs sharing a frame: the tokens say one brand and the backdrop says another.
    static let backdropBlobs: [InkBlob] = [
        InkBlob(x: -1.25, y: -1.20, color: Color(hex: 0xEFDDD4)),
        InkBlob(x: -0.25, y: -1.25, color: Color(hex: 0xF3E9DF)),
        InkBlob(x: 0.35, y: -1.25, color: Color(hex: 0xF1EDE4)),
        InkBlob(x: 1.20, y: -1.05, color: Color(hex: 0xEAE7DC)),
        InkBlob(x: 1.25, y: 0.05, color: Color(hex: 0xEEEBE1)),
        InkBlob(x: 1.20, y: 1.15, color: Color(hex: 0xF0E7D8)),
        InkBlob(x: 0.05, y: 1.25, color: Color(hex: 0xF4EBDC)),
        InkBlob(x: -0.75, y: 1.20, color: Color(hex: 0xEDDFD3)),
        InkBlob(x: -1.25, y: 0.45, color: Color(hex: 0xE9E4D8)),
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

    /// The pairing every role resolves through: New York for display, SF Pro for reading.
    ///
    /// Drawn face and measured face are produced together and from the same decision, because the
    /// two must never disagree — a serif headline whose line spacing was computed from a sans is
    /// the kind of bug that looks like bad taste rather than like a defect.
    static func system(size: CGFloat, weight: RundeWeight) -> Resolved {
        let sans = NSFont.systemFont(ofSize: size, weight: weight.appKitWeight)
        guard size >= Font.inkDisplayThreshold else {
            return Resolved(
                font: .system(size: size, weight: weight.swiftUIWeight),
                metrics: sans,
                isCustom: false)
        }
        // `withDesign` is the only supported route to New York; if a future macOS stops offering it,
        // the sans metrics are still correct for the sans fallback SwiftUI would then draw.
        let serifMetrics = sans.fontDescriptor.withDesign(.serif)
            .flatMap { NSFont(descriptor: $0, size: size) } ?? sans
        return Resolved(
            font: .system(size: size, weight: weight.swiftUIWeight, design: .serif),
            metrics: serifMetrics,
            isCustom: false)
    }
}

extension Font {
    /// The size at or above which a run of text is display type rather than reading type.
    ///
    /// One threshold rather than a flag on every call site: the split is a fact about the role, and
    /// every role in this system already encodes its role in its size. A headline is never 15 pt
    /// here and body copy is never 24.
    static let inkDisplayThreshold: CGFloat = 22

    /// Anthropic's pairing, in the faces macOS actually ships.
    ///
    /// Their identity is an editorial serif over a quiet grotesque — Tiempos and Styrene — and
    /// neither is licensable to bundle. New York is Apple's companion serif to SF and the closest
    /// honest stand-in: same editorial weight in a headline, same warmth, no licence. Below the
    /// display threshold the text falls to SF Pro, which is what a native macOS app should be
    /// setting body copy in anyway.
    ///
    /// This replaces Open Runde, a rounded geometric carried over from the product site. It was the
    /// single most off-brand thing left in the window: rounded terminals read as friendly-consumer,
    /// which is a different company's voice entirely.
    static func openRunde(_ size: CGFloat, _ weight: RundeWeight = .regular) -> Font {
        if size >= inkDisplayThreshold {
            return .system(size: size, weight: weight.swiftUIWeight, design: .serif)
        }
        return .system(size: size, weight: weight.swiftUIWeight)
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
    /// `Ink.mid`.
    static var prose: InkTextStyle {
        runde(15, .regular, tracking: -0.15, lineHeight: 1.55)
    }

    /// Open Runde 13 / medium / −0.13 / 1.40. Row copy and the popover's headline state. Medium,
    /// not regular: at 13 pt on a paper card, regular goes weedy. Pair with `Ink.ink`.
    static var rowCopy: InkTextStyle {
        runde(13, .medium, tracking: -0.13, lineHeight: 1.40)
    }

    /// Open Runde 11 / regular. Every small line in the popover and the status word in a permission
    /// row. No tracking: below 12 pt, tightening a geometric sans only closes the counters. Pair
    /// with `Ink.mid`, or `Ink.faint` for a single glanceable word.
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
            resolved: InkFonts.system(size: size, weight: weight),
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
        /// Ink fill, paper label.
        case primary
        /// Clear fill, ink label, 1 pt ink hairline.
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

        private var fill: Color {
            switch kind {
            // Pressed lightens rather than darkens: on paper, letting the surface through is the
            // only direction that reads as give.
            case .primary: return pressed ? Ink.ink.opacity(0.82) : Ink.ink
            case .secondary: return pressed ? Ink.inkWash : Color.clear
            }
        }

        private var label: Color {
            kind == .primary ? Ink.paper : Ink.ink
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
                        Capsule(style: .continuous).strokeBorder(Ink.inkHairline, lineWidth: 1)
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

/// One capability, asked for in the app's own voice. The whole row is the target — the checkbox is
/// a state readout, not a separate control.
struct InkPermissionRow: View {
    private let title: String
    private let granted: Bool
    private let status: String
    private let native: Bool
    private let action: () -> Void

    @State private var isHovering = false

    /// Brand shading on the branded sheet; a system fill on the system surface.
    ///
    /// The native fill is deliberately faint. The popover already has a vibrant material behind it
    /// doing the work of separating the row from the window, so anything heavier than a quaternary
    /// wash reads as a second, competing background.
    private var rowFill: Color {
        guard native else { return isHovering ? Ink.surfaceHover : Ink.surface }
        return isHovering
            ? Color(nsColor: .tertiaryLabelColor).opacity(0.12)
            : Color(nsColor: .quaternaryLabelColor).opacity(0.5)
    }

    /// - Parameters:
    ///   - title: the first-person sentence, e.g. "I would like to hear you".
    ///   - granted: drives the checkbox fill.
    ///   - status: one word — `Granted` / `Open` / `Checking` / `Action required`.
    /// `native` swaps the brand palette for the system's semantic colours.
    ///
    /// The same row appears on two surfaces that should not look alike. In onboarding it sits on a
    /// branded sheet and should read as ours; in the menu bar it sits on the popover's vibrant
    /// material beside every other menu bar extra on the machine, where a warm ivory fill reads as
    /// a website pasted into the system UI — and is unreadable outright in dark mode, because the
    /// brand tones are fixed and the material behind them is not.
    init(title: String, granted: Bool, status: String, native: Bool = false, action: @escaping () -> Void) {
        self.native = native
        self.title = title
        self.granted = granted
        self.status = status
        self.action = action
    }

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: 13, style: .continuous)
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 11) {
                InkCheckbox(granted: granted)
                Text(title)
                    .inkStyle(InkType.rowCopy, color: native ? Color(nsColor: .labelColor) : Ink.ink)
                    .multilineTextAlignment(.leading)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text(status)
                    .inkStyle(
                        InkType.statusLabel,
                        color: native ? Color(nsColor: .tertiaryLabelColor) : Ink.faint)
                    .fixedSize()
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 11)
            .frame(maxWidth: .infinity, alignment: .leading)
            // Paper on paper: a half-step of warm shading plus a hairline. A fill strong enough to
            // read on its own would box three sentences into three grey slabs.
            .background(shape.fill(rowFill))
            .overlay(shape.strokeBorder(Ink.line, lineWidth: 1))
            .contentShape(shape)
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isHovering)
        .accessibilityLabel(Text("\(title). \(status)"))
    }
}

/// 18 × 18, corner radius 6, ink hairline; fills ink with a paper checkmark when granted.
struct InkCheckbox: View {
    let granted: Bool

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: 6, style: .continuous)
    }

    var body: some View {
        shape
            .fill(granted ? Ink.ink : Color.clear)
            .overlay(shape.strokeBorder(granted ? Color.clear : Ink.inkHairline, lineWidth: 1))
            .overlay(
                Image(systemName: "checkmark")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(Ink.paper)
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
    var color: Color = Ink.ink

    init(size: CGFloat, pulsing: Bool = false, color: Color = Ink.ink) {
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
        Text("i notice things").inkStyle(InkType.introHero, color: Ink.ink)
        Text("First, a few permissions").inkStyle(InkType.firstTitle, color: Ink.ink)
        Text("I listen, I watch, and I remember — all of it stays on this Mac.")
            .inkStyle(InkType.prose, color: Ink.mid)
    }
    .padding(45)
    .background(Ink.paper)
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
    .background(Ink.paper)
}
#endif
