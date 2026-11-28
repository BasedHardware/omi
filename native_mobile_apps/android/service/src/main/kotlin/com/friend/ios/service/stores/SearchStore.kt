package com.friend.ios.service.stores

import android.content.SharedPreferences
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.core.models.ConversationFilter
import com.friend.ios.core.models.DailySummary
import com.friend.ios.core.models.Memory
import com.friend.ios.core.models.Person
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.endpoints.ConversationSearchFilter
import com.friend.ios.persistence.Preferences
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive
import java.time.Instant

/**
 * Port of `SearchStore.swift`: one search over conversations, recaps, tasks and memories. What is
 * already loaded matches at once; the backend's conversation search (titles, overviews and what was
 * said) follows once typing pauses. Filters (starred, a person, a date range) narrow it to
 * conversations; recent searches are kept like Flutter's (`global_search`). Created per search screen.
 */
class SearchStore(
    internal val api: APIClientProtocol,
    internal val conversationsStore: ConversationsStore,
    private val tasksStore: TasksStore,
    private val memoriesStore: MemoriesStore,
    private val scope: CoroutineScope,
    private val debounceMillis: Long = 300,
    /** `UserDefaults.standard`: Flutter's shared preferences file, so an update keeps the list. */
    private val defaults: SharedPreferences? = null,
) {
    enum class Phase {
        /** No query and no filter. */
        Idle,
        /** Waiting for typing to pause, or for the backend. */
        Searching,
        Done,
        /** The backend search failed; local matches still show. */
        Failed,
    }

    /** Narrows the search to conversations (Flutter's starred tile, people, date filter). */
    data class Filter(val starred: Boolean = false, val person: Person? = null, val start: Instant? = null, val end: Instant? = null) {
        val isActive: Boolean get() = starred || person != null || start != null || end != null

        internal val server: ConversationSearchFilter get() = ConversationSearchFilter(start, end, person?.id)
    }

    var query by mutableStateOf("")
        private set
    var phase by mutableStateOf(Phase.Idle)
        private set
    private var filterState by mutableStateOf(Filter())
    var filter: Filter
        get() = filterState
        set(value) {
            val old = filterState
            filterState = value
            if (value != old) search()
        }

    /** Newest first, at most [maxRecents]. */
    var recents: List<String> by mutableStateOf(readRecents())
        private set
    /** Day recaps matching the query. */
    var recaps: List<DailySummary> by mutableStateOf(emptyList())
        private set
    /** Backend hits for [query]; empty until they arrive. */
    internal var serverHits: List<Conversation> by mutableStateOf(emptyList())
    /** The debounced backend search for the current query (tests await it). */
    internal var pending: Job? = null
        private set
    internal val perPage = 30

    internal val needle: String get() = query.trim()

    /** A query or a filter is set: results show instead of the full list. */
    val isActive: Boolean get() = needle.isNotEmpty() || filter.isActive

    /** Loaded and backend matches together, newest first; the loaded copy wins (it has local edits). */
    val conversations: List<Conversation>
        get() {
            if (!isActive) return emptyList()
            // The loaded list does not know who spoke; a person filter is the backend's alone.
            val local = if (filter.person != null) emptyList() else conversationsStore.conversations.filter {
                (needle.isEmpty() || contains(it.title, needle) || contains(it.overview, needle)) && passes(it)
            }
            val known = local.map { it.id }.toSet()
            val loaded = HashMap<String, Conversation>()
            conversationsStore.conversations.forEach { if (it.id !in loaded) loaded[it.id] = it }
            val remote = serverHits.filter { it.id !in known }.map { loaded[it.id] ?: it }.filter(::passes)
            return (local + remote).sortedByDescending { it.date }
        }

    val tasks: List<ActionItem> get() = if (needle.isEmpty() || filter.isActive) emptyList() else tasksStore.matching(needle)

    val memories: List<Memory>
        get() {
            if (needle.isEmpty() || filter.isActive) return emptyList()
            return memoriesStore.memories.filter { contains(it.content, needle) }.sortedByDescending { it.createdAt }
        }

    val hasResults: Boolean get() = conversations.isNotEmpty() || tasks.isNotEmpty() || memories.isNotEmpty() || recaps.isNotEmpty()

    /** Loads whatever the local matches need and has not been loaded yet. */
    suspend fun loadSources() = coroutineScope {
        if (conversationsStore.phase == ConversationsStore.Phase.Idle) launch { conversationsStore.load() }
        if (tasksStore.phase == TasksStore.Phase.Idle) launch { tasksStore.load() }
        if (memoriesStore.phase == MemoriesStore.Phase.Idle) launch { memoriesStore.load() }
    }

    /**
     * Call on every keystroke: local matches update now, the backend is asked once typing pauses,
     * and an answer for an older query is dropped.
     */
    fun update(query: String) {
        if (query == this.query) return
        val previousNeedle = needle
        this.query = query
        if (needle == previousNeedle) return
        search()
    }

    // Recent searches

    /** Keeps [text] on top of the recent searches (on submit, or when a result is opened). */
    fun remember(text: String? = null) {
        val entry = (text ?: query).trim()
        if (entry.isEmpty()) return
        recents = (listOf(entry) + recents.filter { !it.equals(entry, ignoreCase = true) }).take(maxRecents)
        writeRecents(recents)
    }

    fun removeRecent(text: String) {
        recents = recents.filter { it != text }
        writeRecents(recents)
    }

    fun clearRecents() {
        recents = emptyList()
        defaults?.edit()?.remove(recentsKey)?.apply()
    }

    // Backend

    private fun passes(conversation: Conversation): Boolean =
        (!filter.starred || conversation.isStarred) &&
            (filter.start?.let { conversation.date >= it } ?: true) &&
            (filter.end?.let { conversation.date <= it } ?: true)

    private fun search() {
        pending?.cancel()
        serverHits = emptyList()
        recaps = emptyList()
        if (!isActive) {
            pending = null
            phase = Phase.Idle
            return
        }
        phase = Phase.Searching
        val needle = needle
        val filter = filter
        pending = scope.launch {
            delay(debounceMillis)
            val wantsRecaps = needle.isNotEmpty() && !filter.starred && filter.person == null
            val (hits, recapHits) = coroutineScope {
                val found = async { conversations(needle, filter) }
                val days = async {
                    if (!wantsRecaps) emptyList() else try {
                        api.searchRecaps(needle)
                    } catch (e: Exception) {
                        if (e is CancellationException) throw e
                        emptyList()
                    }
                }
                found.await() to days.await()
            }
            if (this@SearchStore.needle != needle || this@SearchStore.filter != filter) return@launch
            serverHits = hits ?: emptyList()
            recaps = recapHits.filter { recap ->
                val day = BackendDate.parse(recap.date + "T12:00:00Z") ?: return@filter true
                (filter.start?.let { day >= it } ?: true) && (filter.end?.let { day <= it } ?: true)
            }
            phase = if (hits == null) Phase.Failed else Phase.Done
        }
    }

    /** Starred with nothing else: the starred list itself. Otherwise the backend search. */
    private suspend fun conversations(needle: String, filter: Filter): List<Conversation>? = try {
        when {
            needle.isEmpty() && filter.starred && filter.server.isEmpty -> api.conversations(50, 0, ConversationFilter.Starred)
            filter.server.isEmpty -> api.searchConversations(needle, 1, perPage)
            else -> api.searchConversations(needle, 1, perPage, filter.server)
        }
    } catch (e: Exception) {
        if (e is CancellationException) throw e
        null
    }

    private fun readRecents(): List<String> {
        val stored = defaults?.getString(recentsKey, null) ?: return emptyList()
        val json = stored.removePrefix(Preferences.LIST_PREFIX)
        return runCatching { (Json.parseToJsonElement(json) as JsonArray).map { it.jsonPrimitive.content } }.getOrDefault(emptyList())
    }

    private fun writeRecents(values: List<String>) {
        val json = JsonArray(values.map(::JsonPrimitive)).toString()
        defaults?.edit()?.putString(recentsKey, Preferences.LIST_PREFIX + json)?.apply()
    }

    companion object {
        /** Flutter's key and limit, so an update keeps the list. */
        const val recentsKey = "flutter.globalSearchRecentQueries"
        const val maxRecents = 6

        /** `localizedStandardContains`: case and diacritics ignored. */
        internal fun contains(text: String, needle: String): Boolean = ConversationDetail.fold(text).contains(ConversationDetail.fold(needle))
    }
}

/** The search screen's store (`SearchStore(api:conversations:tasks:memories:)` in the shell). */
fun ConversationsStore.makeSearchStore(tasks: TasksStore, memories: MemoriesStore, scope: CoroutineScope): SearchStore =
    SearchStore(api, this, tasks, memories, scope, defaults = defaults)
