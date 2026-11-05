import OmiCore
import OmiDesign
import OmiService
import SwiftUI

// MARK: - Memory

/// The memory the answer leaned on, and the way to Memories.
struct MemoryBlockCard: View {
    @Environment(MemoriesStore.self) private var memories
    @Environment(\.openURL) private var openURL
    let block: ChatBlock
    let memoryID: String
    let summary: String

    var body: some View {
        ChatBlockLinkCard(
            block: block,
            symbol: "sparkles",
            eyebrow: L("chatBlockMemory"),
            summary: summary,
            action: L("chatBlockOpenInMemories"),
            onOpen: {
                if memories.memories.contains(where: { $0.id == memoryID }) {
                    openURL(DeepLink.memory(id: memoryID).url)
                } else {
                    openURL(DeepLink.memories.url)
                }
            }
        )
    }
}

// MARK: - Conversation

/// The conversation (or the recording) the answer came from, with the next steps it recommends.
/// Read-only: the card opens the conversation and never edits the tasks it lists.
struct ConversationBlockCard: View {
    @Environment(\.openURL) private var openURL
    let block: ChatBlock
    let conversationID: String
    let summary: String
    let actionItems: [ChatBlock.ActionItemHint]
    let isCapture: Bool
    var onOpenConversation: ((String) -> Void)?

    var body: some View {
        ChatBlockLinkCard(
            block: block,
            symbol: isCapture ? "waveform" : "bubble.left.and.text.bubble.right",
            eyebrow: isCapture ? L("conversations") : L("chatBlockConversation"),
            summary: summary,
            action: L("chatBlockOpenConversation"),
            footer: actionItems.isEmpty ? nil : { AnyView(steps) },
            onOpen: open
        )
    }

    private var steps: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.xs) {
            Text(L("chatBlockRecommendedNextSteps"))
                .font(DS.Typography.caption.weight(.semibold))
                .foregroundStyle(DS.Palette.inkTertiary)
            ForEach(Array(actionItems.enumerated()), id: \.offset) { _, item in
                HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.sm) {
                    Circle()
                        .fill(DS.Palette.inkTertiary)
                        .frame(width: 4, height: 4)
                        .accessibilityHidden(true)
                    Text(item.description)
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func open() {
        DSHaptics.tap()
        guard let onOpenConversation else {
            openURL(DeepLink.conversation(id: conversationID).url)
            return
        }
        onOpenConversation(conversationID)
    }
}
