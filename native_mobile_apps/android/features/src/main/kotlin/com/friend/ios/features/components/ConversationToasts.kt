package com.friend.ios.features.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.rememberHaptics
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.stores.ConversationsStore

/**
 * Port of `UndoDeleteToast` (`ConversationToasts.swift`): "Conversation deleted · Undo" while a
 * delete waits out its undo window. The app shell shows it above every screen, so a delete from the
 * detail page can be undone back on Home. (`OmiToast` is in `OmiToast.kt`.)
 */
@Composable
fun UndoDeleteToast(modifier: Modifier = Modifier) {
    val conversations = LocalConversationsStore.current
    val haptics = rememberHaptics()
    val pending = conversations.pendingDeletion
    // Keeps the last text while the toast animates out.
    var shown by remember { mutableStateOf<ConversationsStore.PendingDeletion?>(null) }
    if (pending != null) shown = pending
    AnimatedVisibility(
        visible = pending != null,
        modifier = modifier,
        enter = slideInVertically(DS.Motion.standard()) { it } + fadeIn(DS.Motion.standard()),
        exit = slideOutVertically(DS.Motion.standard()) { it } + fadeOut(DS.Motion.standard()),
    ) {
        val count = shown?.ids?.size ?: 1
        OmiToast(
            if (count == 1) L("conversationDeleted") else L("nativeConversationsDeleted", "$count"),
            "trash",
            actionTitle = L("undo"),
        ) {
            haptics.tap()
            conversations.undoDelete()
        }
    }
}
