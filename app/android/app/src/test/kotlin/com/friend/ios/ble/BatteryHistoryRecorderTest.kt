package com.friend.ios.ble

import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test

class BatteryHistoryRecorderTest {
    @Test fun `unchanged notifications avoid reads and writes including relaunch`() {
        var stored = "[]"
        var reads = 0
        var writes = 0
        fun recorder() = BatteryHistoryRecorder({ reads++; stored }, { _, value -> writes++; stored = value })
        val first = recorder()
        first.record("device", 80, 0)
        repeat(1000) { first.record("device", 79, it.toLong()) }
        assertEquals(1, reads)
        assertEquals(1, writes)
        recorder().record("device", 79, 60_000)
        assertEquals(2, reads)
        assertEquals(1, writes)
        assertEquals(1, JSONArray(stored).length())
    }

    @Test fun `interval delta and both low threshold boundaries persist`() {
        for ((level, time) in listOf(79 to 900_000L, 75 to 1L, 85 to 1L)) {
            var writes = 0
            val recorder = BatteryHistoryRecorder({ """[{"ts":0,"level":80}]""" }, { _, _ -> writes++ })
            recorder.record("device", level, time)
            assertEquals(1, writes)
        }
        for ((before, after) in listOf(20 to 19, 19 to 20)) {
            var writes = 0
            val recorder = BatteryHistoryRecorder({ """[{"ts":0,"level":$before}]""" }, { _, _ -> writes++ })
            recorder.record("device", after, 1)
            assertEquals(1, writes)
        }
    }

    @Test fun `failed persistence keeps baseline and devices remain independent`() {
        val storage = mutableMapOf<String, String>()
        var fail = true
        val recorder = BatteryHistoryRecorder({ storage[it] ?: "[]" }, { key, value ->
            if (fail) throw IllegalStateException("failed write")
            storage[key] = value
        })
        assertThrows(IllegalStateException::class.java) { recorder.record("a", 80, 0) }
        fail = false
        recorder.record("a", 80, 1)
        recorder.record("b", 80, 1)
        assertEquals(setOf("a", "b"), storage.keys)
    }

    @Test fun `prunes expired samples tolerates malformed entries and clock rollback`() {
        var stored = """[{"ts":0,"level":80},null,{"level":5},{"ts":700000000,"level":60}]"""
        val recorder = BatteryHistoryRecorder({ stored }, { _, value -> stored = value })
        recorder.record("device", 60, 699_000_000)
        val history = JSONArray(stored)
        assertEquals(2, history.length())
        assertEquals(699_000_000L, history.getJSONObject(1).getLong("ts"))
    }
    @Test fun `just below interval and delta limits stay sampled and history stays capped`() {
        var writes = 0
        val unchanged = BatteryHistoryRecorder({ """[{"ts":0,"level":80}]""" }, { _, _ -> writes++ })
        unchanged.record("device", 76, 899_999)
        assertEquals(0, writes)
        val entries = JSONArray()
        repeat(2000) { entries.put(org.json.JSONObject().put("ts", it).put("level", 80)) }
        var stored = entries.toString()
        BatteryHistoryRecorder({ stored }, { _, value -> stored = value }).record("device", 75, 2000)
        assertEquals(2000, JSONArray(stored).length())
        assertEquals(1, JSONArray(stored).getJSONObject(0).getInt("ts"))
    }

    @Test fun `shared retention includes exact cutoff and excludes older samples`() {
        assertEquals(7L * 24 * 3600 * 1000, BatteryHistoryRecorder.RETENTION_MS)
        assertEquals(2000, BatteryHistoryRecorder.MAX_POINTS)
        var stored = """[{"ts":99,"level":80},{"ts":100,"level":80}]"""
        val recorder = BatteryHistoryRecorder({ stored }, { _, value -> stored = value })
        recorder.record("device", 80, BatteryHistoryRecorder.RETENTION_MS + 100)
        val history = JSONArray(stored)
        assertEquals(2, history.length())
        assertEquals(100L, history.getJSONObject(0).getLong("ts"))
    }

}
