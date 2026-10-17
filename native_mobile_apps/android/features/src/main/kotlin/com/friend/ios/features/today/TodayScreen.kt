package com.friend.ios.features.today

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.DailySummary
import com.friend.ios.design.DS
import com.friend.ios.features.components.GoalUndoToast
import com.friend.ios.service.LocalAgentStore
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.LocalGoalsStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.ConversationsStore
import com.friend.ios.service.stores.GoalsStore
import com.friend.ios.service.stores.TasksStore
import com.friend.ios.service.stores.loadRecommendations
import com.friend.ios.service.stores.loadWorkstreams
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch

/**
 * Port of `TodayScreen.swift`. Home: what Omi hears now, "Needs you" (at most five cards, then
 * "Later" and "All tasks"), then every conversation by day (each day led by its recap), goals at
 * the end. [bottomInset] keeps the last rows clear of the Omi bar. Voices to name (VoicesStore's
 * speaker prompts) arrive as a "Needs you" card.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TodayScreen(
    onOpenConversation: (String) -> Unit,
    onOpenAllTasks: () -> Unit,
    onOpenSearch: () -> Unit,
    onAskOmi: (String) -> Unit,
    modifier: Modifier = Modifier,
    bottomInset: Dp = 0.dp,
    /** One day's recap, pushed like a conversation (the shell pushes `Route.Recap`). */
    onOpenRecap: (DailySummary) -> Unit = {},
    /** A task card's detail (text, due date, where it came from): `TaskDetailSheet`. */
    onOpenTask: (ActionItem) -> Unit = { onOpenAllTasks() },
    /** "Omi takes over": `HandOverSheet`. */
    onHandOver: (ActionItem) -> Unit = {},
    /** Omi's run on a task (task id): the hand-over sheet in progress or with its result. */
    onOpenRun: (String) -> Unit = {},
    onOpenSiriTip: () -> Unit = {},
    /**
     * The swipe's "Moved to Later" with Undo. The shell passes one and shows the toast over its Omi
     * bar (the bar's fade would cover it here); without one, Home shows it itself.
     */
    laterUndo: TaskLaterUndo? = null,
) {
    val conversations = LocalConversationsStore.current
    val tasks = LocalTasksStore.current
    val goals = LocalGoalsStore.current
    val agent = LocalAgentStore.current
    val ownUndo = remember { TaskLaterUndo() }
    val undo = laterUndo ?: ownUndo
    val scope = rememberCoroutineScope()
    /** Conversations picked for a bulk action; null outside selection mode. */
    var selection by remember { mutableStateOf<Set<String>?>(null) }
    /** "For you" nudges (the proactivity feed), made once this screen exists. */
    val forYou = remember(conversations) { conversations.makeForYouStore() }
    val listState = rememberConversationListState()
    var refreshing by remember { mutableStateOf(false) }
    val openConversation: (com.friend.ios.core.models.Conversation) -> Unit = { onOpenConversation(it.id) }

    LaunchedEffect(Unit) { if (conversations.phase == ConversationsStore.Phase.Idle) conversations.load() }
    LaunchedEffect(Unit) { forYou.load() }
    LaunchedEffect(Unit) { if (goals.phase == GoalsStore.Phase.Idle) goals.load() }
    // The iOS shell loads tasks once signed in (`TasksStore.load` in the app); Home asks when nobody has.
    LaunchedEffect(Unit) { if (tasks.phase == TasksStore.Phase.Idle) tasks.load() }
    // Reloads when the list changes: a new conversation can mean a new day to recap.
    LaunchedEffect(conversations.conversations.size) { conversations.loadRecaps() }
    // What matters now, and runs from earlier sessions (tasks carry their workstream).
    LaunchedEffect(Unit) { agent.loadRecommendations() }
    LaunchedEffect(tasks.tasks.size) { agent.loadWorkstreams(tasks.tasks) }
    val voices = com.friend.ios.service.LocalVoicesStore.current
    LaunchedEffect(Unit) { voices.loadPrompts() }
    // The day's tidy-up: once the tasks are in, on the first visit after 6:00.
    // `-omiNoTidyUp YES` keeps it off (an account that must not change), `-omiTidyUpNow YES` runs it now.
    LaunchedEffect(tasks.phase == TasksStore.Phase.Loaded) {
        val force = com.friend.ios.features.components.DebugLaunch.flag("omiTidyUpNow")
        if (tasks.phase != TasksStore.Phase.Loaded || com.friend.ios.features.components.DebugLaunch.flag("omiNoTidyUp") || !(force || tasks.tidyUpIsDue())) {
            return@LaunchedEffect
        }
        // The words behind each task help it spot requests made of someone else.
        conversations.loadSources(tasks.tasks.filter { it.isOpen })
        tasks.tidyUpIfDue(source = { conversations.source(it)?.title }, quote = { conversations.quote(it) }, force = force)
    }

    Box(modifier.fillMaxSize()) {
        PullToRefreshBox(
            isRefreshing = refreshing,
            onRefresh = {
                scope.launch {
                    refreshing = true
                    coroutineScope {
                        listOf(
                            async { conversations.load() },
                            async { tasks.load() },
                            async { conversations.loadRecaps() },
                            async { conversations.reloadFiltered() },
                            async { goals.load() },
                            async { forYou.load() },
                            async { agent.loadRecommendations() },
                            async { voices.loadPrompts() },
                        ).awaitAll()
                    }
                    refreshing = false
                }
            },
            modifier = Modifier.fillMaxSize(),
        ) {
            LazyColumn(
                Modifier.fillMaxSize(),
                contentPadding = PaddingValues(
                    start = DS.Spacing.gutter, end = DS.Spacing.gutter, top = DS.Spacing.sm,
                    bottom = DS.Spacing.section + bottomInset,
                ),
            ) {
                // Capture (and-capture): the live bar while recording, then a recording that ended unexpectedly.
                item(key = "capture") {
                    val capture = com.friend.ios.service.LocalCaptureStore.current
                    androidx.compose.foundation.layout.Column {
                        if (capture.phase != com.friend.ios.service.stores.CaptureStore.Phase.Idle) LiveBar(Modifier.padding(bottom = DS.Spacing.lg))
                        if (capture.recovery != null || capture.notice != null) {
                            CaptureRecoveryBanner(Modifier.padding(bottom = DS.Spacing.lg))
                        }
                    }
                }
                item(key = "needsYou") {
                    NeedsYouSection(
                        forYou = forYou, onOpenRun = onOpenRun, onHandOver = onHandOver,
                        onOpenConversation = { id -> scope.launch { conversations.conversation(id)?.let(openConversation) } },
                        onOpenSiriTip = onOpenSiriTip, onOpenAllTasks = onOpenAllTasks, onOpenTask = onOpenTask, onAskOmi = onAskOmi,
                        laterUndo = undo,
                    )
                }
                conversationList(conversations, listState, selection, { selection = it }, openConversation, onOpenRecap)
                item(key = "goals") { GoalsCard() }
            }
        }
        ConversationListSheets(listState, { selection = it }, openConversation)
        AnimatedVisibility(
            visible = selection != null,
            modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = bottomInset),
            enter = slideInVertically(DS.Motion.standard()) { it } + fadeIn(DS.Motion.standard()),
            exit = slideOutVertically(DS.Motion.standard()) { it } + fadeOut(DS.Motion.standard()),
        ) {
            SelectionBar(selection.orEmpty(), { selection = it }, listState)
        }
        GoalUndoToast(Modifier.align(Alignment.BottomCenter).padding(bottom = DS.Spacing.lg + bottomInset))
        if (laterUndo == null) TaskLaterUndoToast(undo, Modifier.align(Alignment.BottomCenter).padding(bottom = DS.Spacing.lg + bottomInset))
    }
}
