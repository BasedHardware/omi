package com.friend.ios.ble

import org.json.JSONArray
import org.json.JSONObject

/**
 * A disconnect row and the outage marker for the same event can be written
 * a moment apart. A later, unrelated disconnect is not evidence for this marker.
 */
internal const val AUDIO_OUTAGE_MATCH_TOLERANCE_MS = 5_000L

/**
 * A copied session start is the stored `started_at`, within a few milliseconds.
 * Anything after `started_at` is a disconnect on that link.
 */
internal const val AUDIO_OUTAGE_ECHO_TOLERANCE_MS = 5L

internal const val AUDIO_RECOVERY_PROOF_RETENTION_MS = 7L * 24 * 3600 * 1000
internal const val AUDIO_RECOVERY_PROOF_LIMIT = 500

internal fun audioRecoveryProofsKey(device: String) = "audio_recovery_proofs_$device"

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

/** True when [marker] is a copy of [started], not a disconnect before or during that link. */
internal fun isSessionStartEcho(started: Long, marker: Long): Boolean {
    if (marker <= 0L || started <= 0L || marker > started) return false
    return started - marker <= AUDIO_OUTAGE_ECHO_TOLERANCE_MS
}

/**
 * True when a disconnect row records this marker. Rows further than
 * [AUDIO_OUTAGE_MATCH_TOLERANCE_MS] after [marker] are later events.
 */
internal fun disconnectEvidenceSupportsMarker(history: JSONArray, marker: Long): Boolean {
    if (marker <= 0L) return false
    for (i in 0 until history.length()) {
        val item = history.optJSONObject(i) ?: continue
        if (item.optString("eventType") != "disconnect") continue
        val delta = item.optLong("timestamp", 0L) - marker
        if (delta >= 0L && delta <= AUDIO_OUTAGE_MATCH_TOLERANCE_MS) return true
    }
    return false
}

/**
 * Non-null when [marker] is the current session start, not an independent outage.
 * A marker after `started_at` is a disconnect whose session row is still on disk.
 * A marker before this session is a real outage that reconnected. Disconnect
 * evidence for this marker wins over either tolerance.
 */
internal fun sessionStartMatchingMarker(
    sessionJson: String?,
    epoch: Long,
    marker: Long,
    history: JSONArray? = null,
): Long? {
    if (marker <= 0L) return null
    if (history != null && disconnectEvidenceSupportsMarker(history, marker)) return null
    val started = provenSessionStartedAt(sessionJson, epoch) ?: return null
    return started.takeIf { isSessionStartEcho(it, marker) }
}

/**
 * Drop an `audio_recovered` row only when it is the current session start and
 * no disconnect row records it. A later marker stays: a short link can die
 * before the session row is removed. Returns [history] itself when nothing is dropped.
 */
internal fun dropUnmeasuredAudioRecoveries(history: JSONArray, sessionStartedAt: Long?): JSONArray {
    if (sessionStartedAt == null || sessionStartedAt <= 0L) return history
    val kept = JSONArray()
    var dropped = false
    for (i in 0 until history.length()) {
        val item = history.optJSONObject(i) ?: continue
        val timestamp = item.optLong("timestamp")
        if (item.optString("eventType") == "audio_recovered" &&
            isSessionStartEcho(sessionStartedAt, timestamp) &&
            !disconnectEvidenceSupportsMarker(history, timestamp)
        ) {
            dropped = true
            continue
        }
        kept.put(item)
    }
    return if (dropped) kept else history
}

internal data class AudioRecoveryStamp(val start: Long, val at: Long)

/** Append one genuine standalone recovery and drop expired or other-epoch proofs. */
internal fun appendAudioRecoveryProof(
    existing: String?,
    start: Long,
    resolvedAt: Long,
    epoch: Long,
    now: Long,
): String {
    val kept = JSONArray()
    for (stamp in audioRecoveryStamps(existing, epoch, now)) {
        kept.put(JSONObject().put("start", stamp.start).put("at", stamp.at).put("identity_epoch", epoch))
    }
    if (start > 0L && resolvedAt > 0L) {
        kept.put(JSONObject().put("start", start).put("at", resolvedAt).put("identity_epoch", epoch))
    }
    val limited = JSONArray()
    val startIndex = (kept.length() - AUDIO_RECOVERY_PROOF_LIMIT).coerceAtLeast(0)
    for (i in startIndex until kept.length()) limited.put(kept.getJSONObject(i))
    return limited.toString()
}

internal fun audioRecoveryStamps(proofsJson: String?, epoch: Long, now: Long): List<AudioRecoveryStamp> {
    val source = try {
        JSONArray(proofsJson?.takeIf { it.isNotBlank() } ?: "[]")
    } catch (_: Exception) {
        return emptyList()
    }
    val stamps = mutableListOf<AudioRecoveryStamp>()
    for (i in 0 until source.length()) {
        val item = source.optJSONObject(i) ?: continue
        if (item.optLong("identity_epoch", Long.MIN_VALUE) != epoch) continue
        val start = item.optLong("start", 0L)
        val at = item.optLong("at", 0L)
        if (start <= 0L || at <= 0L || now - at > AUDIO_RECOVERY_PROOF_RETENTION_MS) continue
        stamps.add(AudioRecoveryStamp(start, at))
    }
    return stamps
}

/** Latest proof fills the singular stamp fields; every proof is listed for Dart. */
internal fun putAudioRecoveryStamps(target: JSONObject, proofsJson: String?, epoch: Long, now: Long): JSONObject {
    val stamps = audioRecoveryStamps(proofsJson, epoch, now)
    if (stamps.isEmpty()) return target
    val latest = stamps.last()
    target.put("audio_outage_resolved_start", latest.start)
    target.put("audio_outage_resolved_at", latest.at)
    val proofs = JSONArray()
    for (stamp in stamps) proofs.put(JSONObject().put("start", stamp.start).put("at", stamp.at))
    target.put("audio_outage_recovery_proofs", proofs)
    return target
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
    val parsed = try {
        JSONArray(historyJson?.takeIf { it.isNotBlank() } ?: "[]")
    } catch (_: Exception) {
        val echo = markerEpochMatches && sessionStartMatchingMarker(sessionJson, epoch, marker) != null
        return AudioOutageCleanup(dropMarker = echo, rewrittenHistory = null)
    }
    val sessionStarted = provenSessionStartedAt(sessionJson, epoch)
    val echo = markerEpochMatches && sessionStartMatchingMarker(sessionJson, epoch, marker, parsed) != null
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
        // session start only when it equals started_at and no disconnect row
        // records it. A marker after started_at is a short link that died before
        // the session row was removed. Missing session evidence keeps the marker.
        if (read("audio_outage_epoch_$device")?.toLongOrNull() != epoch()) return null
        val marker = read("audio_outage_$device")?.toLongOrNull() ?: return null
        val history = try {
            JSONArray(read("disconnect_history_$device") ?: "[]")
        } catch (_: Exception) {
            null
        }
        if (sessionStartMatchingMarker(read("session_$device"), epoch(), marker, history) != null) {
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
