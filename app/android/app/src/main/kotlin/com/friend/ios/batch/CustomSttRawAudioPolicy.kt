package com.friend.ios.batch

import org.json.JSONObject

internal object CustomSttRawAudioPolicy {
    private val knownProviders = setOf(
        "omi", "omiParakeet", "openai", "openaiDiarize", "deepgram", "deepgramLive",
        "falai", "gemini", "geminiLive", "localWhisper", "custom", "customLive", "onDeviceWhisper",
    )

    fun allowsForwarding(rawConfig: String): Boolean {
        if (rawConfig.isEmpty()) return true

        return try {
            val config = JSONObject(rawConfig)
            val provider = config.opt("provider")
            if (provider !is String || provider !in knownProviders) {
                false
            } else if (config.has("privacy_policy")) {
                // An explicit typed policy is authoritative. Unknown or
                // malformed values fail privacy-closed; only a missing field
                // falls back to the legacy provider/boolean migration.
                when (config.opt("privacy_policy")) {
                    "full" -> true
                    "transcriptOnly", "localOnly" -> false
                    else -> false
                }
            } else if (provider == "omi") {
                true
            } else {
                config.optBoolean("send_raw_audio_to_omi", true)
            }
        } catch (_: Exception) {
            false
        }
    }
}
