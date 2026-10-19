package com.friend.ios.ble

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class BatteryHistorySessionStoreTest {
    @Test fun `process death does not turn the live session start into an outage`() {
        val disk = mutableMapOf<String, String>()
        fun process() = BatteryHistorySessionStore({ disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        process().start("device", 1000, "new+2")
        val restarted = process()
        assertNull(restarted.openSince("device"))
        restarted.start("device", 12000, "new+2")
        assertNull(restarted.openSince("device"))
        assertFalse(disk.keys.any { it.startsWith("audio_outage_") })
        assertTrue(disk["session_device"]!!.contains("new+2"))
    }
    @Test fun `measured disconnect marker survives reconnect until recovery`() {
        val disk = mutableMapOf<String, String>()
        fun process() = BatteryHistorySessionStore({ disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        val first = process()
        first.start("device", 1000, "new+2")
        first.end("device", 5000)
        val restarted = process()
        assertEquals(5000L, restarted.openSince("device"))
        restarted.start("device", 12000, "new+2")
        assertEquals(5000L, restarted.openSince("device"))
        disk.remove("audio_outage_device")
        assertNull(restarted.openSince("device"))
    }
    @Test fun `session start echo is discarded and not revived`() {
        val disk = mutableMapOf<String, String>()
        fun process() = BatteryHistorySessionStore({ disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        val first = process()
        first.start("device", 1000, "build")
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = "1000"
        val restarted = process()
        assertNull(restarted.openSince("device"))
        assertFalse(disk.keys.any { it.startsWith("audio_outage_") })
        restarted.start("device", 12000, "build")
        assertNull(restarted.openSince("device"))
        assertTrue(disk["session_device"]!!.contains("12000"))
        // A disconnect a few seconds before this session is a fast reconnect, not an echo.
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = "9000"
        assertEquals(9000L, restarted.openSince("device"))
        assertEquals("9000", disk["audio_outage_device"])
    }
    @Test fun `pruned disconnect history keeps a genuine marker`() {
        val disk = mutableMapOf<String, String>()
        val store = BatteryHistorySessionStore({ disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        store.start("device", 1000, "build")
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = "90000"
        assertEquals(90000L, store.openSince("device"))
        assertEquals("90000", disk["audio_outage_device"])
        val plan = planAudioOutageCleanup("[]", disk["session_device"], 7L, 90000L, markerEpochMatches = true)
        assertFalse(plan.dropMarker)
        assertNull(plan.rewrittenHistory)
    }
    @Test fun `unreadable disconnect history keeps a genuine marker`() {
        val session = JSONObject().put("device", "device").put("started_at", 1000).put("identity_epoch", 7).toString()
        val genuine = planAudioOutageCleanup("{", session, 7L, 90000L, markerEpochMatches = true)
        assertFalse(genuine.dropMarker)
        assertNull(genuine.rewrittenHistory)
        val echo = planAudioOutageCleanup("{", session, 7L, 1000L, markerEpochMatches = true)
        assertTrue(echo.dropMarker)
        assertNull(echo.rewrittenHistory)
        val mismatchedEpoch = planAudioOutageCleanup("[]", session, 8L, 1000L, markerEpochMatches = true)
        assertFalse(mismatchedEpoch.dropMarker)
        assertNull(mismatchedEpoch.rewrittenHistory)
    }
    @Test fun `only a session-start echo recovery is dropped`() {
        val history = JSONArray()
            .put(JSONObject().put("eventType", "audio_recovered").put("timestamp", 1000).put("lostAudioResolvedAt", 20000))
            .put(JSONObject().put("eventType", "disconnect").put("timestamp", 8000))
            .put(JSONObject().put("eventType", "audio_recovered").put("timestamp", 90000).put("lostAudioResolvedAt", 91000))
        val kept = dropUnmeasuredAudioRecoveries(history, 1000)
        assertEquals(2, kept.length())
        assertEquals("disconnect", kept.getJSONObject(0).getString("eventType"))
        assertEquals(90000L, kept.getJSONObject(1).getLong("timestamp"))
        assertSame(history, dropUnmeasuredAudioRecoveries(history, null))
        val beforeSession = JSONArray().put(JSONObject().put("eventType", "audio_recovered").put("timestamp", 9000))
        assertSame(beforeSession, dropUnmeasuredAudioRecoveries(beforeSession, 12000))
    }
    @Test fun `manual teardown writes marker before session cleanup`() {
        val disk = mutableMapOf<String, String>()
        val operations = mutableListOf<String>()
        val store = BatteryHistorySessionStore({ disk[it] }, { k, v -> operations.add("write:$k"); disk[k] = v },
            { operations.add("remove:$it"); disk.remove(it) }, { 1L }, { true })
        store.start("device", 1000, "build")
        operations.clear()
        store.end("device", 2000)
        assertEquals(listOf("write:audio_outage_epoch_device", "write:audio_outage_device", "remove:session_device"), operations)
        assertEquals(2000L, store.openSince("device"))
    }
    @Test fun `consent and identity fence restart records`() {
        val disk = mutableMapOf<String, String>()
        var epoch = 1L
        var enabled = true
        fun store() = BatteryHistorySessionStore({ disk[it] }, { k, v -> disk[k] = v }, { disk.remove(it) }, { epoch }, { enabled })
        store().start("device", 1000, "build")
        epoch++
        assertNull(store().openSince("device"))
        disk.clear()
        enabled = false
        store().start("device", 2000, "build")
        store().end("device", 3000)
        assertTrue(disk.isEmpty())
    }
}
