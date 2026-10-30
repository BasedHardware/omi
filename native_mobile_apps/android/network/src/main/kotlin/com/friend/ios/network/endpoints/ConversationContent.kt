package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.CaptureGap
import com.friend.ios.core.models.Folder
import com.friend.ios.core.models.FolderDraft
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

/**
 * Port of `APIClient+ConversationContent.swift`: editing what a conversation says and how the list
 * is organized: the summary text, folders with their look, and the meetings Omi did not capture.
 * Contracts from `backend/routers/conversations.py`, `folders.py` and `google_calendar.py`.
 *
 * Capture gaps have no screen on iOS, so this port has none either: the model and the call are the
 * deliverable (`docs/PARITY.md`).
 */
interface ConversationContentAPI {
    /** `appID` `null` edits Omi's own summary; otherwise that app's result. */
    suspend fun updateConversationSummary(conversationID: String, appID: String?, content: String)

    /** Calendar meetings in `[from, to]` without a kept conversation; empty without a calendar. */
    suspend fun captureGaps(from: Instant, to: Instant): List<CaptureGap>

    /** `POST v1/folders`. */
    suspend fun createFolder(draft: FolderDraft): Folder

    /** `PATCH v1/folders/{id}` with the edited fields. */
    suspend fun updateFolder(id: String, draft: FolderDraft): Folder

    /** `moveTo` null: the folder's conversations leave every folder. */
    suspend fun deleteFolder(id: String, moveTo: String?)
}

internal class ConversationContentEndpoints(private val http: HttpCore) : ConversationContentAPI {
    /**
     * `PATCH v1/conversations/{id}/summary` `{app_id, content}` (the backend drops the generated
     * sections when Omi's own summary changes).
     */
    override suspend fun updateConversationSummary(conversationID: String, appID: String?, content: String) {
        val body = buildJsonObject {
            put("app_id", appID?.let(::JsonPrimitive) ?: JsonNull)
            put("content", content)
        }
        http.data(Method.PATCH, "v1/conversations/$conversationID/summary", body = Body.Json(body.toString()))
    }

    /**
     * `GET v1/calendar/capture-gaps?start=&end=` (at most 31 days). A 400 means no Google Calendar
     * is connected: nothing was missed that Omi could know about.
     */
    override suspend fun captureGaps(from: Instant, to: Instant): List<CaptureGap> {
        val query = listOf("start" to utc(from), "end" to utc(to))
        val text = try {
            http.data(Method.GET, "v1/calendar/capture-gaps", query = query)
        } catch (e: APIError.Http) {
            if (e.status == 400) return emptyList()
            throw e
        }
        return JsonAccess.array(text).mapNotNull { (it as? JsonObject)?.let(ConversationContentMapper::captureGap) }
    }

    override suspend fun createFolder(draft: FolderDraft): Folder {
        val text = http.data(Method.POST, "v1/folders", body = Body.Json(ConversationContentMapper.folderBody(draft)))
        return ConversationContentMapper.folder(text)
    }

    override suspend fun updateFolder(id: String, draft: FolderDraft): Folder {
        val text = http.data(Method.PATCH, "v1/folders/$id", body = Body.Json(ConversationContentMapper.folderBody(draft)))
        return ConversationContentMapper.folder(text)
    }

    override suspend fun deleteFolder(id: String, moveTo: String?) {
        val query = moveTo?.let { listOf("move_to_folder_id" to it) } ?: emptyList()
        http.data(Method.DELETE, "v1/folders/$id", query = query)
    }

    companion object {
        /** `ConversationExtras.utc`: ISO-8601 in UTC, without fractions. */
        private fun utc(date: Instant): String = DateTimeFormatter.ISO_INSTANT.format(date.atOffset(ZoneOffset.UTC).withNano(0))
    }
}

/** Port of `ConversationContentMapper`. */
internal object ConversationContentMapper {
    fun captureGap(json: JsonObject): CaptureGap? {
        val id = json.string("event_id") ?: return null
        val start = BackendDate.parse(json.string("start_time")) ?: return null
        val end = BackendDate.parse(json.string("end_time")) ?: return null
        val title = (json.string("title") ?: "").trim()
        return CaptureGap(id = id, title = title, start = start, end = end)
    }

    fun folderBody(draft: FolderDraft): String = buildJsonObject {
        put("name", draft.name)
        put("icon", draft.icon)
        put("color", draft.color)
        put("description", draft.description)
    }.toString()

    fun folder(text: String): Folder = FolderMapper.map(JsonAccess.obj(text)) ?: throw APIError.Decoding("folder")
}
