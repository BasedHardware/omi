package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.core.models.Person
import com.friend.ios.core.models.SpeakerRejection
import com.friend.ios.core.models.SpeakerTarget
import com.friend.ios.core.models.VoiceMatch
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import com.friend.ios.network.generated.OmiAPI
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.Base64
import java.util.Locale

/**
 * Port of the transcript-labels half of `APIClient+Speakers.swift` (naming voices in a
 * transcript, voice matches, clips); the people and voice-settings half is [SpeakersAPI]
 * (backend `routers/conversations.py`, `speaker_labels.py`, `speaker_tag_prompts.py`, `users.py`).
 */
interface TranscriptLabelsAPI {
    /** `POST v1/users/people` (idempotent by name): the stored person. */
    suspend fun createPerson(named: String): Person

    /**
     * Names lines: `PATCH .../assign-speaker/{speaker}` for every line of a voice, otherwise
     * `PATCH .../segments/assign-bulk`. Returns the updated conversation.
     */
    suspend fun assignSpeaker(conversationID: String, segmentIDs: List<String>, speakerID: Int?, to: SpeakerTarget): ConversationDetail

    /** `POST v1/conversations/{id}/speakers/{speaker}/reject`: the label on this voice is wrong. */
    suspend fun rejectSpeaker(conversationID: String, speakerID: Int, kind: SpeakerRejection, personID: String?, segmentIDs: List<String>?): ConversationDetail

    /** `GET v1/users/people/{id}/voice-matches`: unnamed voices in recent conversations that sound like them. */
    suspend fun voiceMatches(personID: String): List<VoiceMatch>

    /** `GET v1/speaker-tag-prompts/clip`: up to 12 s of the user's own stored audio, as WAV bytes. */
    suspend fun speakerClip(conversationID: String, start: Double, end: Double): ByteArray
}

internal class TranscriptLabelsEndpoints(private val http: HttpCore) : TranscriptLabelsAPI {
    override suspend fun createPerson(named: String): Person {
        val text = http.data(Method.POST, "v1/users/people", body = Body.Json(buildJsonObject { put("name", named) }.toString()))
        return PersonMapper.map(JsonAccess.obj(text)) ?: throw APIError.Decoding("person")
    }

    override suspend fun assignSpeaker(conversationID: String, segmentIDs: List<String>, speakerID: Int?, to: SpeakerTarget): ConversationDetail {
        val (type, value) = when (to) {
            SpeakerTarget.User -> "is_user" to "true"
            is SpeakerTarget.Person -> "person_id" to to.id
        }
        val body = buildJsonObject {
            put("segment_ids", buildJsonArray { segmentIDs.forEach { add(JsonPrimitive(it)) } })
            put("assign_type", type)
            put("value", value)
        }
        val text = if (speakerID != null) {
            http.data(
                Method.PATCH, "v1/conversations/$conversationID/assign-speaker/$speakerID",
                query = listOf("assign_type" to type, "value" to value), body = Body.Json(body.toString()),
            )
        } else {
            http.data(Method.PATCH, "v1/conversations/$conversationID/segments/assign-bulk", body = Body.Json(body.toString()))
        }
        return ConversationMapper.detail(http.decode(OmiAPI.Conversation.serializer(), text))
    }

    override suspend fun rejectSpeaker(conversationID: String, speakerID: Int, kind: SpeakerRejection, personID: String?, segmentIDs: List<String>?): ConversationDetail {
        val body = buildJsonObject {
            put("kind", kind.rawValue)
            personID?.let { put("person_id", it) }
            segmentIDs?.let { ids -> put("segment_ids", buildJsonArray { ids.forEach { add(JsonPrimitive(it)) } }) }
        }
        val text = http.data(Method.POST, "v1/conversations/$conversationID/speakers/$speakerID/reject", body = Body.Json(body.toString()))
        return ConversationMapper.detail(http.decode(OmiAPI.Conversation.serializer(), text))
    }

    override suspend fun voiceMatches(personID: String): List<VoiceMatch> =
        http.jsonObject(Method.GET, "v1/users/people/$personID/voice-matches").objects("matches").mapNotNull(TranscriptLabelsMapper::voiceMatch)

    override suspend fun speakerClip(conversationID: String, start: Double, end: Double): ByteArray {
        val query = listOf(
            "conversation_id" to conversationID,
            "start" to String.format(Locale.ROOT, "%.3f", start),
            "end" to String.format(Locale.ROOT, "%.3f", minOf(end, start + 12)),
        )
        val base64 = http.jsonObject(Method.GET, "v1/speaker-tag-prompts/clip", query = query).string("audio_base64") ?: throw APIError.Decoding("clip")
        return runCatching { Base64.getDecoder().decode(base64) }.getOrElse { throw APIError.Decoding("clip") }
    }
}

/** `SpeakerMapper.voiceMatch`. */
internal object TranscriptLabelsMapper {
    fun voiceMatch(item: JsonObject): VoiceMatch? {
        val conversationID = item.string("conversation_id") ?: return null
        val speakerID = item.int("speaker_id") ?: return null
        return VoiceMatch(
            conversationID = conversationID,
            title = item.string("title") ?: "",
            startedAt = BackendDate.parse(item.string("started_at")),
            speakerID = speakerID,
            talkSeconds = item.double("talk_seconds") ?: 0.0,
            segmentIDs = item.strings("segment_ids"),
            clipStart = item.double("clip_start") ?: 0.0,
            clipEnd = item.double("clip_end") ?: 0.0,
            isStrong = item.string("match_level") == "strong",
        )
    }
}
