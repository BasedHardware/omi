package com.friend.ios.features.tasks

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ActionItem
import com.friend.ios.design.CircleIconButton
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiEmptyState
import com.friend.ios.design.OmiSearchField
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.SkeletonBlock
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.AgentTaskStatus
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.features.components.GoalsScreen
import com.friend.ios.features.components.TaskRow
import com.friend.ios.features.components.TaskToasts
import com.friend.ios.features.components.displayTitle
import com.friend.ios.features.conversations.ShareRequest
import com.friend.ios.features.conversations.rememberShareSheet
import com.friend.ios.service.LocalAgentStore
import com.friend.ios.service.LocalCapabilitiesStore
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.ConversationsStore
import com.friend.ios.service.stores.TakeOverEligibility
import com.friend.ios.service.stores.TasksStore
import com.friend.ios.service.stores.descendants
import com.friend.ios.service.stores.dismissShare
import com.friend.ios.service.stores.displayIndents
import com.friend.ios.service.stores.loadWorkstreams
import com.friend.ios.service.stores.shareLink
import kotlinx.coroutines.launch
import java.time.LocalDate

/**
 * Port of `TasksScreen.swift`: who does what: my tasks by due date, what others committed to,
 * what is done. Subtasks indent under their parent; long press for indent, export, share and
 * select. [onOpenDay] opens one day's tasks (`DayTasksScreen`, pushed by the shell). Each task
 * shows Omi's status (`AgentTaskStatus`, from AgentStore's workstreams). iOS also syncs Apple
 * Reminders on refresh; Reminders is iOS only, so Android's refresh reloads the tasks alone.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TasksScreen(
    onHandOver: (ActionItem) -> Unit,
    onOpenConversation: (String) -> Unit,
    modifier: Modifier = Modifier,
    onOpenDay: (LocalDate) -> Unit = {},
) {
    val store = LocalTasksStore.current
    val conversations = LocalConversationsStore.current
    val capabilities = LocalCapabilitiesStore.current
    val agent = LocalAgentStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    val context = LocalContext.current
    val shareSheet = rememberShareSheet()
    var showsCompleted by rememberSaveable { mutableStateOf(false) }
    var query by rememberSaveable { mutableStateOf("") }
    var refreshing by remember { mutableStateOf(false) }
    var showsNewTask by remember { mutableStateOf(DebugLaunch.flag("omiNewTask")) }
    var editing by remember { mutableStateOf<ActionItem?>(null) }
    /** Tasks picked for a bulk action; null outside selection mode. */
    var selection by remember { mutableStateOf<Set<String>?>(null) }
    var showsGoals by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) { if (store.phase == TasksStore.Phase.Idle) store.load() }
    LaunchedEffect(Unit) { if (conversations.phase == ConversationsStore.Phase.Idle) conversations.load() }
    LaunchedEffect(Unit) { capabilities.load() }
    // `-omiTasksDay YES` opens today's page (scripted screenshots).
    LaunchedEffect(Unit) { if (DebugLaunch.flag("omiTasksDay")) onOpenDay(LocalDate.now()) }
    // Where each open task came from: its conversation's words, loaded once per conversation.
    LaunchedEffect(store.tasks.size) { conversations.loadSources(store.tasks.filter { !it.isCompleted }) }
    LaunchedEffect(store.tasks.size) { agent.loadWorkstreams(store.tasks) }

    fun share(ids: List<String>) {
        scope.launch { store.shareLink(ids)?.let { shareSheet(ShareRequest(listOf(it))) } }
    }

    /** In selection mode a tap picks the row (with its subtasks); otherwise it edits the task. */
    fun tap(task: ActionItem) {
        val chosen = selection
        if (chosen == null) {
            editing = task
            return
        }
        haptics.selection()
        val group = listOf(task.id) + store.descendants(task.id)
        selection = if (task.id in chosen) chosen - group.toSet() else chosen + group
    }

    @Composable
    fun Row(task: ActionItem, indent: Int) {
        val source = conversations.source(task)
        val status = AgentTaskStatus.of(task, agent)
        val picked = selection
        val menu = taskContextMenu(task, onEdit = { editing = task }, onShare = ::share, onSelect = { selection = it })
        ContextMenuBox(
            sections = { if (selection == null) menu else emptyList() },
            modifier = Modifier.padding(start = DS.Spacing.gutter + DS.Spacing.xl * indent, end = DS.Spacing.gutter, top = DS.Spacing.xs, bottom = DS.Spacing.xs),
            onTap = { tap(task) },
        ) {
            HStack(spacing = DS.Spacing.sm) {
                if (picked != null) {
                    SFImage(
                        if (task.id in picked) "checkmark.circle.fill" else "circle",
                        size = 20.sp,
                        tint = if (task.id in picked) DS.Palette.agent else DS.Palette.inkTertiary,
                    )
                }
                if (indent > 0) Box(Modifier.size(2.dp, 20.dp).background(DS.Palette.hairline, CircleShape))
                TaskRow(
                    task,
                    Modifier.weight(1f),
                    source = source?.displayTitle(context),
                    sourceEmoji = source?.emoji,
                    quote = conversations.quote(task),
                    onOpenSource = if (picked == null) source?.let { conversation -> { onOpenConversation(conversation.id) } } else null,
                    // While selecting, the row does not react on its own (`.allowsHitTesting(selection == nil)`).
                    agentStatus = status,
                    onToggle = { if (picked == null) scope.launch { store.setCompleted(task.id, !task.isCompleted) } else tap(task) },
                    // Omi's work opens where it has some; a new hand-over only for what Omi can do digitally.
                    onHandOver = if (picked == null && (status != null || TakeOverEligibility.canTakeOver(task))) ({ onHandOver(task) }) else null,
                )
            }
        }
    }

    Column(modifier.fillMaxSize()) {
        // The search row stays put above the list, at the same place as on Memories.
        HStack(Modifier.padding(horizontal = DS.Spacing.gutter).padding(bottom = DS.Spacing.xs), spacing = DS.Spacing.sm) {
            OmiSearchField(L("nativeSearchTasks"), query, { query = it }, L("cancel"), Modifier.weight(1f))
            TasksHeaderMenu(onSelect = { selection = emptySet() }, onGoals = { showsGoals = true })
            CircleIconButton("plus", contentDescription = L("addTask")) { showsNewTask = true }
        }
        Box(Modifier.weight(1f)) {
            PullToRefreshBox(
                isRefreshing = refreshing,
                onRefresh = {
                    scope.launch {
                        refreshing = true
                        store.load()
                        refreshing = false
                    }
                },
                modifier = Modifier.fillMaxSize(),
            ) {
                if (store.phase == TasksStore.Phase.Loaded && store.tasks.isEmpty()) {
                    OmiEmptyState(
                        L("nativeNoTasks"), "checklist", Modifier.padding(top = 72.dp).align(Alignment.TopCenter),
                        message = L("nativeNoTasksBody"), actionTitle = L("addTask"),
                    ) { showsNewTask = true }
                }
                LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(top = DS.Spacing.xs, bottom = DS.Spacing.section + 72.dp)) {
                    if (store.phase == TasksStore.Phase.Loading && store.tasks.isEmpty()) {
                        items(5) { SkeletonBlock(Modifier.padding(horizontal = DS.Spacing.gutter, vertical = DS.Spacing.xs), height = 52.dp) }
                    }
                    store.sections(query).forEach { (bucket, tasks) ->
                        val indents = store.displayIndents(tasks)
                        if (bucket == TasksStore.Bucket.Completed) {
                            item(key = "done") {
                                val rotation by animateFloatAsState(if (showsCompleted) 90f else 0f, DS.Motion.standard(), label = "done")
                                HStack(
                                    Modifier
                                        .fillMaxWidth()
                                        .plainButton { showsCompleted = !showsCompleted }
                                        .padding(horizontal = DS.Spacing.gutter, vertical = DS.Spacing.md),
                                ) {
                                    Text(L("nativeDoneCount", "${tasks.size}"), style = DS.Typography.sectionLabel, color = DS.Palette.inkSecondary)
                                    Spacer(Modifier.weight(1f))
                                    SFImage("chevron.right", Modifier.rotate(rotation), size = 13.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkSecondary)
                                }
                            }
                            if (showsCompleted) items(tasks, key = { it.id }) { Row(it, indents[it.id] ?: 0) }
                        } else {
                            item(key = "header.$bucket") {
                                // "Today" also opens the day's page (due and added that day, as Flutter's one-day tasks page).
                                val label = Modifier.padding(start = DS.Spacing.gutter, end = DS.Spacing.gutter, top = DS.Spacing.md, bottom = DS.Spacing.xs)
                                Text(
                                    title(bucket),
                                    style = DS.Typography.sectionLabel,
                                    color = DS.Palette.inkSecondary,
                                    modifier = if (bucket == TasksStore.Bucket.Today) label.plainButton { onOpenDay(LocalDate.now()) } else label,
                                )
                            }
                            items(tasks, key = { it.id }) { Row(it, indents[it.id] ?: 0) }
                            if (bucket == TasksStore.Bucket.WaitingOnOthers) {
                                item(key = "footer.$bucket") {
                                    Text(
                                        L("nativeWaitingOnOthersFooter"),
                                        style = DS.Typography.caption,
                                        color = DS.Palette.inkSecondary,
                                        modifier = Modifier.padding(horizontal = DS.Spacing.gutter, vertical = DS.Spacing.xs),
                                    )
                                }
                            }
                        }
                    }
                }
            }
            Column(
                Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(bottom = DS.Spacing.sm),
                verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
            ) {
                TaskToasts()
                AnimatedVisibility(
                    selection != null,
                    enter = slideInVertically(DS.Motion.standard()) { it } + fadeIn(DS.Motion.standard()),
                    exit = slideOutVertically(DS.Motion.standard()) { it } + fadeOut(DS.Motion.standard()),
                ) {
                    TaskSelectionBar(selection, { selection = it }, onShare = ::share)
                }
            }
        }
    }

    if (showsNewTask) NewTaskSheet(onDismiss = { showsNewTask = false }, onShare = ::share)
    editing?.let { task ->
        OmiSheet(onDismiss = { editing = null }, detents = setOf(Detent.Medium, Detent.Large)) {
            TaskFormSheet(task, onDismiss = { editing = null }, onOpenConversation = onOpenConversation, onHandOver = onHandOver, onShare = ::share)
        }
    }
    if (showsGoals) {
        OmiSheet(onDismiss = { showsGoals = false }) {
            GoalsScreen()
        }
    }
    store.incomingShare?.let { share -> SharedTasksSheet(share, onDismiss = { store.dismissShare() }) }
}

@Composable
private fun title(bucket: TasksStore.Bucket): String = when (bucket) {
    TasksStore.Bucket.Overdue -> L("nativeOverdue")
    TasksStore.Bucket.Today -> L("today")
    TasksStore.Bucket.Upcoming -> L("nativeUpcoming")
    TasksStore.Bucket.Someday -> L("nativeSomeday")
    TasksStore.Bucket.WaitingOnOthers -> L("nativeWaitingOnOthers")
    TasksStore.Bucket.Completed -> L("nativeDone")
}
