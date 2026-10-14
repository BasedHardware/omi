import SwiftUI
#if canImport(UIKit)
    import UIKit
#endif

/// Gates rapid-fire taps so a single interaction doesn't double-fire haptics
/// (e.g. a tap that also opens a sheet). Adapted from Persona Dev.
@MainActor
public enum DSInteractionGate {
    private static var suppressTapUntil: TimeInterval = 0

    public static var allowsTap: Bool {
        CACurrentMediaTime() >= suppressTapUntil
    }

    public static func suppressTaps(for duration: TimeInterval = 0.36) {
        suppressTapUntil = max(suppressTapUntil, CACurrentMediaTime() + duration)
    }
}

/// A plain button that adds a light haptic + a subtle press scale, so every
/// primary tap feels tactile and native. Use `.buttonStyle(.hapticTap)`.
public struct HapticButtonStyle: ButtonStyle {
    /// When false, only the haptic fires — no press scale/dim. For rows that
    /// also carry a native context menu: the system's lift animation is the
    /// press feedback there, and a custom scale fights it (lift + shrink +
    /// re-expand stutter).
    let pressEffect: Bool

    public init(pressEffect: Bool = true) {
        self.pressEffect = pressEffect
    }

    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(pressEffect && configuration.isPressed ? 0.97 : 1)
            .opacity(pressEffect && configuration.isPressed ? 0.9 : 1)
            .animation(.snappy(duration: 0.2), value: configuration.isPressed)
            .onChange(of: configuration.isPressed) { _, pressed in
                if pressed { DSHaptics.tap(.light) }
            }
    }
}

public extension ButtonStyle where Self == HapticButtonStyle {
    /// Plain look + light haptic + subtle press scale.
    static var hapticTap: HapticButtonStyle {
        HapticButtonStyle()
    }

    /// Light haptic only — no press scale/dim. Use on rows with a native
    /// context menu so the system lift is the sole press animation.
    static var hapticTapNoPress: HapticButtonStyle {
        HapticButtonStyle(pressEffect: false)
    }
}

/// Haptic feedback, routed through the design system so feature code doesn't
/// reach UIKit directly.
public enum DSHaptics {
    @discardableResult
    @MainActor
    public static func tap(_ style: Style = .light) -> Bool {
        guard DSInteractionGate.allowsTap else { return false }
        #if canImport(UIKit)
            let generator = UIImpactFeedbackGenerator(style: style.uiStyle)
            generator.prepare()
            generator.impactOccurred(intensity: 1)
        #endif
        return true
    }

    @MainActor
    public static func selection() {
        guard DSInteractionGate.allowsTap else { return }
        #if canImport(UIKit)
            let generator = UISelectionFeedbackGenerator()
            generator.prepare()
            generator.selectionChanged()
        #endif
    }

    /// A barely-there tick, for things that arrive on their own (a step appearing).
    @MainActor
    public static func soft(_ intensity: CGFloat = 0.45) {
        #if canImport(UIKit)
            let generator = UIImpactFeedbackGenerator(style: .soft)
            generator.prepare()
            generator.impactOccurred(intensity: intensity)
        #endif
    }

    /// Something finished well (task done, Omi finished work).
    @MainActor
    public static func success() {
        #if canImport(UIKit)
            let generator = UINotificationFeedbackGenerator()
            generator.prepare()
            generator.notificationOccurred(.success)
        #endif
    }

    public enum Style {
        case light
        case medium
        case heavy

        #if canImport(UIKit)
            var uiStyle: UIImpactFeedbackGenerator.FeedbackStyle {
                switch self {
                case .light: .light
                case .medium: .medium
                case .heavy: .heavy
                }
            }
        #endif
    }
}
