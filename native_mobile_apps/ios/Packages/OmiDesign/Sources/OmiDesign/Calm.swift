import SwiftUI

// Omi's calm components: hairline chips and separators, the live pill, the status line and the
// pendant drawn as a thin warm stroke. Restraint first: one accent, lots of air.

/// A small pill with a hairline edge ("Power on your Omi", a filter, a source tag).
public struct OmiChip: View {
    let text: String
    let systemImage: String?
    let tint: Color?

    /// `tint` colors the icon and text (an active filter); `nil` keeps them quiet gray.
    public init(_ text: String, systemImage: String? = nil, tint: Color? = nil) {
        self.text = text
        self.systemImage = systemImage
        self.tint = tint
    }

    public var body: some View {
        HStack(spacing: DS.Spacing.xs + 2) {
            if let systemImage { Image(systemName: systemImage).imageScale(.small) }
            Text(text).lineLimit(1)
        }
        .font(DS.Typography.label)
        .tracking(DS.Tracking.label)
        .foregroundStyle(tint ?? DS.Palette.inkSecondary)
        .padding(.horizontal, DS.Spacing.md)
        .padding(.vertical, DS.Spacing.xs + 2)
        .background(DS.Palette.card, in: Capsule())
        .overlay { Capsule().strokeBorder(tint?.opacity(0.4) ?? DS.Palette.cardStroke, lineWidth: DS.Stroke.regular) }
    }
}

/// A hairline between quiet rows, starting at `leading` (the text's edge).
public struct OmiHairline: View {
    let leading: CGFloat

    public init(leading: CGFloat = 0) {
        self.leading = leading
    }

    public var body: some View {
        Rectangle()
            .fill(DS.Palette.hairline)
            .frame(height: DS.Stroke.hairline)
            .padding(.leading, leading)
            .accessibilityHidden(true)
    }
}

/// A quiet bottom status line: a small blue spinner and a short sentence ("Looking for your Omi").
public struct OmiStatusLine: View {
    let text: String
    let isWorking: Bool

    public init(_ text: String, isWorking: Bool = true) {
        self.text = text
        self.isWorking = isWorking
    }

    public var body: some View {
        HStack(spacing: DS.Spacing.sm + 2) {
            if isWorking {
                ProgressView().controlSize(.small).tint(DS.Palette.agent)
            }
            Text(text).font(DS.Typography.button).foregroundStyle(DS.Palette.ink)
        }
        .accessibilityElement(children: .combine)
    }
}

/// The capsule shown while Omi records: the source (the pendant, or a symbol for the phone or the
/// watch), a line of text (the latest words), a big tabular timer counting from `since`, a thin
/// blue outline with a soft glow, and an optional trailing control (stop).
public struct OmiLivePill<Trailing: View>: View {
    let since: Date?
    let title: String?
    let symbol: String?
    let trailing: Trailing

    /// `since` `nil` (paused, starting) hides the timer. `symbol` `nil` shows the Omi pendant.
    public init(since: Date?, title: String? = nil, symbol: String? = nil, @ViewBuilder trailing: () -> Trailing) {
        self.since = since
        self.title = title
        self.symbol = symbol
        self.trailing = trailing()
    }

    public var body: some View {
        HStack(spacing: DS.Spacing.md) {
            if let symbol {
                Image(systemName: symbol)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(DS.Palette.agent)
                    .frame(width: 30, height: 30)
                    .background(DS.Palette.agentSoft, in: Circle())
                    .accessibilityHidden(true)
            } else {
                OmiPendantThumbnail(size: 30)
            }
            if let title {
                // The newest words stay visible: long text gives up its start.
                Text(title).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkSecondary)
                    .lineLimit(1)
                    .truncationMode(.head)
            }
            Spacer(minLength: DS.Spacing.sm)
            if let since {
                TimelineView(.periodic(from: since, by: 1)) { context in
                    Text(Self.elapsed(context.date.timeIntervalSince(since)))
                        .font(DS.Typography.timer)
                        .foregroundStyle(DS.Palette.ink)
                        .contentTransition(.numericText())
                }
            }
            trailing
        }
        .padding(.leading, DS.Spacing.sm)
        .padding(.trailing, DS.Spacing.sm)
        .frame(minHeight: 48)
        .background(DS.Palette.card, in: Capsule())
        .overlay { Capsule().strokeBorder(DS.Palette.agent.opacity(0.55), lineWidth: DS.Stroke.regular) }
        .shadow(color: DS.Glow.live.opacity(0.5), radius: DS.Glow.liveRadius)
    }

    /// "4:07", "1:02:33".
    public static func elapsed(_ seconds: TimeInterval) -> String {
        let total = max(0, Int(seconds.rounded(.down)))
        let hours = total / 3600, minutes = total / 60 % 60, rest = total % 60
        return hours > 0 ? String(format: "%d:%02d:%02d", hours, minutes, rest) : String(format: "%d:%02d", minutes, rest)
    }
}

public extension OmiLivePill where Trailing == EmptyView {
    init(since: Date?, title: String? = nil, symbol: String? = nil) {
        self.init(since: since, title: title, symbol: symbol) { EmptyView() }
    }
}

/// The Omi pendant as a small thumbnail (the live pill, a device row).
public struct OmiPendantThumbnail: View {
    let size: CGFloat

    public init(size: CGFloat = 30) {
        self.size = size
    }

    public var body: some View {
        Group {
            #if canImport(UIKit)
                OmiMedia.device.resizable().scaledToFit()
            #else
                Circle().fill(DS.Palette.fill)
            #endif
        }
        .frame(width: size, height: size)
        .shadow(color: DS.Glow.live.opacity(0.6), radius: size / 5)
        .accessibilityHidden(true)
    }
}

/// The Omi itself, large (My Omi's headline, as AirPods in iOS Settings): the photo with a soft
/// shadow under it; gray and faded while the Omi is away.
public struct OmiPendantPhoto: View {
    let size: CGFloat
    let isFaded: Bool

    public init(size: CGFloat = 150, isFaded: Bool = false) {
        self.size = size
        self.isFaded = isFaded
    }

    public var body: some View {
        Group {
            #if canImport(UIKit)
                OmiMedia.device.resizable().scaledToFit()
            #else
                Circle().fill(DS.Palette.fill)
            #endif
        }
        .frame(width: size, height: size)
        .saturation(isFaded ? 0 : 1)
        .opacity(isFaded ? 0.45 : 1)
        .shadow(color: .black.opacity(isFaded ? 0.06 : 0.18), radius: size / 12, y: size / 18)
        .animation(DS.Motion.gentle, value: isFaded)
        .accessibilityHidden(true)
    }
}

/// The Omi pendant drawn as a hero: a thin outline that warms from hairline gray into amber on one
/// side with a soft glow, the inner disc as a hairline, the loop on top and the blue light in the
/// middle. `pointsAtLight` adds a small blue arrow to the light (press here).
public struct OmiPendantIllustration: View {
    let size: CGFloat
    let pointsAtLight: Bool
    let isGlowing: Bool

    public init(size: CGFloat = 220, pointsAtLight: Bool = false, isGlowing: Bool = true) {
        self.size = size
        self.pointsAtLight = pointsAtLight
        self.isGlowing = isGlowing
    }

    public var body: some View {
        ZStack {
            // Warm glow on the right, behind the stroke.
            Circle()
                .fill(DS.Gradient.heroGlow)
                .frame(width: size * 1.2, height: size * 1.2)
                .offset(x: size * 0.18)
                .blur(radius: size * 0.08)
                .opacity(isGlowing ? 1 : 0)
            // Body: near-black disc, gradient outline.
            Circle()
                .fill(DS.Palette.card)
                .overlay { Circle().strokeBorder(DS.Gradient.heroStroke, lineWidth: DS.Stroke.hero) }
                .frame(width: size, height: size)
            // The loop on top.
            Capsule()
                .strokeBorder(DS.Gradient.heroStroke, lineWidth: DS.Stroke.hero)
                .frame(width: size * 0.16, height: size * 0.09)
                .offset(y: -size / 2 - size * 0.02)
            // Inner disc as a hairline.
            Circle()
                .strokeBorder(DS.Palette.inkTertiary.opacity(0.25), lineWidth: DS.Stroke.hairline)
                .frame(width: size * 0.72, height: size * 0.72)
            // The light.
            Circle()
                .fill(DS.Palette.agent)
                .frame(width: size * 0.035, height: size * 0.035)
                .shadow(color: DS.Palette.agent, radius: size * 0.04)
                .shadow(color: DS.Glow.live, radius: size * 0.1)
            if pointsAtLight {
                Image(systemName: "arrow.left")
                    .font(.system(size: size * 0.11, weight: .semibold))
                    .foregroundStyle(DS.Palette.agent)
                    .offset(x: size * 0.16)
            }
        }
        .frame(width: size * 1.2, height: size * 1.2)
        .accessibilityHidden(true)
    }
}
