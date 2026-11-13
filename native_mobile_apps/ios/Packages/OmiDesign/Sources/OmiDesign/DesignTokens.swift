import SwiftUI

/// The single source of visual truth. Feature code uses `DS` only: no raw colors, sizes or
/// durations. Omi's look is restraint, in the spirit of the ChatGPT app: a soft graphite (or white)
/// page, text-first lists without cards or tinted icon circles, thin monochrome line icons, SF Pro,
/// and one accent: Omi blue for what is live or active.
public enum DS {
    public enum Palette {
        /// Soft graphite at night, white by day.
        public static let background = Color(light: 0xFFFFFF, dark: 0x212121)
        /// The few raised surfaces (a banner, a settings group, the composer).
        public static let card = Color(light: 0xF4F4F4, dark: 0x2F2F2F)
        /// Same surface as `card`: one card color everywhere.
        public static let conversationCard = card
        /// A surface on a surface (a pill on a card, a pressed row).
        public static let cardRaised = Color(light: 0xF4F4F4, dark: 0x303030)
        /// A raised surface's edge: only visible by day.
        public static let cardStroke = Color(light: 0xE6E6E6, dark: 0x2F2F2F)
        /// The small square behind an emoji or icon on a row.
        public static let tile = Color(light: 0xF4F4F4, dark: 0x2F2F2F)
        public static let fill = Color(light: 0xECECEC, dark: 0x3A3A3A)
        /// Separators, used sparingly.
        public static let hairline = Color(light: 0xE6E6E6, dark: 0x343434)

        public static let ink = Color(light: 0x0D0D0D, dark: 0xECECEC)
        /// Subtitles, meta, section labels.
        public static let inkSecondary = Color(light: 0x5D5D5D, dark: 0xB4B4B4)
        public static let inkTertiary = Color(light: 0x8F8F8F, dark: 0x8E8E8E)
        public static let inkDisabled = Color(light: 0xC4C4C4, dark: 0x5A5A5A)

        /// Omi's accent is ink: black on paper, white at night; text on it is the background.
        public static let accent = ink
        public static let onAccent = Color(light: 0xFFFFFF, dark: 0x000000)
        /// Omi blue: what is live or active, and everything the agent does.
        public static let agent = Color(light: 0x2463EB, dark: 0x3B82F6)
        /// Text and glyphs on Omi blue (white in both modes).
        public static let onAgent = Color(light: 0xFFFFFF, dark: 0xFFFFFF)
        public static let agentSoft = Color(light: 0x2463EB, dark: 0x3B82F6).opacity(0.12)
        /// Recording and destructive: a calm red.
        public static let live = Color(light: 0xE5484D, dark: 0xFF5A5F)
        public static let success = Color(light: 0x2F9E5B, dark: 0x3DD68C)
        /// Warm amber: attention, and the warm end of the hero stroke.
        public static let warning = Color(light: 0xD9822B, dark: 0xF5A04A)
        public static let amber = Color(light: 0xE8833A, dark: 0xF59A4A)

        /// Chat bubbles, as in Messages but softer: yours in a light tint of Omi blue with ink text
        /// (a deep blue at night), Omi's on the card surface.
        public static let bubbleUser = Color(light: 0xDCE7FC, dark: 0x233C66)
        public static let onBubbleUser = ink
        public static let bubbleAssistant = card
    }

    /// Line weights: hairlines on surfaces, a thin stroke on illustrations.
    public enum Stroke {
        public static let hairline: CGFloat = 0.75
        public static let regular: CGFloat = 1
        /// Device illustrations (1 to 1.5 pt in the reference).
        public static let hero: CGFloat = 1.5
    }

    public enum Gradient {
        /// A hero illustration's outline: quiet hairline gray that warms into amber on one side.
        public static var heroStroke: LinearGradient {
            LinearGradient(
                stops: [
                    .init(color: Palette.inkTertiary.opacity(0.35), location: 0),
                    .init(color: Palette.inkTertiary.opacity(0.35), location: 0.45),
                    .init(color: Palette.amber, location: 1),
                ],
                startPoint: .leading, endPoint: .trailing
            )
        }

        /// The warm glow beside a hero stroke.
        public static var heroGlow: RadialGradient {
            RadialGradient(
                colors: [Palette.amber.opacity(0.35), Palette.amber.opacity(0)],
                center: .trailing, startRadius: 0, endRadius: 160
            )
        }
    }

    public enum Glow {
        /// What is live (the live pill's outline, a recording dot): Omi blue, softly blurred.
        public static let live = Palette.agent.opacity(0.45)
        public static let liveRadius: CGFloat = 10
    }

    public enum Spacing {
        public static let xxs: CGFloat = 2
        public static let xs: CGFloat = 4
        public static let sm: CGFloat = 8
        public static let md: CGFloat = 12
        public static let lg: CGFloat = 16
        /// The screen's horizontal gutter.
        public static let gutter: CGFloat = 20
        public static let xl: CGFloat = 24
        public static let section: CGFloat = 32
    }

    public enum Radius {
        public static let sm: CGFloat = 10
        /// Emoji and icon tiles inside a card.
        public static let tile: CGFloat = 10
        public static let md: CGFloat = 16
        public static let card: CGFloat = 20
        /// Chat bubbles and the cards in the thread.
        public static let bubble: CGFloat = 18
        /// A bubble's corner on the sender's side where it joins the next one of its group.
        public static let bubbleJoined: CGFloat = 7
        /// The sender-side bottom corner of a group's last bubble (Messages' tail, quieter).
        public static let bubbleTail: CGFloat = 4
        public static let hero: CGFloat = 28
    }

    /// Debug: render the pre-iOS 26 surfaces on iOS 26 (launch argument `-omiSolidSurfaces YES`).
    public static let forcesSolidSurfaces = UserDefaults.standard.bool(forKey: "omiSolidSurfaces")

    public enum Typography {
        /// Big hero headlines (onboarding, empty states).
        public static let display = Font.largeTitle.weight(.bold)
        /// Screen and sheet titles.
        public static let largeTitle = Font.title.weight(.bold)
        public static let title = Font.title2.weight(.bold)
        /// "Home  Tasks  Memories", the word tabs.
        public static let switcher = Font.title.weight(.bold)
        /// Day titles, "For you", section heads on a page.
        public static let sectionTitle = Font.title3.weight(.semibold)
        /// Quiet list labels ("For you", "Today"): small and gray, as in the ChatGPT app.
        public static let sectionLabel = Font.subheadline.weight(.medium)
        public static let cardTitle = Font.body
        public static let body = Font.body
        public static let callout = Font.subheadline
        /// Chat bubbles and the composer (16 pt at the default text size).
        public static let bubble = Font.callout
        public static let caption = Font.footnote
        public static let micro = Font.caption2.weight(.semibold)
        public static let button = Font.body.weight(.semibold)
        /// Small sans labels (chips, eyebrows, the status line); use with `Tracking.label`.
        public static let label = Font.footnote.weight(.medium)
        /// Timers and counters.
        public static let timer = Font.title3.weight(.semibold).monospacedDigit()
    }

    /// Letter spacing for small sans labels (slightly open).
    public enum Tracking {
        public static let label: CGFloat = 0.3
    }

    public enum Size {
        public static let emojiBadge: CGFloat = 40
        /// Emoji and icon tiles on list cards.
        public static let tile: CGFloat = 38
        public static let headerButton: CGFloat = 40
        /// Omi's picture beside the last bubble of its group in the chat.
        public static let chatAvatar: CGFloat = 26
        /// The chat composer's field, "+" and mic.
        public static let composer: CGFloat = 44
        /// A search field beside the round header buttons.
        public static let searchField: CGFloat = 44
        public static let omiBarHeight: CGFloat = 60
        public static let primaryButtonHeight: CGFloat = 52
    }

    public enum Motion {
        public static let standard = Animation.smooth(duration: 0.32, extraBounce: 0)
        public static let snappy = Animation.snappy(duration: 0.28)
        public static let gentle = Animation.easeInOut(duration: 0.22)
    }
}

public extension Color {
    /// sRGB from a packed 24-bit value.
    init(hex: UInt32, opacity: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: opacity
        )
    }

    /// A color that switches with the interface style.
    init(light: UInt32, dark: UInt32) {
        #if canImport(UIKit)
            self.init(uiColor: UIColor { traits in
                UIColor(Color(hex: traits.userInterfaceStyle == .dark ? dark : light))
            })
        #else
            self.init(hex: light)
        #endif
    }
}

#if canImport(UIKit)
    import UIKit

    extension Color {
        init(uiColorName color: UIColor) {
            self.init(uiColor: color)
        }
    }
#else
    import AppKit

    extension Color {
        enum SystemName {
            case systemGroupedBackground, secondarySystemGroupedBackground, tertiarySystemGroupedBackground
            case tertiarySystemFill, separator, tertiaryLabel, systemRed, systemGreen, systemOrange
        }

        init(uiColorName name: SystemName) {
            switch name {
            case .systemRed: self = .red
            case .systemGreen: self = .green
            case .systemOrange: self = .orange
            case .separator, .tertiaryLabel: self = .gray
            default: self = Color(nsColor: .windowBackgroundColor)
            }
        }
    }
#endif

public extension View {
    /// An animation that collapses when Reduce Motion is on.
    func dsAnimation(_ animation: Animation, value: some Equatable) -> some View {
        modifier(ReduceMotionAnimation(animation: animation, value: value))
    }
}

private struct ReduceMotionAnimation<Value: Equatable>: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let animation: Animation
    let value: Value

    func body(content: Content) -> some View {
        content.animation(reduceMotion ? nil : animation, value: value)
    }
}
