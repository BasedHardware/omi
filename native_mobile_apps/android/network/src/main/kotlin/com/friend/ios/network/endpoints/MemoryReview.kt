package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.MemoryConflict
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Port of `APIClient+MemoryReview.swift`: the backend's memory review queue (`routers/memories.py`
 * review-queue endpoints), memories held back because they contradict earlier ones.
 */
interface MemoryReviewAPI {
    /** `GET v3/memories/review-queue` (pending only). */
    suspend fun memoryReviewQueue(): List<MemoryConflict>

    /** `POST v3/memories/review-queue/{id}/resolve` with `accept` or `reject`. */
    suspend fun resolveMemoryConflict(id: String, decision: MemoryConflict.Decision)
}

internal class MemoryReviewEndpoints(private val http: HttpCore) : MemoryReviewAPI {
    override suspend fun memoryReviewQueue(): List<MemoryConflict> {
        val text = http.data(Method.GET, "v3/memories/review-queue", query = listOf("limit" to "100"))
        return JsonAccess.array(text).mapNotNull { (it as? JsonObject)?.let(MemoryConflictMapper::conflict) }
    }

    override suspend fun resolveMemoryConflict(id: String, decision: MemoryConflict.Decision) {
        val body = buildJsonObject {
            put("decision", decision.rawValue)
            put("reason", "user_review")
        }
        // `addPathSegments` encodes each segment; a slash in the id must not split it.
        val reviewID = id.replace("/", "")
        http.data(Method.POST, "v3/memories/review-queue/$reviewID/resolve", body = Body.Json(body.toString()))
    }
}

internal object MemoryConflictMapper {
    fun conflict(item: JsonObject): MemoryConflict? {
        val id = item.string("review_id")?.takeIf { it.isNotEmpty() } ?: return null
        val status = item.string("status") ?: "pending"
        if (status != "pending" && status != "pending_review") return null
        val candidate = item.obj("candidate") ?: JsonObject(emptyMap())
        val content = (candidate.string("content") ?: "").trim()
        if (content.isEmpty()) return null
        return MemoryConflict(
            id = id,
            factID = item.string("fact_id") ?: candidate.string("id") ?: "",
            candidate = content,
            conflictsWith = item.strings("conflict_with").filter { it.isNotEmpty() },
            createdAt = BackendDate.parse(item.string("created_at")),
        )
    }
}
