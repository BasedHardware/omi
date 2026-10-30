package com.friend.ios.features.agent

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.DeepLink
import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Goal
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiNavBar
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.GoalProgressBar
import com.friend.ios.features.components.GoalRow
import com.friend.ios.features.components.GoalsScreen
import com.friend.ios.service.LocalGoalsStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.TasksStore
import kotlinx.coroutines.launch

/*
 * Port of `ChatBlockTaskCards.swift`: the task the answer created or named, and the goal it moved.
 *
 * iOS opens a task with `openURL(DeepLink.task…)`; the Android port hands the same `omi://` link to
 * the system (`LocalUriHandler`), as `TaskChangeCard` already does.
 */

// Task

/**
 * A task the answer created or named, drawn live from the task list: tick it off here, or open it.
 * The tasks API has no read-by-id, so the card resolves against the loaded list and says so when
 * the row is not in it (Flutter `TaskCardBlock`).
 */
@Composable
fun TaskBlockCard(taskID: String, modifier: Modifier = Modifier) {
    val tasks = LocalTasksStore.current
    val task = tasks.tasks.firstOrNull { it.id == taskID }
    when {
        task != null -> LoadedTask(task, modifier)
        tasks.phase != TasksStore.Phase.Loaded -> {
            ChatBlockNotice("checklist", L("chatBlockTask"), L("loading"), isLoading = true, modifier = modifier)
            LaunchedEffect(taskID) { tasks.load() }
        }

        else -> ChatBlockNotice("checklist", L("chatBlockTask"), L("chatBlockUnavailable"), modifier = modifier)
    }
}

/** A task the list has: its box ticks it off, the card itself opens it. */
@Composable
private fun LoadedTask(task: ActionItem, modifier: Modifier) {
    val tasks = LocalTasksStore.current
    val uri = LocalUriHandler.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    var isToggling by remember(task.id) { mutableStateOf(false) }
    ChatBlockCard(modifier, onTap = { uri.openUri(DeepLink.Task(task.id).url) }) {
        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs + 2.dp)) {
            ChatBlockEyebrow("checklist", L("chatBlockTask"))
            HStack(spacing = DS.Spacing.sm) {
                SFImage(
                    if (task.isCompleted) "checkmark.circle.fill" else "circle",
                    size = 20.sp,
                    tint = if (task.isCompleted) DS.Palette.success else DS.Palette.inkSecondary,
                    contentDescription = if (task.isCompleted) L("markIncomplete") else L("markComplete"),
                    modifier = Modifier
                        .size(32.dp)
                        .plainButton(enabled = !isToggling) {
                            isToggling = true
                            haptics.tap()
                            scope.launch {
                                tasks.setCompleted(task.id, !task.isCompleted)
                                isToggling = false
                            }
                        },
                )
                Text(
                    task.description,
                    style = DS.Typography.callout,
                    color = if (task.isCompleted) DS.Palette.inkSecondary else DS.Palette.ink,
                    textDecoration = if (task.isCompleted) TextDecoration.LineThrough else null,
                )
            }
        }
    }
}

// Goal

/**
 * The goal the answer moved: its current and target, and the way to the goals screen.
 *
 * One difference from iOS, where the card also opens the goal's form (`GoalFormSheet`): that form
 * is not ported yet (see `GoalViews.kt`), so the card is not tappable and only the action is drawn.
 * Nothing else on the card would do anything.
 */
@Composable
fun GoalBlockCard(goalID: String, summary: String, modifier: Modifier = Modifier) {
    val goals = LocalGoalsStore.current
    var showsGoals by remember { mutableStateOf(false) }
    val goal = goals.goals.firstOrNull { it.id == goalID }
    ChatBlockCard(modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
            ChatBlockEyebrow("flag", L("chatBlockGoal"))
            Text(
                summary.ifEmpty { L("chatBlockUnavailable") },
                style = DS.Typography.callout,
                color = if (summary.isEmpty()) DS.Palette.inkSecondary else DS.Palette.ink,
            )
            if (goal != null) {
                GoalProgressBar(goal.progress, GoalRow.tint(goal.progress))
                Text(progressLabel(goal), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
            }
            ChatBlockAction(L("chatBlockOpenInGoals")) { showsGoals = true }
        }
    }
    if (showsGoals) {
        OmiSheet(onDismiss = { showsGoals = false }) {
            GoalsScreen()
        }
    }
}

/** "12 of 20": the goal's own numbers, as its row writes them. */
@Composable
private fun progressLabel(goal: Goal): String = L("nativeGoalProgress", GoalRow.number(goal.current), GoalRow.number(goal.target))
