package com.friend.ios.system

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import com.friend.ios.core.DeepLink
import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.ConversationFilter
import com.friend.ios.core.models.DailySummary
import com.friend.ios.service.stores.AgentStore
import com.friend.ios.service.stores.ConversationsStore
import com.friend.ios.service.stores.TasksStore
import com.friend.ios.service.stores.openShare
import com.friend.ios.shell.Route
import com.friend.ios.shell.Tab
import java.time.LocalDate

/**
 * Port of `DeepLinkRouter.swift`: the one inbox for links (notification taps, `omi://` and h.omi.me
 * links, launcher shortcuts, widgets, `--es omiDeepLink`). A link waits here until `MainTabView`
 * is on screen (cold start, sign-in, onboarding), which then opens it.
 */
class DeepLinkRouter {
    var pending: DeepLink? by mutableStateOf(null)
        private set

    fun open(link: DeepLink?) {
        // A tap without a destination still brings the app forward; nothing to route.
        if (link != null) pending = link
    }

    /** An `omi://` or `https://h.omi.me` URL. */
    fun open(url: String) = open(DeepLink.fromAnyUrl(url))

    fun take(): DeepLink? = pending.also { pending = null }

    /** What the shell shows for a link, with the target loaded first when it is not in a store yet. */
    sealed interface Destination {
        data class Push(val route: Route) : Destination
        data class SelectTab(val tab: Tab) : Destination
        data class HandOver(val task: ActionItem) : Destination
        /** A task Omi has not worked on: its detail over Home. */
        data class TaskDetail(val task: ActionItem) : Destination
        data object Chat : Destination
        data object Device : Destination
        data class ChatDraft(val text: String) : Destination
        data object NewTask : Destination
        data object Record : Destination
        data object Account : Destination
        /** One app's page (`h.omi.me/apps/<id>`). */
        data class App(val id: String) : Destination
    }

    companion object {
        /** The destinations that need nothing loaded; null for the ones that do. */
        fun immediateDestination(link: DeepLink): Destination? = when (link) {
            // The Android route carries the id; the detail screen loads the conversation itself.
            is DeepLink.Conversation -> Destination.Push(Route.Conversation(link.id))
            DeepLink.Tasks -> Destination.Push(Route.AllTasks)
            DeepLink.Memories, is DeepLink.Memory -> Destination.SelectTab(Tab.Memory)
            DeepLink.Home -> Destination.SelectTab(Tab.Home)
            DeepLink.Chat -> Destination.Chat
            DeepLink.Device -> Destination.Device
            is DeepLink.ChatDraft -> Destination.ChatDraft(link.text)
            DeepLink.NewTask -> Destination.NewTask
            DeepLink.Record -> Destination.Record
            DeepLink.Account -> Destination.Account
            is DeepLink.App -> Destination.App(link.id)
            is DeepLink.Task, is DeepLink.Recap, is DeepLink.SharedTasks, is DeepLink.Folder -> null
        }

        suspend fun destination(link: DeepLink, tasks: TasksStore, agent: AgentStore, conversations: ConversationsStore): Destination {
            immediateDestination(link)?.let { return it }
            return when (link) {
                is DeepLink.Task -> {
                    if (tasks.tasks.none { it.id == link.id }) tasks.load()
                    val task = tasks.tasks.firstOrNull { it.id == link.id } ?: return Destination.Push(Route.AllTasks)
                    // Omi worked on it: open the run (progress or the finished result).
                    val hasRun = agent.runs[link.id] != null || task.workstreamID != null
                    if (hasRun) Destination.HandOver(task) else Destination.TaskDetail(task)
                }
                is DeepLink.Recap -> recap(link.key, conversations)?.let { Destination.Push(Route.Recap(it)) } ?: Destination.SelectTab(Tab.Home)
                is DeepLink.SharedTasks -> {
                    // Tasks shows the accept sheet (or says the link expired).
                    tasks.openShare(link.token)
                    Destination.Push(Route.AllTasks)
                }
                is DeepLink.Folder -> {
                    conversations.setFilter(ConversationFilter.Folder(link.id))
                    Destination.SelectTab(Tab.Home)
                }
                else -> Destination.SelectTab(Tab.Home)
            }
        }

        /** By summary id (pushes) or local date (`omi://recap/2026-10-07`, generated if missing). */
        private suspend fun recap(key: String, store: ConversationsStore): DailySummary? {
            fun match() = store.recaps.firstOrNull { it.id == key || it.date == key }
            match()?.let { return it }
            store.loadRecaps()
            match()?.let { return it }
            val day = runCatching { LocalDate.parse(key) }.getOrNull() ?: return null
            store.createRecap(day)
            return match()
        }
    }
}

val LocalDeepLinkRouter = staticCompositionLocalOf<DeepLinkRouter> { error("DeepLinkRouter not provided") }
