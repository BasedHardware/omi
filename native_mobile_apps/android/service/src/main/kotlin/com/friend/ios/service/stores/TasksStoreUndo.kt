package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Port of `TasksStore+Undo.swift`: rows a delete took away, with where they were, until the undo window closes. */
data class PendingTaskDeletion(val ids: List<String>, internal val removed: List<Removed>) {
    data class Removed(val index: Int, val task: ActionItem)
}

// Delete with Undo (Flutter `task_delete_undo.dart`), bulk actions and Clear completed.

/**
 * Hides the tasks now; the backend delete runs after the undo window unless [undoDelete] comes
 * first. A second delete sends the first one right away.
 */
fun TasksStore.deleteWithUndo(ids: List<String>) {
    val hide = ids.toSet()
    val removed = tasks.withIndex().filter { it.value.id in hide }.map { PendingTaskDeletion.Removed(it.index, it.value) }
    if (removed.isEmpty()) return
    pendingDeletion?.let { earlier ->
        deletionJob?.cancel()
        pendingDeletion = null
        scope.launch { send(earlier) }
    }
    tasks = tasks.filter { it.id !in hide }
    pendingDeletion = PendingTaskDeletion(removed.map { it.task.id }, removed)
    deletionJob = scope.launch {
        delay(undoWindowMillis)
        commitDeletion()
    }
}

/** Puts the tasks back where they were; nothing reaches the backend. */
fun TasksStore.undoDelete() {
    val pending = pendingDeletion ?: return
    deletionJob?.cancel()
    deletionJob = null
    pendingDeletion = null
    restore(pending.removed)
}

/** Sends the waiting delete now. Tasks the backend refuses to delete come back. */
suspend fun TasksStore.commitDeletion() {
    val pending = pendingDeletion ?: return
    pendingDeletion = null
    val job = deletionJob
    deletionJob = null
    // Not the running timer itself: cancelling it would stop this send.
    if (job != null && job != kotlin.coroutines.coroutineContext[kotlinx.coroutines.Job]) job.cancel()
    send(pending)
}

/** Every finished task, deleted with Undo. */
fun TasksStore.clearCompleted() {
    deleteWithUndo(tasks.filter { it.isCompleted }.map { it.id })
}

/** Marks many tasks done (or open) at once; each rolls back on its own if the backend refuses. */
suspend fun TasksStore.setCompleted(ids: List<String>, completed: Boolean) {
    for (id in ids) {
        if (tasks.any { it.id == id && it.isCompleted != completed }) setCompleted(id, completed)
    }
}

internal suspend fun TasksStore.send(pending: PendingTaskDeletion) {
    lastError = null
    val deleted: Set<String> = try {
        if (pending.ids.size == 1) {
            api.deleteActionItem(pending.ids[0])
            pending.ids.toSet()
        } else {
            api.deleteActionItems(pending.ids).toSet()
        }
    } catch (e: Exception) {
        if (e is CancellationException) throw e
        lastError = e.toString()
        emptySet()
    }
    val failed = pending.removed.filter { it.task.id !in deleted }
    if (failed.isNotEmpty() && lastError == null) lastError = "not deleted: ${failed.map { it.task.id }}"
    restore(failed)
}

private fun TasksStore.restore(removed: List<PendingTaskDeletion.Removed>) {
    val next = tasks.toMutableList()
    for (entry in removed) {
        if (next.none { it.id == entry.task.id }) next.add(minOf(entry.index, next.size), entry.task)
    }
    tasks = next
}
