package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.IgnoredVoice
import com.friend.ios.core.models.Person
import com.friend.ios.core.models.PersonConversation
import com.friend.ios.core.models.VoiceProfileSettings
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Port of the people and voice-learning half of `APIClient+Speakers.swift` plus
 * `APIClient+Transcription.swift` (`single_language_mode`).
 */
interface SpeakersAPI {
    /** `GET v1/users/people?include_speech_samples=true&include_stats=true`. */
    suspend fun peopleWithStats(): List<Person>
    /** `PATCH v1/users/people/{id}/pinned?value=`. */
    suspend fun setPersonPinned(id: String, pinned: Boolean)
    /** `DELETE v1/users/people/{id}/speech-samples/{index}`. */
    suspend fun deleteSpeechSample(personID: String, index: Int)
    /** `POST v1/conversations/search` with `speaker_id`: conversations this person speaks in, newest first. */
    suspend fun conversationsWithPerson(personID: String, page: Int, perPage: Int): List<PersonConversation>
    /** `GET v1/users/voice-profile-settings`. */
    suspend fun voiceProfileSettings(): VoiceProfileSettings
    /** `PATCH v1/users/voice-profile-settings` with whichever switch changed. */
    suspend fun updateVoiceProfileSettings(asksToTag: Boolean?, savesOtherVoices: Boolean?): VoiceProfileSettings
    /** `GET v1/speaker-tag-prompts/ignored-voices`. */
    suspend fun ignoredVoices(): List<IgnoredVoice>
    /** `DELETE v1/speaker-tag-prompts/ignored-voices/{conversation}/{speaker}`: Omi may ask about it again. */
    suspend fun restoreIgnoredVoice(conversationID: String, speakerID: Int)
    /** `GET v1/users/transcription-preferences` → `single_language_mode`. */
    suspend fun singleLanguageMode(): Boolean
    /** `PATCH v1/users/transcription-preferences`; applies from the next `/v4/listen`. */
    suspend fun setSingleLanguageMode(value: Boolean)
}

internal class SpeakersEndpoints(private val http: HttpCore) : SpeakersAPI {
    override suspend fun peopleWithStats(): List<Person> {
        val text = http.data(Method.GET, "v1/users/people", query = listOf("include_speech_samples" to "true", "include_stats" to "true"))
        return JsonAccess.array(text).mapNotNull { (it as? JsonObject)?.let(PersonMapper::map) }
    }

    override suspend fun setPersonPinned(id: String, pinned: Boolean) {
        http.data(Method.PATCH, "v1/users/people/$id/pinned", query = listOf("value" to "$pinned"))
    }

    override suspend fun deleteSpeechSample(personID: String, index: Int) {
        http.data(Method.DELETE, "v1/users/people/$personID/speech-samples/$index")
    }

    override suspend fun conversationsWithPerson(personID: String, page: Int, perPage: Int): List<PersonConversation> {
        val body = buildJsonObject {
            put("query", "")
            put("page", page)
            put("per_page", perPage)
            put("include_discarded", false)
            put("speaker_id", personID)
        }
        return http.jsonObject(Method.POST, "v1/conversations/search", json = body).objects("items").mapNotNull { item ->
            val id = item.string("id") ?: return@mapNotNull null
            val structured = item.obj("structured")
            val date = BackendDate.parse(item.string("started_at")) ?: BackendDate.parse(item.string("created_at")) ?: BackendDate.distantPast
            PersonConversation(id, structured?.string("title").orEmpty(), structured?.string("emoji")?.takeIf { it.isNotEmpty() }, date)
        }
    }

    override suspend fun voiceProfileSettings(): VoiceProfileSettings = SpeakerMapper.settings(http.jsonObject(Method.GET, "v1/users/voice-profile-settings"))

    override suspend fun updateVoiceProfileSettings(asksToTag: Boolean?, savesOtherVoices: Boolean?): VoiceProfileSettings {
        val body = buildJsonObject {
            put("source", "settings")
            asksToTag?.let { put("speaker_tag_prompts_enabled", it) }
            savesOtherVoices?.let { put("save_other_voice_profiles", it) }
        }
        return SpeakerMapper.settings(http.jsonObject(Method.PATCH, "v1/users/voice-profile-settings", json = body))
    }

    override suspend fun ignoredVoices(): List<IgnoredVoice> =
        http.jsonObject(Method.GET, "v1/speaker-tag-prompts/ignored-voices").objects("voices").mapNotNull(SpeakerMapper::ignoredVoice)

    override suspend fun restoreIgnoredVoice(conversationID: String, speakerID: Int) {
        http.data(Method.DELETE, "v1/speaker-tag-prompts/ignored-voices/$conversationID/$speakerID")
    }

    override suspend fun singleLanguageMode(): Boolean =
        http.jsonObject(Method.GET, "v1/users/transcription-preferences").bool("single_language_mode") ?: false

    override suspend fun setSingleLanguageMode(value: Boolean) {
        http.jsonObject(Method.PATCH, "v1/users/transcription-preferences", json = buildJsonObject { put("single_language_mode", value) })
    }
}

/** Port of `SpeakerMapper` (the parts Settings reads). */
internal object SpeakerMapper {
    fun ignoredVoice(item: JsonObject): IgnoredVoice? {
        val conversationID = item.string("conversation_id") ?: return null
        val speakerID = item.int("speaker_id") ?: return null
        return IgnoredVoice(conversationID, speakerID, item.string("conversation_title").orEmpty(), BackendDate.parse(item.string("ignored_at")))
    }

    fun settings(item: JsonObject) = VoiceProfileSettings(
        asksToTag = item.bool("speaker_tag_prompts_enabled") ?: true,
        savesOtherVoices = item.bool("save_other_voice_profiles") ?: true,
    )
}
