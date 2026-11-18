package com.friend.ios.ble

import android.content.SharedPreferences

/** Attributes recovery latency to a persisted event without controlling connection retries. */
internal class BleReconnectDiagnostics {
    data class Recovery(val timestamp: Long, val durationMs: Long)

    private var pendingTimestamp: Long? = null

    fun record(timestamp: Long, eventType: String, isManual: Boolean) {
        if (isManual) {
            pendingTimestamp = null
        } else if (eventType == "disconnect" || pendingTimestamp == null) {
            // Failed connection attempts belong to the outage already in progress.
            pendingTimestamp = timestamp
        }
    }

    fun recovered(timestamp: Long, hadConnection: Boolean): Recovery? {
        val pending = pendingTimestamp ?: return null
        pendingTimestamp = null
        if (!hadConnection) return null
        return Recovery(pending, (timestamp - pending).coerceAtLeast(0L))
    }

    fun <T> retainedHistory(
        history: List<T>, now: Long, retentionMs: Long, limit: Int, timestampOf: (T) -> Long,
    ): List<T> {
        val recent = history.filter { timestampOf(it) >= now - retentionMs }
        val pendingIndex = recent.indexOfLast { timestampOf(it) == pendingTimestamp }
        // Protect one unresolved outage from a retry storm without extending
        // its age retention or increasing the ring's total entry limit.
        if (pendingIndex >= 0 && pendingIndex < recent.size - limit && limit > 0) {
            return listOf(recent[pendingIndex]) + recent.takeLast(limit - 1)
        }
        return recent.takeLast(limit)
    }

    fun <T> backfilledHistory(
        history: List<T>, now: Long, hadConnection: Boolean,
        timestampOf: (T) -> Long, withDuration: (T, Long) -> T,
    ): List<T>? {
        val recovery = recovered(now, hadConnection) ?: return null
        val index = history.indexOfLast { timestampOf(it) == recovery.timestamp }
        if (index < 0) return null
        return history.mapIndexed { i, event ->
            if (i == index) withDuration(event, recovery.durationMs) else event
        }
    }
}

/** Per-identity durable reconnect evidence, separate from audio outage accounting. */
internal object BleConnectionHistory {
    fun connectedBefore(prefs: SharedPreferences, address: String, enabled: Boolean): Boolean {
        if (!enabled) return false
        val addr = address.uppercase()
        return prefs.getBoolean("ever_connected_$addr", false) ||
            prefs.contains("audio_outage_$addr") || prefs.getInt("reconnect_count_$addr", 0) > 0
    }

    fun connected(prefs: SharedPreferences, address: String) {
        val addr = address.uppercase()
        prefs.edit().putBoolean("ever_connected_$addr", true).remove("reconnect_event_$addr").apply()
    }

    fun disconnected(prefs: SharedPreferences, address: String, timestamp: Long) {
        prefs.edit().putLong("reconnect_event_${address.uppercase()}", timestamp).apply()
    }

    fun eventTimestamp(prefs: SharedPreferences, address: String): Long =
        prefs.getLong("reconnect_event_${address.uppercase()}", prefs.getLong("audio_outage_${address.uppercase()}", 0L))
}
