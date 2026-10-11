package com.friend.ios.ble

import org.json.JSONArray
import org.json.JSONObject

/** Persist only useful chart samples; callers still deliver every live battery notification. */
internal class BatteryHistoryRecorder(
    private val read: (String) -> String,
    private val write: (String, String) -> Unit,
) {
    companion object {
        const val RETENTION_MS = 7L * 24 * 3600 * 1000
        const val MAX_POINTS = 2000
        const val BACKFILL_MAX_AGE_MS = 15L * 60 * 1000
    }

    private data class Point(val level: Int, val timestamp: Long, val charging: Boolean?)
    private val baselines = mutableMapOf<String, Point?>()

    @Synchronized
    fun retire() { baselines.clear() }

    @Synchronized
    fun backfillCharging(key: String, charging: Boolean, nowMs: Long = System.currentTimeMillis()) {
        val history = history(key)
        val latest = history.optJSONObject(history.length() - 1) ?: return
        // Only tag a recent point: stamping the state observed now onto a
        // hours-old sample would mislabel historical battery data.
        if (nowMs - latest.optLong("ts", 0L) > BACKFILL_MAX_AGE_MS) return
        val sample = point(latest) ?: return
        if (!latest.isNull("charging")) return
        latest.put("charging", charging)
        write(key, history.toString())
        baselines[key] = sample.copy(charging = charging)
    }

    @Synchronized
    fun record(key: String, level: Int, nowMs: Long, charging: Boolean? = null, appBuild: String? = null, firmware: String? = null, identityEpoch: Long? = null) {
        var history: JSONArray? = null
        if (!baselines.containsKey(key)) {
            val loaded = history(key)
            history = loaded
            baselines[key] = (loaded.length() - 1 downTo 0).firstNotNullOfOrNull { index ->
                loaded.optJSONObject(index)?.let { point(it) }
            }
        }
        val previous = baselines[key]
        if (previous != null && nowMs >= previous.timestamp &&
            nowMs - previous.timestamp < 60 * 60_000L && level == previous.level && charging == previous.charging) return

        val source = history ?: history(key)
        val pruned = JSONArray()
        val cutoff = nowMs - RETENTION_MS
        for (index in 0 until source.length()) {
            val entry = source.optJSONObject(index) ?: continue
            val sample = point(entry) ?: continue
            if (sample.timestamp >= cutoff) pruned.put(entry)
        }
        pruned.put(JSONObject().put("ts", nowMs).put("level", level).put("charging", charging ?: JSONObject.NULL)
            .put("identity_epoch", identityEpoch ?: JSONObject.NULL).put("app_build", appBuild ?: JSONObject.NULL).put("firmware", firmware ?: JSONObject.NULL))
        while (pruned.length() > MAX_POINTS) pruned.remove(0)
        write(key, pruned.toString())
        // Advance only after the persistence call succeeds; retries keep the last submitted baseline.
        baselines[key] = Point(level, nowMs, charging)
    }

    private fun history(key: String): JSONArray = try { JSONArray(read(key)) } catch (_: Exception) { JSONArray() }

    private fun point(json: JSONObject): Point? = try {
        Point(json.getInt("level"), json.getLong("ts"), if (json.isNull("charging")) null else json.optBoolean("charging"))
    } catch (_: Exception) { null }
}
