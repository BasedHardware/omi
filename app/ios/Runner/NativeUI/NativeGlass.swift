import SwiftUI

/// Shared presentation metrics, so cards, blocks and rows agree across Home and every surface.
enum NativeMetrics {
    /// Matches the system's inset-grouped cell: 26 pt with Liquid Glass (iOS 26+), 10 pt before.
    static var cardRadius: CGFloat {
        if #available(iOS 26.0, *) { return 26 }
        return 10
    }
    /// Code blocks, tables, thumbnails and the reader's current-line highlight.
    static let blockRadius: CGFloat = 12
    /// The minimum tappable row and control height.
    static let rowHeight: CGFloat = 44
    /// Round controls (composer, player, live capture), which are also their own 44 pt hit target.
    static let controlSize: CGFloat = 44
    /// Selection marks and tags. The renderer's own tint is monochrome and the app defines no accent
    /// colour, so `Color.accentColor` would resolve to that tint; this is the system accent.
    static let accent = Color(uiColor: .systemBlue)
    /// A switch's on state. The neutral tint is white in dark mode, where it hid the switch's white knob;
    /// green is the system's state colour for "on".
    static let switchOn = Color(uiColor: .systemGreen)
    /// Ink on the neutral accent (INV-UI-1): black on the white dark-mode accent, white on the black one.
    static let onAccent = Color(uiColor: .systemBackground)
}

private struct NativeOnAccentKey: EnvironmentKey {
    static let defaultValue = false
}

private struct NativeSheetCancelKey: EnvironmentKey {
    static let defaultValue: String? = nil
}

extension EnvironmentValues {
    /// Inside a prominent control, whose fill is the neutral accent: row symbols draw in the inverse ink.
    var nativeOnAccent: Bool {
        get { self[NativeOnAccentKey.self] }
        set { self[NativeOnAccentKey.self] = newValue }
    }

    /// In a presented sheet, the id of its cancel action, so the toolbar places it as a cancellation.
    var nativeSheetCancelID: String? {
        get { self[NativeSheetCancelKey.self] }
        set { self[NativeSheetCancelKey.self] = newValue }
    }
}

/// A row's symbol: red when destructive, otherwise the label colour, or the inverse ink on a prominent
/// control. Layered symbols render hierarchically, like the system's own row icons.
struct NativeRowIcon: View {
    let symbol: String
    let destructive: Bool
    @Environment(\.nativeOnAccent) private var onAccent

    var body: some View {
        Image(systemName: symbol)
            .symbolRenderingMode(.hierarchical)
            .foregroundStyle(destructive ? Color.red : onAccent ? NativeMetrics.onAccent : Color.primary)
    }
}

/// A symbol that changes (a checkbox, play and pause) cross-fades with the system's replace effect on
/// iOS 17+; Reduce Motion keeps the plain swap.
struct NativeSymbolReplace: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @ViewBuilder func body(content: Content) -> some View {
        if #available(iOS 17.0, *), !reduceMotion { content.contentTransition(.symbolEffect(.replace)) }
        else { content }
    }
}

/// Glass belongs to the controls above content; reading surfaces keep an opaque background.
struct NativeGlassControls<Content: View>: View {
    @ViewBuilder let content: () -> Content
    var body: some View {
        if #available(iOS 26.0, *) { GlassEffectContainer(spacing: 12, content: content) }
        else { content() }
    }
}

/// A control's glass. A prominent control is the screen's primary action, filled with the neutral accent
/// (white in dark mode, black in light); callers ask for it only while the action is enabled, so one that
/// cannot act stays plain glass.
struct NativeGlassButtonStyle: ViewModifier {
    var menu = false
    var prominent = false

    func body(content: Content) -> some View {
        if menu {
            if #available(iOS 26.0, *) {
                content.padding(.horizontal, 12).padding(.vertical, 7)
                    .glassEffect(.regular.interactive(), in: .capsule)
            } else { content.padding(7).background(.ultraThinMaterial, in: Capsule()) }
        } else if prominent {
            if #available(iOS 26.0, *) {
                content.buttonStyle(.glassProminent).tint(.primary).environment(\.nativeOnAccent, true)
            } else {
                content.buttonStyle(.borderedProminent).tint(.primary).environment(\.nativeOnAccent, true)
            }
        } else if #available(iOS 26.0, *) { content.buttonStyle(.glass) }
        else { content.buttonStyle(.bordered) }
    }
}

/// A round control of a fixed size, which is also its hit target. Above content it is glass (a material
/// before iOS 26); inside a card it is a quiet fill, as glass belongs to the control layer. A prominent
/// one takes the neutral accent only while enabled, so a Send that cannot send is never white.
struct NativeCircleButtonStyle: ButtonStyle {
    enum Surface { case glass, fill }
    var prominent = false
    var surface = Surface.glass
    var diameter = NativeMetrics.controlSize
    var glyph = Font.body
    @Environment(\.isEnabled) private var enabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        let filled = prominent && enabled
        // The glyph stops growing at the largest standard text size, so it stays inside its fixed circle.
        return configuration.label
            .font(glyph.weight(filled ? .semibold : .medium))
            .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
            .environment(\.nativeOnAccent, filled)
            .frame(width: diameter, height: diameter)
            .contentShape(Circle())
            .modifier(NativeCircleBackground(filled: filled, surface: surface, pressed: configuration.isPressed))
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.92 : 1)
            .animation(reduceMotion ? nil : .spring(response: 0.25, dampingFraction: 0.7), value: configuration.isPressed)
    }
}

private struct NativeCircleBackground: ViewModifier {
    let filled: Bool
    let surface: NativeCircleButtonStyle.Surface
    let pressed: Bool

    func body(content: Content) -> some View {
        if filled {
            content.background(Circle().fill(Color.primary).opacity(pressed ? 0.8 : 1))
        } else if surface == .fill {
            content.background(Circle().fill(Color(uiColor: pressed ? .systemFill : .tertiarySystemFill)))
        } else if #available(iOS 26.0, *) {
            content.glassEffect(.regular.interactive(), in: .circle)
        } else {
            content.background(.regularMaterial, in: Circle())
                .overlay(Circle().strokeBorder(Color.primary.opacity(0.08)))
        }
    }
}

/// The same circle as `NativeCircleButtonStyle`'s glass, drawn behind a control that keeps its own
/// behaviour (a menu). It takes no touches; outside a glass container it stays beneath the control.
struct NativeCircleBackdrop: View {
    var body: some View {
        Group {
            if #available(iOS 26.0, *) {
                Color.clear.glassEffect(.regular, in: .circle)
            } else {
                Circle().fill(.regularMaterial).overlay(Circle().strokeBorder(Color.primary.opacity(0.08)))
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

struct NativeGlassComposerStyle: ViewModifier {
    func body(content: Content) -> some View {
        if #available(iOS 26.0, *) {
            content.glassEffect(.regular.interactive(), in: .rect(cornerRadius: 22))
        } else {
            content.background(.regularMaterial, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).strokeBorder(Color.primary.opacity(0.08)))
        }
    }
}

/// Controls pinned to the bottom of a scrolling surface. iOS 26+ uses the system bar, whose scroll edge
/// effect keeps the controls legible over the content beneath; earlier systems inset the bar, on an
/// opaque background for a reading surface.
struct NativeBottomControls<Bar: View>: ViewModifier {
    var opaque = true
    @ViewBuilder let bar: () -> Bar

    func body(content: Content) -> some View {
        if #available(iOS 26.0, *) {
            content.safeAreaBar(edge: .bottom, content: bar)
        } else if opaque {
            content.safeAreaInset(edge: .bottom) { bar().background(Color(uiColor: .systemBackground)) }
        } else {
            content.safeAreaInset(edge: .bottom, content: bar)
        }
    }
}
