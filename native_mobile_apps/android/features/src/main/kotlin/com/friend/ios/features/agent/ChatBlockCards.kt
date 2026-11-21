package com.friend.ios.features.agent

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.friend.ios.core.models.ChatBlock
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.design.DS

/**
 * Port of `ChatBlocks` (`ChatBlockCards.swift`). A message's structured parts, each as its own
 * card: a task to tick, a link to the goal, memory or conversation it mentions, a discovery to
 * open, a question with prepared answers, a background run, and the day's memories to review.
 * Draws what the wire carried, never a card for nothing: an affordance that cannot do anything is
 * not drawn as one.
 *
 * The same vocabulary as the desktop transcript and the Flutter app
 * (`lib/pages/chat/widgets/content_blocks/`).
 */
@Composable
fun ChatBlocks(
    message: ChatMessage,
    modifier: Modifier = Modifier,
    /** Sends a prepared answer as if it were typed (a question card's options). */
    onSend: (String) -> Unit = {},
    /**
     * The shell's way to a conversation, so a card inside a sheet page opens it instead of leaving
     * the sheet behind. Without one the card falls back to the app's `omi://` link.
     */
    onOpenConversation: ((String) -> Unit)? = null,
) {
    val blocks = message.blocks
    if (blocks.isEmpty()) return
    Column(modifier.bubbleWide(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        for (block in blocks) {
            when (val kind = block.kind) {
                is ChatBlock.Kind.Task -> TaskBlockCard(kind.taskID)
                is ChatBlock.Kind.Goal -> GoalBlockCard(kind.goalID, kind.summary)
                is ChatBlock.Kind.Memory -> MemoryBlockCard(kind.memoryID, kind.summary)
                is ChatBlock.Kind.Conversation -> ConversationBlockCard(
                    kind.conversationID, kind.summary, kind.actionItems, kind.isCapture, onOpenConversation,
                )

                is ChatBlock.Kind.Discovery -> DiscoveryBlockCard(block.id, kind.title, kind.summary, kind.fullText)
                is ChatBlock.Kind.Question -> QuestionBlockCard(kind.question, onSend)
                is ChatBlock.Kind.AgentRun -> AgentRunBlockCard(kind.title, kind.detail, kind.status)
                is ChatBlock.Kind.MemoryReview -> MemoryReviewBlockCard(kind.review)
                // No component of its own: only its line, and only where the cards replaced the body.
                is ChatBlock.Kind.Text, is ChatBlock.Kind.Other -> Unit
            }
        }
    }
}
