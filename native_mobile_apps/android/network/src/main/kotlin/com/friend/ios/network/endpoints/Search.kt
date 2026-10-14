package com.friend.ios.network.endpoints

import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.DailySummary
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import com.friend.ios.network.generated.OmiAPI
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.Instant

/** Server-side narrowing for conversation search (`SearchRequest`), from `APIClient+Discover.swift`. */
data class ConversationSearchFilter(
    val start: Instant? = null,
    val end: Instant? = null,
    /** A person id, or `user` for what the user said. */
    val speakerID: String? = null,
) {
    val isEmpty: Boolean get() = start == null && end == null && speakerID == null
}

/**
 * Port of `APIClient+Search.swift` and the search half of `APIClient+Discover.swift`
 * (backend `routers/conversations.py`, `users.py`).
 */
interface SearchAPI {
    /**
     * `POST v1/conversations/search`: Typesense over titles and overviews, plus spoken-word hits on
     * page 1, newest first. Hits are full conversations.
     */
    suspend fun searchConversations(query: String, page: Int, perPage: Int): List<Conversation>

    /** `POST v1/conversations/search` with `start_date` / `end_date` / `speaker_id`; an empty query with a filter browses. */
    suspend fun searchConversations(query: String, page: Int, perPage: Int, filter: ConversationSearchFilter): List<Conversation>

    /** `GET v1/users/daily-summaries/search?query=`: day recaps where every word appears. */
    suspend fun searchRecaps(query: String): List<DailySummary>
}

internal class SearchEndpoints(private val http: HttpCore) : SearchAPI {
    private val list = ListSerializer(OmiAPI.Conversation.serializer())

    override suspend fun searchConversations(query: String, page: Int, perPage: Int): List<Conversation> =
        searchConversations(query, page, perPage, ConversationSearchFilter())

    override suspend fun searchConversations(query: String, page: Int, perPage: Int, filter: ConversationSearchFilter): List<Conversation> {
        val body = buildJsonObject {
            put("query", query)
            put("page", page)
            put("per_page", perPage)
            put("include_discarded", false)
            filter.start?.let { put("start_date", ConversationsEndpoints.utc(it)) }
            filter.end?.let { put("end_date", ConversationsEndpoints.utc(it)) }
            filter.speakerID?.let { put("speaker_id", it) }
        }
        val text = http.data(Method.POST, "v1/conversations/search", body = Body.Json(body.toString()))
        val items = JsonAccess.obj(text).array("items") ?: JsonArray(emptyList())
        return http.decode(list, items.toString()).map(ConversationMapper::map)
    }

    override suspend fun searchRecaps(query: String): List<DailySummary> {
        val text = http.data(Method.GET, "v1/users/daily-summaries/search", query = listOf("query" to query, "limit" to "10"))
        return JsonAccess.obj(text).objects("summaries").mapNotNull(DailySummaryMapper::map)
    }
}
