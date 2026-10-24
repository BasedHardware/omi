package com.friend.ios.core.models

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

/**
 * `GeolocationSnapshot` of `ConversationPlace.swift` (the capture half; the rest of that file is
 * `ConversationPlace.kt`): where a recording starts, sent with it (Flutter `Geolocation`).
 */
data class GeolocationSnapshot(
    val latitude: Double,
    val longitude: Double,
    val altitude: Double?,
    val accuracy: Double?,
    val capturedAt: Instant,
    val source: Source,
) {
    enum class Source(val rawValue: String) {
        CurrentPosition("current_position"),
        LastKnownPosition("last_known_position"),
    }

    /**
     * Flutter `Geolocation.toJson()`: coordinates, `captured_at` (ISO-8601 UTC) and `capture_source`.
     * Negative accuracy and non-finite values are left out; the backend rejects them. Keys sorted,
     * as the iOS header (`.sortedKeys`).
     */
    val jsonObject: JsonObject
        get() = buildJsonObject {
            if (accuracy != null && accuracy.isFinite() && accuracy >= 0) put("accuracy", accuracy)
            if (altitude != null && altitude.isFinite()) put("altitude", altitude)
            put("capture_source", source.rawValue)
            put("captured_at", iso.format(capturedAt))
            put("latitude", latitude)
            put("longitude", longitude)
        }

    /** The compact JSON the listen socket carries in its upgrade header. */
    val headerValue: String get() = jsonObject.toString()

    companion object {
        /** `ISO8601DateFormatter` with fractional seconds: `2026-10-09T08:00:00.123Z`. */
        private val iso: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").withZone(ZoneOffset.UTC)
    }
}
