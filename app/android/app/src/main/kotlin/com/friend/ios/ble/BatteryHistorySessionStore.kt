package com.friend.ios.ble

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs

/** Session start and a copied outage marker can be stamped a few milliseconds apart. */
internal const val AUDIO_OUTAGE_MATCH_TOLERANCE_MS = 5_000L

/**
 * Start of the durable session when [sessionJson] parses and belongs to [epoch].
 * Parse failure, a missing row, or an epoch mismatch is not proof of anything.
 */
internal fun provenSessionStartedAt(sessionJson: String?, epoch: Long): Long? {
    if (sessionJson.isNullOrEmpty()) return null
    val session = try {
        JSONObject(sessionJson)
    } catch (_: Exception) {
        return null
    }
    if (!session.has("identity_epoch") || session.optLong("identity_epoch") != epoch) return null
    val started = session.optLong("started_at", 0L)
    return started.takeIf { it > 0L }
}

/**
 * Non-null when [marker] is the current session start, not an independent outage.
 * A disconnect stamped just before this session began is a real outage that
 * reconnected quickly; it is not a copy of started_at.
 */
internal fun sessionStartMatchingMarker(sessionJson: String?, epoch: Long, marker: Long): Long? {
    if (marker <= 0L) return null
    val started = provenSessionStartedAt(sessionJson, epoch) ?: return null
    if (marker < started) return null
    return started.takeIf { abs(it - marker) <= AUDIO_OUTAGE_MATCH_TOLERANCE_MS }
}

/**
 * Drop an `audio_recovered` row only when it is the current session start.
 * A row with no disconnect match stays: the disconnect may have been pruned.
 * Returns [history] itself when nothing is dropped.
 */
internal fun dropUnmeasuredAudioRecoveries(history: JSONArray, sessionStartedAt: Long?): JSONArray {
    if (sessionStartedAt == null || sessionStartedAt <= 0L) return history
    val kept = JSONArray()
    var dropped = false
    for (i in 0 until history.length()) {
        val item = history.optJSONObject(i) ?: continue
        val timestamp = item.optLong("timestamp")
        if (item.optString("eventType") == "audio_recovered" &&
            timestamp >= sessionStartedAt &&
            abs(timestamp - sessionStartedAt) <= AUDIO_OUTAGE_MATCH_TOLERANCE_MS
        ) {
            dropped = true
            continue
        }
        kept.put(item)
    }
    return if (dropped) kept else history
}

/**
 * [dropMarker] is true only when the session row proves the marker is a session start.
 * [rewrittenHistory] is null when history must be left untouched (parse failure, or no echo row).
 */
internal class AudioOutageCleanup(val dropMarker: Boolean, val rewrittenHistory: JSONArray?)

internal fun planAudioOutageCleanup(
    historyJson: String?,
    sessionJson: String?,
    epoch: Long,
    marker: Long,
    markerEpochMatches: Boolean,
): AudioOutageCleanup {
    val sessionStarted = provenSessionStartedAt(sessionJson, epoch)
    val echo = markerEpochMatches && sessionStartMatchingMarker(sessionJson, epoch, marker) != null
    val parsed = try {
        JSONArray(historyJson?.takeIf { it.isNotBlank() } ?: "[]")
    } catch (_: Exception) {
        return AudioOutageCleanup(dropMarker = echo, rewrittenHistory = null)
    }
    val kept = dropUnmeasuredAudioRecoveries(parsed, sessionStarted)
    return AudioOutageCleanup(dropMarker = echo, rewrittenHistory = if (kept !== parsed) kept else null)
}

/** Durable session evidence; live ownership is deliberately process-local. */
internal class BatteryHistorySessionStore(
    private val read: (String) -> String?,
    private val write: (String, String) -> Unit,
    private val remove: (String) -> Unit,
    private val epoch: () -> Long,
    private val enabled: () -> Boolean,
) {
    private val live = mutableSetOf<String>()
    fun start(device: String, now: Long, build: String) {
        if (!enabled() || device in live) return
        val old = openSince(device)
        if (old != null) {
            write("audio_outage_epoch_$device", epoch().toString())
            write("audio_outage_$device", old.toString())
        }
        write("session_$device", JSONObject().put("device", device).put("started_at", now)
            .put("app_build", build).put("identity_epoch", epoch()).toString())
        live.add(device)
    }
    fun openSince(device: String): Long? {
        if (!enabled()) return null
        // Only a marker written at disconnect is an outage. session.started_at is
        // when the link came up; after process death it is not lost audio, and
        // billing from it charges the whole connected interval. A marker is that
        // session start only when the current session row says so. Missing or
        // unreadable session evidence keeps the marker.
        if (read("audio_outage_epoch_$device")?.toLongOrNull() != epoch()) return null
        val marker = read("audio_outage_$device")?.toLongOrNull() ?: return null
        if (sessionStartMatchingMarker(read("session_$device"), epoch(), marker) != null) {
            remove("audio_outage_$device")
            remove("audio_outage_epoch_$device")
            return null
        }
        return marker
    }
    fun end(device: String, now: Long) {
        if (!enabled()) return
        val start = openSince(device) ?: now
        write("audio_outage_epoch_$device", epoch().toString())
        write("audio_outage_$device", start.toString())
        remove("session_$device")
        live.remove(device)
    }
    fun retire() { live.clear() }
}
