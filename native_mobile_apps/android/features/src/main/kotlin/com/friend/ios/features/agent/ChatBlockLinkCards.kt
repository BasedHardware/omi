package com.friend.ios.features.agent

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.unit.dp
import com.friend.ios.core.DeepLink
import com.friend.ios.core.models.ChatBlock
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.semibold
import com.friend.ios.service.LocalMemoriesStore

/*
 * Port of `ChatBlockLinkCards.swift`: the cards that point somewhere: the memory the answer
 * leaned on, and the conversation (or recording) it came from.
 *
 * iOS opens a card's destination with `openURL(DeepLink…)`; the Android port hands the same
 * `omi://` link to the system (`LocalUriHandler`), as `TaskChangeCard` already does, and the app's
 * own link handler brings the destination up.
 */

// Memory

/** The memory the answer leaned on, and the way to Memories. */
@Composable
fun MemoryBlockCard(memoryID: String, summary: String, modifier: Modifier = Modifier) {
    val memories = LocalMemoriesStore.current
    val uri = LocalUriHandler.current
    ChatBlockLinkCard(
        symbol = "sparkles",
        eyebrow = L("chatBlockMemory"),
        summary = summary,
        action = L("chatBlockOpenInMemories"),
        modifier = modifier,
        onOpen = {
            // A memory the list has not loaded cannot be scrolled to, so the tab opens instead.
            val link = if (memories.memories.any { it.id == memoryID }) DeepLink.Memory(memoryID) else DeepLink.Memories
            uri.openUri(link.url)
        },
    )
}

// Conversation

/**
 * The conversation (or the recording) the answer came from, with the next steps it recommends.
 * Read-only: the card opens the conversation and never edits the tasks it lists.
 */
@Composable
fun ConversationBlockCard(
    conversationID: String,
    summary: String,
    actionItems: List<ChatBlock.ActionItemHint>,
    isCapture: Boolean,
    onOpenConversation: ((String) -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    val uri = LocalUriHandler.current
    ChatBlockLinkCard(
        symbol = if (isCapture) "waveform" else "bubble.left.and.text.bubble.right",
        eyebrow = if (isCapture) L("conversations") else L("chatBlockConversation"),
        summary = summary,
        action = L("chatBlockOpenConversation"),
        modifier = modifier,
        footer = if (actionItems.isEmpty()) null else ({ Steps(actionItems) }),
        onOpen = {
            if (onOpenConversation != null) {
                onOpenConversation(conversationID)
            } else {
                uri.openUri(DeepLink.Conversation(conversationID).url)
            }
        },
    )
}

/** The next steps the conversation link recommends: plain text, the tasks themselves stay untouched. */
@Composable
private fun Steps(items: List<ChatBlock.ActionItemHint>) {
    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
        Text(L("chatBlockRecommendedNextSteps"), style = DS.Typography.caption.semibold(), color = DS.Palette.inkTertiary)
        for (item in items) {
            HStack(alignment = Alignment.Top, spacing = DS.Spacing.sm) {
                Box(Modifier.padding(top = 6.dp).size(4.dp).background(DS.Palette.inkTertiary, CircleShape))
                Text(item.description, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
            }
        }
    }
}
