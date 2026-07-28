//
//  Ink.swift — the shared visual vocabulary for the onboarding window and the menu bar popover.
//
//  Every value here comes from docs/ambient-design-system.md and is exact. Roles are exposed as
//  whole styles rather than loose numbers because the character of the type lives in the tracking
//  and the leading, not the point size — a caller that hand-assembles `.font(.literata(46, .medium))`
//  and forgets `.tracking(-2.07)` has quietly shipped a different product. `Text.inkStyle(_:)` makes
//  that mistake unavailable.
//
//  Brand: white and neutral accents only (INV-UI-1) — nothing off-brand anywhere in this file.
//

import AppKit
import SwiftUI

// MARK: - Hex literals

extension Color {
    /// `Color(hex: 0xFFFCEC)` — sRGB, the space the design values were picked in.
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
    /// `contentView.layer.backgroundColor`, the visual-effect mask, the status item.
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
    // Base palette.
    static let cream = Color(hex: 0xFFFCEC)
    static let ink = Color(hex: 0x171716)
    static let listeningGreen = Color(hex: 0x2E8B57)
    static let cursorBlue = Color(hex: 0x96C4FF)
    static let errorRed = Color(hex: 0xFFB4AB)

    // The cream alpha ladder. Named because unnamed alphas drift: someone writes 0.6 where the
    // system says 0.55 and the whole surface loses its evenness.
    /// Idle keycap fill / warm glass tint.
    static let creamGlass = Color(hex: 0xFFFCEC, opacity: 0.08)
    /// Borders and hairlines.
    static let creamHairline = Color(hex: 0xFFFCEC, opacity: 0.35)
    /// Dimmed secondary text.
    static let creamDim = Color(hex: 0xFFFCEC, opacity: 0.50)
    /// Secondary button outline.
    static let creamOutline = Color(hex: 0xFFFCEC, opacity: 0.55)
    /// Hint and prompt text.
    static let creamHint = Color(hex: 0xFFFCEC, opacity: 0.70)

    // Permission rows use plain white, not cream — the row is a surface, not a piece of type.
    static let rowSurface = Color.white.opacity(0.05)
    static let rowBorder = Color.white.opacity(0.45)
    static let rowCopy = Color.white.opacity(0.82)
    /// Same value as `rowBorder`; the doc names both uses, so both have a name.
    static let rowStatus = Color.white.opacity(0.45)
    /// Not in the design doc. A row that is tappable has to say so under the pointer, and macOS has
    /// no other affordance for it.
    static let rowSurfaceHover = Color.white.opacity(0.09)

    // AppKit twins for the layers below SwiftUI.
    static let nsCream = NSColor(hex: 0xFFFCEC)
    /// The window root layer is painted with this and never left clear — a clear root shows grey
    /// bands at the screen edges.
    static let nsInk = NSColor(hex: 0x171716)
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
    /// The nine backdrop blobs, in paint order. Owned here because they are colour; the atmosphere
    /// agent owns how they are blurred, masked, risen, and drifted.
    static let backdropBlobs: [InkBlob] = [
        InkBlob(x: -1.25, y: -1.20, color: Color(hex: 0xA85E46)),
        InkBlob(x: -0.25, y: -1.25, color: Color(hex: 0xC78067)),
        InkBlob(x: 0.35, y: -1.25, color: Color(hex: 0xD4AE87)),
        InkBlob(x: 1.20, y: -1.05, color: Color(hex: 0x4E687C)),
        InkBlob(x: 1.25, y: 0.05, color: Color(hex: 0x8EAFA9)),
        InkBlob(x: 1.20, y: 1.15, color: Color(hex: 0xA6AA79)),
        InkBlob(x: 0.05, y: 1.25, color: Color(hex: 0xC6A760)),
        InkBlob(x: -0.75, y: 1.20, color: Color(hex: 0xB86958)),
        InkBlob(x: -1.25, y: 0.45, color: Color(hex: 0x9B6174)),
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

enum InterWeight {
    case regular, medium, semiBold, bold

    /// PostScript names of the bundled faces. Inter-Medium and Inter-SemiBold each ship as their own
    /// family ("Inter Medium", "Inter SemiBold"), so asking for family "Inter" at a weight would
    /// never find them — the PostScript name is the only reliable handle.
    var fontName: String {
        switch self {
        case .regular: return "Inter-Regular"
        case .medium: return "Inter-Medium"
        case .semiBold: return "Inter-SemiBold"
        case .bold: return "Inter-Bold"
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

enum LiterataWeight {
    case regular
    /// The headline weight the design doc names. Only Regular (400) and SemiBold (600) are bundled,
    /// so this resolves to Regular — the same face a browser picks for `font-weight: 500` given
    /// those two, and the one that keeps 46 pt display type from going heavy under −2.07 tracking.
    /// The system-serif fallback still uses a true 500.
    case medium
    case semiBold

    var fontName: String {
        switch self {
        case .regular, .medium: return "Literata-Regular"
        case .semiBold: return "Literata-SemiBold"
        }
    }

    var swiftUIWeight: Font.Weight {
        switch self {
        case .regular: return .regular
        case .medium: return .medium
        case .semiBold: return .semibold
        }
    }

    var appKitWeight: NSFont.Weight {
        switch self {
        case .regular: return .regular
        case .medium: return .medium
        case .semiBold: return .semibold
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
        /// must degrade, never crash — the app is still usable in Times and San Francisco.
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
        let names = [InterWeight.regular, .medium, .semiBold, .bold].map(\.fontName)
            + [LiterataWeight.regular, .semiBold].map(\.fontName)
        return names.allSatisfy { NSFont(name: $0, size: 12) != nil }
    }

    static func resolve(
        _ name: String,
        size: CGFloat,
        weight: Font.Weight,
        appKitWeight: NSFont.Weight,
        design: Font.Design
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
                font: .system(size: size, weight: weight, design: design),
                metrics: systemFont(size: size, weight: appKitWeight, design: design),
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

    private static func systemFont(size: CGFloat, weight: NSFont.Weight, design: Font.Design) -> NSFont {
        let base = NSFont.systemFont(ofSize: size, weight: weight)
        guard design == .serif else { return base }
        guard let descriptor = base.fontDescriptor.withDesign(.serif) else { return base }
        return NSFont(descriptor: descriptor, size: size) ?? base
    }
}

extension Font {
    static func inter(_ size: CGFloat, _ weight: InterWeight = .regular) -> Font {
        InkFonts.resolve(
            weight.fontName,
            size: size,
            weight: weight.swiftUIWeight,
            appKitWeight: weight.appKitWeight,
            design: .default
        ).font
    }

    static func literata(_ size: CGFloat, _ weight: LiterataWeight = .regular) -> Font {
        InkFonts.resolve(
            weight.fontName,
            size: size,
            weight: weight.swiftUIWeight,
            appKitWeight: weight.appKitWeight,
            design: .serif
        ).font
    }
}

// MARK: - Type roles

struct InkTextShadow: Equatable {
    let color: Color
    let radius: CGFloat
    let x: CGFloat
    let y: CGFloat

    /// The only shadow in the system: black at 50 %, blur 18, offset (0, 1).
    static let introHero = InkTextShadow(color: Color.black.opacity(0.45), radius: 12, x: 0, y: 1)
}

/// A complete type role: face, size, tracking, leading, and shadow travelling together so none of
/// them can be dropped at a call site.
struct InkTextStyle {
    /// Point size, before tracking or leading.
    let size: CGFloat
    let font: Font
    /// `.tracking` in points; 0 when the role has none.
    let tracking: CGFloat
    /// Target line box as a multiple of `size`; nil when the role uses the face's natural leading.
    let lineHeightMultiple: CGFloat?
    /// Extra leading that lands the line box on `lineHeightMultiple`.
    ///
    /// Clamped at zero: `NSParagraphStyle.lineSpacing` is defined as non-negative, so a multiple
    /// *tighter* than the face's own leading (the 1.08 hero, the 1.2 step headline) cannot be
    /// expressed with `.lineSpacing` and renders at the face's natural leading instead.
    let lineSpacing: CGFloat
    let shadow: InkTextShadow?
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
        lineHeightMultiple: CGFloat? = nil,
        shadow: InkTextShadow? = nil
    ) {
        self.size = size
        self.font = resolved.font
        self.tracking = tracking
        self.lineHeightMultiple = lineHeightMultiple
        self.shadow = shadow
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
    /// Literata 46 / medium / −2.07 / 1.08, with the one shadow in the system.
    /// The tracking is the signature of the whole product; it is never optional.
    static var introHero: InkTextStyle {
        literata(30, .medium, tracking: -1.05, lineHeight: 1.16, shadow: .introHero)
    }

    /// Literata 38 / medium / −1.2 / 1.2.
    static var stepHeadline: InkTextStyle {
        literata(26, .medium, tracking: -0.8, lineHeight: 1.2)
    }

    /// Inter 38 / medium / −1.5. The "First…" line — sans, where the step headline is serif.
    static var firstTitle: InkTextStyle {
        inter(26, .medium, tracking: -0.9)
    }

    /// Inter 20 / medium / −0.3 / 1.5.
    static var prose: InkTextStyle {
        inter(14, .medium, tracking: -0.1, lineHeight: 1.45)
    }

    /// Inter 15 / regular / 1.35. Pair with `Ink.rowCopy`.
    static var rowCopy: InkTextStyle {
        inter(13, .regular, lineHeight: 1.32)
    }

    /// Inter 12 / regular. Pair with `Ink.rowStatus` in a permission row.
    static var statusLabel: InkTextStyle {
        inter(11, .regular)
    }

    /// Inter 16 / semibold.
    static var buttonLabel: InkTextStyle {
        inter(14, .semiBold)
    }

    /// The roles, in the order they appear in the design doc. Used by previews and by the
    /// completeness test that every role resolves to a real face.
    static let allRoles: [InkTextStyle] = [
        introHero, stepHeadline, firstTitle, prose, rowCopy, statusLabel, buttonLabel,
    ]

    private static func inter(
        _ size: CGFloat,
        _ weight: InterWeight,
        tracking: CGFloat = 0,
        lineHeight: CGFloat? = nil,
        shadow: InkTextShadow? = nil
    ) -> InkTextStyle {
        InkTextStyle(
            size: size,
            resolved: InkFonts.resolve(
                weight.fontName,
                size: size,
                weight: weight.swiftUIWeight,
                appKitWeight: weight.appKitWeight,
                design: .default
            ),
            tracking: tracking,
            lineHeightMultiple: lineHeight,
            shadow: shadow
        )
    }

    private static func literata(
        _ size: CGFloat,
        _ weight: LiterataWeight,
        tracking: CGFloat = 0,
        lineHeight: CGFloat? = nil,
        shadow: InkTextShadow? = nil
    ) -> InkTextStyle {
        InkTextStyle(
            size: size,
            resolved: InkFonts.resolve(
                weight.fontName,
                size: size,
                weight: weight.swiftUIWeight,
                appKitWeight: weight.appKitWeight,
                design: .serif
            ),
            tracking: tracking,
            lineHeightMultiple: lineHeight,
            shadow: shadow
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
    /// leading and the shadow are `Text`-level and stay with the `Text` overload below.
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
    /// The whole role: face, size, tracking, leading, shadow, and optionally the colour.
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
        .inkShadow(style.shadow)
    }

    /// Face + size + tracking only, still a `Text`, for the rare case that needs to concatenate or
    /// feed a `Label`. Loses the leading and the shadow — prefer `inkStyle(_:)`.
    func inkFont(_ style: InkTextStyle) -> Text {
        font(style.font).tracking(style.tracking)
    }
}

extension View {
    @ViewBuilder
    fileprivate func inkShadow(_ shadow: InkTextShadow?) -> some View {
        if let shadow {
            self.shadow(color: shadow.color, radius: shadow.radius, x: shadow.x, y: shadow.y)
        } else {
            self
        }
    }
}

// MARK: - Button

/// The only action shape in the app: a full stadium, never a rounded rectangle.
struct InkButton: View {
    enum Kind {
        /// Cream fill, ink label.
        case primary
        /// Clear fill, cream label, 1 pt cream-55 % border.
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
            case .primary: return pressed ? Ink.cream.opacity(0.82) : Ink.cream
            case .secondary: return pressed ? Ink.creamGlass : Color.clear
            }
        }

        private var label: Color {
            kind == .primary ? Ink.ink : Ink.cream
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
                        Capsule(style: .continuous).strokeBorder(Ink.creamOutline, lineWidth: 1)
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
    private let action: () -> Void

    @State private var isHovering = false

    /// - Parameters:
    ///   - title: the first-person sentence, e.g. "I would like to hear you".
    ///   - granted: drives the checkbox fill.
    ///   - status: one word — `Granted` / `Open` / `Checking` / `Action required`.
    init(title: String, granted: Bool, status: String, action: @escaping () -> Void) {
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
                    .inkStyle(InkType.rowCopy, color: Ink.rowCopy)
                    .multilineTextAlignment(.leading)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text(status)
                    .inkStyle(InkType.statusLabel, color: Ink.rowStatus)
                    .fixedSize()
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 11)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(shape.fill(isHovering ? Ink.rowSurfaceHover : Ink.rowSurface))
            .contentShape(shape)
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isHovering)
        .accessibilityLabel(Text("\(title). \(status)"))
    }
}

/// 20 × 20, corner radius 6, white-45 % border; fills cream with an ink checkmark when granted.
struct InkCheckbox: View {
    let granted: Bool

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: 6, style: .continuous)
    }

    var body: some View {
        shape
            .fill(granted ? Ink.cream : Color.clear)
            .overlay(shape.strokeBorder(Ink.rowBorder, lineWidth: 1))
            .overlay(
                Image(systemName: "checkmark")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(Ink.ink)
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
    var color: Color = Ink.cream

    init(size: CGFloat, pulsing: Bool = false, color: Color = Ink.cream) {
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
        Text("i notice things").inkStyle(InkType.introHero, color: Ink.cream)
        Text("First, a few permissions").inkStyle(InkType.firstTitle, color: Ink.cream)
        Text("I listen, I watch, and I remember — all of it stays on this Mac.")
            .inkStyle(InkType.prose, color: Ink.creamHint)
    }
    .padding(45)
    .background(Ink.ink)
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
    .background(Ink.ink)
}
#endif
