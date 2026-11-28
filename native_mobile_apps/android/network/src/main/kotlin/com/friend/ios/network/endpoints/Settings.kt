package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.AssistantVoice
import com.friend.ios.core.models.Person
import com.friend.ios.core.models.PhoneNumber
import com.friend.ios.core.models.SpokenLanguage
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Port of `APIClient+Settings.swift` (notifications, privacy, assistant voice, vocabulary, people,
 * phone numbers) plus `availableLanguages` from `APIClient+Integrations.swift`.
 */
interface SettingsAPI {
    /** `GET v1/users/daily-summary-settings`. */
    suspend fun dailySummary(): Pair<Boolean, Int>
    suspend fun setDailySummary(enabled: Boolean, hour: Int)
    /** `GET v1/users/mentor-notification-settings` (0 off ... 5 often). */
    suspend fun notificationFrequency(): Int
    suspend fun setNotificationFrequency(value: Int)
    /** `GET v1/users/store-recording-permission`. */
    suspend fun storesRecordings(): Boolean
    suspend fun setStoresRecordings(value: Boolean)
    /** `GET v1/tts/voices` + `GET v1/users/voice`: the catalog and the chosen one (else the default). */
    suspend fun assistantVoices(): Pair<List<AssistantVoice>, String?>
    suspend fun setAssistantVoice(id: String)
    /** `GET v1/users/transcription-preferences` → `vocabulary`. */
    suspend fun vocabulary(): List<String>
    suspend fun setVocabulary(words: List<String>)
    /** `GET v1/users/people?include_speech_samples=true`. */
    suspend fun people(): List<Person>
    suspend fun addPerson(name: String)
    suspend fun renamePerson(id: String, name: String)
    suspend fun deletePerson(id: String)
    /** `GET v1/phone/numbers`. */
    suspend fun phoneNumbers(): List<PhoneNumber>
    /** `GET v1/users/available-languages`. */
    suspend fun availableLanguages(): List<SpokenLanguage>
}

internal class SettingsEndpoints(private val http: HttpCore) : SettingsAPI {
    override suspend fun dailySummary(): Pair<Boolean, Int> {
        val o = http.jsonObject(Method.GET, "v1/users/daily-summary-settings")
        return (o.bool("enabled") ?: true) to (o.int("hour") ?: 22)
    }

    override suspend fun setDailySummary(enabled: Boolean, hour: Int) {
        http.jsonObject(Method.PATCH, "v1/users/daily-summary-settings", json = buildJsonObject { put("enabled", enabled); put("hour", hour) })
    }

    override suspend fun notificationFrequency(): Int = http.jsonObject(Method.GET, "v1/users/mentor-notification-settings").int("frequency") ?: 0

    override suspend fun setNotificationFrequency(value: Int) {
        http.jsonObject(Method.PATCH, "v1/users/mentor-notification-settings", json = buildJsonObject { put("frequency", value) })
    }

    override suspend fun storesRecordings(): Boolean =
        http.jsonObject(Method.GET, "v1/users/store-recording-permission").bool("store_recording_permission") ?: false

    override suspend fun setStoresRecordings(value: Boolean) {
        http.jsonObject(Method.POST, "v1/users/store-recording-permission", query = listOf("value" to "$value"))
    }

    override suspend fun assistantVoices(): Pair<List<AssistantVoice>, String?> {
        val catalog = http.jsonObject(Method.GET, "v1/tts/voices")
        val voices = catalog.objects("voices").mapNotNull { voice ->
            val id = voice.string("id") ?: return@mapNotNull null
            AssistantVoice(id, voice.string("name") ?: id)
        }
        val selected = runCatching { http.jsonObject(Method.GET, "v1/users/voice").string("voice_id") }.getOrNull()
        return voices to (selected ?: catalog.string("default_voice_id"))
    }

    override suspend fun setAssistantVoice(id: String) {
        http.jsonObject(Method.PATCH, "v1/users/voice", json = buildJsonObject { put("voice_id", id) })
    }

    override suspend fun vocabulary(): List<String> = http.jsonObject(Method.GET, "v1/users/transcription-preferences").strings("vocabulary")

    override suspend fun setVocabulary(words: List<String>) {
        val body = JsonObject(mapOf("vocabulary" to JsonArray(words.map(::JsonPrimitive))))
        http.jsonObject(Method.PATCH, "v1/users/transcription-preferences", json = body)
    }

    override suspend fun people(): List<Person> {
        val text = http.data(Method.GET, "v1/users/people", query = listOf("include_speech_samples" to "true"))
        return JsonAccess.array(text).mapNotNull { (it as? JsonObject)?.let(PersonMapper::map) }
    }

    override suspend fun addPerson(name: String) {
        http.jsonObject(Method.POST, "v1/users/people", json = buildJsonObject { put("name", name) })
    }

    override suspend fun renamePerson(id: String, name: String) {
        http.jsonObject(Method.PATCH, "v1/users/people/$id/name", query = listOf("value" to name))
    }

    override suspend fun deletePerson(id: String) {
        http.jsonObject(Method.DELETE, "v1/users/people/$id")
    }

    override suspend fun phoneNumbers(): List<PhoneNumber> =
        http.jsonObject(Method.GET, "v1/phone/numbers").objects("numbers").mapNotNull { item ->
            val id = item.string("id") ?: return@mapNotNull null
            PhoneNumber(id, item.string("phone_number").orEmpty(), item.has("verified_at"))
        }

    override suspend fun availableLanguages(): List<SpokenLanguage> =
        http.jsonObject(Method.GET, "v1/users/available-languages").objects("languages").mapNotNull { item ->
            val name = item.string("name") ?: return@mapNotNull null
            val code = item.string("code") ?: return@mapNotNull null
            SpokenLanguage(name, code)
        }
}

/** Port of `PersonMapper` (`SpeakerModels.swift`). */
internal object PersonMapper {
    fun map(item: JsonObject): Person? {
        val id = item.string("id") ?: return null
        return Person(
            id = id,
            name = item.string("name").orEmpty(),
            sampleCount = item.array("speech_samples")?.size ?: 0,
            sampleURLs = item.strings("speech_samples"),
            isPinned = item.bool("pinned") ?: false,
            confidence = Person.Confidence.from(item.string("confidence")) ?: Person.Confidence.Unknown,
            conversationCount = item.int("conversation_count"),
            talkSeconds = item.double("talk_seconds"),
            lastHeardAt = BackendDate.parse(item.string("last_heard_at")),
        )
    }
}
