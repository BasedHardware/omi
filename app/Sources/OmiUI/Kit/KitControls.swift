import SwiftUI

// Control primitives ported from `react-native/src/ui/`: the FocusPressable
// press/feedback behavior (`Pressable.tsx`), the Button variants
// (`Button.tsx`), the Field input frame (`Field.tsx`), and the mobile
// StatePanel (`MobileAppSurface.tsx`).

/// FocusPressable: pressed opacity 0.78 and a focus-color ring when focused.
public struct KitPressableStyle: ButtonStyle {
    public var pressedOpacity: Double = Opacity.pressed
    public var disabledOpacity: Double = Opacity.disabled

    public init(pressedOpacity: Double = Opacity.pressed) {
        self.pressedOpacity = pressedOpacity
    }

    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .opacity(configuration.isPressed ? pressedOpacity : 1)
            .animation(KitMotion.press, value: configuration.isPressed)
    }
}

/// The Button component: primary / secondary / ghost / danger across
/// compact / default / large / icon sizes.
public struct KitButton: View {
    public enum KitButtonVariant { case primary, secondary, ghost, danger }
    public enum KitButtonSize { case compact, standard, large, icon }

    public let title: String
    public let variant: KitButtonVariant
    public let size: KitButtonSize
    public let disabled: Bool
    public let action: () -> Void

    public init(
        _ title: String,
        variant: KitButtonVariant = .primary,
        size: KitButtonSize = .standard,
        disabled: Bool = false,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.variant = variant
        self.size = size
        self.disabled = disabled
        self.action = action
    }

    public var body: some View {
        Button(action: action) {
            Text(title)
                .font(Typography.label.font)
                .foregroundColor(labelColor)
                .lineLimit(1)
        }
        .buttonStyle(KitPressableStyle())
        .opacity(disabled ? Opacity.disabled : 1)
        .disabled(disabled)
        .frame(minHeight: height)
        .padding(.horizontal, size == .icon ? 0 : Space.md)
        .frame(maxWidth: size == .icon ? height : nil)
        .background(background)
        .overlay(
            RoundedRectangle(cornerRadius: Radius.md)
                .strokeBorder(borderColor, lineWidth: borderWidth)
        )
        .clipShape(RoundedRectangle(cornerRadius: Radius.md))
        .accessibilityLabel(title)
    }

    private var height: CGFloat {
        switch size {
        case .compact: return Size.controlCompact
        case .standard: return Size.control
        case .large: return Size.controlLarge
        case .icon: return Size.control
        }
    }

    private var background: Color {
        switch variant {
        case .primary: return Palette.primary
        case .secondary: return Palette.input
        case .ghost: return Color.clear
        case .danger: return Color.clear
        }
    }

    private var labelColor: Color {
        switch variant {
        case .primary: return Palette.textInverse
        case .secondary, .ghost: return Palette.text
        case .danger: return Palette.danger
        }
    }

    private var borderColor: Color {
        switch variant {
        case .secondary: return Palette.line
        case .danger: return Palette.danger
        default: return Color.clear
        }
    }

    private var borderWidth: CGFloat {
        switch variant {
        case .secondary, .danger: return Borders.width
        default: return 0
        }
    }
}

/// The Field component: an input frame with optional label, hint, and error
/// copy (`Field.tsx`). The binding is owned by the caller.
public struct KitField: View {
    public let label: String?
    public let hint: String?
    public let error: String?
    public let placeholder: String
    @Binding public var value: String

    public init(
        label: String? = nil, hint: String? = nil, error: String? = nil,
        placeholder: String, value: Binding<String>
    ) {
        self.label = label
        self.hint = hint
        self.error = error
        self.placeholder = placeholder
        self._value = value
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            if let label {
                Text(label)
                    .font(Typography.label.font)
                    .foregroundColor(Palette.text)
            }
            HStack(spacing: Space.sm) {
                TextField(placeholder, text: $value)
                    .font(Typography.body.font)
                    .foregroundColor(Palette.text)
                    .accentColor(Palette.focus)
            }
            .padding(.horizontal, Space.md)
            .frame(minHeight: Size.control)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Palette.input)
            .overlay(
                RoundedRectangle(cornerRadius: Radius.md)
                    .strokeBorder(
                        error == nil ? Palette.line : Palette.danger,
                        lineWidth: Borders.width
                    )
            )
            .clipShape(RoundedRectangle(cornerRadius: Radius.md))
            if error == nil, let hint {
                Text(hint)
                    .font(Typography.caption.font)
                    .foregroundColor(Palette.textMuted)
            }
            if let error {
                Text(error)
                    .font(Typography.caption.font)
                    .foregroundColor(Palette.danger)
            }
        }
    }
}

/// The mobile StatePanel: one quiet row of status copy per projection state.
public struct KitStatePanel: View {
    public let status: String
    public let noun: String

    public init(status: String, noun: String) {
        self.status = status
        self.noun = noun
    }

    public var body: some View {
        Text(KitStateCopy.panel(status: status, noun: noun))
            .font(MobileType.body.font)
            .foregroundColor(MobilePalette.textMuted)
            .frame(maxWidth: .infinity, alignment: .leading)
            .frame(minHeight: 44)
            .padding(.vertical, 8)
            .accessibilityLabel("\(noun) \(status) state")
    }
}
