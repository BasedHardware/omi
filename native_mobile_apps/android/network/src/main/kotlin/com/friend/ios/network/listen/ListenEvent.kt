package com.friend.ios.network.listen

import com.friend.ios.network.endpoints.JsonAccess
import com.friend.ios.network.endpoints.bool
import com.friend.ios.network.endpoints.double
import com.friend.ios.network.endpoints.int
import com.friend.ios.network.endpoints.obj
import com.friend.ios.network.endpoints.objects
import com.friend.ios.network.endpoints.string
import com.friend.ios.network.endpoints.strings
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject

/**
 * One live transcript segment from `/v4/listen`. Segments are re-sent with the same id when the
 * backend refines them, so clients upsert by id.
 */
data class LiveSegment(
    val id: String,
    val text: String,
    val speaker: String?,
    val speakerID: Int?,
    val isUser: Boolean,
    val start: Double,
    val end: Double,
    /** The person the backend matched this voice to (`person_id`). */
    val personID: String? = null,
    /** The backend's translations into the primary language (`translating`, Automatic translation). */
    val translations: List<Translation> = emptyList(),
) {
    /** One translated text (backend `models/transcript_segment.py` `Translation`). */
    data class Translation(val lang: String, val text: String)

    companion object {
        /** The Swift `init(from:)`: tolerant, every field optional. */
        fun from(json: JsonObject): LiveSegment {
            val text = json.string("text") ?: ""
            val start = json.double("start") ?: 0.0
            return LiveSegment(
                id = json.string("id") ?: "$start-${text.hashCode()}",
                text = text,
                speaker = json.string("speaker"),
                speakerID = json.int("speaker_id"),
                isUser = json.bool("is_user") ?: false,
                start = start,
                end = json.double("end") ?: start,
                personID = json.string("person_id")?.takeIf { it.isNotEmpty() },
                translations = json.objects("translations").mapNotNull { item ->
                    val lang = item.string("lang") ?: return@mapNotNull null
                    Translation(lang, item.string("text") ?: return@mapNotNull null)
                },
            )
        }
    }
}

/** Server -> client messages on `/v4/listen` (backend `models/message_event.py`). */
sealed interface ListenEvent {
    data class Segments(val segments: List<LiveSegment>) : ListenEvent

    /** `service_status`: initiating, stt_initiating, ready, stt_failed ... */
    data class Status(val status: String) : ListenEvent

    /** The live conversation id (`conversation_session`). */
    data class ConversationStarted(val id: String) : ListenEvent

    data class ProcessingStarted(val conversationID: String) : ListenEvent

    /** `memory_created`: the conversation is finalized. */
    data class ConversationCreated(val id: String) : ListenEvent

    data class SegmentsDeleted(val ids: List<String>) : ListenEvent

    /** `translating`: segments sent again with their translations (only the translations are new). */
    data class Translated(val segments: List<LiveSegment>) : ListenEvent

    /**
     * `freemium_threshold_reached`: the plan's transcription minutes run out soon (or did, at 0).
     * [requiresOnDevice]: the backend asks the app to transcribe on the phone (`setup_on_device_stt`).
     */
    data class FreemiumThreshold(val remainingSeconds: Int, val requiresOnDevice: Boolean) : ListenEvent

    data class Other(val type: String) : ListenEvent

    companion object {
        /** Parses one text frame. Arrays are segments; objects are typed events; `"ping"` is null. */
        fun parse(text: String): ListenEvent? {
            if (text == "ping") return null
            val element = JsonAccess.parse(text) ?: return null
            if (element is JsonArray) return Segments(element.mapNotNull { (it as? JsonObject)?.let(LiveSegment::from) })
            val json = element as? JsonObject ?: return null
            val type = json.string("type") ?: return null
            return when (type) {
                // Older backends announced the threshold as a status (Flutter still accepts both).
                "service_status" ->
                    if (json.string("status") == "freemium_threshold_reached") freemium(json) else Status(json.string("status") ?: "unknown")
                "freemium_threshold_reached" -> freemium(json)
                "translating" -> Translated(json.objects("segments").map(LiveSegment::from))
                "conversation_session" -> json.string("conversation_id")?.let(::ConversationStarted)
                "memory_processing_started" -> json.string("conversation_id")?.let(::ProcessingStarted)
                "memory_created" -> (json.string("conversation_id") ?: json.obj("memory")?.string("id"))?.let(::ConversationCreated)
                "segments_deleted" -> SegmentsDeleted(json.strings("segment_ids"))
                else -> Other(type)
            }
        }

        private fun freemium(json: JsonObject) = FreemiumThreshold(
            remainingSeconds = json.int("remaining_seconds") ?: 0,
            requiresOnDevice = json.string("action") == "setup_on_device_stt",
        )
    }
}
