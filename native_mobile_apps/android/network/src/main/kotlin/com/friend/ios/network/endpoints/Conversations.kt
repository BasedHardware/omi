package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.ConversationPerson
import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.core.models.ConversationDigest
import com.friend.ios.core.models.ConversationFilter
import com.friend.ios.core.models.ConversationLocation
import com.friend.ios.core.models.ConversationQuery
import com.friend.ios.core.models.DailySummary
import com.friend.ios.core.models.Folder
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import com.friend.ios.network.await
import com.friend.ios.network.generated.OmiAPI
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import java.io.IOException
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.concurrent.TimeUnit

/**
 * Port of `APIClient+Conversations.swift`, the list half of `APIClient+ConversationActions.swift`
 * and `APIClient+ConversationExtras.swift`, and the conversation and recap calls of
 * `APIClient+Edits.swift` (contracts: `backend/routers/conversations.py`, `folders.py`, `users.py`).
 * The conversation detail's calls live next to it: audio, transcript edits, summary templates,
 * calendar links and photos in `ConversationExtras.kt`; summary edits, folder drafts, capture gaps
 * and the summary feedback in `ConversationContent.kt` and `ConversationExtras.kt`.
 */
interface ConversationsAPI {
    /** `GET v1/conversations`, same query as the Flutter app's `getConversations`. */
    suspend fun conversations(limit: Int, offset: Int): List<Conversation>

    /** `GET v1/conversations/{id}` */
    suspend fun conversationDetail(id: String): ConversationDetail

    /** `GET v1/conversations` with `starred=true` or `folder_id=`. */
    suspend fun conversations(limit: Int, offset: Int, filter: ConversationFilter): List<Conversation>

    /** `GET v1/conversations` with discarded ones and/or a date range (`start_date`/`end_date`, inclusive). */
    suspend fun conversations(limit: Int, offset: Int, query: ConversationQuery): List<Conversation>

    /** `PATCH v1/conversations/{id}/starred?starred=`. */
    suspend fun setConversationStarred(id: String, starred: Boolean)

    /** `PATCH v1/conversations/{id}/visibility?value=shared|private`. */
    suspend fun setConversationVisibility(id: String, visibility: Conversation.Visibility)

    /** `POST v1/conversations/{id}/reprocess`: summarizes again; returns the new conversation. */
    suspend fun reprocessConversation(id: String): ConversationDetail

    /**
     * `POST v1/conversations/merge`: starts merging in the background (the sources turn `merging`,
     * then are replaced by one new conversation). Returns the backend's warning, if any.
     */
    suspend fun mergeConversations(ids: List<String>): String?

    /** `GET v1/folders` (creating, editing and deleting folders: `ConversationContentAPI`). */
    suspend fun folders(): List<Folder>

    /** `PATCH v1/conversations/{id}/folder`; null takes it out of every folder. */
    suspend fun moveConversation(id: String, toFolder: String?)

    /** `POST v1/folders/{id}/conversations/bulk-move`. */
    suspend fun moveConversations(ids: List<String>, toFolder: String)

    /** `PATCH v1/conversations/{id}/title?title=`. */
    suspend fun renameConversation(id: String, title: String)

    /** `DELETE v1/conversations/{id}`. */
    suspend fun deleteConversation(id: String)

    /** `GET v1/users/daily-summaries`, newest first. */
    suspend fun dailySummaries(limit: Int): List<DailySummary>

    /** `POST v1/users/daily-summaries`: the recap for a local date, generated if there is none yet. */
    suspend fun createDailySummary(date: String): DailySummary?

    /** `DELETE v1/users/daily-summaries/{id}`; a recap already gone counts as deleted. */
    suspend fun deleteDailySummary(id: String)
}

internal class ConversationsEndpoints(private val http: HttpCore) : ConversationsAPI {
    private val list = ListSerializer(OmiAPI.Conversation.serializer())

    override suspend fun conversations(limit: Int, offset: Int): List<Conversation> {
        val text = http.data(
            Method.GET, "v1/conversations",
            query = listOf("include_discarded" to "false", "limit" to "$limit", "offset" to "$offset", "statuses" to "processing,completed"),
        )
        return http.decode(list, text).map(ConversationMapper::map)
    }

    override suspend fun conversationDetail(id: String): ConversationDetail {
        val text = http.data(Method.GET, "v1/conversations/$id")
        return ConversationMapper.detail(http.decode(OmiAPI.Conversation.serializer(), text))
    }

    override suspend fun conversations(limit: Int, offset: Int, filter: ConversationFilter): List<Conversation> {
        val query = mutableListOf("include_discarded" to "false", "limit" to "$limit", "offset" to "$offset", "statuses" to "processing,completed")
        when (filter) {
            ConversationFilter.All -> Unit
            ConversationFilter.Starred -> query += "starred" to "true"
            is ConversationFilter.Folder -> query += "folder_id" to filter.id
        }
        return http.decode(list, http.data(Method.GET, "v1/conversations", query = query)).map(ConversationMapper::map)
    }

    override suspend fun conversations(limit: Int, offset: Int, query: ConversationQuery): List<Conversation> {
        val items = mutableListOf(
            "include_discarded" to "${query.includeDiscarded}", "limit" to "$limit", "offset" to "$offset", "statuses" to "processing,completed",
        )
        when (val filter = query.filter) {
            ConversationFilter.All -> Unit
            ConversationFilter.Starred -> items += "starred" to "true"
            is ConversationFilter.Folder -> items += "folder_id" to filter.id
        }
        query.start?.let { items += "start_date" to utc(it) }
        query.end?.let { items += "end_date" to utc(it) }
        return http.decode(list, http.data(Method.GET, "v1/conversations", query = items)).map(ConversationMapper::map)
    }

    override suspend fun setConversationStarred(id: String, starred: Boolean) {
        http.data(Method.PATCH, "v1/conversations/$id/starred", query = listOf("starred" to "$starred"))
    }

    override suspend fun setConversationVisibility(id: String, visibility: Conversation.Visibility) {
        http.data(Method.PATCH, "v1/conversations/$id/visibility", query = listOf("value" to visibility.rawValue))
    }

    override suspend fun reprocessConversation(id: String): ConversationDetail {
        val request = http.request(Method.POST, "v1/conversations/$id/reprocess")
        // Processing runs the summary models inline.
        val long = http.client.newBuilder().callTimeout(120, TimeUnit.SECONDS).readTimeout(120, TimeUnit.SECONDS).build()
        val response = try {
            long.newCall(request).await()
        } catch (e: IOException) {
            throw APIError.Transport(e.message ?: e.toString())
        }
        val text = response.use {
            val body = withContext(Dispatchers.IO) { it.body?.string().orEmpty() }
            if (it.code !in 200..299) throw APIError.Http(it.code, body.take(500))
            body
        }
        return ConversationMapper.detail(http.decode(OmiAPI.Conversation.serializer(), text))
    }

    override suspend fun mergeConversations(ids: List<String>): String? {
        val body = buildJsonObject {
            put("conversation_ids", buildJsonArray { ids.forEach { add(JsonPrimitive(it)) } })
            put("reprocess", true)
        }
        val text = http.data(Method.POST, "v1/conversations/merge", body = Body.Json(body.toString()))
        return (runCatching { http.decode(JsonObject.serializer(), text) }.getOrNull()?.get("warning") as? JsonPrimitive)?.contentOrNull
    }

    override suspend fun folders(): List<Folder> {
        val text = http.data(Method.GET, "v1/folders")
        return (http.decode(JsonElement.serializer(), text) as? JsonArray).orEmpty()
            .mapNotNull { (it as? JsonObject)?.let(FolderMapper::map) }
            .sortedBy { it.order }
    }

    override suspend fun moveConversation(id: String, toFolder: String?) {
        val body = buildJsonObject { put("folder_id", toFolder?.let(::JsonPrimitive) ?: JsonNull) }
        http.data(Method.PATCH, "v1/conversations/$id/folder", body = Body.Json(body.toString()))
    }

    override suspend fun moveConversations(ids: List<String>, toFolder: String) {
        val body = buildJsonObject { put("conversation_ids", buildJsonArray { ids.forEach { add(JsonPrimitive(it)) } }) }
        http.data(Method.POST, "v1/folders/$toFolder/conversations/bulk-move", body = Body.Json(body.toString()))
    }

    override suspend fun renameConversation(id: String, title: String) {
        http.data(Method.PATCH, "v1/conversations/$id/title", query = listOf("title" to title))
    }

    override suspend fun deleteConversation(id: String) {
        http.data(Method.DELETE, "v1/conversations/$id")
    }

    override suspend fun dailySummaries(limit: Int): List<DailySummary> {
        val text = http.data(Method.GET, "v1/users/daily-summaries", query = listOf("limit" to "$limit"))
        val root = http.decode(JsonElement.serializer(), text) as? JsonObject
        return (root?.get("summaries") as? JsonArray).orEmpty().mapNotNull { (it as? JsonObject)?.let(DailySummaryMapper::map) }
    }

    override suspend fun createDailySummary(date: String): DailySummary? {
        val text = http.data(Method.POST, "v1/users/daily-summaries", body = Body.Json(buildJsonObject { put("date", date) }.toString()))
        return (http.decode(JsonElement.serializer(), text) as? JsonObject)?.let(DailySummaryMapper::map)
    }

    override suspend fun deleteDailySummary(id: String) {
        try {
            http.data(Method.DELETE, "v1/users/daily-summaries/$id")
        } catch (e: APIError.Http) {
            if (e.status != 404) throw e
        }
    }

    companion object {
        /** `ConversationExtras.utc`: the backend's date filter in UTC, ISO-8601 without fractions. */
        internal fun utc(date: Instant): String = DateTimeFormatter.ISO_INSTANT.format(date.atOffset(ZoneOffset.UTC).withNano(0))
    }
}

/** Port of `ConversationMapper.swift`. */
internal object ConversationMapper {
    fun map(dto: OmiAPI.Conversation): Conversation {
        val structured = dto.structured
        return Conversation(
            id = dto.id,
            title = structured.title?.takeIf { it.isNotEmpty() } ?: "",
            overview = structured.overview ?: "",
            emoji = structured.emoji?.takeIf { it.isNotEmpty() },
            category = structured.category?.rawValue,
            createdAt = BackendDate.parse(dto.createdAt) ?: BackendDate.distantPast,
            startedAt = BackendDate.parse(dto.startedAt),
            finishedAt = BackendDate.parse(dto.finishedAt),
            status = status(dto.status),
            isStarred = dto.starred ?: false,
            actionItemCount = structured.actionItems?.size ?: 0,
            folderID = dto.folderId,
            visibility = visibility(dto.visibility),
            isLocked = dto.isLocked ?: false,
            summaryRetryable = dto.summaryRetryable ?: false,
            location = dto.geolocation?.let { ConversationLocation(it.latitude, it.longitude, it.address, it.googlePlaceId) },
            isDiscarded = dto.discarded ?: false,
            captureGroupID = if ((dto.captureGroup?.members?.size ?: 0) > 1) dto.captureGroup?.id else null,
            captureGroupPrimaryID = dto.captureGroup?.primaryId,
            people = people(structured.participants.orEmpty(), dto.calendarEvent),
        )
    }

    /**
     * Participants first (they carry organizations), then calendar attendees. An attendee entry is
     * a display name or an address; `attendee_emails` fills in the address when it is a name.
     */
    fun people(participants: List<OmiAPI.Participant>, event: OmiAPI.CalendarEventLink?): List<ConversationPerson> {
        val fromSummary = participants.filter { it.isAiAgent != true }.map {
            ConversationPerson(it.name?.takeIf(String::isNotBlank), it.email?.takeIf(String::isNotBlank), it.organization?.takeIf(String::isNotBlank))
        }
        val emails = event?.attendeeEmails.orEmpty().toMutableList()
        val fromCalendar = event?.attendees.orEmpty().map { entry ->
            if ("@" in entry) {
                emails.remove(entry)
                ConversationPerson(null, entry, null)
            } else {
                val first = entry.substringBefore(" ").lowercase()
                val email = emails.firstOrNull { it.substringBefore("@").lowercase().startsWith(first) }?.also { emails.remove(it) }
                ConversationPerson(entry, email, null)
            }
        } + emails.map { ConversationPerson(null, it, null) }
        val known = fromSummary.mapNotNull { it.email?.lowercase() }.toSet()
        return fromSummary + fromCalendar.filter { it.email?.lowercase() !in known }
    }

    fun status(status: OmiAPI.ConversationStatus?): Conversation.Status = when (status) {
        OmiAPI.ConversationStatus.in_progress -> Conversation.Status.InProgress
        OmiAPI.ConversationStatus.processing -> Conversation.Status.Processing
        OmiAPI.ConversationStatus.merging -> Conversation.Status.Merging
        OmiAPI.ConversationStatus.completed, null -> Conversation.Status.Completed
        OmiAPI.ConversationStatus.failed -> Conversation.Status.Failed
        OmiAPI.ConversationStatus._unknown -> Conversation.Status.Unknown
    }

    fun visibility(visibility: OmiAPI.ConversationVisibility?): Conversation.Visibility = when (visibility) {
        OmiAPI.ConversationVisibility.shared -> Conversation.Visibility.Shared
        OmiAPI.ConversationVisibility.public_ -> Conversation.Visibility.Public
        else -> Conversation.Visibility.Private
    }

    fun detail(dto: OmiAPI.Conversation): ConversationDetail {
        val structured = dto.structured
        val apps = dto.appsResults.orEmpty()
            .map { ConversationDetail.AppSummary(it.appId, it.content.trim()) }
            .filter { it.content.isNotEmpty() }
        val events = structured.events.orEmpty().map { event ->
            ConversationDetail.Event(
                title = event.title, description = event.description_ ?: "",
                start = BackendDate.parse(event.start), duration = event.duration ?: 30, isCreated = event.created ?: false,
            )
        }
        val conversation = map(dto)
        return ConversationDetail(
            conversation = conversation,
            summaryActionItems = structured.actionItems.orEmpty().map { it.description_ }.filter { it.isNotEmpty() },
            transcript = transcript(dto.transcriptSegments.orEmpty()),
            summary = apps.firstOrNull()?.content ?: summary(structured.overview, structured.sections.orEmpty()),
            // Only for Omi's own summary: an app's result has no gist of its own. The gist comes with
            // the generated sections; an edited summary drops them, and its old gist with them.
            gist = if (apps.isEmpty() && structured.sections.orEmpty().isNotEmpty()) gist(structured.shortSummary) else null,
            otherSummaries = apps.drop(1),
            keyPoints = structured.insights.orEmpty().map { it.text }.filter { it.isNotEmpty() },
            // Indexes stay the backend's (`PATCH .../events` addresses events by position).
            events = events,
            hasAudio = dto.audioFiles.orEmpty().isNotEmpty() || dto.conversationAudio != null,
            summaryAppID = apps.firstOrNull()?.appID,
            // An app's result is shown instead of Omi's own summary.
            summaryIsOmiOwn = apps.isEmpty(),
            calendarEvent = dto.calendarEvent?.let(::calendarEvent),
            photos = photos(dto.photos.orEmpty()),
            recordings = recordings(dto, conversation),
            audioParts = audioParts(dto.audioFiles.orEmpty()),
            participantSpeakerIDs = dto.speakerResolution?.let { if (it.status == "unavailable") null else it.participantSpeakerIds ?: emptyList() },
            actionItemSources = actionItemSources(structured.actionItems.orEmpty()),
            chapters = chapters(structured.sections.orEmpty()),
        )
    }

    fun transcript(segments: List<OmiAPI.TranscriptSegment>): List<ConversationDetail.Line> = segments.mapIndexed { index, segment ->
        ConversationDetail.Line(
            id = index,
            speaker = if (segment.isUser) "You" else speakerName(segment),
            isUser = segment.isUser,
            text = segment.text,
            start = segment.start,
            segmentID = segment.id,
            speakerID = segment.speakerId,
            personID = segment.personId,
        )
    }

    /** The stored audio pieces, oldest first. */
    fun audioParts(files: List<OmiAPI.AudioFile>): List<com.friend.ios.core.models.AudioPart> = files
        .map { com.friend.ios.core.models.AudioPart(it.id, com.friend.ios.core.models.AudioPart.Status.Unavailable, null, it.duration, BackendDate.parse(it.startedAt)) }
        .sortedBy { it.startedAt ?: Instant.MAX }

    /** Inline bytes when the photo carries them; stored ones are fetched by id. */
    fun photos(photos: List<OmiAPI.ConversationPhoto>): List<com.friend.ios.core.models.ConversationPhoto> = photos.mapIndexed { index, photo ->
        com.friend.ios.core.models.ConversationPhoto(
            id = photo.id ?: "photo-$index",
            data = if (photo.base64.isEmpty()) null else runCatching { java.util.Base64.getMimeDecoder().decode(photo.base64) }.getOrNull(),
            description = photo.description_?.takeIf { it.isNotEmpty() },
            isDiscarded = photo.discarded ?: false,
            isStored = photo.storageId != null,
        )
    }

    fun calendarEvent(dto: OmiAPI.CalendarEventLink): com.friend.ios.core.models.CalendarEventLink? {
        val start = BackendDate.parse(dto.startTime) ?: return null
        val end = BackendDate.parse(dto.endTime) ?: return null
        return com.friend.ios.core.models.CalendarEventLink(
            eventID = dto.eventId, title = dto.title, attendees = dto.attendees.orEmpty(), attendeeEmails = dto.attendeeEmails.orEmpty(),
            start = start, end = end, htmlLink = dto.htmlLink,
        )
    }

    fun recordings(dto: OmiAPI.Conversation, conversation: Conversation): List<com.friend.ios.core.models.CaptureRecording> {
        val members = dto.captureGroup?.members.orEmpty().map {
            com.friend.ios.core.models.CaptureRecording(it.id, it.source, BackendDate.parse(it.startedAt), BackendDate.parse(it.finishedAt), isCurrent = false)
        }
        return com.friend.ios.core.models.CaptureRecording.list(
            members, conversation.id, dto.source?.rawValue, conversation.startedAt ?: conversation.createdAt, conversation.finishedAt,
        )
    }

    /** The notes' sections that cite transcript segments: the transcript's chapters. */
    fun chapters(sections: List<OmiAPI.Section>): List<ConversationDetail.Chapter> = sections.mapNotNull { section ->
        val heading = section.heading.trim()
        val ids = section.sourceSegmentIds
        if (heading.isEmpty() || ids.isNullOrEmpty()) null else ConversationDetail.Chapter(heading, ids)
    }

    /** Each extracted action item's context and cited segments, keyed by its description. */
    fun actionItemSources(items: List<OmiAPI.ActionItem>): Map<String, ConversationDetail.ActionItemSource> {
        val sources = LinkedHashMap<String, ConversationDetail.ActionItemSource>()
        for (item in items) {
            if (item.description_.isEmpty()) continue
            val source = ConversationDetail.ActionItemSource(item.context ?: "", item.sourceSegmentIds ?: emptyList())
            if (source.context.isEmpty() && source.segmentIDs.isEmpty()) continue
            sources[ConversationDigest.normalized(item.description_)] = source
        }
        return sources
    }

    fun gist(text: String?): String? = (text ?: "").trim().ifEmpty { null }

    /** The overview, else the sections as Markdown (`## heading` + body; heading-only sections dropped). */
    fun summary(overview: String?, sections: List<OmiAPI.Section>): String {
        val text = (overview ?: "").trim()
        if (text.isNotEmpty()) return text
        return sections.mapNotNull { section ->
            val body = section.bodyMarkdown.trim()
            if (body.isEmpty()) return@mapNotNull null
            val heading = section.heading.trim()
            if (heading.isEmpty()) body else "## $heading\n\n$body"
        }.joinToString("\n\n")
    }

    fun speakerName(segment: OmiAPI.TranscriptSegment): String {
        segment.speakerId?.let { return "Speaker ${it + 1}" }
        return segment.speaker ?: "Speaker"
    }
}

/** `FolderMapper`. */
internal object FolderMapper {
    fun map(json: JsonObject): Folder? {
        val id = json.string("id") ?: return null
        val name = json.string("name") ?: return null
        return Folder(
            id = id, name = name,
            icon = json.string("icon") ?: "📁",
            color = json.string("color") ?: "#6B7280",
            description = json.string("description") ?: "",
            isSystem = (json["is_system"] as? JsonPrimitive)?.booleanOrNull ?: false,
            order = (json["order"] as? JsonPrimitive)?.intOrNull ?: 0,
            conversationCount = (json["conversation_count"] as? JsonPrimitive)?.intOrNull ?: 0,
        )
    }
}

/** `DailySummaryMapper`. */
internal object DailySummaryMapper {
    fun map(json: JsonObject): DailySummary? {
        val id = json.string("id") ?: return null
        val date = json.string("date") ?: return null
        val highlights = (json["highlights"] as? JsonArray).orEmpty().mapNotNull { element ->
            val item = element as? JsonObject ?: return@mapNotNull null
            val topic = item.string("topic") ?: return@mapNotNull null
            DailySummary.Highlight(topic, item.string("emoji"), item.string("summary") ?: "")
        }
        val decisions = (json["decisions_made"] as? JsonArray).orEmpty().mapNotNull { (it as? JsonObject)?.string("decision") }
        val stats = json["stats"] as? JsonObject
        return DailySummary(
            id = id, date = date,
            headline = json.string("headline") ?: "",
            overview = json.string("overview") ?: "",
            emoji = json.string("day_emoji"),
            conversationCount = (stats?.get("total_conversations") as? JsonPrimitive)?.intOrNull,
            highlights = highlights, decisions = decisions,
        )
    }
}

/** `json[key] as? String`. */
