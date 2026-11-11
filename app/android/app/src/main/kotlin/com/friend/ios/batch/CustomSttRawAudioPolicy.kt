package com.friend.ios.batch

import org.json.JSONObject

internal object CustomSttRawAudioPolicy {
    fun allowsForwarding(rawConfig: String): Boolean {
        if (rawConfig.isEmpty()) return true

        return try {
            val config = JSONObject(rawConfig)
            config.optString("provider", "omi") == "omi" ||
                config.optBoolean("send_raw_audio_to_omi", true)
        } catch (_: Exception) {
            false
        }
    }
}
