package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem
import kotlinx.coroutines.CancellationException
import java.util.UUID

/** Port of `TasksStore+Sharing.swift`: what a task action reports back, shown once as a toast. */
class TaskNotice(val kind: Kind) {
    sealed interface Kind {
        /** [count] tasks sent to [app]; [failed] did not make it. */
        data class Exported(val app: String, val count: Int, val failed: Int) : Kind
        /** Everything chosen was exported before. */
        data object AlreadyExported : Kind
        data class ExportFailed(val app: String) : Kind
        data class SharedAdded(val count: Int) : Kind
        data object ShareExpired : Kind
        data object ShareFailed : Kind
        data object ShareLinkFailed : Kind
    }

    val id: String = UUID.randomUUID().toString()

    override fun equals(other: Any?): Boolean = other is TaskNotice && other.id == id

    override fun hashCode(): Int = id.hashCode()
}

// Export to the user's task app (Flutter `ActionItemExportService`), share links and accepting
// shared tasks (`AcceptSharedTasksSheet`).

/** `TasksStore.appleReminders`: kept for the backend key; Android has no Reminders exporter. */
const val TasksStoreAppleReminders = "apple_reminders"

/**
 * Sends each task to [app] (a backend key: todoist, asana, clickup, google_tasks) and marks it
 * exported. Tasks exported before are skipped.
 */
suspend fun TasksStore.export(ids: List<String>, app: String): TaskNotice.Kind {
    val chosen = tasks.filter { it.id in ids }
    val pending = chosen.filter { !it.isExported }
    if (pending.isEmpty()) {
        val kind = if (chosen.isEmpty()) TaskNotice.Kind.ExportFailed(app) else TaskNotice.Kind.AlreadyExported
        notice = TaskNotice(kind)
        return kind
    }
    var exported = 0
    for (task in pending) if (exportOne(task, app)) exported += 1
    val kind = if (exported == 0) TaskNotice.Kind.ExportFailed(app) else TaskNotice.Kind.Exported(app, exported, pending.size - exported)
    notice = TaskNotice(kind)
    return kind
}

/** "Export all open": my open tasks that were not exported yet. */
suspend fun TasksStore.exportAllOpen(app: String): TaskNotice.Kind =
    export(tasks.filter { !it.isCompleted && it.owner != ActionItem.Owner.Other }.map { it.id }, app)

/** The public link for these tasks, or null (and a notice) when the backend refuses. */
suspend fun TasksStore.shareLink(ids: List<String>): String? = try {
    api.shareActionItems(ids)
} catch (e: Exception) {
    if (e is CancellationException) throw e
    notice = TaskNotice(TaskNotice.Kind.ShareLinkFailed)
    null
}

/** A shared link was opened: loads what it holds for the accept sheet. */
suspend fun TasksStore.openShare(token: String) {
    try {
        val share = api.sharedActionItems(token)
        if (share.tasks.isEmpty()) notice = TaskNotice(TaskNotice.Kind.ShareExpired) else incomingShare = share
    } catch (e: Exception) {
        if (e is CancellationException) throw e
        notice = TaskNotice(TaskNotice.Kind.ShareExpired)
    }
}

/** Adds the shared tasks to this account; returns whether it worked. */
suspend fun TasksStore.acceptShare(): Boolean {
    val share = incomingShare ?: return false
    return try {
        val count = api.acceptSharedActionItems(share.token)
        incomingShare = null
        notice = TaskNotice(TaskNotice.Kind.SharedAdded(count))
        load()
        true
    } catch (e: Exception) {
        if (e is CancellationException) throw e
        notice = TaskNotice(TaskNotice.Kind.ShareFailed)
        false
    }
}

fun TasksStore.dismissShare() {
    incomingShare = null
}

fun TasksStore.clearNotice(shown: TaskNotice) {
    if (notice == shown) notice = null
}

private suspend fun TasksStore.exportOne(task: ActionItem, app: String): Boolean = try {
    // Apple Reminders has no Android exporter (`reminderExporter`): it never succeeds here.
    if (app == TasksStoreAppleReminders) throw IllegalStateException("no reminders exporter")
    api.createIntegrationTask(app, task.description, task.dueAt)
    api.markActionItemExported(task.id, app, null)
    tasks = tasks.map { if (it.id == task.id) it.copy(exportPlatform = app, appleReminderID = null) else it }
    true
} catch (e: Exception) {
    if (e is CancellationException) throw e
    lastError = e.toString()
    false
}
