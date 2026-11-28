package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.Memory
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import com.friend.ios.network.generated.OmiAPI
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.put

/**
 * Port of `APIClient+Memories.swift`, the memory half of `APIClient+Edits.swift` and
 * `APIClient+MemoryExtras.swift` (contracts: `backend/routers/memories.py`).
 */
interface MemoriesAPI {
    /** `GET v3/memories` (offset paging, at most 500 per page). */
    suspend fun memories(limit: Int, offset: Int): List<Memory>

    /** `POST v3/memories`: `manual` for what the user typed in, `system` for what they told Omi. */
    suspend fun createMemory(content: String, category: String): Memory

    /** `PATCH v3/memories/{id}` with `{"value": content}`. */
    suspend fun editMemory(id: String, content: String)

    /** `DELETE v3/memories/{id}`. */
    suspend fun deleteMemory(id: String)

    /** `PATCH v3/memories/{id}/visibility` with `{"value": "private"|"public"}`. */
    suspend fun setMemoryVisibility(id: String, visibility: Memory.Visibility)

    /** `PATCH v3/memories/{id}/baseline?value=`. */
    suspend fun setMemoryBaseline(id: String, pinned: Boolean)

    /** `POST v3/memories/{id}/review?value=`: true keeps it, false discards it. */
    suspend fun reviewMemory(id: String, isRight: Boolean)

    /** `DELETE v3/memories` (`scope=all`): every memory, for good. */
    suspend fun deleteAllMemories()
}

internal class MemoriesEndpoints(private val http: HttpCore) : MemoriesAPI {
    override suspend fun memories(limit: Int, offset: Int): List<Memory> {
        val text = http.data(Method.GET, "v3/memories", query = listOf("limit" to "$limit", "offset" to "$offset"))
        return http.decode(ListSerializer(OmiAPI.MemoryDB.serializer()), text).map(MemoryMapper::map)
    }

    override suspend fun createMemory(content: String, category: String): Memory {
        val body = buildJsonObject {
            put("content", content)
            put("visibility", "private")
            put("category", category)
        }
        val text = http.data(Method.POST, "v3/memories", body = Body.Json(body.toString()))
        return MemoryMapper.map(http.decode(OmiAPI.MemoryDB.serializer(), text))
    }

    override suspend fun editMemory(id: String, content: String) {
        http.data(Method.PATCH, "v3/memories/$id", body = Body.Json(buildJsonObject { put("value", content) }.toString()))
    }

    override suspend fun deleteMemory(id: String) {
        http.data(Method.DELETE, "v3/memories/$id")
    }

    override suspend fun setMemoryVisibility(id: String, visibility: Memory.Visibility) {
        http.data(Method.PATCH, "v3/memories/$id/visibility", body = Body.Json(buildJsonObject { put("value", visibility.rawValue) }.toString()))
    }

    override suspend fun setMemoryBaseline(id: String, pinned: Boolean) {
        http.data(Method.PATCH, "v3/memories/$id/baseline", query = listOf("value" to "$pinned"))
    }

    override suspend fun reviewMemory(id: String, isRight: Boolean) {
        http.data(Method.POST, "v3/memories/$id/review", query = listOf("value" to "$isRight"))
    }

    override suspend fun deleteAllMemories() {
        http.data(Method.DELETE, "v3/memories", query = listOf("scope" to "all"))
    }
}

internal object MemoryMapper {
    fun map(dto: OmiAPI.MemoryDB): Memory = Memory(
        id = dto.id,
        content = dto.content,
        headline = dto.headline?.takeIf { it.isNotEmpty() },
        category = dto.category?.rawValue ?: "other",
        createdAt = BackendDate.parse(dto.createdAt) ?: BackendDate.distantPast,
        conversationID = dto.conversationId,
        visibility = Memory.Visibility.from(dto.visibility) ?: Memory.Visibility.Private,
        isBaseline = dto.isBaseline ?: false,
        reviewed = dto.reviewed ?: false,
        userReview = dto.userReview,
        captureDevice = dto.primaryCaptureDevice?.takeIf { it.isNotEmpty() },
        isLocked = dto.isLocked ?: false,
        veracity = dto.veracity,
        captureConfidence = dto.captureConfidence,
        uncertaintyReasons = dto.uncertaintyReasons ?: emptyList(),
        subjectAttribution = dto.subjectAttribution?.takeIf { it != OmiAPI.SubjectAttribution._unknown }?.rawValue,
        subjectName = subjectName(dto.arguments),
        evidence = dto.evidence.orEmpty().map {
            Memory.Evidence(sourceType = it.sourceType ?: "unknown", sourceID = it.sourceId, capturedAt = BackendDate.parse(it.capturedAt))
        },
    )

    /** The person a fact is about, when its arguments name one. */
    fun subjectName(arguments: Map<String, JsonElement>?): String? {
        if (arguments == null) return null
        for (key in listOf("subject_name", "subject", "person", "name", "who")) {
            val value = (arguments[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull ?: continue
            val trimmed = value.trim()
            if (trimmed.isNotEmpty() && trimmed.length <= 40 && trimmed.lowercase() != "user") return trimmed
        }
        return null
    }
}
