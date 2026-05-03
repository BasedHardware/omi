package com.omi.ambientcompanion

import org.json.JSONObject
import java.time.Instant
import java.util.UUID

enum class AmbientHealthState {
    IDLE_CONTEXT_WATCH,
    VAD_WATCH,
    AUDIO_OK,
    SPEECH_DETECTED,
    AUDIO_LOW_SIGNAL,
    AUDIO_SILENCED_BY_SYSTEM,
    COMMUNICATION_MODE_DEGRADED,
    CAPTION_FALLBACK_ACTIVE,
    LOCAL_STT_ACTIVE,
    MEDIA_PROJECTION_ACTIVE,
    NETWORK_DOWN_BUFFERING,
    STORAGE_LIMIT_REACHED,
    PRIVATE_MODE,
    PERMISSION_MISSING,
    RECOVERY_NEEDED,
}

enum class FallbackSource {
    LOCAL_STT,
    ACCESSIBILITY_CAPTION,
    LIVE_CAPTION_NOTIFICATION,
    SOUND_NOTIFICATION,
    GAP_MARKER,
}

data class HealthEvent(
    val state: AmbientHealthState,
    val reason: String,
    val foregroundPackage: String? = null,
    val dbfs: Double? = null,
    val zeroRatio: Double? = null,
    val timestamp: Instant = Instant.now(),
) {
    fun toJson(): JSONObject = JSONObject()
        .put("state", state.name)
        .put("reason", reason)
        .put("timestamp", timestamp.toString())
        .put("foreground_app", foregroundPackage)
        .put("dbfs", dbfs)
        .put("zero_frame_ratio", zeroRatio)
}

data class FallbackSegment(
    val id: String = UUID.randomUUID().toString(),
    val text: String,
    val source: FallbackSource,
    val start: Instant,
    val end: Instant,
    val confidence: Double? = null,
    val healthState: AmbientHealthState,
    val rawAudioAvailable: Boolean,
    val foregroundApp: String? = null,
    val uploaded: Boolean = false,
) {
    fun apiSource(): String = when (source) {
        FallbackSource.LOCAL_STT -> "local_stt"
        FallbackSource.ACCESSIBILITY_CAPTION -> "accessibility_caption"
        FallbackSource.LIVE_CAPTION_NOTIFICATION -> "live_caption"
        FallbackSource.SOUND_NOTIFICATION -> "gap_marker"
        FallbackSource.GAP_MARKER -> "gap_marker"
    }

    fun toJson(): JSONObject = JSONObject()
        .put("id", id)
        .put("text", text)
        .put("source", apiSource())
        .put("start", start.toString())
        .put("end", end.toString())
        .put("confidence", confidence)
        .put("health_state", healthState.name)
        .put("raw_audio_available", rawAudioAvailable)
        .put("foreground_app", foregroundApp)
        .put("uploaded", uploaded)

    companion object {
        private fun sourceFromApi(value: String): FallbackSource = when (value) {
            "local_stt" -> FallbackSource.LOCAL_STT
            "accessibility_caption" -> FallbackSource.ACCESSIBILITY_CAPTION
            "live_caption" -> FallbackSource.LIVE_CAPTION_NOTIFICATION
            "sound_notification" -> FallbackSource.SOUND_NOTIFICATION
            "gap_marker" -> FallbackSource.GAP_MARKER
            else -> FallbackSource.valueOf(value.uppercase())
        }

        fun fromJson(json: JSONObject): FallbackSegment = FallbackSegment(
            id = json.optString("id"),
            text = json.optString("text"),
            source = sourceFromApi(json.optString("source")),
            start = Instant.parse(json.optString("start")),
            end = Instant.parse(json.optString("end")),
            confidence = if (json.has("confidence") && !json.isNull("confidence")) json.optDouble("confidence") else null,
            healthState = AmbientHealthState.valueOf(json.optString("health_state")),
            rawAudioAvailable = json.optBoolean("raw_audio_available"),
            foregroundApp = json.optString("foreground_app").ifBlank { null },
            uploaded = json.optBoolean("uploaded"),
        )
    }
}

data class SpoolMetadata(
    val sessionId: String,
    val startedAt: Instant,
    val filePath: String,
    val bytes: Long,
    val durationEstimateSeconds: Double,
    val status: String,
    val localSttStatus: String? = null,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("session_id", sessionId)
        .put("started_at", startedAt.toString())
        .put("file_path", filePath)
        .put("bytes", bytes)
        .put("duration_estimate", durationEstimateSeconds)
        .put("status", status)
        .put("local_stt_status", localSttStatus)
}
