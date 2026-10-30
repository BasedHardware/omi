import OmiCore
import OmiDesign
import OmiService
import SwiftUI

// MARK: - Discovery

/// Something Omi found: a title, its summary, and the whole text behind Show More. Tappable only
/// while there is more to read than what is already shown.
struct DiscoveryBlockCard: View {
    let block: ChatBlock
    let title: String
    let summary: String
    let fullText: String
    @State private var expanded = false

    private var hasMore: Bool {
        !fullText.isEmpty && fullText != summary
    }

    private var body_: String {
        expanded && hasMore ? fullText : summary
    }

    var body: some View {
        ChatBlockCard(
            onTap: hasMore ? { withAnimation(DS.Motion.standard) { expanded.toggle() } } : nil,
            content: {
                VStack(alignment: .leading, spacing: DS.Spacing.xs + 2) {
                    ChatBlockEyebrow(symbol: "sparkle.magnifyingglass", label: L("discovery"))
                    if !title.isEmpty {
                        Text(title)
                            .font(DS.Typography.callout.weight(.semibold))
                            .foregroundStyle(DS.Palette.ink)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if !body_.isEmpty {
                        Text(body_)
                            .font(DS.Typography.callout)
                            .foregroundStyle(DS.Palette.ink)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if hasMore {
                        HStack(spacing: DS.Spacing.xs) {
                            Text(expanded ? L("chatBlockShowLess") : L("chatBlockShowMore"))
                                .font(DS.Typography.caption.weight(.semibold))
                            Image(systemName: expanded ? "chevron.up" : "chevron.down")
                                .font(.system(size: 10, weight: .semibold))
                        }
                        .foregroundStyle(DS.Palette.agent)
                    }
                }
            }
        )
        .accessibilityIdentifier("chat.block.discovery.\(block.id)")
    }
}

// MARK: - Question

/// Omi's question with the answers it prepared: tapping one sends it as the user's own words.
/// Once answered, only the chosen answer stays, marked and no longer tappable (Flutter
/// `QuestionCardBlock`).
struct QuestionBlockCard: View {
    let block: ChatBlock
    let question: ChatQuestion
    let onSend: (String) -> Void

    var body: some View {
        ChatBlockCard {
            VStack(alignment: .leading, spacing: DS.Spacing.sm) {
                ChatBlockEyebrow(symbol: "questionmark.circle", label: L("chatBlockQuestion"))
                if !question.text.isEmpty {
                    Text(question.text)
                        .font(DS.Typography.callout)
                        .foregroundStyle(DS.Palette.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                VStack(alignment: .leading, spacing: DS.Spacing.sm) {
                    ForEach(question.visibleOptions, id: \.id) { option in
                        optionView(option)
                    }
                }
            }
        }
        .accessibilityIdentifier("chat.block.question.\(block.id)")
    }

    @ViewBuilder
    private func optionView(_ option: ChatQuestion.Option) -> some View {
        let answer = prepared(option)
        if question.isAnswered {
            HStack(spacing: DS.Spacing.sm) {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(option.id == question.selectedOptionID ? DS.Palette.agent : DS.Palette.inkTertiary)
                    .accessibilityHidden(true)
                Text(option.label)
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .accessibilityIdentifier("chat.block.question.\(block.id).answered")
        } else if answer.isEmpty {
            // Nothing to send: a label, not a button.
            Text(option.label)
                .font(DS.Typography.callout)
                .foregroundStyle(DS.Palette.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
        } else {
            Button {
                DSHaptics.tap()
                onSend(answer)
            } label: {
                Text(option.label)
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.ink)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, DS.Spacing.md)
                    .padding(.vertical, DS.Spacing.sm)
                    .frame(minHeight: 36)
                    .overlay(Capsule().stroke(DS.Palette.cardStroke, lineWidth: 1))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("chat.block.question.\(block.id).option.\(option.id)")
        }
    }

    /// What tapping sends: the answer the backend prepared, or the label when it prepared none.
    private func prepared(_ option: ChatQuestion.Option) -> String {
        let prepared = option.preparedAnswer.trimmingCharacters(in: .whitespacesAndNewlines)
        return prepared.isEmpty ? option.label.trimmingCharacters(in: .whitespacesAndNewlines) : prepared
    }
}

// MARK: - Agent run

/// A background run: what it is doing, or how it ended. Read-only on purpose: the phone has no
/// place to watch a run (Flutter `_AgentRunCard`).
struct AgentRunBlockCard: View {
    let block: ChatBlock
    let title: String
    let detail: String
    let status: ChatBlock.AgentRunStatus

    var body: some View {
        ChatBlockCard {
            VStack(alignment: .leading, spacing: DS.Spacing.xs + 2) {
                ChatBlockEyebrow(symbol: symbol, label: label)
                if !title.isEmpty {
                    Text(title)
                        .font(DS.Typography.callout.weight(.semibold))
                        .foregroundStyle(DS.Palette.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if !detail.isEmpty {
                    Text(detail)
                        .font(DS.Typography.callout)
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .lineLimit(6)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .accessibilityIdentifier("chat.block.agentRun.\(block.id)")
    }

    private var symbol: String {
        switch status {
        case .running: "cpu"
        case .completed: "checkmark.circle"
        case .cancelled: "slash.circle"
        case .timedOut: "clock.badge.exclamationmark"
        case .failed: "exclamationmark.triangle"
        }
    }

    private var label: String {
        switch status {
        case .running: L("processing")
        case .completed: L("statusCompleted")
        case .cancelled: L("cancelled")
        case .timedOut: L("statusTimedOut")
        case .failed: L("statusFailed")
        }
    }
}

// MARK: - Memory review

/// "Things I learned today": up to three memories Omi stored, each named live from the store,
/// with the two verdicts the review API takes. A verdict is addressed by id, so a memory the list
/// has not loaded yet is still answerable; while a verdict is in flight its row does not offer
/// another.
struct MemoryReviewBlockCard: View {
    @Environment(MemoriesStore.self) private var memories
    let block: ChatBlock
    let review: ChatMemoryReview
    @State private var settled: [String: Bool] = [:]
    @State private var inFlight: Set<String> = []
    @State private var failed: Set<String> = []

    var body: some View {
        ChatBlockCard {
            VStack(alignment: .leading, spacing: DS.Spacing.md) {
                VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                    Text(L("memoryReviewTitle"))
                        .font(DS.Typography.callout.weight(.semibold))
                        .foregroundStyle(DS.Palette.ink)
                    Text(L("nativeMemoryReviewHint"))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkTertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ForEach(review.items) { item in
                    row(item)
                }
            }
        }
        .accessibilityIdentifier("chat.block.memoryReview.\(block.id)")
        .task { if memories.phase != .loaded { await memories.load() } }
    }

    private func row(_ item: ChatMemoryReview.Item) -> some View {
        let memory = memories.memories.first { $0.id == item.memoryID }
        let state = settled[item.memoryID] ?? memory?.userReview
        return VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            Text(memory?.content ?? item.content)
                .font(DS.Typography.callout)
                .foregroundStyle(state == false ? DS.Palette.inkTertiary : DS.Palette.ink)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: DS.Spacing.md) {
                if !item.category.isEmpty {
                    Text(item.category)
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkTertiary)
                        .tracking(DS.Tracking.label)
                }
                if let state {
                    Text(state ? L("memoryReviewConfirmed") : L("memoryReviewDropped"))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .accessibilityIdentifier("chat.block.memoryReview.\(block.id).status.\(item.memoryID)")
                } else {
                    Spacer(minLength: 0)
                    verdict(L("memoryReviewRight"), id: "right", item: item, isRight: true)
                    verdict(L("memoryReviewWrong"), id: "wrong", item: item, isRight: false)
                }
            }
            if failed.contains(item.memoryID) {
                Text(L("memoryReviewSaveFailed"))
                    .font(DS.Typography.caption)
                    .foregroundStyle(DS.Palette.warning)
                    .accessibilityIdentifier("chat.block.memoryReview.\(block.id).error.\(item.memoryID)")
            }
        }
        .padding(DS.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.Palette.fill, in: RoundedRectangle(cornerRadius: DS.Radius.sm, style: .continuous))
        .accessibilityIdentifier("chat.block.memoryReview.\(block.id).row.\(item.memoryID)")
    }

    private func verdict(_ title: String, id: String, item: ChatMemoryReview.Item, isRight: Bool) -> some View {
        Button {
            vote(item, isRight: isRight)
        } label: {
            Text(title)
                .font(DS.Typography.caption.weight(.semibold))
                .foregroundStyle(isRight ? DS.Palette.agent : DS.Palette.inkSecondary)
                .padding(.horizontal, DS.Spacing.md)
                .frame(minHeight: 36)
                .background(DS.Palette.background, in: Capsule())
        }
        .buttonStyle(.plain)
        .disabled(inFlight.contains(item.memoryID))
        .accessibilityIdentifier("chat.block.memoryReview.\(block.id).\(id).\(item.memoryID)")
    }

    private func vote(_ item: ChatMemoryReview.Item, isRight: Bool) {
        guard !inFlight.contains(item.memoryID) else { return }
        inFlight.insert(item.memoryID)
        failed.remove(item.memoryID)
        DSHaptics.tap()
        Task {
            await memories.review(item.memoryID, isRight: isRight)
            inFlight.remove(item.memoryID)
            if let message = memories.lastError, !message.isEmpty {
                // The store rolled its own change back: this row is unanswered again.
                failed.insert(item.memoryID)
            } else {
                settled[item.memoryID] = isRight
            }
        }
    }
}
