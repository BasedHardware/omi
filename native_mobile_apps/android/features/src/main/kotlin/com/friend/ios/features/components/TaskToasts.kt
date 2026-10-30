package com.friend.ios.features.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.settings.capabilityName
import com.friend.ios.service.LocalGoalsStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.TaskNotice
import com.friend.ios.service.stores.TasksStoreAppleReminders
import com.friend.ios.service.stores.clearNotice
import com.friend.ios.service.stores.undoDelete
import kotlinx.coroutines.delay

// Port of `TaskToasts.swift`.

/**
 * "Task deleted · Undo" while a task delete waits out its undo window, then any short outcome
 * (exported, shared tasks added, ...) for a few seconds.
 */
@Composable
fun TaskToasts(modifier: Modifier = Modifier) {
    val tasks = LocalTasksStore.current
    val haptics = rememberHaptics()
    val pending = tasks.pendingDeletion
    val notice = tasks.notice
    val shown: Any? = pending ?: notice
    AnimatedContent(
        targetState = shown,
        modifier = modifier,
        transitionSpec = {
            (slideInVertically(DS.Motion.standard()) { it } + fadeIn(DS.Motion.standard())) togetherWith
                (slideOutVertically(DS.Motion.standard()) { it } + fadeOut(DS.Motion.standard()))
        },
        contentKey = { state ->
            when (state) {
                is com.friend.ios.service.stores.PendingTaskDeletion -> state.ids
                is TaskNotice -> state.id
                else -> null
            }
        },
        label = "taskToasts",
    ) { state ->
        when (state) {
            is com.friend.ios.service.stores.PendingTaskDeletion -> OmiToast(
                if (state.ids.size == 1) L("actionItemDeleted") else L("nativeTasksDeleted", "${state.ids.size}"),
                "trash",
                actionTitle = L("undo"),
            ) {
                haptics.tap()
                tasks.undoDelete()
            }
            is TaskNotice -> {
                OmiToast(TaskToastsText.text(state.kind), TaskToastsText.symbol(state.kind))
                LaunchedEffect(state.id) {
                    delay(3_000)
                    tasks.clearNotice(state)
                }
            }
            else -> Box(Modifier)
        }
    }
}

/** `TaskToasts.text`, `.symbol`, `.appName`. */
object TaskToastsText {
    @Composable
    fun text(kind: TaskNotice.Kind): String = when (kind) {
        is TaskNotice.Kind.Exported -> if (kind.failed == 0) L("nativeExportedCount", appName(kind.app), "${kind.count}")
        else L("nativeExportedSomeFailed", appName(kind.app), "${kind.count}", "${kind.failed}")
        TaskNotice.Kind.AlreadyExported -> L("nativeAlreadyExported")
        is TaskNotice.Kind.ExportFailed -> L("nativeExportFailed", appName(kind.app))
        is TaskNotice.Kind.SharedAdded -> L("nativeSharedTasksAdded", "${kind.count}")
        TaskNotice.Kind.ShareExpired -> L("sharedTasksLinkExpired")
        TaskNotice.Kind.ShareFailed -> L("sharedTasksAcceptFailed")
        TaskNotice.Kind.ShareLinkFailed -> L("nativeShareLinkFailed")
    }

    fun symbol(kind: TaskNotice.Kind): String = when (kind) {
        is TaskNotice.Kind.Exported, TaskNotice.Kind.AlreadyExported -> "square.and.arrow.up"
        is TaskNotice.Kind.SharedAdded -> "checkmark.circle"
        else -> "exclamationmark.circle"
    }

    /** Display name of a task app by backend key. */
    @Composable
    fun appName(key: String): String = if (key == TasksStoreAppleReminders) L("nativeRemindersName") else capabilityName(key)
}

/** "Goal deleted · Undo" while a goal delete waits out its undo window. */
@Composable
fun GoalUndoToast(modifier: Modifier = Modifier) {
    val goals = LocalGoalsStore.current
    val haptics = rememberHaptics()
    AnimatedVisibility(
        visible = goals.pendingDeletion != null,
        modifier = modifier,
        enter = slideInVertically(DS.Motion.standard()) { it } + fadeIn(DS.Motion.standard()),
        exit = slideOutVertically(DS.Motion.standard()) { it } + fadeOut(DS.Motion.standard()),
    ) {
        OmiToast(L("goalDeleted"), "trash", actionTitle = L("undo")) {
            haptics.tap()
            goals.undoDelete()
        }
    }
}
