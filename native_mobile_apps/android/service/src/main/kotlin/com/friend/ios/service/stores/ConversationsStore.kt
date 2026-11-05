package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.core.models.ConversationDigest
import com.friend.ios.core.models.ConversationDisplay
import com.friend.ios.core.models.ConversationFilter
import com.friend.ios.core.models.DailySummary
import com.friend.ios.core.models.Folder
import com.friend.ios.core.models.FolderDraft
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.persistence.Preferences
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/**
 * Port of `ConversationsStore.swift` (+`Display`, `+Folders`, `+Organizing`, `+TaskSources`):
 * the conversation list. Mirrors the Flutter app's `conversation_provider.dart`; star, folders,
 * delete with undo, merge and reprocess are below.
 */
class ConversationsStore(
    internal val api: APIClientProtocol,
    private val scope: CoroutineScope,
    /** The user's calendar (`Calendar.current`): days are local days in this zone. */
    internal val zone: ZoneId = ZoneId.systemDefault(),
    internal val undoWindowMillis: Long = 5_000,
    internal val mergeRefreshDelayMillis: Long = 8_000,
    internal val preferences: Preferences? = null,
    /** Where the "For you" store keeps the producers the user stopped (`UserDefaults.standard`). */
    internal val defaults: android.content.SharedPreferences? = null,
) {
    sealed interface Phase {
        data object Idle : Phase
        data object Loading : Phase
        data object Loaded : Phase
        data class Failed(val message: String) : Phase
    }

    data class DaySection(val day: LocalDate, val conversations: List<Conversation>) {
        val id: LocalDate get() = day
    }

    /** Conversations removed from the list whose backend delete waits out the undo window. */
    class PendingDeletion internal constructor(
        val ids: List<String>,
        internal val removed: List<Pair<Int, Conversation>>,
        internal val removedFiltered: List<Pair<Int, Conversation>>,
    ) {
        override fun equals(other: Any?): Boolean = other is PendingDeletion && other.ids == ids
        override fun hashCode(): Int = ids.hashCode()
    }

    var phase: Phase by mutableStateOf(Phase.Idle)
        internal set
    /** Every conversation, newest first (the unfiltered list other screens look titles up in). */
    var conversations: List<Conversation> by mutableStateOf(emptyList())
        internal set
    var hasMore by mutableStateOf(true)
        internal set
    var isLoadingMore by mutableStateOf(false)
        internal set

    /** What the Home list shows; anything but `All` fills `filtered` from the backend. */
    var filter: ConversationFilter by mutableStateOf(ConversationFilter.All)
        internal set
    var filtered: List<Conversation> by mutableStateOf(emptyList())
        internal set
    var filteredHasMore by mutableStateOf(false)
        internal set
    var isLoadingFiltered by mutableStateOf(false)
        internal set
    var folders: List<Folder> by mutableStateOf(emptyList())
        internal set
    var pendingDeletion: PendingDeletion? by mutableStateOf(null)
        internal set
    /** Conversations opened outside the loaded pages (from a memory, a search), kept current here. */
    internal var known: Map<String, Conversation> by mutableStateOf(emptyMap())
    /** Details loaded for task sources (where each task came from), by conversation id. */
    var sourceDetails: Map<String, ConversationDetail> by mutableStateOf(emptyMap())
        internal set
    private var deletionJob: Job? = null

    /** Discarded and short conversations shown or hidden (`ConversationsStore+Display.swift`). */
    var display: ConversationDisplay by mutableStateOf(preferences?.let(::display) ?: ConversationDisplay())
        internal set

    internal val pageSize = 50

    /** Omi's daily recaps, newest first. */
    var recaps: List<DailySummary> by mutableStateOf(emptyList())
        private set
    var isCreatingRecap by mutableStateOf(false)
        private set

    suspend fun loadRecaps() {
        attempt { api.dailySummaries(14) }?.let { recaps = it }
    }

    /** Generates (or fetches) the recap for a local day. */
    suspend fun createRecap(day: LocalDate) {
        if (isCreatingRecap) return
        isCreatingRecap = true
        try {
            val recap = attempt { api.createDailySummary(dayKey(day)) } ?: return
            recaps = listOf(recap) + recaps.filter { it.id != recap.id && it.date != recap.date }
        } finally {
            isCreatingRecap = false
        }
    }

    /**
     * What Home shows first under a day: that day's recap, or for yesterday (with conversations,
     * no recap yet) the offer to write it. Only in the unfiltered list.
     */
    sealed interface RecapSlot {
        data class Recap(val recap: DailySummary) : RecapSlot
        data class Write(val day: LocalDate) : RecapSlot
    }

    fun recapSlot(day: LocalDate, now: Instant = Instant.now()): RecapSlot? {
        if (filter != ConversationFilter.All) return null
        recaps.firstOrNull { it.date == dayKey(day) }?.let { return RecapSlot.Recap(it) }
        val yesterday = localDay(now).minusDays(1)
        if (day != yesterday || conversations.none { localDay(it.date) == day }) return null
        return RecapSlot.Write(day)
    }

    /** `YYYY-MM-DD` in the user's calendar, how recaps name their day. */
    internal fun dayKey(day: LocalDate): String = day.toString()

    internal fun localDay(instant: Instant): LocalDate = instant.atZone(zone).toLocalDate()

    /** Optimistic rename; the old title comes back if the backend refuses. */
    suspend fun rename(id: String, title: String) {
        val text = title.trim()
        if (text.isEmpty()) return
        val edit = edit(setOf(id)) { it.copy(title = text) }
        if (edit.isEmpty) return
        try {
            api.renameConversation(id, text)
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            revert(edit)
        }
    }

    /** Removes the conversation at once (no undo); it comes back if the backend refuses. */
    suspend fun delete(id: String) {
        val index = conversations.indexOfFirst { it.id == id }
        if (index < 0) return
        val removed = conversations[index]
        conversations = conversations.toMutableList().apply { removeAt(index) }
        try {
            api.deleteConversation(id)
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            conversations = conversations.toMutableList().apply { add(minOf(index, size), removed) }
        }
    }

    suspend fun load() {
        if (conversations.isEmpty()) phase = Phase.Loading
        try {
            val page = fetchPage(0)
            // A delete waiting for its undo window stays hidden.
            val hidden = pendingDeletion?.ids.orEmpty().toSet()
            conversations = page.filter { it.id !in hidden }
            hasMore = page.size == pageSize
            phase = Phase.Loaded
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            // Keep showing what we had; only an empty screen shows the error state.
            phase = Phase.Failed(e.toString())
        }
    }

    /** Next page (`offset` paging, like the Flutter app). Call when the last row appears. */
    suspend fun loadMore() {
        if (filter != ConversationFilter.All) return loadMoreFiltered()
        if (!hasMore || isLoadingMore || phase != Phase.Loaded) return
        isLoadingMore = true
        try {
            val page = attempt { fetchPage(conversations.size) } ?: return
            val known = conversations.map { it.id }.toSet()
            conversations = conversations + page.filter { it.id !in known }
            hasMore = page.size == pageSize
        } finally {
            isLoadingMore = false
        }
    }

    /**
     * What the list shows under the current filter (short and discarded ones as `display` says,
     * one row per capture group).
     */
    val visible: List<Conversation>
        get() = ConversationDisplay.oneRowPerCaptureGroup(
            (if (filter == ConversationFilter.All) conversations else filtered).filter(display::keeps),
        )

    /** Newest day first, newest conversation first within a day. */
    val sections: List<DaySection>
        get() {
            val grouped = visible.groupBy { localDay(it.date) }
            return grouped.keys.sortedDescending().map { day ->
                DaySection(day, grouped.getValue(day).sortedByDescending { it.date })
            }
        }

    /**
     * The conversation with this id: from the list, otherwise fetched (a memory can come from a
     * conversation older than the loaded pages). Null when it is gone.
     */
    suspend fun conversation(id: String): Conversation? {
        (conversations.firstOrNull { it.id == id } ?: known[id])?.let { return it }
        return attempt { api.conversationDetail(id).conversation }
    }

    fun today(now: Instant = Instant.now()): List<Conversation> =
        conversations.filter { localDay(it.date) == localDay(now) }.sortedByDescending { it.date }

    // Display (ConversationsStore+Display.swift)

    /** Shows or hides discarded conversations, then reloads the list. */
    suspend fun setShowsDiscarded(shows: Boolean) {
        if (display.showsDiscarded == shows) return
        display = display.copy(showsDiscarded = shows)
        preferences?.set(Preferences.Key.ShowDiscardedMemories, shows)
        load()
    }

    /** Hides conversations shorter than [seconds]; null shows every length. */
    fun hideShorter(seconds: Int?) {
        display = if (seconds != null) {
            preferences?.set(Preferences.Key.ShortConversationThreshold, seconds)
            display.copy(showsShort = false, shortThreshold = seconds)
        } else {
            display.copy(showsShort = true)
        }
        preferences?.set(Preferences.Key.ShowShortConversations, display.showsShort)
    }

    /** One page of the unfiltered list, discarded ones included when shown. */
    internal suspend fun fetchPage(offset: Int): List<Conversation> {
        if (display.showsDiscarded) {
            return api.conversations(pageSize, offset, com.friend.ios.core.models.ConversationQuery(includeDiscarded = true))
        }
        return api.conversations(pageSize, offset)
    }

    /** The one-day page (Flutter `day_conversations_page`). */
    fun makeDayStore(day: LocalDate): DayConversationsStore = DayConversationsStore(api, day, zone, display)

    // Folders (ConversationsStore+Folders.swift)

    /** Shows only starred conversations or one folder's; `All` goes back to the full list. */
    suspend fun setFilter(filter: ConversationFilter) {
        if (filter == this.filter) return
        this.filter = filter
        filtered = emptyList()
        filteredHasMore = false
        if (filter == ConversationFilter.All) return
        reloadFiltered()
    }

    suspend fun loadFolders() {
        attempt { api.folders() }?.let { folders = it }
    }

    fun folder(id: String?): Folder? = id?.let { folders.firstOrNull { folder -> folder.id == it } }

    /**
     * Creates a folder from the editor's draft; null when the name is empty or the backend refuses
     * (e.g. the 50-folder limit).
     */
    suspend fun createFolder(draft: FolderDraft): Folder? {
        val draft = draft.trimmed ?: return null
        val folder = attempt { api.createFolder(draft) } ?: return null
        folders = folders + folder
        return folder
    }

    /**
     * Optimistic edit of a folder's name and look; the old folder comes back if the backend
     * refuses. False when the draft is empty or the folder is gone.
     */
    suspend fun updateFolder(id: String, draft: FolderDraft): Boolean {
        val draft = draft.trimmed ?: return false
        val index = folders.indexOfFirst { it.id == id }
        if (index < 0) return false
        val previous = folders[index]
        applyDraft(draft, index)
        return try {
            val updated = api.updateFolder(id, draft)
            val current = folders.indexOfFirst { it.id == id }
            if (current >= 0) folders = folders.toMutableList().apply { set(current, updated) }
            true
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            val current = folders.indexOfFirst { it.id == id }
            if (current >= 0) folders = folders.toMutableList().apply { set(current, previous) }
            false
        }
    }

    private fun applyDraft(draft: FolderDraft, index: Int) {
        folders = folders.toMutableList().apply {
            set(index, get(index).copy(name = draft.name, icon = draft.icon, color = draft.color, description = draft.description))
        }
    }

    /**
     * Deletes a custom folder; the backend keeps its conversations (they move to [moveTo], or leave
     * every folder when that is null).
     */
    suspend fun deleteFolder(id: String, moveTo: String? = null) {
        val index = folders.indexOfFirst { it.id == id }
        if (index < 0 || folders[index].isSystem) return
        val removed = folders[index]
        folders = folders.toMutableList().apply { removeAt(index) }
        // A folder cannot be its own destination.
        val destination = if (moveTo == id) null else moveTo
        try {
            api.deleteFolder(id, destination)
            if (filter == ConversationFilter.Folder(id)) setFilter(ConversationFilter.All)
            // The backend re-files the folder's conversations; the next page load shows where.
            load()
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            folders = folders.toMutableList().apply { add(minOf(index, size), removed) }
        }
    }

    /** The filter's first page again. */
    suspend fun reloadFiltered() {
        val filter = filter
        if (filter == ConversationFilter.All) return
        isLoadingFiltered = true
        try {
            val page = attempt { api.conversations(pageSize, 0, filter) } ?: return
            if (filter != this.filter) return
            val hidden = pendingDeletion?.ids.orEmpty().toSet()
            filtered = page.filter { it.id !in hidden }
            filteredHasMore = page.size == pageSize
        } finally {
            isLoadingFiltered = false
        }
    }

    internal suspend fun loadMoreFiltered() {
        val filter = filter
        if (!filteredHasMore || isLoadingFiltered) return
        isLoadingFiltered = true
        try {
            val page = attempt { api.conversations(pageSize, filtered.size, filter) } ?: return
            if (filter != this.filter) return
            val known = filtered.map { it.id }.toSet()
            filtered = filtered + page.filter { it.id !in known }
            filteredHasMore = page.size == pageSize
        } finally {
            isLoadingFiltered = false
        }
    }

    // Organizing (ConversationsStore+Organizing.swift)

    sealed interface MergeOutcome {
        /** The backend took it; the merged conversation replaces the sources shortly. */
        data class Started(val warning: String?) : MergeOutcome
        data object NeedsTwo : MergeOutcome
        /** A conversation is still processing, already merging, or locked. */
        data object NotReady : MergeOutcome
        data object Failed : MergeOutcome
    }

    /** The list's (or the remembered) copy of a conversation, so a change made anywhere shows everywhere. */
    fun current(conversation: Conversation): Conversation =
        conversations.firstOrNull { it.id == conversation.id } ?: filtered.firstOrNull { it.id == conversation.id }
            ?: known[conversation.id] ?: conversation

    /** Keeps a conversation opened outside the list current (detail screens call it on load). */
    fun remember(conversation: Conversation) {
        known = known + (conversation.id to conversation)
        replace(conversation)
    }

    suspend fun setStarred(id: String, starred: Boolean) {
        val edit = edit(setOf(id), keepInFilter = { filter != ConversationFilter.Starred || it.isStarred }) { it.copy(isStarred = starred) }
        try {
            api.setConversationStarred(id, starred)
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            revert(edit)
        }
    }

    /** `Shared` makes the link work for anyone who has it. Returns whether the backend agreed. */
    suspend fun setVisibility(id: String, visibility: Conversation.Visibility): Boolean {
        val edit = edit(setOf(id)) { it.copy(visibility = visibility) }
        return try {
            api.setConversationVisibility(id, visibility)
            true
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            revert(edit)
            false
        }
    }

    /** Moves into a folder, or out of every folder with null. */
    suspend fun move(ids: List<String>, folderID: String?) {
        if (ids.isEmpty()) return
        val edit = edit(ids.toSet(), keepInFilter = { filter.keeps(it) }) { it.copy(folderID = folderID) }
        try {
            if (folderID != null && ids.size > 1) {
                api.moveConversations(ids, folderID)
            } else {
                for (id in ids) api.moveConversation(id, folderID)
            }
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            revert(edit)
        }
        loadFolders()
    }

    /** Summarizes again (also the retry for a failed summary). Returns the new detail. */
    suspend fun reprocess(id: String, appID: String? = null): ConversationDetail? {
        val edit = edit(setOf(id)) { it.copy(status = Conversation.Status.Processing) }
        return try {
            val detail = if (appID != null) api.reprocessConversation(id, appID) else api.reprocessConversation(id)
            replace(detail.conversation)
            if (known[id] != null) known = known + (id to detail.conversation)
            detail
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            revert(edit)
            null
        }
    }

    /** Merges into one new conversation, with the backend's constraints checked first. */
    suspend fun merge(ids: List<String>): MergeOutcome {
        val unique = ids.distinct()
        if (unique.size < 2) return MergeOutcome.NeedsTwo
        val selected = unique.mapNotNull { id -> visible.firstOrNull { it.id == id } ?: conversations.firstOrNull { it.id == id } }
        if (!selected.all { it.canMerge }) return MergeOutcome.NotReady
        val edit = edit(unique.toSet()) { it.copy(status = Conversation.Status.Merging) }
        return try {
            val warning = api.mergeConversations(unique)
            scope.launch {
                delay(mergeRefreshDelayMillis)
                reloadAfterMerge()
            }
            MergeOutcome.Started(warning)
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            revert(edit)
            MergeOutcome.Failed
        }
    }

    /**
     * Takes the conversations off the list now; the backend delete waits [undoWindowMillis] for
     * [undoDelete]. A second delete commits the first.
     */
    fun deleteWithUndo(ids: List<String>) {
        val present = ids.filter { id -> visible.any { it.id == id } || conversations.any { it.id == id } }
        if (present.isEmpty()) return
        pendingDeletion?.let { earlier ->
            deletionJob?.cancel()
            pendingDeletion = null
            scope.launch { send(earlier) }
        }
        val hide = present.toSet()
        val removed = conversations.withIndex().filter { it.value.id in hide }.map { it.index to it.value }
        val removedFiltered = filtered.withIndex().filter { it.value.id in hide }.map { it.index to it.value }
        conversations = conversations.filter { it.id !in hide }
        filtered = filtered.filter { it.id !in hide }
        val pending = PendingDeletion(present, removed, removedFiltered)
        pendingDeletion = pending
        deletionJob = scope.launch {
            delay(undoWindowMillis)
            commitDeletion()
        }
    }

    /** Puts the conversations back where they were; nothing reaches the backend. */
    fun undoDelete() {
        val pending = pendingDeletion ?: return
        deletionJob?.cancel()
        deletionJob = null
        pendingDeletion = null
        restore(pending)
    }

    /** Sends the waiting delete now. A conversation the backend refuses to delete comes back. */
    suspend fun commitDeletion() {
        val pending = pendingDeletion ?: return
        pendingDeletion = null
        deletionJob = null
        send(pending)
    }

    internal suspend fun send(pending: PendingDeletion) {
        val failed = mutableSetOf<String>()
        for (id in pending.ids) {
            try {
                api.deleteConversation(id)
                known = known - id
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                failed += id
            }
        }
        if (failed.isEmpty()) return
        restore(
            PendingDeletion(
                pending.ids.filter { it in failed },
                pending.removed.filter { it.second.id in failed },
                pending.removedFiltered.filter { it.second.id in failed },
            ),
        )
    }

    /** The previous copies of what an optimistic change touched, to put back on failure. */
    internal class Edit {
        val main = mutableListOf<Pair<Int, Conversation>>()
        val filtered = mutableListOf<Pair<Int, Conversation>>()
        val known = mutableMapOf<String, Conversation>()
        val isEmpty: Boolean get() = main.isEmpty() && filtered.isEmpty() && known.isEmpty()
    }

    /**
     * Applies [change] to every copy of the conversations; ones that no longer match the filter
     * ([keepInFilter]) leave the filtered list.
     */
    internal fun edit(ids: Set<String>, keepInFilter: (Conversation) -> Boolean = { true }, change: (Conversation) -> Conversation): Edit {
        val edit = Edit()
        conversations = conversations.mapIndexed { index, conversation ->
            if (conversation.id in ids) {
                edit.main += index to conversation
                change(conversation)
            } else conversation
        }
        val nextFiltered = mutableListOf<Conversation>()
        filtered.forEachIndexed { index, conversation ->
            if (conversation.id in ids) {
                edit.filtered += index to conversation
                val changed = change(conversation)
                if (keepInFilter(changed)) nextFiltered += changed
            } else nextFiltered += conversation
        }
        filtered = nextFiltered
        val nextKnown = known.toMutableMap()
        for (id in ids) {
            val copy = known[id] ?: continue
            edit.known[id] = copy
            nextKnown[id] = change(copy)
        }
        known = nextKnown
        return edit
    }

    internal fun revert(edit: Edit) {
        val main = conversations.toMutableList()
        for ((index, old) in edit.main) {
            val current = main.indexOfFirst { it.id == old.id }
            if (current >= 0) main[current] = old else main.add(minOf(index, main.size), old)
        }
        conversations = main
        val list = filtered.toMutableList()
        for ((index, old) in edit.filtered) {
            val current = list.indexOfFirst { it.id == old.id }
            if (current >= 0) list[current] = old else list.add(minOf(index, list.size), old)
        }
        filtered = list
        known = known + edit.known
    }

    /** Swaps in a fresher copy wherever the conversation is listed. */
    internal fun replace(conversation: Conversation) {
        conversations = conversations.map { if (it.id == conversation.id) conversation else it }
        filtered = filtered.map { if (it.id == conversation.id) conversation else it }
    }

    internal fun restore(pending: PendingDeletion) {
        val main = conversations.toMutableList()
        for ((index, conversation) in pending.removed) {
            if (main.none { it.id == conversation.id }) main.add(minOf(index, main.size), conversation)
        }
        conversations = main
        val list = filtered.toMutableList()
        for ((index, conversation) in pending.removedFiltered) {
            if (list.none { it.id == conversation.id }) list.add(minOf(index, list.size), conversation)
        }
        filtered = list
    }

    internal suspend fun reloadAfterMerge() {
        load()
        if (filter != ConversationFilter.All) reloadFiltered()
    }

    // Task sources (ConversationsStore+TaskSources.swift)

    /** The task's source conversation when known (the loaded list or a detail fetched for it). */
    fun source(task: ActionItem): Conversation? {
        val id = task.conversationID ?: return null
        return currentConversation(id) ?: sourceDetails[id]?.conversation
    }

    /**
     * The transcript words (or the context line) the task was extracted from, once its
     * conversation's detail is loaded ([loadSources]).
     */
    fun quote(task: ActionItem): String? {
        val id = task.conversationID ?: return null
        val detail = sourceDetails[id] ?: return null
        return ConversationDigest.quote(task.description, detail)
    }

    /**
     * Loads the details behind these tasks (each conversation once, at most [limit], newest
     * tasks first), so their rows can show where they came from.
     */
    suspend fun loadSources(tasks: List<ActionItem>, limit: Int = 20) {
        val ids = mutableListOf<String>()
        for (task in tasks.sortedByDescending { it.createdAt ?: Instant.MIN }) {
            val id = task.conversationID ?: continue
            if (sourceDetails[id] != null || id in ids) continue
            ids += id
            if (ids.size == limit) break
        }
        for (id in ids) {
            attempt { api.conversationDetail(id) }?.let { sourceDetails = sourceDetails + (id to it) }
        }
    }

    private fun currentConversation(id: String): Conversation? = known[id] ?: conversations.firstOrNull { it.id == id }

    // StoreFactories.swift

    fun makeForYouStore(): ForYouStore = ForYouStore(api, defaults, scope)

    companion object {
        /** The thresholds Flutter offers, in seconds. */
        val shortThresholds = listOf(60, 120, 180, 240, 300)

        internal fun display(preferences: Preferences): ConversationDisplay = ConversationDisplay(
            showsDiscarded = preferences.bool(Preferences.Key.ShowDiscardedMemories, false),
            showsShort = preferences.bool(Preferences.Key.ShowShortConversations, false),
            shortThreshold = preferences.integer(Preferences.Key.ShortConversationThreshold, 0),
        )
    }
}

/** Swift `try?`: the value, or null on failure (cancellation still cancels). */
private suspend fun <T> attempt(block: suspend () -> T): T? = try {
    block()
} catch (e: CancellationException) {
    throw e
} catch (e: Exception) {
    null
}
