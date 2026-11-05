import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// The day's summary Omi posts in the evening: "Day Summary · 7 Oct" over a numbered list of what
/// happened (`day_summary` messages; Flutter `DaySummaryWidget`).
struct DaySummaryCard: View {
    @Environment(\.chatBubbleWidth) private var bubbleWidth
    let message: ChatMessage

    var body: some View {
        let items = ChatDaySummary.items(message.text)
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            if !message.text.isEmpty {
                Text(L("daySummaryForDate", Self.date(message.createdAt)))
                    .font(DS.Typography.sectionTitle)
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .accessibilityAddTraits(.isHeader)
            }
            VStack(alignment: .leading, spacing: DS.Spacing.sm) {
                ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                    HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.md) {
                        Text("\(index + 1).")
                            .font(DS.Typography.callout.weight(.bold))
                            .foregroundStyle(DS.Palette.inkTertiary)
                            .monospacedDigit()
                        Text(item)
                            .font(DS.Typography.callout)
                            .foregroundStyle(DS.Palette.ink)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                if items.isEmpty {
                    MarkdownBlocks(message.text, font: DS.Typography.bubble, selectable: false)
                        .foregroundStyle(DS.Palette.ink)
                }
            }
        }
        .frame(maxWidth: bubbleWidth, alignment: .leading)
        .accessibilityIdentifier("chat.daySummary")
    }

    /// The day the summary covers, as "7 Oct 2026" in the reader's language.
    static func date(_ date: Date) -> String {
        date.formatted(date: .abbreviated, time: .omitted)
    }
}
