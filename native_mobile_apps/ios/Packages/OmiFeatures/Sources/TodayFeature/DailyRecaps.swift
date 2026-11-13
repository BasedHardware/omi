import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// A day's recap as the first row under its day on Home: "Recap: <headline>", opens the recap.
/// For yesterday without one (but with conversations) the row offers to write it.
struct RecapRow: View {
    @Environment(ConversationsStore.self) private var conversations
    let kind: ConversationsStore.RecapSlot
    let onOpen: (DailySummary) -> Void

    var body: some View {
        Button(action: tap) {
            HStack(spacing: DS.Spacing.md) {
                VStack(alignment: .leading, spacing: 3) {
                    // Text-first like the conversations below; only Omi's sparkle carries the accent.
                    HStack(spacing: 6) {
                        if case .write = kind, conversations.isCreatingRecap {
                            ProgressView().controlSize(.mini)
                        } else {
                            Image(systemName: symbol).font(.system(size: 14, weight: .regular)).foregroundStyle(DS.Palette.agent)
                        }
                        Text(title)
                            .font(DS.Typography.cardTitle)
                            .foregroundStyle(DS.Palette.ink)
                            .lineLimit(2)
                    }
                    Text(subtitle)
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .lineLimit(1)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .multilineTextAlignment(.leading)
            .padding(.vertical, DS.Spacing.sm + 2)
            .contentShape(Rectangle())
        }
        .buttonStyle(.hapticTap)
        .disabled(isWriting)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(accessibilityID)
    }

    private var isWriting: Bool {
        if case .write = kind { conversations.isCreatingRecap } else { false }
    }

    private var symbol: String {
        switch kind {
        case .recap: "calendar"
        case .write: "sparkles"
        }
    }

    private var title: String {
        switch kind {
        // Headlines are sentences ("Q4 roadmap and physio."); after "Recap:" the period reads odd.
        case let .recap(recap): L(
                "nativeHomeRecapTitle",
                recap.headline.hasSuffix(".") ? String(recap.headline.dropLast()) : recap.headline
            )
        case .write: L("nativeHomeWriteRecap")
        }
    }

    private var subtitle: String {
        switch kind {
        case let .recap(recap): recap.overview.replacingOccurrences(of: "\n", with: " ")
        case .write: L("nativeHomeWriteRecapHint")
        }
    }

    private var accessibilityID: String {
        switch kind {
        case let .recap(recap): "home.recap.\(recap.date)"
        case .write: "home.recap.write"
        }
    }

    private func tap() {
        switch kind {
        case let .recap(recap): onOpen(recap)
        case let .write(day): Task { await conversations.createRecap(for: day) }
        }
    }
}

/// One day in review, pushed like a conversation (so the edge swipe goes back), with that day's
/// conversations to open.
public struct RecapScreen: View {
    @Environment(ConversationsStore.self) private var conversations
    let recap: DailySummary
    let onOpenConversation: (Conversation) -> Void

    public init(recap: DailySummary, onOpenConversation: @escaping (Conversation) -> Void) {
        self.recap = recap
        self.onOpenConversation = onOpenConversation
    }

    private var dayConversations: [Conversation] {
        guard let day = recap.day else { return [] }
        return conversations.conversations.filter { Calendar.current.isDate($0.date, inSameDayAs: day) }
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DS.Spacing.xl) {
                VStack(alignment: .leading, spacing: DS.Spacing.sm) {
                    Text(recap.day.map { Formatting.dayTitle($0) } ?? recap.date)
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                    HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.sm) {
                        if let emoji = recap.emoji { Text(emoji).font(.system(size: 22)).accessibilityHidden(true) }
                        Text(recap.headline).font(DS.Typography.title).foregroundStyle(DS.Palette.ink)
                    }
                    Text(recap.overview)
                        .font(DS.Typography.body)
                        .foregroundStyle(DS.Palette.ink)
                        .lineSpacing(3)
                        .padding(.top, DS.Spacing.xs)
                }
                if !recap.highlights.isEmpty {
                    section(L("highlights")) {
                        ForEach(recap.highlights, id: \.self) { highlight in
                            HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.md) {
                                Text(highlight.emoji ?? "•").font(.system(size: 22)).frame(width: 30).accessibilityHidden(true)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(highlight.topic).font(DS.Typography.cardTitle).foregroundStyle(DS.Palette.ink)
                                    Text(highlight.summary).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
                if !recap.decisions.isEmpty {
                    section(L("decisions")) {
                        ForEach(recap.decisions, id: \.self) { decision in
                            HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.md) {
                                Image(systemName: "checkmark")
                                    .font(.system(size: 14, weight: .regular))
                                    .foregroundStyle(DS.Palette.inkSecondary)
                                    .frame(width: 30)
                                    .accessibilityHidden(true)
                                Text(decision).font(DS.Typography.body).foregroundStyle(DS.Palette.ink)
                            }
                        }
                    }
                }
                if !dayConversations.isEmpty {
                    section(L("nativeThatDaysConversations")) {
                        // The same rows as on Home.
                        ForEach(dayConversations) { conversation in
                            Button { onOpenConversation(conversation) } label: { ConversationRow(conversation, style: .plain) }
                                .buttonStyle(.hapticTap)
                        }
                    }
                }
            }
            .padding(DS.Spacing.gutter)
        }
        .background(DS.Palette.background)
        .navigationBarTitleDisplayMode(.inline)
    }

    /// A small gray label, then the rows on the page (no card).
    private func section(_ title: String, @ViewBuilder content: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: DS.Spacing.md) {
            Text(title)
                .font(DS.Typography.sectionLabel)
                .foregroundStyle(DS.Palette.inkSecondary)
                .accessibilityAddTraits(.isHeader)
            VStack(alignment: .leading, spacing: DS.Spacing.md) { content() }
        }
    }
}
