import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// A message's structured parts, each as its own card: a task to tick, a link to the goal, memory
/// or conversation it mentions, a discovery to open, a question with prepared answers, a
/// background run, and the day's memories to review. Draws what the wire carried, never a card
/// for nothing: an affordance that cannot do anything is not drawn as one.
///
/// The same vocabulary as the desktop transcript and the Flutter app
/// (`lib/pages/chat/widgets/content_blocks/`).
struct ChatBlocks: View {
    @Environment(\.chatBubbleWidth) private var bubbleWidth
    let message: ChatMessage
    /// Sends a prepared answer as if it were typed (a question card's options).
    var onSend: (String) -> Void = { _ in }
    /// The shell's way to a conversation, so a card inside the sheet page opens it instead of
    /// leaving the sheet behind. Without one the card falls back to the app's `omi://` link.
    var onOpenConversation: ((String) -> Void)?

    var body: some View {
        let blocks = message.blocks
        if !blocks.isEmpty {
            VStack(alignment: .leading, spacing: DS.Spacing.sm) {
                ForEach(blocks) { block in
                    view(block)
                }
            }
            .frame(maxWidth: bubbleWidth, alignment: .leading)
        }
    }

    @ViewBuilder
    private func view(_ block: ChatBlock) -> some View {
        switch block.kind {
        case let .task(taskID): TaskBlockCard(block: block, taskID: taskID)
        case let .goal(goalID, summary): GoalBlockCard(block: block, goalID: goalID, summary: summary)
        case let .memory(memoryID, summary): MemoryBlockCard(block: block, memoryID: memoryID, summary: summary)
        case let .conversation(id, summary, actionItems, isCapture):
            ConversationBlockCard(
                block: block, conversationID: id, summary: summary, actionItems: actionItems,
                isCapture: isCapture, onOpenConversation: onOpenConversation
            )
        case let .discovery(title, summary, fullText): DiscoveryBlockCard(block: block, title: title, summary: summary, fullText: fullText)
        case let .question(question): QuestionBlockCard(block: block, question: question, onSend: onSend)
        case let .agentRun(title, detail, status): AgentRunBlockCard(block: block, title: title, detail: detail, status: status)
        case let .memoryReview(review): MemoryReviewBlockCard(block: block, review: review)
        case .text, .other:
            // No component of its own: only its line, and only where the cards replaced the body.
            EmptyView()
        }
    }
}
