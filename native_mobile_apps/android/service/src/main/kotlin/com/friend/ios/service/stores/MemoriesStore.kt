package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.Memory
import com.friend.ios.network.APIClientProtocol
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Port of `MemoriesStore.swift` + `MemoriesStore+Manage.swift`: what Omi knows about the user.
 * `@Observable` becomes Compose snapshot state, so screens recompose on exactly what they read.
 */
class MemoriesStore(
    internal val api: APIClientProtocol,
    private val scope: CoroutineScope,
    private val pageSize: Int = 500,
    internal val undoWindowMillis: Long = 5_000,
) {
    sealed interface Phase {
        data object Idle : Phase
        data object Loading : Phase
        data object Loaded : Phase
        data class Failed(val message: String) : Phase
    }

    /** A delete waiting out its undo window: off the list, the backend not told yet. */
    data class PendingDeletion(val memory: Memory, internal val index: Int)

    var phase: Phase by mutableStateOf(Phase.Idle)
        internal set
    var memories: List<Memory> by mutableStateOf(emptyList())
        internal set
    /** Set when an action failed. */
    var lastError: String? by mutableStateOf(null)
        internal set
    var pendingDeletion: PendingDeletion? by mutableStateOf(null)
        internal set
    private var deletionJob: Job? = null

    /** Every memory: pages until one comes back short. */
    suspend fun load() {
        if (memories.isEmpty()) phase = Phase.Loading
        try {
            val all = Paging.all(pageSize) { limit, offset -> api.memories(limit, offset) }
            val hidden = pendingDeletion?.memory?.id
            memories = all.filter { it.id != hidden }
            phase = Phase.Loaded
        } catch (e: Exception) {
            phase = Phase.Failed(e.toString())
        }
    }

    /** A memory the user types in themselves. Returns whether the backend took it. */
    suspend fun add(content: String): Boolean {
        val text = content.trim()
        if (text.isEmpty()) return false
        lastError = null
        return try {
            memories = listOf(api.createMemory(text, "manual")) + memories
            true
        } catch (e: Exception) {
            lastError = e.toString()
            false
        }
    }

    /** Optimistic edit; the old text comes back if the backend refuses. */
    suspend fun edit(id: String, content: String) {
        val text = content.trim()
        val previous = memories.firstOrNull { it.id == id } ?: return
        if (text.isEmpty()) return
        replace(id) { it.copy(content = text) }
        try {
            api.editMemory(id, text)
        } catch (e: Exception) {
            replace(id) { it.copy(content = previous.content) }
        }
    }

    /** Categories by size, newest memory first inside each. */
    fun grouped(query: String = ""): List<Pair<String, List<Memory>>> {
        val needle = query.trim()
        val visible = if (needle.isEmpty()) memories else memories.filter { it.content.contains(needle, ignoreCase = true) }
        return visible.groupBy { it.category }
            .map { (category, items) -> category to items.sortedByDescending { it.createdAt } }
            .sortedWith(compareByDescending<Pair<String, List<Memory>>> { it.second.size }.thenBy { it.first })
    }

    /** The filter chips: the three kinds first (always), then any other category present, with counts. */
    fun filterChips(query: String = ""): List<Pair<String, Int>> {
        val counts = grouped(query).associate { it.first to it.second.size }
        val others = counts.keys.filter { it !in kinds }.sortedByDescending { counts[it] ?: 0 }
        return (kinds + others).map { it to (counts[it] ?: 0) }
    }

    /** Newest first, narrowed to one category (null: all) and the search text. */
    fun visible(query: String = "", category: String? = null): List<Memory> =
        grouped(query).filter { category == null || it.first == category }.flatMap { it.second }.sortedByDescending { it.createdAt }

    // Management (MemoriesStore+Manage.swift)

    val publicCount: Int get() = memories.count { it.visibility == Memory.Visibility.Public }
    val privateCount: Int get() = memories.count { it.visibility == Memory.Visibility.Private }

    /** Takes the memory off the list now; the backend delete waits for [undoDelete]. A second delete commits the first. */
    fun deleteWithUndo(id: String) {
        val index = memories.indexOfFirst { it.id == id }
        if (index < 0) return
        pendingDeletion?.let { earlier ->
            deletionJob?.cancel()
            pendingDeletion = null
            scope.launch { send(earlier) }
        }
        val pending = PendingDeletion(memories[index], index)
        memories = memories.toMutableList().apply { removeAt(index) }
        pendingDeletion = pending
        deletionJob = scope.launch {
            delay(undoWindowMillis)
            if (pendingDeletion != pending) return@launch
            pendingDeletion = null
            send(pending)
        }
    }

    fun undoDelete() {
        val pending = pendingDeletion ?: return
        deletionJob?.cancel()
        deletionJob = null
        pendingDeletion = null
        memories = memories.toMutableList().apply { add(minOf(pending.index, size), pending.memory) }
    }

    /** Sends a waiting delete at once (tests; leaving the screen). */
    suspend fun commitPendingDeletion() {
        val pending = pendingDeletion ?: return
        deletionJob?.cancel()
        deletionJob = null
        pendingDeletion = null
        send(pending)
    }

    private suspend fun send(pending: PendingDeletion) {
        try {
            api.deleteMemory(pending.memory.id)
        } catch (e: Exception) {
            lastError = e.toString()
            memories = memories.toMutableList().apply { add(minOf(pending.index, size), pending.memory) }
        }
    }

    suspend fun setVisibility(id: String, visibility: Memory.Visibility) =
        change(id, { it.copy(visibility = visibility) }) { api.setMemoryVisibility(id, visibility) }

    /** No bulk endpoint: one request per memory that differs. Returns whether all took. */
    suspend fun setAllVisibility(visibility: Memory.Visibility): Boolean {
        lastError = null
        var allTook = true
        for (memory in memories.filter { it.visibility != visibility }) {
            try {
                api.setMemoryVisibility(memory.id, visibility)
                replace(memory.id) { it.copy(visibility = visibility) }
            } catch (e: Exception) {
                allTook = false
                lastError = e.toString()
            }
        }
        return allTook
    }

    suspend fun setBaseline(id: String, pinned: Boolean) =
        change(id, { it.copy(isBaseline = pinned) }) { api.setMemoryBaseline(id, pinned) }

    /**
     * "Is this right?": right keeps it as reviewed; wrong discards it, so it leaves the list.
     * Addressed by id alone: a caller that has the id but not the loaded row (the chat's review
     * card) still votes, and the load that follows reads the verdict back.
     */
    suspend fun review(id: String, isRight: Boolean) {
        lastError = null
        val index = memories.indexOfFirst { it.id == id }
        val previous = memories.getOrNull(index)
        if (previous != null) {
            memories = if (isRight) {
                memories.toMutableList().apply { set(index, previous.copy(reviewed = true, userReview = true)) }
            } else {
                memories.toMutableList().apply { removeAt(index) }
            }
        }
        try {
            api.reviewMemory(id, isRight)
        } catch (e: Exception) {
            lastError = e.toString()
            // Nothing on screen changed for a row the list never had.
            if (previous == null) return
            val current = memories.indexOfFirst { it.id == id }
            memories = memories.toMutableList().apply { if (current >= 0) set(current, previous) else add(minOf(index, size), previous) }
        }
    }

    /** Every memory, for good. Returns whether the backend took it. */
    suspend fun deleteAll(): Boolean {
        lastError = null
        return try {
            api.deleteAllMemories()
            deletionJob?.cancel()
            pendingDeletion = null
            memories = emptyList()
            phase = Phase.Loaded
            true
        } catch (e: Exception) {
            lastError = e.toString()
            false
        }
    }

    private suspend fun change(id: String, apply: (Memory) -> Memory, request: suspend () -> Unit) {
        val previous = memories.firstOrNull { it.id == id } ?: return
        replace(id, apply)
        lastError = null
        try {
            request()
        } catch (e: Exception) {
            lastError = e.toString()
            replace(id) { previous }
        }
    }

    private fun replace(id: String, transform: (Memory) -> Memory) {
        memories = memories.map { if (it.id == id) transform(it) else it }
    }

    // Memory review (and-onboarding): `MemoriesStore+Review.swift`, the logic in MemoriesStoreReview.kt.
    /** The backend's held-back conflicts (`v3/memories/review-queue`), pending only. */
    var reviewConflicts: List<com.friend.ios.core.models.MemoryConflict> by mutableStateOf(emptyList())
        internal set

    companion object {
        /** Flutter's three kinds, always offered as filters. */
        val kinds = listOf("system", "interesting", "manual")
    }
}
