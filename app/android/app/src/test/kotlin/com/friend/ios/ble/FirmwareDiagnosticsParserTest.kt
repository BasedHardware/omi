package com.friend.ios.ble

import org.junit.Assert.*
import org.junit.Test

class FirmwareDiagnosticsParserTest {
    @Test fun `firmware connection tail preserves old fields and ignores incomplete or unknown values`() {
        val base = ByteArray(25).also { it[0] = 1 }
        val keys = listOf("conn_interval", "conn_latency", "conn_timeout", "tx_phy", "rx_phy")
        for (length in 25..37) {
            val partial = FirmwareDiagnosticsParser.parse(base.copyOf(length), 1)!!
            for (key in keys) assertFalse(partial.has(key))
        }
        val tail = base + byteArrayOf(-1, -1, -1, -1, -1, 0x34, 0x12, 0x78, 0x56, 0x58, 2, 2, 4)
        val parsed = FirmwareDiagnosticsParser.parse(tail, 1)!!
        for ((key, expected) in keys.zip(listOf(0x1234, 0x5678, 600, 2, 4))) assertEquals(expected, parsed.getInt(key))
        for (key in listOf("last_off_charger_mv", "charge_pin_edges", "soc_frozen")) assertFalse(parsed.has(key))
        val old = FirmwareDiagnosticsParser.parse(base, 1)!!
        for (key in old.keys()) assertEquals(old.get(key).toString(), parsed.get(key).toString())
        assertEquals(parsed.toString(), FirmwareDiagnosticsParser.parse(tail + byteArrayOf(99), 1)!!.toString())
        for (offset in 30..37) tail[offset] = -1
        for (key in keys) assertFalse(FirmwareDiagnosticsParser.parse(tail, 1)!!.has(key))
        for (offset in 30..37) tail[offset] = 0
        tail[36] = 1; tail[37] = 1
        val zero = FirmwareDiagnosticsParser.parse(tail, 1)!!
        assertEquals(0, zero.getInt("conn_latency"))
        assertEquals(1, zero.getInt("tx_phy"))
    }

    @Test fun `base and battery extension remain compatible`() {
        assertNull(FirmwareDiagnosticsParser.parse(ByteArray(24), 1))
        assertNull(FirmwareDiagnosticsParser.parse(ByteArray(25), 1))
        val base = ByteArray(25).also { it[0] = 1; it[5] = 42 }
        val old = FirmwareDiagnosticsParser.parse(base, 1)!!
        assertEquals(42L, old.getLong("uptime_s"))
        assertFalse(old.has("conn_interval"))
        val battery = base + byteArrayOf(0x34, 0x12, 0x78, 0x56, 1)
        val decoded = FirmwareDiagnosticsParser.parse(battery, 1)!!
        assertEquals(0x1234, decoded.getInt("last_off_charger_mv"))
        assertEquals(0x5678, decoded.getInt("charge_pin_edges"))
        assertTrue(decoded.getBoolean("soc_frozen"))
        assertFalse(decoded.has("conn_timeout"))
    }
}
