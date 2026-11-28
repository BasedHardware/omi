package com.friend.ios.service.customstt

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.network.customstt.CustomSTTConfig
import com.friend.ios.network.customstt.CustomSTTProvider
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.Key
import com.friend.ios.persistence.Preferences.NativeKey
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.put

/** Port of `SecretStore`: small secrets kept out of preferences (iOS: the Keychain; Android: the Keystore). */
interface SecretStore {
    fun secret(key: String): String?
    fun setSecret(value: String?, key: String)
}

/**
 * Port of `CustomSTTSettings.swift`. Settings > Listening > Advanced transcription: which
 * speech-to-text service the phone uses (Flutter `transcription_settings_page`). Off means Omi
 * transcribes. The provider, model, language and endpoint stay under Flutter's `customSttConfig`
 * key; the API key goes to the secret store, and a key the Flutter app had saved in its JSON moves
 * there on first read.
 */
class CustomSTTSettings(private val preferences: Preferences, private val secrets: SecretStore) {
    /** The saved provider; null when Omi (or the phone) transcribes. */
    var config: CustomSTTConfig? by mutableStateOf(null)
        private set

    init {
        config = load()
    }

    /** A provider is chosen and ready to receive audio. */
    val isActive: Boolean get() = config?.isComplete == true

    /** Saves the setup (the key to the secret store). `null` goes back to Omi's transcription. */
    fun save(config: CustomSTTConfig?) {
        if (config == null) {
            preferences.set(Key.CustomSttConfig, null as String?)
            secrets.setSecret(null, KEY_NAME)
            this.config = null
            return
        }
        val trimmedKey = config.apiKey?.trim()
        secrets.setSecret(if (config.provider.requiresAPIKey) trimmedKey else null, KEY_NAME)
        preferences.set(Key.CustomSttConfig, json(config))
        this.config = config.copy(apiKey = if (config.provider.requiresAPIKey) trimmedKey else null)
    }

    /**
     * Reads Flutter's JSON. Providers native does not run (Gemini, on-device Whisper, custom live)
     * read as off; Flutter's on-device choice is the phone's own recognizer here.
     */
    private fun load(): CustomSTTConfig? {
        val text = preferences.string(Key.CustomSttConfig)
        val root = text?.let { runCatching { Json.parseToJsonElement(it) as? JsonObject }.getOrNull() }
        if (root == null) {
            // Signed out (preferences cleared): the key goes too.
            secrets.setSecret(null, KEY_NAME)
            return null
        }
        fun field(name: String) = (root[name] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
        val flutterKey = field("api_key")?.ifEmpty { null }
        if (field("provider") == "onDeviceWhisper") preferences.set(NativeKey.OnDeviceTranscription, true)
        val provider = CustomSTTProvider.from(field("provider"))
        if (provider == null) {
            if (flutterKey != null) preferences.set(Key.CustomSttConfig, null as String?)
            return null
        }
        val config = CustomSTTConfig(provider, model = field("model"), language = field("language"), url = field("url"))
        if (flutterKey != null) {
            // Out of preferences for good: the JSON is rewritten without it (and without headers holding it).
            secrets.setSecret(flutterKey, KEY_NAME)
            preferences.set(Key.CustomSttConfig, json(config))
        }
        return config.copy(apiKey = if (provider.requiresAPIKey) secrets.secret(KEY_NAME) else null)
    }

    companion object {
        internal const val KEY_NAME = "customStt.apiKey"

        /** Flutter's field names, no secrets; keys sorted as iOS writes them. */
        fun json(config: CustomSTTConfig): String {
            val fields = sortedMapOf<String, Any>("provider" to config.provider.rawValue, "send_raw_audio_to_omi" to true)
            config.model?.takeIf { it.isNotEmpty() }?.let { fields["model"] = it }
            config.language?.takeIf { it.isNotEmpty() }?.let { fields["language"] = it }
            if (config.provider.takesURL) config.url?.takeIf { it.isNotEmpty() }?.let { fields["url"] = it }
            if (config.provider.isLive) fields["request_type"] = "streaming"
            return buildJsonObject {
                fields.forEach { (key, value) -> if (value is Boolean) put(key, value) else put(key, value.toString()) }
            }.toString()
        }
    }
}

/** In memory (tests, and a phone without a Keystore). */
class MemorySecretStore : SecretStore {
    private val values = mutableMapOf<String, String>()

    override fun secret(key: String): String? = values[key]

    override fun setSecret(value: String?, key: String) {
        if (value == null) values.remove(key) else values[key] = value
    }
}
