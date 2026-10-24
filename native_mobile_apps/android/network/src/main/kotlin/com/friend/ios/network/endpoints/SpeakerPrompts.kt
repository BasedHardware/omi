package com.friend.ios.network.endpoints

import java.util.Base64
import com.friend.ios.core.models.SpeakerPrompt
import com.friend.ios.core.models.SpeakerPromptAnswer
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import java.util.Locale

/**
 * Port of the "Who is this?" half of `APIClient+Speakers.swift` (backend `speaker_tag_prompts.py`).
 */
interface SpeakerPromptsAPI {
    /** `GET v1/speaker-tag-prompts`: today's few voices to confirm (empty while cooling down or disabled). */
    suspend fun speakerPrompts(): List<SpeakerPrompt>

    /** `POST v1/speaker-tag-prompts/shown`: starts the once-a-day cooldown. */
    suspend fun markSpeakerPromptsShown(ids: List<String>)

    /** `POST v1/speaker-tag-prompts/dismiss`: closed without answering; Omi asks less often. */
    suspend fun dismissSpeakerPrompts()

    /** `POST v1/speaker-tag-prompts/answer`. */
    suspend fun answerSpeakerPrompt(prompt: SpeakerPrompt, answer: SpeakerPromptAnswer)

    // `speakerClip` (the prompt's sample) is `TranscriptLabelsAPI.speakerClip`, shared with the transcript.
}

internal class SpeakerPromptsEndpoints(private val http: HttpCore) : SpeakerPromptsAPI {
    override suspend fun speakerPrompts(): List<SpeakerPrompt> =
        http.jsonObject(Method.GET, "v1/speaker-tag-prompts").objects("prompts").mapNotNull(SpeakerPromptMapper::prompt)

    override suspend fun markSpeakerPromptsShown(ids: List<String>) {
        val body = buildJsonObject { putJsonArray("prompt_ids") { ids.take(10).forEach { add(JsonPrimitive(it)) } } }
        http.data(Method.POST, "v1/speaker-tag-prompts/shown", body = Body.Json(body.toString()))
    }

    override suspend fun dismissSpeakerPrompts() {
        http.data(Method.POST, "v1/speaker-tag-prompts/dismiss")
    }

    override suspend fun answerSpeakerPrompt(prompt: SpeakerPrompt, answer: SpeakerPromptAnswer) {
        val body = buildJsonObject {
            put("prompt_id", prompt.id)
            put("kind", prompt.kind.rawValue)
            put("origin", prompt.origin)
            put("conversation_id", prompt.conversationID)
            put("speaker_id", prompt.speakerID)
            putJsonArray("segment_ids") { prompt.segmentIDs.take(50).forEach { add(JsonPrimitive(it)) } }
            put("answer", answer.wire)
            when (answer) {
                is SpeakerPromptAnswer.Person -> put("person_id", answer.id)
                is SpeakerPromptAnswer.NewPerson -> put("name", answer.name)
                else -> Unit
            }
            prompt.suggestedPersonID?.let { put("suggested_person_id", it) }
        }
        http.data(Method.POST, "v1/speaker-tag-prompts/answer", body = Body.Json(body.toString()))
    }
}

internal object SpeakerPromptMapper {
    fun prompt(item: JsonObject): SpeakerPrompt? {
        val id = item.string("id") ?: return null
        val kind = SpeakerPrompt.Kind.from(item.string("kind")) ?: return null
        val conversationID = item.string("conversation_id") ?: return null
        val speakerID = item.int("speaker_id") ?: return null
        val candidates = item.objects("candidates").mapNotNull { candidate ->
            val personID = candidate.string("person_id") ?: return@mapNotNull null
            val name = candidate.string("name") ?: return@mapNotNull null
            SpeakerPrompt.Candidate(personID, name)
        }
        return SpeakerPrompt(
            id = id, kind = kind, origin = item.string("origin") ?: "unnamed",
            conversationID = conversationID, conversationTitle = item.string("conversation_title") ?: "",
            speakerID = speakerID, segmentIDs = item.strings("segment_ids"),
            clipStart = item.double("clip_start") ?: 0.0, clipEnd = item.double("clip_end") ?: 0.0,
            excerpt = item.string("excerpt") ?: "",
            suggestedPersonID = item.string("suggested_person_id"),
            suggestedPersonName = item.string("suggested_person_name"),
            candidates = candidates,
        )
    }
}
