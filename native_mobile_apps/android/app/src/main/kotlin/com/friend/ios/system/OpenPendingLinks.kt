package com.friend.ios.system

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import com.friend.ios.service.LocalAgentStore
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.LocalTasksStore

/**
 * `MainTabView.openPendingLink()`: once the shell is on screen it opens what [DeepLinkRouter]
 * holds, and again whenever a new link arrives. [open] closes what is open and shows the
 * destination (the shell owns its sheets and pages).
 */
@Composable
fun OpenPendingLinks(open: suspend (DeepLinkRouter.Destination) -> Unit) {
    val router = LocalDeepLinkRouter.current
    val tasks = LocalTasksStore.current
    val agent = LocalAgentStore.current
    val conversations = LocalConversationsStore.current
    val pending = router.pending
    LaunchedEffect(pending) {
        val link = router.take() ?: return@LaunchedEffect
        open(DeepLinkRouter.destination(link, tasks, agent, conversations))
    }
}
