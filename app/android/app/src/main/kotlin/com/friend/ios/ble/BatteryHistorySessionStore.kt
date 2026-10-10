package com.friend.ios.ble

import org.json.JSONObject

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
        if (read("audio_outage_epoch_$device")?.toLongOrNull() == epoch()) read("audio_outage_$device")?.toLongOrNull()?.let { return it }
        if (device in live) return null
        val session = try { JSONObject(read("session_$device") ?: return null) } catch (_: Exception) { return null }
        return if (session.optLong("identity_epoch", -1) == epoch()) session.optLong("started_at") else null
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
