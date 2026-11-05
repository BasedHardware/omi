package com.friend.ios.features.today

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.OmiToast
import com.friend.ios.service.LocalTasksStore
import kotlinx.coroutines.delay

/**
 * The task card's right swipe put these tasks off until tomorrow; "Moved to Later" with Undo shows
 * for a few seconds at the bottom (docs/HOME_TASK_CARD.md).
 */
class TaskLaterUndo {
    /** The tasks the last swipe snoozed, while Undo is offered. */
    var pending: List<String>? by mutableStateOf(null)
        private set
    /** Bumps on every swipe, so a second one restarts the timer. */
    internal var generation by mutableStateOf(0)
        private set

    fun show(ids: List<String>) {
        pending = ids
        generation += 1
    }

    fun clear() {
        pending = null
    }

    companion object {
        /** How long Undo stays. */
        const val VISIBLE_MILLIS = 4_000L
    }
}

/** "Moved to Later · Undo" over the bottom of Home, above the Omi bar. */
@Composable
fun TaskLaterUndoToast(undo: TaskLaterUndo, modifier: Modifier = Modifier) {
    val tasks = LocalTasksStore.current
    val haptics = rememberHaptics()
    LaunchedEffect(undo.generation) {
        if (undo.pending == null) return@LaunchedEffect
        delay(TaskLaterUndo.VISIBLE_MILLIS)
        undo.clear()
    }
    AnimatedVisibility(
        visible = undo.pending != null,
        modifier = modifier,
        enter = slideInVertically(DS.Motion.standard()) { it } + fadeIn(DS.Motion.standard()),
        exit = slideOutVertically(DS.Motion.standard()) { it } + fadeOut(DS.Motion.standard()),
    ) {
        OmiToast(L("nativeMovedToLater"), "clock", actionTitle = L("undo")) {
            haptics.tap()
            undo.pending?.let { tasks.unsnooze(it) }
            undo.clear()
        }
    }
}
