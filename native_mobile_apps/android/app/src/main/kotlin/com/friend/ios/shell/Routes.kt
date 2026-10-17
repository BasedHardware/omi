package com.friend.ios.shell

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.DailySummary
import com.friend.ios.design.L
import com.friend.ios.design.OmiPushedScreen
import com.friend.ios.design.OmiSheet
import com.friend.ios.features.agent.HandOverSheet
import com.friend.ios.features.conversations.ConversationDetailScreen
import com.friend.ios.features.conversations.SearchScreen
import com.friend.ios.features.tasks.DayTasksScreen
import com.friend.ios.features.tasks.TasksScreen
import com.friend.ios.features.today.RecapScreen
import com.friend.ios.service.stores.makeGraphStore
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.LocalMemoriesStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.makeDetailStore
import com.friend.ios.service.stores.makeSearchStore
import java.time.LocalDate

/** `MainTabView.Route`: everything pushed over the tabs. */
sealed interface Route {
    data class Conversation(val id: String) : Route
    /** One day in review, from its row on Home. */
    data class Recap(val recap: DailySummary) : Route
    data object Search : Route
    /** Every task, from Home's "All tasks (n)". */
    data object AllTasks : Route
    /** Memories > Memory graph (and-onboarding). */
    data object MemoryGraph : Route
    /** One day's tasks (`TasksScreen`'s `navigationDestination` to `DayTasksScreen`). */
    data class DayTasks(val date: LocalDate) : Route
}

/**
 * `.navigationDestination(for: Route.self)`. [onAskOmi] goes to the Chat tab at the root (the chat
 * already points at the conversation).
 */
@Composable
fun RouteDestination(route: Route, onBack: () -> Unit, push: (Route) -> Unit, onAskOmi: () -> Unit = {}) {
    val conversations = LocalConversationsStore.current
    // `handOver`: Omi's hand-over for a task from a pushed screen (`MainTabView+Sheets.swift`).
    var handOverTask by remember { mutableStateOf<ActionItem?>(null) }
    val handOver: (ActionItem) -> Unit = { handOverTask = it }
    when (route) {
        is Route.Recap -> OmiPushedScreen("", onBack) {
            RecapScreen(route.recap, onOpenConversation = { push(Route.Conversation(it.id)) })
        }
        Route.MemoryGraph -> {
            val memories = com.friend.ios.service.LocalMemoriesStore.current
            val session = com.friend.ios.service.LocalSessionStore.current
            val graph = androidx.compose.runtime.remember { memories.makeGraphStore(session.displayName) }
            com.friend.ios.features.memory.MemoryGraphScreen(graph, onBack)
        }
        Route.AllTasks -> OmiPushedScreen(L("tasks"), onBack) {
            TasksScreen(onHandOver = handOver, onOpenConversation = { push(Route.Conversation(it)) }, onOpenDay = { push(Route.DayTasks(it)) })
        }
        is Route.DayTasks -> DayTasksScreen(route.date, onBack, onOpenConversation = { push(Route.Conversation(it)) })
        is Route.Conversation -> {
            val store = remember(route.id) { conversations.makeDetailStore(route.id) }
            ConversationDetailScreen(
                store,
                onBack = onBack,
                onHandOver = handOver,
                onAskOmi = onAskOmi,
                onOpenConversation = { push(Route.Conversation(it.id)) },
            )
        }
        Route.Search -> {
            val tasks = LocalTasksStore.current
            val memories = LocalMemoriesStore.current
            val scope = rememberCoroutineScope()
            val store = remember { conversations.makeSearchStore(tasks, memories, scope) }
            SearchScreen(
                store,
                onBack = onBack,
                onOpenConversation = { push(Route.Conversation(it.id)) },
                onOpenRecap = { push(Route.Recap(it)) },
            )
        }
    }
    handOverTask?.let { task ->
        val title = task.conversationID?.let { id -> conversations.conversations.firstOrNull { it.id == id }?.title }
        OmiSheet(onDismiss = { handOverTask = null }) { HandOverSheet(task, title, onDismiss = { handOverTask = null }) }
    }
}
