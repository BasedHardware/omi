package com.friend.ios.ble

import org.junit.Assert.*
import org.junit.Test
import org.json.JSONArray
import org.json.JSONObject
import android.app.Activity
import android.app.Application
import android.content.Context
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothGattCallback
import android.os.SystemClock
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

class DeviceDiagnosticsContractTest {
    @Test fun `read outcomes do not fabricate an attempt or parse success`() {
        for (outcome in FirmwareReadOutcome.entries) {
            val status = firmwareReadDiagnosticStatus(JSONObject(), outcome, null, 100)
            assertEquals(outcome.name.lowercase(), status.getString("outcome"))
            assertEquals("not_attempted", status.getString("parse_outcome"))
            assertEquals(outcome != FirmwareReadOutcome.ATTEMPTED, status.isNull("attempted_at_ms"))
        }
        val attempted = firmwareReadDiagnosticStatus(JSONObject(), FirmwareReadOutcome.ATTEMPTED, null, 100)
        val timedOut = firmwareReadDiagnosticStatus(attempted, FirmwareReadOutcome.TIMEOUT, null, 110)
        val skipped = firmwareReadDiagnosticStatus(timedOut, FirmwareReadOutcome.SKIPPED, "throttled", 120)
        assertEquals(100L, skipped.getLong("attempted_at_ms"))
        assertEquals("throttled", skipped.getString("skip_reason"))
        assertEquals("timeout", skipped.getString("last_attempt_outcome"))
        assertFalse(skipped.toString().contains("payload"))
    }
    @Test fun `audio age is generation scoped and remains unknown without a notification`() {
        val samples = GenerationAudioAge<Any>()
        val old = Any()
        val current = Any()
        assertNull(samples.ageMs("device", old, 100))
        samples.begin("device", old)
        samples.record("device", old, 100)
        assertEquals(50L, samples.ageMs("device", old, 150))
        assertNull(samples.ageMs("device", current, 150))
        samples.forget("device")
        assertNull(samples.ageMs("device", old, 150))
        samples.begin("device", current)
        samples.record("device", current, 200)
        samples.record("device", old, 220)
        assertEquals(50L, samples.ageMs("device", current, 250))
        assertNull(samples.ageMs("device", current, 199))
        samples.forget("device")
        samples.record("device", current, 300)
        assertNull(samples.ageMs("device", current, 300))
        samples.clear()
        assertNull(samples.ageMs("device", current, 300))
    }
    @Test fun `CCCD timeout retains retry and exhausted recovery reasons`() {
        val status = OmiBleManager.CCCD_TIMEOUT_STATUS
        assertEquals("cccd_timeout", BleDisconnectReason.connectionErrorFromStatus(status, true))
        assertEquals("cccd_timeout_exhausted", BleDisconnectReason.connectionErrorFromStatus(status, false))
        assertEquals("cccd_ack_timeout", BleDisconnectReason.fromStatus(status))
        assertEquals("gatt_status_22", BleDisconnectReason.connectionErrorFromStatus(0x16, false))
    }

    @Test fun `local host termination during readiness keeps its status without a pairing claim`() {
        assertEquals("gatt_status_22", BleDisconnectReason.connectionErrorFromStatus(0x16))
    }

    @Test fun `connection errors preserve bond loss clean disconnect and generic statuses`() {
        assertEquals("pairing_lost", BleDisconnectReason.connectionErrorFromStatus(137))
        assertNull(BleDisconnectReason.connectionErrorFromStatus(0))
        for (status in listOf(-1, 8, 19, 34, 62, 133)) {
            assertEquals("gatt_status_$status", BleDisconnectReason.connectionErrorFromStatus(status))
        }
    }

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

@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class, sdk = [35])
class FeedbackDiagnosticsServiceParityTest {
    @Test fun `a callback captured before retirement cannot record in the next identity`() {
        val app = RuntimeEnvironment.getApplication()
        OmiBleManager.initialize(app)
        val manager = OmiBleManager.instance
        val address = "00:11:22:33:44:55"
        val gatt = BluetoothAdapter.getDefaultAdapter().getRemoteDevice(address)
            .connectGatt(app, false, object : BluetoothGattCallback() {}) ?: error("Robolectric GATT unavailable")
        manager.connectedGatts[address] = gatt
        DeviceHealthPersistence.setPolicy(app, true, 7, true)
        manager.recordAudioNotification(address, gatt, 7, SystemClock.elapsedRealtime())
        assertNotNull(manager.lastAudioNotificationAgeMs(address))
        // The callback already captured epoch 7, then waited behind retirement.
        lateinit var delayed: Thread
        synchronized(DeviceHealthPersistence) {
            delayed = Thread { manager.recordAudioNotification(address, gatt, 7, SystemClock.elapsedRealtime()) }
            delayed.start()
            DeviceHealthPersistence.setPolicy(app, true, 8, true)
        }
        delayed.join(5000)
        assertFalse(delayed.isAlive)
        assertNull(manager.lastAudioNotificationAgeMs(address))
        manager.recordAudioNotification(address, gatt, 8, SystemClock.elapsedRealtime())
        assertNotNull(manager.lastAudioNotificationAgeMs(address))
        manager.closeGatt(address)
        manager.recordAudioNotification(address, gatt, 8, SystemClock.elapsedRealtime())
        assertNull(manager.lastAudioNotificationAgeMs(address))
        DeviceHealthPersistence.setPolicy(app, false, 9, true)
    }

    @Test fun `persisted feedback evidence exports with service present and absent and obeys retirement`() {
        val app = RuntimeEnvironment.getApplication()
        OmiBleManager.initialize(app)
        DeviceHealthPersistence.setPolicy(app, true, 7, true)
        val prefs = app.getSharedPreferences("ble_diagnostics", Context.MODE_PRIVATE)
        val service = Robolectric.buildService(OmiBleForegroundService::class.java).get()
        val activity = Robolectric.buildActivity(Activity::class.java).get()
        val host = BleHostApiImpl { activity }
        for (populated in listOf(false, true)) {
            if (populated) prefs.edit()
                .putString("firmware_read_DEVICE", "{\"outcome\":\"timeout\",\"parse_outcome\":\"not_attempted\"}")
                .putString("process_exit_collection", "{\"outcome\":\"empty\",\"records\":[]}")
                .putString("previous_run_exit", "{\"legacy_run_open\":true,\"match\":\"unknown\",\"exit\":null}").commit()
            val present = JSONObject(service.getExtendedDeviceDiagnostics("device"))
            var absent = JSONObject()
            host.getExtendedDeviceDiagnostics("device") { absent = JSONObject(it.getOrThrow()) }
            for (field in listOf("firmware_diagnostics_read", "process_exit_collection", "previous_run_exit", "battery_history_v2", "disconnect_history_v2")) {
                assertEquals(field, present.get(field).toString(), absent.get(field).toString())
                if (!populated && field.endsWith("collection")) assertTrue(present.isNull(field))
            }
        }
        DeviceHealthPersistence.setPolicy(app, false, 8, true)
        assertEquals("{}", service.getExtendedDeviceDiagnostics("device"))
        host.getExtendedDeviceDiagnostics("device") { assertEquals("{}", it.getOrThrow()) }
        assertFalse(prefs.contains("process_exit_collection"))
    }
}
