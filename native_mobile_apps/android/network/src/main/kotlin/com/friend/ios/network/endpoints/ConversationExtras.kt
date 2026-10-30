package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.AudioPart
import com.friend.ios.core.models.CalendarEventCandidate
import com.friend.ios.core.models.CalendarEventLink
import com.friend.ios.core.models.ConversationAudio
import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.core.models.ConversationFeedbackKind
import com.friend.ios.core.models.ConversationScreenshot
import com.friend.ios.core.models.OmiApp
import com.friend.ios.core.models.SummaryFeedbackReason
import com.friend.ios.core.models.SummaryTemplateDraft
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import com.friend.ios.network.await
import com.friend.ios.network.generated.OmiAPI
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.time.Instant
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * Port of the detail half of `APIClient+ConversationActions.swift` (transcript edits, audio) and of
 * `APIClient+ConversationExtras.swift`: summary templates, calendar links, feedback, photos and
 * screenshots, other devices' recordings, the developer test prompt. Contracts from
 * `backend/routers/conversations.py`, `apps.py`, `users.py`, `google_calendar.py`,
 * `mobile_feedback.py`, `screen_frames.py` and `sync.py`.
 */
interface ConversationExtrasAPI {
    /** `PATCH v1/conversations/{id}/segments/text`. */
    suspend fun editTranscriptSegment(conversationID: String, segmentID: String, text: String)

    /** `GET v1/sync/audio/{id}/urls`: the conversation's playback file when it is built. */
    suspend fun conversationAudio(id: String): ConversationAudio

    /** `POST v1/sync/audio/{id}/precache`: builds the playback files in the background. */
    suspend fun precacheConversationAudio(id: String)

    /** `POST v1/conversations/{id}/reprocess?app_id=`: summarizes again with that app only. */
    suspend fun reprocessConversation(id: String, appID: String): ConversationDetail

    /** `GET v1/conversations/{id}/suggested-apps`: the apps Omi suggests for this conversation. */
    suspend fun suggestedSummaryApps(conversationID: String): List<OmiApp>

    /** `GET v2/apps/search?installed_apps=true`, kept to enabled apps that summarize conversations. */
    suspend fun summaryApps(): List<OmiApp>

    /** `PUT v1/users/preferences/app?app_id=`: the app future conversations are summarized with. */
    suspend fun setPreferredSummaryApp(id: String)

    /** `POST v1/app/generate-description-emoji`; Flutter's fallback when it fails. Returns (description, emoji). */
    suspend fun generateAppDescription(name: String, prompt: String): Pair<String, String>

    /** `POST v1/apps` (multipart `app_data` JSON + `file` icon): a private or public summary app. Returns its id. */
    suspend fun createSummaryApp(draft: SummaryTemplateDraft, description: String, icon: ByteArray): String

    /** `GET v1/calendar/google/events` between two times (30 at most). */
    suspend fun calendarEvents(from: Instant, to: Instant): List<CalendarEventCandidate>

    /** `POST v1/conversations/{id}/calendar-event` `{event_id}`. */
    suspend fun linkCalendarEvent(conversationID: String, eventID: String): CalendarEventLink

    /** `DELETE v1/conversations/{id}/calendar-event`. */
    suspend fun unlinkCalendarEvent(conversationID: String)

    /** `PATCH v1/conversations/{id}/events` `{events_idx, values}`: marks found events as added. */
    suspend fun setEventsCreated(conversationID: String, indexes: List<Int>, created: Boolean)

    /**
     * `POST v1/mobile/feedback`: +1, or -1 with a reason, about the summary or the recording
     * ([kind]). [feedbackID] is reused on retry; true when the backend's receipt says it was stored.
     */
    suspend fun sendConversationFeedback(
        conversationID: String,
        kind: ConversationFeedbackKind,
        helpful: Boolean,
        reason: SummaryFeedbackReason?,
        feedbackID: String,
    ): Boolean

    /** `POST v1/conversations/{id}/test-prompt` `{prompt}`: one summary with this prompt, not saved. */
    suspend fun testConversationPrompt(conversationID: String, prompt: String): String

    /** `GET v1/conversations/{id}/photos/{photo_id}/image`: a stored photo's bytes. */
    suspend fun conversationPhoto(conversationID: String, photoID: String): ByteArray

    /** `GET v1/conversations/{id}/screenshots`: banner first, then the strip. */
    suspend fun conversationScreenshots(conversationID: String): List<ConversationScreenshot>

    /** `DELETE v1/conversations/{id}/screenshots/{frame_id}`; returns what is left. */
    suspend fun deleteConversationScreenshot(conversationID: String, screenshotID: String): List<ConversationScreenshot>

    /** `POST v1/conversations/{id}/capture-group/separate`: that recording leaves its group for good. */
    suspend fun separateRecording(conversationID: String)
}

internal class ConversationExtrasEndpoints(private val http: HttpCore) : ConversationExtrasAPI {
    override suspend fun editTranscriptSegment(conversationID: String, segmentID: String, text: String) {
        val body = buildJsonObject {
            put("segment_id", segmentID)
            put("text", text)
        }
        http.data(Method.PATCH, "v1/conversations/$conversationID/segments/text", body = Body.Json(body.toString()))
    }

    override suspend fun conversationAudio(id: String): ConversationAudio =
        ConversationAudioMapper.map(JsonAccess.obj(http.data(Method.GET, "v1/sync/audio/$id/urls")))

    override suspend fun precacheConversationAudio(id: String) {
        http.data(Method.POST, "v1/sync/audio/$id/precache")
    }

    override suspend fun reprocessConversation(id: String, appID: String): ConversationDetail {
        val request = http.request(Method.POST, "v1/conversations/$id/reprocess", query = listOf("app_id" to appID))
        return ConversationMapper.detail(http.decode(OmiAPI.Conversation.serializer(), send(request, 120)))
    }

    override suspend fun suggestedSummaryApps(conversationID: String): List<OmiApp> =
        JsonAccess.obj(http.data(Method.GET, "v1/conversations/$conversationID/suggested-apps")).objects("suggested_apps").mapNotNull(AppsMapper::app)

    override suspend fun summaryApps(): List<OmiApp> {
        val text = http.data(Method.GET, "v2/apps/search", query = listOf("installed_apps" to "true", "offset" to "0", "limit" to "100"))
        return JsonAccess.obj(text).objects("data").mapNotNull(AppsMapper::app).filter { it.isEnabled && "memories" in it.capabilities }
    }

    override suspend fun setPreferredSummaryApp(id: String) {
        http.data(Method.PUT, "v1/users/preferences/app", query = listOf("app_id" to id))
    }

    override suspend fun generateAppDescription(name: String, prompt: String): Pair<String, String> {
        val body = buildJsonObject {
            put("name", name)
            put("prompt", prompt)
        }
        val json = JsonAccess.obj(http.data(Method.POST, "v1/app/generate-description-emoji", body = Body.Json(body.toString())))
        val description = json.string("description")?.takeIf { it.isNotEmpty() } ?: "A custom app that $prompt"
        val emoji = json.string("emoji")?.takeIf { it.isNotEmpty() } ?: "✨"
        return description to emoji
    }

    override suspend fun createSummaryApp(draft: SummaryTemplateDraft, description: String, icon: ByteArray): String {
        val app = buildJsonObject {
            put("name", draft.name.trim())
            put("description", description)
            put("capabilities", buildJsonArray { add(JsonPrimitive("memories")) })
            put("deleted", false)
            put("category", "conversation-analysis")
            put("private", !draft.isPublic)
            put("is_paid", false)
            put("price", 0.0)
            put("memory_prompt", draft.prompt.trim())
            put("thumbnails", JsonArray(emptyList()))
        }
        val multipart = MultipartBody.Builder("omi-${UUID.randomUUID()}")
            .setType(MultipartBody.FORM)
            .addFormDataPart("app_data", app.toString())
            .addFormDataPart("file", "icon.png", icon.toRequestBody("image/png".toMediaType()))
            .build()
        val request = http.request(Method.POST, "v1/apps").newBuilder().post(multipart).build()
        return JsonAccess.obj(send(request, 60)).string("app_id") ?: throw APIError.Decoding("app_id")
    }

    override suspend fun calendarEvents(from: Instant, to: Instant): List<CalendarEventCandidate> {
        val query = listOf("max_results" to "30", "time_min" to ConversationsEndpoints.utc(from), "time_max" to ConversationsEndpoints.utc(to))
        return JsonAccess.array(http.data(Method.GET, "v1/calendar/google/events", query = query))
            .mapNotNull { (it as? JsonObject)?.let(CalendarMapper::candidate) }
    }

    override suspend fun linkCalendarEvent(conversationID: String, eventID: String): CalendarEventLink {
        val body = buildJsonObject { put("event_id", eventID) }
        val text = http.data(Method.POST, "v1/conversations/$conversationID/calendar-event", body = Body.Json(body.toString()))
        return ConversationMapper.calendarEvent(http.decode(OmiAPI.CalendarEventLink.serializer(), text)) ?: throw APIError.Decoding("calendar_event")
    }

    override suspend fun unlinkCalendarEvent(conversationID: String) {
        http.data(Method.DELETE, "v1/conversations/$conversationID/calendar-event")
    }

    override suspend fun setEventsCreated(conversationID: String, indexes: List<Int>, created: Boolean) {
        val body = buildJsonObject {
            put("events_idx", buildJsonArray { indexes.forEach { add(JsonPrimitive(it)) } })
            put("values", buildJsonArray { indexes.forEach { _ -> add(JsonPrimitive(created)) } })
        }
        http.data(Method.PATCH, "v1/conversations/$conversationID/events", body = Body.Json(body.toString()))
    }

    override suspend fun sendConversationFeedback(
        conversationID: String,
        kind: ConversationFeedbackKind,
        helpful: Boolean,
        reason: SummaryFeedbackReason?,
        feedbackID: String,
    ): Boolean {
        val body = buildJsonObject {
            put("schema_version", "mobile_feedback.v1")
            put("feedback_id", feedbackID)
            put("kind", kind.rawValue)
            put("target_kind", "conversation")
            put("target_id", conversationID)
            put("value", if (helpful) 1 else -1)
            put("client_app_namespace", "omi-native-android")
            if (reason != null && !helpful) put("reason", reason.rawValue)
        }
        val receipt = JsonAccess.obj(http.data(Method.POST, "v1/mobile/feedback", body = Body.Json(body.toString())))
        return receipt.string("schema_version") == "mobile_feedback_receipt.v1" && receipt.bool("persisted") == true &&
            receipt.string("feedback_id") == feedbackID
    }

    override suspend fun testConversationPrompt(conversationID: String, prompt: String): String {
        val body = buildJsonObject { put("prompt", prompt) }
        val request = http.request(Method.POST, "v1/conversations/$conversationID/test-prompt", body = Body.Json(body.toString()))
        return JsonAccess.obj(send(request, 120)).string("summary") ?: ""
    }

    override suspend fun conversationPhoto(conversationID: String, photoID: String): ByteArray {
        val request = http.request(Method.GET, "v1/conversations/$conversationID/photos/$photoID/image")
        val response = try {
            http.client.newCall(request).await()
        } catch (e: IOException) {
            throw APIError.Transport(e.message ?: e.toString())
        }
        return response.use {
            val bytes = withContext(Dispatchers.IO) { it.body?.bytes() ?: ByteArray(0) }
            if (it.code !in 200..299) throw APIError.Http(it.code, String(bytes.take(500).toByteArray()))
            bytes
        }
    }

    override suspend fun conversationScreenshots(conversationID: String): List<ConversationScreenshot> =
        ScreenshotMapper.map(JsonAccess.obj(http.data(Method.GET, "v1/conversations/$conversationID/screenshots")))

    override suspend fun deleteConversationScreenshot(conversationID: String, screenshotID: String): List<ConversationScreenshot> =
        ScreenshotMapper.map(JsonAccess.obj(http.data(Method.DELETE, "v1/conversations/$conversationID/screenshots/$screenshotID")))

    override suspend fun separateRecording(conversationID: String) {
        http.data(Method.POST, "v1/conversations/$conversationID/capture-group/separate")
    }

    /** Sends a prepared request with a longer timeout and the usual status check. */
    private suspend fun send(request: Request, timeoutSeconds: Long): String {
        val client = http.client.newBuilder().callTimeout(timeoutSeconds, TimeUnit.SECONDS).readTimeout(timeoutSeconds, TimeUnit.SECONDS).build()
        val response = try {
            client.newCall(request).await()
        } catch (e: IOException) {
            throw APIError.Transport(e.message ?: e.toString())
        }
        return response.use {
            val text = withContext(Dispatchers.IO) { it.body?.string().orEmpty() }
            if (it.code !in 200..299) throw APIError.Http(it.code, text.take(500))
            text
        }
    }
}

internal object ConversationAudioMapper {
    /**
     * The dense conversation file first; one cached part also plays, several play in a row;
     * anything pending is polled.
     */
    fun map(json: JsonObject): ConversationAudio {
        val retry = (json.int("poll_after_ms") ?: 2000) / 1000.0
        val audio = json.obj("conversation_audio")
        if (audio != null && audio.string("status") == "cached") {
            audio.string("signed_url")?.let { return ConversationAudio.Ready(it, audio.double("duration")) }
        }
        val densePending = audio?.string("status") == "pending"
        val files = json.objects("audio_files")
        if (files.any { it.string("status") == "pending" }) return ConversationAudio.Pending(retry)
        val cached = files.mapNotNull { file ->
            val id = file.string("id") ?: return@mapNotNull null
            val url = file.string("signed_url") ?: return@mapNotNull null
            if (file.string("status") != "cached") return@mapNotNull null
            AudioPart(id, AudioPart.Status.Cached, url, file.double("duration") ?: 0.0, contentType = file.string("content_type"))
        }
        if (cached.size == 1) return ConversationAudio.Ready(cached[0].url!!, cached[0].duration.takeIf { it > 0 })
        // Several parts (Flutter's `ConcatenatingAudioSource` path); the store orders them by start.
        if (cached.size > 1) return ConversationAudio.Parts(cached)
        return if (densePending) ConversationAudio.Pending(retry) else ConversationAudio.Unavailable
    }
}

internal object CalendarMapper {
    fun candidate(json: JsonObject): CalendarEventCandidate? {
        val id = json.string("event_id") ?: return null
        val start = BackendDate.parse(json.string("start_time")) ?: return null
        val end = BackendDate.parse(json.string("end_time")) ?: return null
        return CalendarEventCandidate(id, json.string("title") ?: "", start, end, json.strings("attendees"))
    }
}

internal object ScreenshotMapper {
    /** `ConversationScreenFrameSet`: the banner, then the strip by rank. */
    fun map(json: JsonObject): List<ConversationScreenshot> {
        val banner = listOfNotNull(json.obj("banner"))
        val strip = json.objects("strip").sortedBy { it.int("rank") ?: 0 }
        return (banner + strip).mapNotNull { frame ->
            val id = frame.string("id") ?: return@mapNotNull null
            ConversationScreenshot(
                id = id,
                caption = frame.string("caption") ?: "",
                imageURL = frame.string("content_url"),
                thumbnailURL = frame.string("thumbnail_url"),
                capturedAt = BackendDate.parse(frame.string("captured_at")),
            )
        }
    }
}
