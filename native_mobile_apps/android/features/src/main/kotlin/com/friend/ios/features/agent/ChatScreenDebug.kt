package com.friend.ios.features.agent

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.service.LocalChatStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.ChatThreadFilter
import com.friend.ios.service.stores.showDemoBlocks
import com.friend.ios.service.stores.showDemoCards
import com.friend.ios.service.stores.showDemoThread
import kotlinx.coroutines.delay

/**
 * Port of `ChatScreen+Debug.swift`: debug launch arguments for screenshots of the chat, read in
 * debug builds only and inert otherwise (`DebugLaunch`): `-omiChatSearch <words>`,
 * `-omiChatFilter approvals|drafts|jobs|files`, `-omiChatDraft <words>` (in the composer, not sent;
 * `\n` for a new line), `-omiChatDemoThread YES` (a made-up exchange on this phone only),
 * `-omiChatJumpTo <message id>` (scrolled up to that message, as from a search match),
 * `-omiChatDemoCards YES` (a connect card, a task card and source chips on the newest answer),
 * `-omiChatDemoBlocks YES` (a made-up exchange carrying one of every content block, plus the task
 * row its task card points at).
 *
 * Not ported: `omiChatDemoAsks` and `omiChatRunTask`, which drive the agent area's stores.
 */
@Composable
internal fun ChatDebugDemos(state: ChatScreenState) {
    val chat = LocalChatStore.current
    val tasks = LocalTasksStore.current
    LaunchedEffect(Unit) {
        DebugLaunch.string("omiChatSearch")?.let { words ->
            state.isSearching = true
            state.query = words
        }
        DebugLaunch.string("omiChatFilter")?.let { name ->
            ChatThreadFilter.entries.firstOrNull { it.rawValue == name }?.let { value ->
                state.isSearching = true
                state.filter = value
            }
        }
        DebugLaunch.string("omiChatDraft")?.let { words -> state.draft = words.replace("\\n", "\n") }
        val wantsDemo = DebugLaunch.flag("omiChatDemoBlocks") || DebugLaunch.flag("omiChatDemoCards") || DebugLaunch.flag("omiChatDemoThread")
        // The made-up thread goes under the real one, so the real one has to be there first.
        if (wantsDemo) repeat(50) { if (!chat.hasLoaded) delay(100) }
        if (DebugLaunch.flag("omiChatDemoThread")) chat.showDemoThread()
        if (DebugLaunch.flag("omiChatDemoBlocks")) {
            // The task card resolves against the real list, so the list comes first: a load after
            // the demo row would take the row with it.
            tasks.load()
            chat.showDemoBlocks(tasks)
        }
        if (DebugLaunch.flag("omiChatDemoCards")) chat.showDemoCards()
        DebugLaunch.string("omiChatJumpTo")?.let { id ->
            // Once the thread has settled at its end: scrolled up to that message, as from a search match.
            delay(1_500)
            state.jumpTarget = id
        }
    }
}
