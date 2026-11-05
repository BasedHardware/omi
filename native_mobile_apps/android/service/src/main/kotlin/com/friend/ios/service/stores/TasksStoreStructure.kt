package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.TaskLayout
import kotlinx.coroutines.CancellationException
import java.time.Instant
import java.time.LocalDate

// Port of `TasksStore+Structure.swift`: subtasks (indent / outdent) and the one-day view. Flutter
// keeps a flat list with an `indent_level` per row: a row belongs to the nearest row above it with a
// smaller level.

const val TasksStoreMaxIndent = 3

/**
 * One level deeper is allowed only under a row above it in the same section (Flutter
 * `_showTaskMenu`: `index <= 0 ? 0 : min(previous.indentLevel + 1, 3)`).
 */
fun TasksStore.canIndent(id: String, now: Instant = Instant.now()): Boolean {
    val (rows, index) = placement(id, now) ?: return false
    if (index <= 0) return false
    return rows[index].indentLevel < minOf(rows[index - 1].indentLevel + 1, TasksStoreMaxIndent)
}

fun TasksStore.canOutdent(id: String): Boolean = (tasks.firstOrNull { it.id == id }?.indentLevel ?: 0) > 0

suspend fun TasksStore.indent(id: String, now: Instant = Instant.now()) {
    if (!canIndent(id, now)) return
    val task = tasks.firstOrNull { it.id == id } ?: return
    setIndent(id, task.indentLevel + 1, now)
}

suspend fun TasksStore.outdent(id: String, now: Instant = Instant.now()) {
    val task = tasks.firstOrNull { it.id == id } ?: return
    if (task.indentLevel <= 0) return
    setIndent(id, task.indentLevel - 1, now)
}

/**
 * Display depth per row: never more than one below the row above (the first row is a parent), so a
 * subtask whose parent sits in another section or is filtered out still reads correctly.
 */
fun TasksStore.displayIndents(rows: List<ActionItem>): Map<String, Int> {
    val result = HashMap<String, Int>()
    var previous = -1
    for (row in rows) {
        val level = minOf(row.indentLevel, previous + 1, TasksStoreMaxIndent)
        result[row.id] = maxOf(level, 0)
        previous = maxOf(level, 0)
    }
    return result
}

/** The rows under [id] in its section (each following row deeper than it), for selecting a parent with its subtasks. */
fun TasksStore.descendants(id: String, now: Instant = Instant.now()): List<String> {
    val (rows, index) = placement(id, now) ?: return emptyList()
    val level = rows[index].indentLevel
    return rows.drop(index + 1).takeWhile { it.indentLevel > level }.map { it.id }
}

/** A day's tasks: due that day, and the others added that day. */
data class DayTasks(val due: List<ActionItem>, val added: List<ActionItem>)

/**
 * A day's tasks: due that day, and the others added that day (Flutter `DayTasksPage` lists what was
 * created on the day; due dates are what the Tasks tab groups by, so both show).
 */
fun TasksStore.day(date: LocalDate): DayTasks {
    fun sameDay(instant: Instant?) = instant?.atZone(zone)?.toLocalDate() == date
    val due = tasks.filter { sameDay(it.dueAt) }
    val dueIDs = due.map { it.id }.toSet()
    val added = tasks.filter { it.id !in dueIDs && sameDay(it.createdAt) }
    val order = compareBy<ActionItem>({ if (it.isCompleted) 1 else 0 }, { it.dueAt ?: it.createdAt ?: Instant.MIN })
    return DayTasks(due.sortedWith(order), added.sortedWith(order))
}

/** The section's rows in display order and the row's index in it. */
private fun TasksStore.placement(id: String, now: Instant): Pair<List<ActionItem>, Int>? {
    val task = tasks.firstOrNull { it.id == id } ?: return null
    val target = bucket(task, now)
    val rows = sections(now = now).firstOrNull { it.first == target }?.second ?: return null
    val index = rows.indexOfFirst { it.id == id }
    if (index < 0) return null
    return rows to index
}

/**
 * Optimistic: the new level and, so the parent stays above it, the section's current order as
 * `sort_order` (Flutter numbers rows 1000, 2000, ...). Rolls back if the backend refuses.
 */
private suspend fun TasksStore.setIndent(id: String, level: Int, now: Instant) {
    val (rows, _) = placement(id, now) ?: return
    val before = tasks
    val entries = mutableListOf<TaskLayout>()
    var next = tasks
    rows.forEachIndexed { offset, row ->
        val order = (offset + 1) * 1000
        val newLevel = if (row.id == id) level else null
        if (row.sortOrder == order && newLevel == null) return@forEachIndexed
        entries += TaskLayout(row.id, sortOrder = if (row.sortOrder == order) null else order, indentLevel = newLevel)
        next = next.map { if (it.id == row.id) it.copy(sortOrder = order, indentLevel = newLevel ?: it.indentLevel) else it }
    }
    tasks = next
    lastError = null
    try {
        api.setTaskLayout(entries)
    } catch (e: Exception) {
        if (e is CancellationException) throw e
        tasks = before
        lastError = e.toString()
    }
}
