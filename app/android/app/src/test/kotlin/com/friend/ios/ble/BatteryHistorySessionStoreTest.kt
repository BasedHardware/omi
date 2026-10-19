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
    @Test fun `synthetic recovery without a disconnect is not billable`() {
        val history = JSONArray()
            .put(JSONObject().put("eventType", "audio_recovered").put("timestamp", 1000).put("lostAudioResolvedAt", 20000))
            .put(JSONObject().put("eventType", "disconnect").put("timestamp", 8000))
            .put(JSONObject().put("eventType", "audio_recovered").put("timestamp", 8002).put("lostAudioResolvedAt", 9000))
        assertFalse(audioOutageMatchesDisconnect(history, 1000))
        assertTrue(audioOutageMatchesDisconnect(history, 8002))
        val kept = dropUnmeasuredAudioRecoveries(history)
        assertEquals(2, kept.length())
        assertEquals("disconnect", kept.getJSONObject(0).getString("eventType"))
        assertEquals(8002L, kept.getJSONObject(1).getLong("timestamp"))
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
