import SwiftUI

/// Section title with an optional trailing action ("See all").
public struct SectionHeader: View {
    let title: String
    let actionTitle: String?
    let action: (() -> Void)?

    public init(_ title: String, actionTitle: String? = nil, action: (() -> Void)? = nil) {
        self.title = title
        self.actionTitle = actionTitle
        self.action = action
    }

    public var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                .font(DS.Typography.sectionTitle)
                .accessibilityAddTraits(.isHeader)
            Spacer()
            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.inkSecondary)
            }
        }
    }
}

/// Square emoji badge used by conversation rows.
public struct EmojiBadge: View {
    let emoji: String

    public init(_ emoji: String?) {
        self.emoji = emoji ?? "💬"
    }

    public var body: some View {
        Text(emoji)
            .font(.title3)
            .frame(width: DS.Size.emojiBadge, height: DS.Size.emojiBadge)
            .background(DS.Palette.fill, in: RoundedRectangle(cornerRadius: DS.Radius.sm, style: .continuous))
            .accessibilityHidden(true)
    }
}

/// Shimmer-free skeleton block for loading states (skeleton, never a spinner).
public struct SkeletonBlock: View {
    let height: CGFloat

    public init(height: CGFloat = 64) {
        self.height = height
    }

    public var body: some View {
        RoundedRectangle(cornerRadius: DS.Radius.card, style: .continuous)
            .fill(DS.Palette.card)
            .frame(height: height)
            .overlay(alignment: .leading) {
                HStack(spacing: DS.Spacing.md) {
                    RoundedRectangle(cornerRadius: DS.Radius.sm).fill(DS.Palette.fill)
                        .frame(width: DS.Size.emojiBadge, height: DS.Size.emojiBadge)
                    VStack(alignment: .leading, spacing: DS.Spacing.sm) {
                        Capsule().fill(DS.Palette.fill).frame(width: 160, height: 10)
                        Capsule().fill(DS.Palette.fill).frame(width: 100, height: 8)
                    }
                }
                .padding(.horizontal, DS.Spacing.lg)
            }
            .redacted(reason: .placeholder)
            .accessibilityHidden(true)
    }
}

/// Small pill label (counts, statuses).
public struct Pill: View {
    let text: String
    let tint: Color

    public init(_ text: String, tint: Color = DS.Palette.inkSecondary) {
        self.text = text
        self.tint = tint
    }

    public var body: some View {
        Text(text)
            .font(DS.Typography.micro)
            .foregroundStyle(tint)
            .padding(.horizontal, DS.Spacing.sm)
            .padding(.vertical, DS.Spacing.xxs + 1)
            .background(tint.opacity(0.12), in: Capsule())
    }
}
