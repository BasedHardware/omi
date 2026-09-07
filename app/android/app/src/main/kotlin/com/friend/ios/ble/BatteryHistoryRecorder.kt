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
    }

    private data class Point(val level: Int, val timestamp: Long)
    private val baselines = mutableMapOf<String, Point?>()

    @Synchronized
    fun record(key: String, level: Int, nowMs: Long) {
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
            nowMs - previous.timestamp < 15 * 60_000L &&
            kotlin.math.abs(level - previous.level) < 5 &&
            (level < 20) == (previous.level < 20)) return

        val source = history ?: history(key)
        val pruned = JSONArray()
        val cutoff = nowMs - RETENTION_MS
        for (index in 0 until source.length()) {
            val entry = source.optJSONObject(index) ?: continue
            val sample = point(entry) ?: continue
            if (sample.timestamp >= cutoff) pruned.put(entry)
        }
        pruned.put(JSONObject().put("ts", nowMs).put("level", level))
        while (pruned.length() > MAX_POINTS) pruned.remove(0)
        write(key, pruned.toString())
        // Advance only after the persistence call succeeds; retries keep the last submitted baseline.
        baselines[key] = Point(level, nowMs)
    }

    private fun history(key: String): JSONArray = try { JSONArray(read(key)) } catch (_: Exception) { JSONArray() }

    private fun point(json: JSONObject): Point? = try {
        Point(json.getInt("level"), json.getLong("ts"))
    } catch (_: Exception) { null }
}
