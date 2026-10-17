package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.Goal
import com.friend.ios.network.APIClientProtocol
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Port of `GoalsStore.swift`: numeric goals (Flutter `GoalsProvider` + `goals_widget.dart`):
 * title, current of target. Delete is immediate with Undo, like tasks.
 */
class GoalsStore(
    private val api: APIClientProtocol,
    private val scope: CoroutineScope,
    private val undoWindowMillis: Long = 5_000,
) {
    sealed interface Phase {
        data object Idle : Phase
        data object Loading : Phase
        data object Loaded : Phase
        data class Failed(val message: String) : Phase
    }

    var phase: Phase by mutableStateOf(Phase.Idle)
        private set
    var goals: List<Goal> by mutableStateOf(emptyList())
        private set
    var lastError: String? by mutableStateOf(null)
        private set
    /** The goal waiting out its undo window. */
    var pendingDeletion: Goal? by mutableStateOf(null)
        private set
    private var deletionJob: Job? = null
    private var deletedIndex = 0

    val canAdd: Boolean get() = goals.size < maxGoals

    suspend fun load() {
        if (goals.isEmpty()) phase = Phase.Loading
        try {
            val all = api.goals()
            goals = all.filter { it.id != pendingDeletion?.id }
            phase = Phase.Loaded
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            phase = Phase.Failed(e.toString())
        }
    }

    /** Returns whether the backend took it. A blank title or a fifth goal is refused. */
    suspend fun create(title: String, current: Double, target: Double): Boolean {
        val text = title.trim()
        if (text.isEmpty() || !canAdd) return false
        lastError = null
        return try {
            goals = goals + api.createGoal(text, current, target)
            true
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            lastError = e.toString()
            false
        }
    }

    /** Optimistic edit; rolls back if the backend refuses. */
    suspend fun update(id: String, title: String, current: Double, target: Double): Boolean {
        val text = title.trim()
        val previous = goals.firstOrNull { it.id == id }
        if (text.isEmpty() || previous == null) return false
        replace(id) { it.copy(title = text, current = current, target = target) }
        return save(previous) { api.updateGoal(id, text, current, target) }
    }

    /** Optimistic progress change (the minus / plus on a goal). */
    suspend fun setProgress(id: String, current: Double): Boolean {
        val previous = goals.firstOrNull { it.id == id } ?: return false
        val value = maxOf(current, 0.0)
        replace(id) { it.copy(current = value) }
        return save(previous) { api.setGoalProgress(id, value) }
    }

    /** Hides the goal now; the backend delete runs after the undo window. A second delete sends the first. */
    fun deleteWithUndo(id: String) {
        val index = goals.indexOfFirst { it.id == id }
        if (index < 0) return
        pendingDeletion?.let { earlier ->
            deletionJob?.cancel()
            pendingDeletion = null
            val earlierIndex = deletedIndex
            scope.launch { send(earlier, earlierIndex) }
        }
        deletedIndex = index
        pendingDeletion = goals[index]
        goals = goals.toMutableList().apply { removeAt(index) }
        deletionJob = scope.launch {
            delay(undoWindowMillis)
            commitDeletion()
        }
    }

    fun undoDelete() {
        val goal = pendingDeletion ?: return
        deletionJob?.cancel()
        pendingDeletion = null
        goals = goals.toMutableList().apply { add(minOf(deletedIndex, size), goal) }
    }

    suspend fun commitDeletion() {
        val goal = pendingDeletion ?: return
        pendingDeletion = null
        deletionJob = null
        send(goal, deletedIndex)
    }

    private suspend fun send(goal: Goal, index: Int) {
        try {
            api.deleteGoal(goal.id)
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            goals = goals.toMutableList().apply { add(minOf(index, size), goal) }
            lastError = e.toString()
        }
    }

    private suspend fun save(previous: Goal, call: suspend () -> Goal): Boolean {
        lastError = null
        return try {
            val saved = call()
            replace(saved.id) { saved }
            true
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            replace(previous.id) { previous }
            lastError = e.toString()
            false
        }
    }

    private fun replace(id: String, change: (Goal) -> Goal) {
        goals = goals.map { if (it.id == id) change(it) else it }
    }

    companion object {
        /** Flutter's goals widget allows four at a time. */
        const val maxGoals = 4
    }
}
