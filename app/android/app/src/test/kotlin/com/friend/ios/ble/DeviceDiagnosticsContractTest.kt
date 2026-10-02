package com.friend.ios.ble

import org.junit.Assert.*
import org.junit.Test

class DeviceDiagnosticsContractTest {
    @Test fun `local host termination does not claim another phone paired`() {
        // HCI 0x16 reports local termination, not the reason the host requested it.
        assertEquals("gatt_error_22", BleDisconnectReason.fromStatus(0x16))
    }

    @Test fun `link layer response timeout is classified as a timeout`() {
        assertEquals("connection_timeout", BleDisconnectReason.fromStatus(0x22))
    }

    @Test fun `connection establishment failure is not an instant passed error`() {
        // HCI Instant Passed is 0x28, not the failed-establishment status 0x3e.
        assertEquals("gatt_error_62", BleDisconnectReason.fromStatus(0x3e))
        assertEquals("gatt_error_40", BleDisconnectReason.fromStatus(0x28))
    }

    @Test fun `adjacent HCI statuses retain their existing reason vocabulary`() {
        val expected = mapOf(
            0 to "clean_disconnect", 8 to "connection_timeout", 19 to "remote_device_terminated",
            -1 to "app_closed", 133 to "gatt_error_133",
        )
        for ((status, reason) in expected) assertEquals(reason, BleDisconnectReason.fromStatus(status))
    }

    @Test fun `firmware decoder rejects short and version zero and accepts append fields`() {
        assertNull(FirmwareDiagnosticsParser.parse(ByteArray(24), 1))
        assertNull(FirmwareDiagnosticsParser.parse(ByteArray(25), 1))
        val value = ByteArray(30)
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
