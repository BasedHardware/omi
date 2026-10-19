package com.friend.ios.ble

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs

/** Disconnect-event timestamps and the outage key are stamped a few milliseconds apart. */
internal const val AUDIO_OUTAGE_MATCH_TOLERANCE_MS = 5_000L

/** True when [marker] is a disconnect-written outage, not a restored session start. */
internal fun audioOutageMatchesDisconnect(history: JSONArray, marker: Long): Boolean {
    for (i in 0 until history.length()) {
        val item = history.optJSONObject(i) ?: continue
        if (item.optString("eventType") != "disconnect") continue
        if (abs(item.optLong("timestamp") - marker) <= AUDIO_OUTAGE_MATCH_TOLERANCE_MS) return true
    }
    return false
}

/**
 * Drop synthetic recoveries whose timestamp is not a measured disconnect.
 * Those rows are a restored session start billed as lost audio.
 */
internal fun dropUnmeasuredAudioRecoveries(history: JSONArray): JSONArray {
    val kept = JSONArray()
    for (i in 0 until history.length()) {
        val item = history.optJSONObject(i) ?: continue
        if (item.optString("eventType") == "audio_recovered" &&
            !audioOutageMatchesDisconnect(history, item.optLong("timestamp"))
        ) {
            continue
        }
        kept.put(item)
    }
    return kept
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
        // billing from it charges the whole connected interval.
        if (read("audio_outage_epoch_$device")?.toLongOrNull() == epoch()) {
            read("audio_outage_$device")?.toLongOrNull()?.let { return it }
        }
        return null
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
