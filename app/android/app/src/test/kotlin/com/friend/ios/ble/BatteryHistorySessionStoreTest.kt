package com.friend.ios.ble

import org.junit.Assert.*
import org.junit.Test

class BatteryHistorySessionStoreTest {
    @Test fun `connect kill restart reconnect preserves unknown outage until recovery`() {
        val disk = mutableMapOf<String, String>()
        fun process() = BatteryHistorySessionStore({ disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        process().start("device", 1000, "new+2")
        val restarted = process()
        assertEquals(1000L, restarted.openSince("device"))
        restarted.start("device", 12000, "new+2")
        assertEquals(1000L, restarted.openSince("device"))
        disk.remove("audio_outage_device") // Successful packet recovery consumes the outage.
        assertNull(restarted.openSince("device"))
        assertTrue(disk["session_device"]!!.contains("new+2"))
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
