package com.friend.ios.core.models

import java.time.Instant

/** Port of the models in `APIClient+Developer.swift`: the webhooks Omi calls for the user's own tools (backend `WebhookType`). */
enum class DeveloperWebhook(val rawValue: String) {
    /** "Conversation events": a conversation was created (the backend still calls it a memory). */
    ConversationCreated("memory_created"),
    RealtimeTranscript("realtime_transcript"),
    /** Raw audio every few seconds; the interval travels in the URL field as `<url>,<seconds>`. */
    AudioBytes("audio_bytes"),
    DaySummary("day_summary");

    val id: String get() = rawValue

    companion object {
        /** The backend default for the audio interval (`utils/webhooks.py`). */
        const val DEFAULT_AUDIO_INTERVAL = 5

        /** Splits the stored `<url>,<seconds>` of the audio webhook. */
        fun splitAudio(stored: String): Pair<String, Int> {
            val parts = stored.split(",", limit = 2).map { it.trim() }
            val seconds = if (parts.size > 1) parts[1].toIntOrNull() ?: DEFAULT_AUDIO_INTERVAL else DEFAULT_AUDIO_INTERVAL
            return (parts.firstOrNull() ?: "") to maxOf(1, seconds)
        }

        fun joinAudio(url: String, seconds: Int): String = if (url.isEmpty()) "" else "$url,${maxOf(1, seconds)}"
    }
}

/**
 * A developer API key (`v1/dev/keys`) or MCP key (`v1/mcp/keys`). [secret] is only present right
 * after creation: the backend never shows it again.
 */
data class DeveloperKey(
    val id: String,
    val name: String,
    /** e.g. `omi_dev_1e0b...ae0a`. */
    val prefix: String,
    val createdAt: Instant?,
    val lastUsedAt: Instant?,
    val scopes: List<String>,
    val secret: String?,
) {
    enum class Kind(val rawValue: String) {
        Api("dev"), Mcp("mcp");

        companion object {
            fun from(raw: String?): Kind? = entries.firstOrNull { it.rawValue == raw }
        }
    }
}
