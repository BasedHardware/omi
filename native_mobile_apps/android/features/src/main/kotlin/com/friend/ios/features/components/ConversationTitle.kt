package com.friend.ios.features.components

import androidx.compose.runtime.Composable
import com.friend.ios.core.models.Conversation
import com.friend.ios.design.L
import com.friend.ios.design.Strings

/** Port of `ConversationTitle.swift`: the title, else "Discarded Conversation" or "Untitled conversation". */
@Composable
fun Conversation.displayTitle(): String {
    if (title.isNotEmpty()) return title
    return if (isDiscarded) L("discardedConversation") else L("untitledConversation")
}

/** [displayTitle] outside composition. */
fun Conversation.displayTitle(context: android.content.Context): String {
    if (title.isNotEmpty()) return title
    return Strings.get(context, if (isDiscarded) "discardedConversation" else "untitledConversation")
}
