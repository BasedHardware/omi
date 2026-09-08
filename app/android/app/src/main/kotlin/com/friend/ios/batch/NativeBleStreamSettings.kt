package com.friend.ios.batch

import org.json.JSONObject
import java.util.Locale

internal interface NativeBlePreferences {
    fun string(key: String, defaultValue: String = ""): String
    fun boolean(key: String, defaultValue: Boolean = false): Boolean
    fun integer(key: String, defaultValue: Int): Int
}

internal data class NativeBleStreamConfig(
    val deviceId: String,
    val codec: String,
    val sampleRate: Int,
    val source: String,
    val apiBaseUrl: String,
    val serviceUuid: String,
    val characteristicUuid: String,
    val deviceType: String,
    val geolocation: String?,
)

internal data class NativeBleStreamSettings(
    val config: NativeBleStreamConfig,
    val uid: String,
    val token: String,
    val deviceIdHash: String,
    val language: String,
    val sttService: String,
    val timeout: Int,
    val vadGate: Boolean,
)

/** Read security gates synchronously: SharedPreferences listeners can lag BLE callbacks.
 * Only JSON decoding is cached; every use observes the current preference values. */
internal class NativeBleStreamSettingsReader(private val prefs: NativeBlePreferences) {
    private var configRaw: String? = null
    private var config: NativeBleStreamConfig? = null
    private var policyRaw: String? = null
    private var allowsForwarding = false

    @Synchronized
    fun config(): NativeBleStreamConfig? {
        if (!prefs.boolean("nativeBleStreamingEnabled")) return null
        val policy = prefs.string("customSttConfig")
        if (policyRaw != policy) {
            allowsForwarding = CustomSttRawAudioPolicy.allowsForwarding(policy)
            policyRaw = policy
        }
        if (!allowsForwarding) return null
        val raw = prefs.string("nativeBleStreamConfig")
        if (raw != configRaw) {
            config = parseConfig(raw)
            configRaw = raw
        }
        return config
    }

    fun settings(): NativeBleStreamSettings? {
        val config = config() ?: return null
        val uid = prefs.string("uid")
        val token = prefs.string("nativeAuthToken").ifEmpty { prefs.string("authToken") }
        if (uid.isEmpty() || token.isEmpty()) return null
        return NativeBleStreamSettings(
            config, uid, token, prefs.string("deviceIdHash"),
            if (prefs.boolean("hasSetPrimaryLanguage")) {
                prefs.string("userPrimaryLanguage", "multi").ifEmpty { "multi" }
            } else "multi",
            prefs.string("transcriptionModel3", "soniox").ifEmpty { "soniox" },
            prefs.integer("conversationSilenceDuration", 120).takeIf { it > 0 } ?: 120,
            prefs.boolean("vadGateEnabled"),
        )
    }

    private fun parseConfig(raw: String): NativeBleStreamConfig? = try {
        val json = JSONObject(raw)
        val deviceId = json.optString("deviceId")
        val serviceUuid = json.optString("serviceUuid").lowercase(Locale.US)
        val characteristicUuid = json.optString("characteristicUuid").lowercase(Locale.US)
        if (deviceId.isEmpty() || serviceUuid.isEmpty() || characteristicUuid.isEmpty()) null else {
            NativeBleStreamConfig(
                deviceId, json.optString("codec", "pcm8"), json.optInt("sampleRate", 16000),
                json.optString("source"), json.optString("apiBaseUrl"), serviceUuid, characteristicUuid,
                json.optString("deviceType"), json.optJSONObject("geolocation")?.toString(),
            )
        }
    } catch (_: Exception) {
        null
    }
}
