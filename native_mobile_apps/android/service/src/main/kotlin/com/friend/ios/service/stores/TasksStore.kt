package com.friend.ios.service.stores

import android.content.SharedPreferences
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.ActionItem
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.core.models.SharedTasks
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import java.time.Instant
import java.time.ZoneId

/**
 * Port of `TasksStore.swift` + `TasksStore+Inbox.swift` and the state of `TasksStore+TidyUp.swift`:
 * tasks across all conversations. Mirrors `action_items_provider.dart`, grouped for the Tasks
 * list: mine by due date, waiting on others, done.
 * `+Undo`, `+Sharing`, `+Structure` are in `TasksStoreUndo.kt`, `TasksStoreSharing.kt`,
 * `TasksStoreStructure.kt`. The tidy-up runs here ([tidyUpIfDue] asks the agent in a chat
 * session, `TaskTidyUp.kt` holds its data); Home starts it once a day (`TodayScreen`).
 */
class TasksStore(
    internal val api: APIClientProtocol,
    /** The user's calendar (`Calendar.current`). */
    internal val zone: ZoneId = ZoneId.systemDefault(),
    private val pageSize: Int = 500,
    /** Snoozes, the tidy-up's day and its suggestion; null keeps them in memory (tests). */
    private val defaults: SharedPreferences? = null,
    /** Runs the delayed delete after the undo window (`TasksStore+Undo.swift`). */
    internal val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default),
    internal val undoWindowMillis: Long = 5_000,
) {
    // Undo and sharing state (`TasksStore+Undo.swift`, `TasksStore+Sharing.swift`).
    /** Tasks someone shared by link, waiting for the accept sheet. */
    var incomingShare: SharedTasks? by mutableStateOf(null)
        internal set
    /** A short outcome to show as a toast (export done, shared tasks added, ...). */
    var notice: TaskNotice? by mutableStateOf(null)
        internal set
    var pendingDeletion: PendingTaskDeletion? by mutableStateOf(null)
        internal set
    internal var deletionJob: Job? = null

    sealed interface Phase {
        data object Idle : Phase
        data object Loading : Phase
        data object Loaded : Phase
        data class Failed(val message: String) : Phase
    }

    enum class Bucket { Overdue, Today, Upcoming, Someday, WaitingOnOthers, Completed }

    var phase: Phase by mutableStateOf(Phase.Idle)
        private set
    var tasks: List<ActionItem> by mutableStateOf(emptyList())
        internal set
    /** Set when a change failed and was rolled back. */
    var lastError: String? by mutableStateOf(null)
        internal set

    /** Task id -> hidden from Home until then ("Later"). Local only. */
    var snoozes: Map<String, Instant> by mutableStateOf(emptyMap())
        internal set
    /** Today's tidy-up suggestion, until applied or put off. */
    var tidyUp: TaskTidyUp.Proposal? by mutableStateOf(null)
        internal set
    var isTidyingUp by mutableStateOf(false)
        internal set
    /** The last tidy-up without `defaults` (tests), epoch seconds. */
    internal var lastTidyUpInMemory: Long = 0

    init {
        restoreInbox()
    }

    /** Every task: pages until one comes back short. */
    suspend fun load() {
        if (tasks.isEmpty()) phase = Phase.Loading
        try {
            val all = Paging.all(pageSize) { limit, offset -> api.actionItems(limit, offset) }
            // Tasks that are gone for the user stay hidden: cancelled ("Not a task") and merged into another one.
            tasks = all.filter { it.status != ActionItem.Status.Cancelled && it.status != ActionItem.Status.Superseded }
            phase = Phase.Loaded
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            phase = Phase.Failed(e.toString())
        }
    }

    /** A task the user writes down themselves. Returns whether the backend took it. */
    suspend fun add(description: String, dueAt: Instant?): Boolean {
        val text = description.trim()
        if (text.isEmpty()) return false
        lastError = null
        return try {
            tasks = listOf(api.createActionItem(text, dueAt)) + tasks
            true
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            lastError = e.toString()
            false
        }
    }

    /** Tasks whose text contains the query (case insensitive). */
    fun matching(query: String): List<ActionItem> {
        val needle = query.trim()
        if (needle.isEmpty()) return tasks
        return tasks.filter { it.description.contains(needle, ignoreCase = true) }
    }

    /** Optimistic: flips immediately, rolls back if the backend refuses. */
    suspend fun setCompleted(id: String, completed: Boolean) {
        if (tasks.none { it.id == id }) return
        replace(id) { it.withCompleted(completed) }
        lastError = null
        try {
            api.setActionItem(id, completed)
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            replace(id) { it.withCompleted(!completed) }
            lastError = e.toString()
        }
    }

    /** Optimistic edit of text and due date (null clears it); rolls back if the backend refuses. Returns whether it was saved. */
    suspend fun update(id: String, description: String, dueAt: Instant?): Boolean {
        val text = description.trim()
        val previous = tasks.firstOrNull { it.id == id }
        if (text.isEmpty() || previous == null) return false
        replace(id) { it.copy(description = text, dueAt = dueAt) }
        lastError = null
        return try {
            val saved = api.updateActionItem(id, text, dueAt)
            replace(id) { saved }
            true
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            replace(id) { previous }
            lastError = e.toString()
            false
        }
    }

    /** Optimistic delete; the task comes back if the backend refuses. */
    suspend fun delete(id: String) {
        val index = tasks.indexOfFirst { it.id == id }
        if (index < 0) return
        val removed = tasks[index]
        tasks = tasks.toMutableList().apply { removeAt(index) }
        lastError = null
        try {
            api.deleteActionItem(id)
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            tasks = tasks.toMutableList().apply { add(minOf(index, size), removed) }
            lastError = e.toString()
        }
    }

    fun bucket(task: ActionItem, now: Instant = Instant.now()): Bucket {
        if (task.isCompleted) return Bucket.Completed
        if (task.owner == ActionItem.Owner.Other) return Bucket.WaitingOnOthers
        val due = task.dueAt ?: return Bucket.Someday
        val today = startOfDay(now)
        if (due < today) return Bucket.Overdue
        if (due.atZone(zone).toLocalDate() == now.atZone(zone).toLocalDate()) return Bucket.Today
        return Bucket.Upcoming
    }

    /**
     * Non-empty buckets in display order. Rows placed by hand (`sortOrder > 0`, set when a subtask is
     * indented) come first in their order, as in Flutter; the rest by due date, then creation.
     */
    fun sections(matching: String = "", now: Instant = Instant.now()): List<Pair<Bucket, List<ActionItem>>> {
        val grouped = matching(matching).groupBy { bucket(it, now) }
        return Bucket.entries.mapNotNull { bucket ->
            val items = grouped[bucket]
            if (items.isNullOrEmpty()) null else bucket to items.sortedWith(displayOrder)
        }
    }

    /** Open tasks that need attention now (overdue first, then today), for the Today briefing. */
    fun focus(now: Instant = Instant.now(), limit: Int = 3): List<ActionItem> =
        sections(now = now).filter { it.first == Bucket.Overdue || it.first == Bucket.Today }.flatMap { it.second }.take(limit)

    /** The canonical tasks that came out of one conversation ("next steps"). */
    fun tasks(forConversation: String): List<ActionItem> =
        tasks.filter { it.conversationID == forConversation && it.owner != ActionItem.Owner.Other }.sortedBy { it.isCompleted }

    /** What others committed to in that conversation. */
    fun othersTasks(forConversation: String): List<ActionItem> =
        tasks.filter { it.conversationID == forConversation && it.owner == ActionItem.Owner.Other }

    // Inbox (TasksStore+Inbox.swift): Home's task cards.

    /** Open tasks after the client rules ("All tasks (n)" counts these with the full list). */
    val openCount: Int get() = tasks.count { it.isOpen }

    /** "Later": off Home until tomorrow morning; the due date on the backend does not move. */
    fun snooze(ids: List<String>, now: Instant = Instant.now()) {
        val tomorrow = startOfDay(now).atZone(zone).plusDays(1).toInstant()
        val next = snoozes.toMutableMap()
        for (id in ids) next[id] = tomorrow
        // Expired ones go, so the list never grows.
        snoozes = next.filterValues { it > now }
        saveSnoozes()
    }

    fun unsnooze(ids: List<String>) {
        snoozes = snoozes - ids.toSet()
        saveSnoozes()
    }

    /** Every task on a card done at once (the duplicates are the same task). */
    suspend fun complete(ids: List<String>) {
        for (id in ids) setCompleted(id, true)
    }

    /** "Not a task": cancelled on the backend (the learning signal); it disappears everywhere. */
    suspend fun markNotTask(ids: List<String>) {
        for (id in ids) setStatus(id, ActionItem.Status.Cancelled)
    }

    /**
     * Optimistic: a completed task stays (ticked off), a cancelled or merged one leaves the list;
     * rolls back if the backend refuses. Returns whether it was saved.
     */
    suspend fun setStatus(id: String, status: ActionItem.Status, supersededBy: String? = null): Boolean {
        val index = tasks.indexOfFirst { it.id == id }
        if (index < 0) return false
        val previous = tasks[index]
        if (status == ActionItem.Status.Completed || status == ActionItem.Status.Active) {
            replace(id) { it.withCompleted(status == ActionItem.Status.Completed) }
        } else {
            tasks = tasks.toMutableList().apply { removeAt(index) }
        }
        lastError = null
        return try {
            api.setActionItemStatus(id, status, supersededBy)
            true
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            val current = tasks.indexOfFirst { it.id == id }
            tasks = tasks.toMutableList().apply { if (current >= 0) set(current, previous) else add(minOf(index, size), previous) }
            lastError = e.toString()
            false
        }
    }

    // Tidy-up state (TasksStore+TidyUp.swift)

    /** The first visit after [tidyUpHour] on a day that has not had one. */
    fun tidyUpIsDue(now: Instant = Instant.now()): Boolean {
        val start = now.atZone(zone).toLocalDate().atTime(tidyUpHour, 0).atZone(zone).toInstant()
        if (now < start) return false
        val last = defaults?.getLong(tidyUpLastRunKey, 0) ?: lastTidyUpInMemory
        return last < start.epochSecond
    }

    /** Today's suggestion, without changes to tasks that were closed since. */
    val currentTidyUp: TaskTidyUp.Proposal?
        get() {
            val proposal = tidyUp ?: return null
            val current = proposal.restricted(tasks.filter { it.isOpen }.map { it.id }.toSet())
            return if (current.isEmpty) null else current
        }

    /** "Not now": the card goes until tomorrow's tidy-up. */
    fun dismissTidyUp() {
        setTidyUp(null)
    }

    // Running the tidy-up (TasksStore+TidyUp.swift, and-onboarding)

    init {
        restoreTidyUp()
    }

    /**
     * Asks the agent when the day's tidy-up is due (or [force]); the suggestion lands in [tidyUp].
     * [source] names a task's conversation for the prompt.
     */
    suspend fun tidyUpIfDue(
        source: (ActionItem) -> String?,
        quote: (ActionItem) -> String? = { null },
        now: Instant = Instant.now(),
        force: Boolean = false,
    ) {
        if (isTidyingUp || !(force || tidyUpIsDue(now)) || phase != Phase.Loaded) return
        // Marked first: a failure waits for tomorrow instead of asking again on every visit.
        markTidyUpRun(now)
        // Newest first; ties keep the list's order.
        val open = tasks.withIndex().filter { it.value.isOpen && it.value.owner != ActionItem.Owner.Other }
            .sortedWith(compareByDescending<IndexedValue<ActionItem>> { it.value.createdAt ?: Instant.MIN }.thenBy { it.index })
            .map { it.value }
            .take(TaskTidyUp.maxTasks)
        if (open.size < 2) return
        isTidyingUp = true
        try {
            val keys = TaskTidyUp.keys(open)
            val prompt = TaskTidyUp.prompt(open, source, quote, now, zone)
            val answer = askTidyUp(prompt) ?: return
            val proposal = TaskTidyUp.parse(answer, keys) ?: return
            setTidyUp(proposal)
        } finally {
            isTidyingUp = false
        }
    }

    /** Applies the changes the user kept, one PATCH each; the card goes. Returns how many were saved. */
    suspend fun applyTidyUp(edits: List<TaskTidyUp.Edit>): Int {
        var saved = 0
        for (edit in edits) {
            val into = (edit.kind as? TaskTidyUp.Edit.Kind.Merge)?.into
            if (setStatus(edit.taskID, edit.status, supersededBy = into)) saved += 1
        }
        setTidyUp(null)
        return saved
    }

    private suspend fun askTidyUp(prompt: String): String? {
        val session = tidyUpSession() ?: return null
        var text = ""
        try {
            api.sendChatMessage(prompt, emptyList(), null, session, emptyList()).collect { event ->
                when (event) {
                    is com.friend.ios.network.endpoints.ChatStreamEvent.Delta -> text += event.text
                    is com.friend.ios.network.endpoints.ChatStreamEvent.Done -> if (event.message.text.isNotEmpty()) text = event.message.text
                    is com.friend.ios.network.endpoints.ChatStreamEvent.Failed -> throw TidyUpFailed()
                    else -> Unit
                }
            }
        } catch (e: TidyUpFailed) {
            return null
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            // A session that is gone: a new one tomorrow.
            defaults?.edit()?.remove(tidyUpSessionKey)?.apply()
            return null
        }
        return text
    }

    private class TidyUpFailed : Exception()

    private suspend fun tidyUpSession(): String? {
        // The stored thread only if it is this account's (another account may have signed in since).
        val stored = defaults?.getString(tidyUpSessionKey, null)
        if (stored != null) {
            val mine = runCatching { api.chatSessions(AgentStore.RUN_SESSION_APP_ID) }.getOrNull()
            if (mine != null && mine.any { it.first == stored }) return stored
        }
        // Without the app id the title prefix still keeps it out of the chat's list.
        val created = runCatching { api.createChatSession(tidyUpSessionTitle, AgentStore.RUN_SESSION_APP_ID) }.getOrNull()
            ?: runCatching { api.createChatSession(tidyUpSessionTitle) }.getOrNull()
            ?: return null
        defaults?.edit()?.putString(tidyUpSessionKey, created)?.apply()
        return created
    }

    private fun markTidyUpRun(now: Instant) {
        lastTidyUpInMemory = now.epochSecond
        defaults?.edit()?.putLong(tidyUpLastRunKey, now.epochSecond)?.apply()
    }

    private fun setTidyUp(proposal: TaskTidyUp.Proposal?) {
        tidyUp = proposal
        if (proposal != null) defaults?.edit()?.putString(tidyUpProposalKey, TaskTidyUp.encode(proposal))?.apply()
        else defaults?.edit()?.remove(tidyUpProposalKey)?.apply()
    }

    internal fun restoreTidyUp() {
        val stored = defaults?.getString(tidyUpProposalKey, null) ?: return
        tidyUp = TaskTidyUp.decode(stored)
    }

    internal fun restoreInbox() {
        val stored = defaults?.getString(snoozesKey, null) ?: return
        val now = Instant.now()
        snoozes = stored.split(',').mapNotNull { entry ->
            val parts = entry.split('=')
            val until = parts.getOrNull(1)?.toLongOrNull() ?: return@mapNotNull null
            parts[0] to Instant.ofEpochSecond(until)
        }.toMap().filterValues { it > now }
    }

    private fun saveSnoozes() {
        defaults?.edit()?.putString(snoozesKey, snoozes.entries.joinToString(",") { "${it.key}=${it.value.epochSecond}" })?.apply()
    }

    private fun startOfDay(now: Instant): Instant = now.atZone(zone).toLocalDate().atStartOfDay(zone).toInstant()

    private fun replace(id: String, change: (ActionItem) -> ActionItem) {
        tasks = tasks.map { if (it.id == id) change(it) else it }
    }

    companion object {
        const val snoozesKey = "omi.taskSnoozes"
        const val tidyUpLastRunKey = "omi.tidyUp.lastRun"
        /** The hour from which a day's tidy-up may run (local time). */
        const val tidyUpHour = 6
        const val tidyUpProposalKey = "omi.tidyUp.proposal"
        const val tidyUpSessionKey = "omi.tidyUp.session"
        /** The tidy-up's own thread: the title prefix the chat skips (`AgentStore.sessionTitlePrefix`). */
        val tidyUpSessionTitle = AgentStore.SESSION_TITLE_PREFIX + "Tidy up tasks"

        internal val displayOrder = Comparator<ActionItem> { lhs, rhs ->
            val left = lhs.sortOrder > 0
            val right = rhs.sortOrder > 0
            when {
                left && right && lhs.sortOrder != rhs.sortOrder -> lhs.sortOrder.compareTo(rhs.sortOrder)
                left && !right -> -1
                !left && right -> 1
                else -> compareValuesBy(lhs, rhs, { it.dueAt ?: Instant.MAX }, { it.createdAt ?: Instant.MIN })
            }
        }
    }
}
