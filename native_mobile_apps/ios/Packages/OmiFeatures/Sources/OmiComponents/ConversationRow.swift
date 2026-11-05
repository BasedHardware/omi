import OmiCore
import OmiDesign
import SwiftUI

/// One conversation as Omi shows it: emoji tile, title, "9:12 AM · 2m". On Home each row is its own
/// card; inside a system `List` (search, call history) use `.plain`, the list draws the cell. A star
/// marks starred ones; while selecting, a check circle leads.
public struct ConversationRow: View {
    public enum Style { case card, plain }

    let conversation: Conversation
    let isSelected: Bool?
    let style: Style

    /// `isSelected` is `nil` outside selection mode.
    public init(_ conversation: Conversation, isSelected: Bool? = nil, style: Style = .card) {
        self.conversation = conversation
        self.isSelected = isSelected
        self.style = style
    }

    public var body: some View {
        HStack(spacing: DS.Spacing.md) {
            if let isSelected {
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 22))
                    .foregroundStyle(isSelected ? DS.Palette.agent : DS.Palette.inkTertiary)
                    .accessibilityHidden(true)
            }
            // Cards keep the emoji tile; plain lists show the emoji on its own, no tile behind it.
            if style == .card {
                EmojiTile(conversation.emoji ?? "💬")
            } else {
                Text(conversation.emoji ?? "💬").font(.system(size: 22)).frame(width: 30).accessibilityHidden(true)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(conversation.displayTitle)
                    .font(DS.Typography.cardTitle)
                    .foregroundStyle(DS.Palette.ink)
                    .lineLimit(1)
                HStack(spacing: DS.Spacing.sm) {
                    Text(Formatting.meta(for: conversation))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .fixedSize()
                    status
                }
                .lineLimit(1)
            }
            Spacer(minLength: 0)
            if conversation.isStarred {
                Image(systemName: "star.fill")
                    .font(.system(size: 13))
                    .foregroundStyle(DS.Palette.warning)
                    .accessibilityLabel(L("starred"))
            }
        }
        .padding(.horizontal, style == .card ? DS.Spacing.md : 0)
        .padding(.vertical, style == .card ? DS.Spacing.md - 2 : DS.Spacing.xxs)
        .background { if style == .card { Color.clear.omiCardSurface() } }
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(isSelected == true ? .isSelected : [])
    }

    @ViewBuilder
    private var status: some View {
        if conversation.status == .processing || conversation.status == .inProgress {
            Pill(L("nativeProcessing"), tint: DS.Palette.warning)
        } else if conversation.status == .merging {
            Pill(L("nativeMerging"), tint: DS.Palette.agent)
        } else if conversation.summaryFailed {
            Pill(L("nativeSummaryFailed"), tint: DS.Palette.live)
        } else if conversation.actionItemCount > 0 {
            // Quiet: Home shows many rows; the agent color is for what Omi does, not for counts.
            HStack(spacing: 3) {
                Image(systemName: "checklist").imageScale(.small).accessibilityHidden(true)
                Text(nextStepsLabel)
            }
            .font(DS.Typography.caption)
            .foregroundStyle(DS.Palette.inkTertiary)
        }
    }

    private var nextStepsLabel: String {
        conversation.actionItemCount == 1
            ? L("nativeNextStepOne")
            : L("nativeNextStepsCount", String(conversation.actionItemCount))
    }
}

/// The square emoji tile on conversation and recap rows.
public struct EmojiTile: View {
    let emoji: String
    let fill: Color

    /// On the page itself (not on a card) pass `DS.Palette.card` as `fill`.
    public init(_ emoji: String, fill: Color = DS.Palette.tile) {
        self.emoji = emoji
        self.fill = fill
    }

    public var body: some View {
        Text(emoji)
            .font(.system(size: 20))
            .frame(width: DS.Size.tile, height: DS.Size.tile)
            .background(fill, in: RoundedRectangle(cornerRadius: DS.Radius.tile, style: .continuous))
            .accessibilityHidden(true)
    }
}

public enum Formatting {
    /// "9:12 AM · 2m", Omi's row meta.
    public static func meta(for conversation: Conversation) -> String {
        let time = conversation.date.formatted(date: .omitted, time: .shortened)
        guard let duration = conversation.duration else { return time }
        return "\(time) · \(length(duration))"
    }

    /// "2m", "1h 35m"; anything under a minute counts as a minute, as in Omi.
    public static func length(_ duration: TimeInterval) -> String {
        let minutes = max(1, Int((duration / 60).rounded()))
        return minutes >= 60 ? "\(minutes / 60)h \(minutes % 60)m" : "\(minutes)m"
    }

    /// "Today", "Yesterday", or "Tue, Sep 29".
    public static func dayTitle(_ day: Date, now: Date = .now, calendar: Calendar = .current) -> String {
        if calendar.isDate(day, inSameDayAs: now) { return L("today") }
        if let yesterday = calendar.date(byAdding: .day, value: -1, to: now), calendar.isDate(day, inSameDayAs: yesterday) {
            return L("yesterday")
        }
        return day.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day())
    }
}
