package com.friend.ios.features.tasks

import androidx.compose.runtime.Composable
import com.friend.ios.design.Detent
import com.friend.ios.design.OmiSheet

/**
 * Port of `NewTaskSheet.swift`: "Add task" from outside the task list (the Home Screen quick
 * action): the same form as the list's add button. `TaskDetailSheet` lives in `TaskFormSheet.kt`.
 */
@Composable
fun NewTaskSheet(onDismiss: () -> Unit, onShare: ((List<String>) -> Unit)? = null) {
    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium)) {
        TaskFormSheet(null, onDismiss = onDismiss, onShare = onShare)
    }
}
