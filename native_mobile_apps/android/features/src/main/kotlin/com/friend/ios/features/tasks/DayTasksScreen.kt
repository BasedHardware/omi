package com.friend.ios.features.tasks

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.friend.ios.core.models.ActionItem
import com.friend.ios.design.CircleIconButton
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.SFImage
import androidx.compose.foundation.layout.size
import androidx.compose.ui.unit.sp
import com.friend.ios.design.OmiEmptyState
import com.friend.ios.design.OmiPushedScreen
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.Formatting
import com.friend.ios.features.components.TaskRow
import com.friend.ios.features.components.TaskToasts
import com.friend.ios.features.components.displayTitle
import com.friend.ios.features.components.relativeDay
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.ConversationsStore
import com.friend.ios.service.stores.day
import com.friend.ios.service.stores.deleteWithUndo
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

/**
 * Port of `DayTasksScreen.swift`: one day's tasks (Flutter `day_tasks_page.dart`): due that day and
 * added that day, with the previous / next day in the toolbar (never past today, as in Flutter).
 * The list's swipe to delete is the row's long-press menu here (no row swipes on Android lists).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DayTasksScreen(date: LocalDate, onBack: () -> Unit, onOpenConversation: (String) -> Unit) {
    val store = LocalTasksStore.current
    val conversations = LocalConversationsStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    val zone = ZoneId.systemDefault()
    var day by rememberSaveable { mutableStateOf(date) }
    var editing by remember { mutableStateOf<ActionItem?>(null) }
    var refreshing by remember { mutableStateOf(false) }
    val tasks = store.day(day)
    val today = LocalDate.now(zone)

    fun move(days: Long) {
        haptics.selection()
        day = day.plusDays(days)
    }

    // The source line needs the conversations (this page can open before Home loaded them).
    LaunchedEffect(tasks.due.map { it.id } + tasks.added.map { it.id }) {
        if (conversations.phase == ConversationsStore.Phase.Idle) conversations.load()
        conversations.loadSources(tasks.due + tasks.added)
    }

    OmiPushedScreen(
        Formatting.relativeDay(day.atStartOfDay(zone).toInstant()),
        onBack,
        trailing = {
            CircleIconButton("chevron.left", contentDescription = L("previousDay")) { move(-1) }
            if (day == today) DisabledIcon("chevron.right") else CircleIconButton("chevron.right", contentDescription = L("nextDay")) { move(1) }
        },
    ) {
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
                if (tasks.due.isEmpty() && tasks.added.isEmpty()) {
                    val formatted = DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).format(day)
                    OmiEmptyState(L("noTasksOnDate", formatted), "checklist", Modifier.align(Alignment.Center))
                }
                LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(top = DS.Spacing.xs, bottom = 96.dp)) {
                    if (tasks.due.isNotEmpty()) {
                        item(key = "due") { Label(L("nativeDueThatDay")) }
                        items(tasks.due, key = { "due.${it.id}" }) { Row(it, onTap = { editing = it }, onOpenConversation = onOpenConversation) }
                    }
                    if (tasks.added.isNotEmpty()) {
                        item(key = "added") { Label(L("nativeAddedThatDay")) }
                        items(tasks.added, key = { "added.${it.id}" }) { Row(it, onTap = { editing = it }, onOpenConversation = onOpenConversation) }
                    }
                }
            }
            TaskToasts(Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(bottom = DS.Spacing.sm))
        }
    }
    editing?.let { task ->
        TaskDetailSheet(task, onDismiss = { editing = null }, onOpenConversation = onOpenConversation)
    }
}

/** A toolbar glyph while it is disabled. */
@Composable
private fun DisabledIcon(systemImage: String) {
    Box(Modifier.size(DS.Size.headerButton), contentAlignment = Alignment.Center) {
        SFImage(systemImage, size = 19.sp, tint = DS.Palette.inkDisabled)
    }
}

@Composable
private fun Label(title: String) {
    Text(
        title,
        style = DS.Typography.sectionLabel,
        color = DS.Palette.inkSecondary,
        modifier = Modifier.padding(start = DS.Spacing.gutter, end = DS.Spacing.gutter, top = DS.Spacing.md, bottom = DS.Spacing.xs),
    )
}

@Composable
private fun Row(task: ActionItem, onTap: () -> Unit, onOpenConversation: (String) -> Unit) {
    val store = LocalTasksStore.current
    val conversations = LocalConversationsStore.current
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val source = conversations.source(task)
    val delete = L("delete")
    ContextMenuBox(
        sections = { listOf(MenuSection(items = listOf(MenuItem(delete, "trash", destructive = true) { store.deleteWithUndo(listOf(task.id)) }))) },
        modifier = Modifier.padding(horizontal = DS.Spacing.gutter, vertical = DS.Spacing.xs),
        onTap = onTap,
    ) {
        TaskRow(
            task,
            source = source?.displayTitle(context),
            sourceEmoji = source?.emoji,
            quote = conversations.quote(task),
            onOpenSource = source?.let { conversation -> { onOpenConversation(conversation.id) } },
            onToggle = { scope.launch { store.setCompleted(task.id, !task.isCompleted) } },
        )
    }
}
