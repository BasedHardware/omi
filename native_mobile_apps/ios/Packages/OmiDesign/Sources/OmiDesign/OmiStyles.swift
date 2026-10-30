import SwiftUI

/// Omi's primary action: full width, ink fill (white on dark), background-colored label.
public struct OmiPrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    public init() {}

    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(DS.Typography.button)
            .foregroundStyle(isEnabled ? DS.Palette.onAccent : DS.Palette.inkDisabled)
            .frame(maxWidth: .infinity, minHeight: DS.Size.primaryButtonHeight)
            .background(isEnabled ? DS.Palette.accent : DS.Palette.fill, in: Capsule())
            .opacity(configuration.isPressed ? 0.85 : 1)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.snappy(duration: 0.2), value: configuration.isPressed)
            .onChange(of: configuration.isPressed) { _, pressed in if pressed { DSHaptics.tap(.light) } }
    }
}

/// Secondary action on a card surface.
public struct OmiSecondaryButtonStyle: ButtonStyle {
    public init() {}

    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(DS.Typography.button)
            .foregroundStyle(DS.Palette.ink)
            .frame(maxWidth: .infinity, minHeight: DS.Size.primaryButtonHeight)
            .background(DS.Palette.card, in: RoundedRectangle(cornerRadius: DS.Radius.md, style: .continuous))
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}

/// Small pill action ("Allow", "Connect", "Get").
public struct OmiPillButtonStyle: ButtonStyle {
    let prominent: Bool

    public init(prominent: Bool = true) { self.prominent = prominent }

    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(prominent ? DS.Palette.onAccent : DS.Palette.ink)
            .padding(.horizontal, DS.Spacing.lg)
            .padding(.vertical, DS.Spacing.sm)
            .background(prominent ? DS.Palette.accent : DS.Palette.cardRaised, in: Capsule())
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}

public extension ButtonStyle where Self == OmiPrimaryButtonStyle {
    static var omiPrimary: OmiPrimaryButtonStyle { OmiPrimaryButtonStyle() }
}

public extension ButtonStyle where Self == OmiSecondaryButtonStyle {
    static var omiSecondary: OmiSecondaryButtonStyle { OmiSecondaryButtonStyle() }
}

public extension ButtonStyle where Self == OmiPillButtonStyle {
    static var omiPill: OmiPillButtonStyle { OmiPillButtonStyle() }
    static var omiPillSubtle: OmiPillButtonStyle { OmiPillButtonStyle(prominent: false) }
}

/// The round header buttons (search, settings, back, share).
public struct CircleIconButton: View {
    let systemImage: String
    let action: () -> Void

    public init(_ systemImage: String, action: @escaping () -> Void) {
        self.systemImage = systemImage
        self.action = action
    }

    public var body: some View {
        Button(action: action) { OmiCircleIcon(systemImage) }
            .buttonStyle(.plain)
    }
}

/// The round header button's look, for a `Menu` label ("…") beside `CircleIconButton`s.
public struct OmiCircleIcon: View {
    let systemImage: String

    public init(_ systemImage: String) {
        self.systemImage = systemImage
    }

    public var body: some View {
        // A plain line glyph, as in the ChatGPT app: no circle behind it.
        Image(systemName: systemImage)
            .font(.system(size: 19, weight: .regular))
            .foregroundStyle(DS.Palette.ink)
            .frame(width: DS.Size.headerButton, height: DS.Size.headerButton)
            .contentShape(Rectangle())
    }
}

/// The search capsule at the top of Tasks and Memories: magnifying glass, field, clear button.
public struct OmiSearchField: View {
    let prompt: String
    @Binding var text: String
    let clearLabel: String

    /// `clearLabel` is the clear button's accessibility label.
    public init(_ prompt: String, text: Binding<String>, clearLabel: String) {
        self.prompt = prompt
        _text = text
        self.clearLabel = clearLabel
    }

    public var body: some View {
        HStack(spacing: DS.Spacing.sm) {
            Image(systemName: "magnifyingglass").foregroundStyle(DS.Palette.inkTertiary).accessibilityHidden(true)
            field
            if !text.isEmpty {
                Button { text = "" } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(DS.Palette.inkTertiary) }
                    .buttonStyle(.plain)
                    .accessibilityLabel(clearLabel)
            }
        }
        .font(DS.Typography.callout)
        .padding(.horizontal, DS.Spacing.lg)
        .frame(minHeight: DS.Size.searchField)
        .omiSurface(Capsule())
    }

    private var field: some View {
        #if os(iOS)
            TextField(prompt, text: $text).textInputAutocapitalization(.never).autocorrectionDisabled()
        #else
            TextField(prompt, text: $text).autocorrectionDisabled()
        #endif
    }
}

/// One empty state for every list: a soft round icon, a title, a line of help, an optional action.
public struct OmiEmptyState: View {
    let systemImage: String
    let title: String
    let message: String?
    let actionTitle: String?
    let action: (() -> Void)?

    public init(_ title: String, systemImage: String, message: String? = nil, actionTitle: String? = nil, action: (() -> Void)? = nil) {
        self.title = title
        self.systemImage = systemImage
        self.message = message
        self.actionTitle = actionTitle
        self.action = action
    }

    public var body: some View {
        VStack(spacing: DS.Spacing.md) {
            Image(systemName: systemImage)
                .font(.system(size: 24, weight: .semibold))
                .foregroundStyle(DS.Palette.agent)
                .frame(width: 60, height: 60)
                .background(DS.Palette.agentSoft, in: Circle())
                .padding(.bottom, DS.Spacing.xs)
                .accessibilityHidden(true)
            Text(title)
                .font(DS.Typography.sectionTitle)
                .foregroundStyle(DS.Palette.ink)
            if let message {
                Text(message)
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.inkSecondary)
            }
            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .buttonStyle(.omiPillSubtle)
                    .padding(.top, DS.Spacing.xs)
            }
        }
        .multilineTextAlignment(.center)
        .frame(maxWidth: 320)
        .frame(maxWidth: .infinity)
        .padding(.horizontal, DS.Spacing.xl)
        .accessibilityElement(children: .combine)
    }
}

/// Omi's input field: dark rounded box with a hairline border.
public struct OmiFieldModifier: ViewModifier {
    public func body(content: Content) -> some View {
        content
            .font(DS.Typography.body)
            .padding(.horizontal, DS.Spacing.lg)
            .frame(minHeight: 56)
            .background(DS.Palette.card, in: RoundedRectangle(cornerRadius: DS.Radius.md, style: .continuous))
            .overlay { RoundedRectangle(cornerRadius: DS.Radius.md, style: .continuous).stroke(DS.Palette.hairline, lineWidth: 1) }
    }
}

public extension View {
    func omiField() -> some View { modifier(OmiFieldModifier()) }
}

public extension View {
    /// Omi's control surface (round header buttons, the Ask bar, search fields, toasts): the quiet
    /// card color edged by a hairline. Solid on purpose: glass over the paper page read as a gray
    /// smudge with a drop shadow, and the calm look is flat surfaces and hairlines.
    func omiSurface(_ shape: some InsettableShape, interactive _: Bool = false) -> some View {
        background(DS.Palette.card, in: shape)
            .overlay { shape.strokeBorder(DS.Palette.cardStroke, lineWidth: DS.Stroke.regular) }
    }
}

/// The page behind Omi's screens: near-black at night, warm paper by day, with at most a breath of
/// light at the top (no color wash). `AuroraBackground` is the old name.
public struct CalmBackground: View {
    @Environment(\.colorScheme) private var colorScheme

    public init() {}

    public var body: some View {
        ZStack(alignment: .top) {
            DS.Palette.background
            RadialGradient(
                colors: [Color.white.opacity(colorScheme == .dark ? 0.035 : 0.45), .clear],
                center: .top, startRadius: 0, endRadius: 420
            )
            .frame(height: 460)
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
    }
}

public typealias AuroraBackground = CalmBackground
