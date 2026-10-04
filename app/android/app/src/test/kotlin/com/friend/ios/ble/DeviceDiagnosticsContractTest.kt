package com.friend.ios.ble

import org.junit.Assert.*
import org.junit.Test
import org.json.JSONArray

class DeviceDiagnosticsContractTest {
    @Test fun `firmware decoder rejects short and version zero and accepts append fields`() {
        assertNull(FirmwareDiagnosticsParser.parse(ByteArray(24), 1))
        assertNull(FirmwareDiagnosticsParser.parse(ByteArray(25), 1))
        val value = ByteArray(25)
        value[0] = 1
        value[1] = 0x11
        value[5] = 42
        value[9] = 0x34
        value[10] = 0x12
        value[11] = 1
        val decoded = FirmwareDiagnosticsParser.parse(value, 123)!!
        assertEquals(1, decoded.getInt("version"))
        assertEquals(17L, decoded.getLong("reset_cause_raw"))
        assertEquals("RESET_PIN", decoded.getJSONArray("reset_cause_names").getString(0))
        assertEquals("RESET_WATCHDOG", decoded.getJSONArray("reset_cause_names").getString(1))
        assertEquals(42L, decoded.getLong("uptime_s"))
        assertEquals(0x1234, decoded.getInt("battery_mv"))
        assertTrue(decoded.getBoolean("charging"))
        assertFalse(decoded.has("last_off_charger_mv"))
        assertFalse(decoded.has("charge_pin_edges"))
        assertFalse(decoded.has("soc_frozen"))
        val tail = value.copyOf(30)
        tail[25] = 0x34
        tail[26] = 0x12
        tail[27] = 0x78
        tail[28] = 0x56
        tail[29] = 1
        val extended = FirmwareDiagnosticsParser.parse(tail, 123)!!
        for (key in decoded.keys()) assertEquals(decoded.get(key).toString(), extended.get(key).toString())
        assertEquals(0x1234, extended.getInt("last_off_charger_mv"))
        assertEquals(0x5678, extended.getInt("charge_pin_edges"))
        assertTrue(extended.getBoolean("soc_frozen"))
        assertEquals(extended.toString(), FirmwareDiagnosticsParser.parse(tail.copyOf(35), 123)!!.toString())
        tail[29] = 0
        assertFalse(FirmwareDiagnosticsParser.parse(tail, 123)!!.getBoolean("soc_frozen"))
        for (offset in 25..29) tail[offset] = 0xff.toByte()
        val unknownTail = FirmwareDiagnosticsParser.parse(tail, 123)!!
        for (key in listOf("last_off_charger_mv", "charge_pin_edges", "soc_frozen")) assertFalse(unknownTail.has(key))
        for (length in 26..29) {
            val partial = FirmwareDiagnosticsParser.parse(tail.copyOf(length), 123)!!
            assertFalse(partial.has("last_off_charger_mv"))
        }
    }

    @Test fun `charging backfill updates only the latest point and the persistence baseline`() {
        for (charging in listOf(true, false)) {
            for (unknown in listOf("", ",\"charging\":null")) {
                var stored = """[{"ts":0,"level":100},{"ts":5,"level":45$unknown}]"""
                var writes = 0
                val recorder = BatteryHistoryRecorder({ stored }, { _, value -> stored = value; writes++ })
                recorder.backfillCharging("device", charging, nowMs = 5)
                val history = JSONArray(stored)
                assertEquals(2, history.length())
                assertTrue(history.getJSONObject(0).isNull("charging"))
                assertEquals(5L, history.getJSONObject(1).getLong("ts"))
                assertEquals(45, history.getJSONObject(1).getInt("level"))
                assertEquals(charging, history.getJSONObject(1).getBoolean("charging"))
                recorder.record("device", 45, 6, charging)
                recorder.backfillCharging("device", !charging)
                assertEquals(1, writes)
                assertEquals(stored, history.toString())
                // A point older than the backfill window stays unknown.
                recorder.backfillCharging("device", !charging, nowMs = 6 + BatteryHistoryRecorder.BACKFILL_MAX_AGE_MS)
                assertEquals(1, writes)
            }
        }
    }

    @Test fun `packet counter accounts for gap wrap duplicate and restart`() {
        val counter = BleAudioPacketCounter()
        fun packet(index: Int) = byteArrayOf(index.toByte(), (index shr 8).toByte(), 0)
        assertFalse(counter.record(byteArrayOf(1, 2)))
        assertTrue(counter.record(packet(65534)))
        assertTrue(counter.record(packet(1))) // Two missing packets across wrap.
        assertFalse(counter.record(packet(1)))
        assertEquals(2L, counter.received)
        assertEquals(4L, counter.expected)
        assertTrue(counter.record(packet(10000)))
        assertTrue(counter.record(packet(10001)))
        assertEquals(4L, counter.received)
        assertEquals(6L, counter.expected)
    }

    @Test fun `rssi trend and sample age use the disconnect window`() {
        val now = 100_000L
        assertEquals("gap", BleRssiDiagnostics.trend(listOf(1L to -50), now))
        assertEquals("unknown", BleRssiDiagnostics.trend(listOf(99_000L to -50), now))
        val fading = listOf(90_000L to -55, 99_000L to -72)
        assertEquals("fading", BleRssiDiagnostics.trend(fading, now))
        assertEquals(1_000L, BleRssiDiagnostics.ageMs(fading, now))
        assertEquals(-1L, BleRssiDiagnostics.ageMs(emptyList(), now))
    }
}
