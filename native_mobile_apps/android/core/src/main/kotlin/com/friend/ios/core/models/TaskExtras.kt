package com.friend.ios.core.models

import java.time.Instant

/**
 * Port of `TaskExtras.swift` (`SharedTasks`, `TaskLayout`). `TaskSyncUpdate` and
 * `PendingTaskSync` belong to Apple Reminders sync, which has no Android counterpart.
 */

/** Tasks someone shared by link (`GET v1/action-items/shared/{token}`), before they are accepted. */
data class SharedTasks(val token: String, val senderName: String?, val tasks: List<Item>) {
    data class Item(val description: String, val dueAt: Instant?)

    val id: String get() = token
}

/** A row's place in the Tasks list (`PATCH v1/action-items/batch`); null fields stay as they are. */
data class TaskLayout(val id: String, val sortOrder: Int? = null, val indentLevel: Int? = null)
