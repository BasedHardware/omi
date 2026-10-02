package com.friend.ios.ble

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
}
