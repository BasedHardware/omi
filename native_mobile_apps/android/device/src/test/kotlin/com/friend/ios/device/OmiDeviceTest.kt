package com.friend.ios.device

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

private fun bytes(vararg values: Int) = ByteArray(values.size) { values[it].toByte() }
private fun be(value: Long, count: Int) = value.bigEndianBytes(count)
private fun le(value: Long, count: Int) = value.littleEndianBytes(count)

/** Port of `OmiGATTTests` + `PairedDeviceTests`. */
class OmiGATTTest {
    @Test fun stripsThreeByteHeader() {
        val frame = assertNotNullAndGet(OmiGATT.audioPayload(bytes(0x34, 0x12, 0x00, 0xAA, 0xBB)))
        assertEquals(0x1234, frame.packetID)
        assertArrayEquals(bytes(0xAA, 0xBB), frame.payload)
        assertNull(OmiGATT.audioPayload(bytes(0x01, 0x02, 0x03)))
    }

    @Test fun codecMapping() {
        assertEquals("opus_fs320", OmiGATT.Codec.fromRaw(21)?.listenValue)
        assertEquals(8000, OmiGATT.Codec.Pcm8.sampleRate)
        assertEquals(16000, OmiGATT.Codec.OpusFS320.sampleRate)
    }

    @Test fun recognizesOmiAdvertisements() {
        assertTrue(OmiGATT.isOmi("Omi DevKit 2", emptyList()))
        assertTrue(OmiGATT.isOmi(null, listOf(OmiGATT.audioService)))
        assertFalse(OmiGATT.isOmi("AirPods", emptyList()))
    }

    @Test fun shortUUIDsUseTheBluetoothBase() {
        assertEquals("0000180f-0000-1000-8000-00805f9b34fb", OmiGATT.batteryService.toString())
        assertEquals("00002a19-0000-1000-8000-00805f9b34fb", OmiGATT.batteryLevel.toString())
    }

    @Test fun parsesButtonEvents() {
        assertEquals(OmiGATT.ButtonEvent.DoubleTap, OmiGATT.ButtonEvent.from(bytes(2, 0, 0, 0)))
        assertEquals(OmiGATT.ButtonEvent.Release, OmiGATT.ButtonEvent.from(bytes(5, 0, 0, 0)))
        assertNull(OmiGATT.ButtonEvent.from(bytes(1, 0)))
        assertNull(OmiGATT.ButtonEvent.from(bytes(9, 0, 0, 0)))
    }

    /** Shape the Flutter app writes under `flutter.btDevice`. */
    @Test fun readsFlutterBtDevice() {
        val json = """{"name":"Omi","id":"AA:BB:CC:DD:EE:FF","type":"omi","rssi":-58,"locator":null,"modelNumber":"Omi CV 1","firmwareRevision":"2.0.10"}"""
        val device = assertNotNullAndGet(PairedDevice.decode(json))
        assertEquals("Omi", device.name)
        assertEquals("2.0.10", device.firmwareRevision)
        assertEquals(-58, device.rssi)
        assertEquals(device.id, PairedDevice.decode(device.encoded)?.id)
        assertNull(PairedDevice.decode(""))
        assertNull(PairedDevice.decode("""{"name":"Omi","id":""}"""))
        // An rssi stored as a string by an older Flutter build still decodes.
        assertEquals(-40, PairedDevice.decode("""{"name":"Omi","id":"X","rssi":"-40"}""")?.rssi)
    }
}

/** Port of `OmiControlsTests`: byte layouts from firmware `transport.c`, `haptic.c`, `features.h`. */
class OmiControlsTest {
    /** A CV1 build: button, battery, USB, haptic, offline storage, LED dimming, mic gain = 0x1FC. */
    @Test fun parsesFeatureBitmask() {
        val features = OmiGATT.Features.from(bytes(0xFC, 0x01, 0x00, 0x00))
        assertTrue(features.contains(OmiGATT.Features.button))
        assertTrue(features.contains(OmiGATT.Features.haptic))
        assertTrue(features.contains(OmiGATT.Features.offlineStorage))
        assertTrue(features.contains(OmiGATT.Features.ledDimming))
        assertTrue(features.contains(OmiGATT.Features.micGain))
        assertFalse(features.contains(OmiGATT.Features.speaker))
        assertFalse(features.contains(OmiGATT.Features.accelerometer))
        assertEquals(0L, OmiGATT.Features.from(bytes(0x01, 0x00)).rawValue)
        assertEquals(OmiGATT.Features.ledDimming, OmiGATT.Features.from(bytes(0x80, 0, 0, 0)))
    }

    /** The dim-ratio and mic-gain writes take exactly one byte; firmware caps 100 and 8. */
    @Test fun encodesSettingsWrites() {
        assertArrayEquals(bytes(42), OmiGATT.ledBrightnessPayload(42))
        assertArrayEquals(bytes(100), OmiGATT.ledBrightnessPayload(150))
        assertArrayEquals(bytes(0), OmiGATT.ledBrightnessPayload(-5))
        assertArrayEquals(bytes(5), OmiGATT.micGainPayload(5))
        assertArrayEquals(bytes(8), OmiGATT.micGainPayload(12))
        assertArrayEquals(bytes(0), OmiGATT.micGainPayload(-1))
    }

    @Test fun readsSettingsAndCharging() {
        assertEquals(100, OmiGATT.settingValue(bytes(0x64)))
        assertEquals(200, OmiGATT.settingValue(bytes(0xC8)))
        assertNull(OmiGATT.settingValue(ByteArray(0)))
        assertEquals(true, OmiGATT.isCharging(bytes(1)))
        assertEquals(false, OmiGATT.isCharging(bytes(0)))
        assertNull(OmiGATT.isCharging(ByteArray(0)))
    }

    @Test fun encodesHaptics() {
        assertArrayEquals(bytes(1), OmiGATT.Haptic.Short.payload)
        assertArrayEquals(bytes(2), OmiGATT.Haptic.Medium.payload)
        assertArrayEquals(bytes(3), OmiGATT.Haptic.Long.payload)
        assertEquals(List(3) { OmiGATT.Haptic.Long }, OmiGATT.findPattern)
        assertEquals(OmiGATT.haptic, OmiGATT.Control.Haptic.characteristic)
        assertEquals(OmiGATT.ledDimRatio, OmiGATT.Control.LedBrightness.characteristic)
    }

    @Test fun parsesSerialNumber() {
        assertEquals("0A1B2C3D4E5F6789", OmiGATT.serialNumber("0a1b2c3d4e5f6789\u0000".toByteArray()))
        assertEquals("0A1B2C3D4E5F6789", OmiGATT.serialNumber(" 0A1B2C3D4E5F6789 ".toByteArray()))
        assertNull(OmiGATT.serialNumber("unknown".toByteArray()))
        assertNull(OmiGATT.serialNumber("FFFFFFFFFFFFFFFF".toByteArray()))
        assertNull(OmiGATT.serialNumber("0A1B2C3D4E5F67".toByteArray()))
        assertNull(OmiGATT.serialNumber(ByteArray(0)))
    }

    @Test fun pairedDeviceKeepsSerial() {
        val json = """{"name":"Omi","id":"AA:BB","type":"omi","rssi":-58,"serialNumber":"0A1B2C3D4E5F6789"}"""
        val device = assertNotNullAndGet(PairedDevice.decode(json))
        assertEquals("0A1B2C3D4E5F6789", device.serialNumber)
        assertEquals("0A1B2C3D4E5F6789", PairedDevice.decode(device.encoded)?.serialNumber)
    }
}

/** Port of `OmiStorageTests`: fixtures laid out like firmware `storage.c` and `transport.c`. */
class OmiStorageTest {
    @Test fun encodesCommands() {
        assertArrayEquals(bytes(0x10), OmiStorage.Command.Info.bytes)
        assertArrayEquals(bytes(0x03), OmiStorage.Command.Stop.bytes)
        assertArrayEquals(bytes(0x11, 0, 0, 0, 0, 0, 0, 0x01, 0x02), OmiStorage.Command.Read(0x0102, null).bytes)
        assertArrayEquals(bytes(0x11, 0, 0, 0, 0, 0, 0, 0, 7, 0, 0, 0x02, 0x58), OmiStorage.Command.Read(7, 600).bytes)
        assertArrayEquals(bytes(0x12, 0, 0, 0, 1, 0, 0, 0, 1), OmiStorage.Command.Advance(0x1_0000_0001L).bytes)
    }

    /** `send_ring_info_response`: read u64, write u64, capacity u32, dropped u64, record size u16 (31 bytes). */
    @Test fun parsesLegacyInfo() {
        val value = bytes(0x02) + be(120, 8) + be(1320, 8) + be(1_000_000, 4) + be(3, 8) + be(444, 2)
        val info = (OmiStorage.Notification.from(value) as OmiStorage.Notification.InfoReply).info
        assertEquals(OmiStorage.Info(readSeq = 120, writeSeq = 1320, capacity = 1_000_000, dropped = 3, ringID = null), info)
        assertEquals(1200L, info.unread)
    }

    @Test fun parsesCustodyInfoRingID() {
        val value = bytes(0x02) + be(5, 8) + be(9, 8) + be(10, 4) + be(0, 8) + be(444, 2) + bytes(0x0F, 0x01) + be(0xABCD, 8)
        assertEquals(0xABCDL, (OmiStorage.Notification.from(value) as OmiStorage.Notification.InfoReply).info.ringID)
    }

    @Test fun parsesControlNotifications() {
        assertEquals(OmiStorage.Notification.Ack(10), OmiStorage.Notification.from(bytes(0x01, 0x0A)))
        assertEquals(OmiStorage.Notification.Done(0, 42), OmiStorage.Notification.from(bytes(0x04, 0x00) + be(42, 8)))
        assertEquals(OmiStorage.Notification.ReadBegin(40, 2), OmiStorage.Notification.from(bytes(0x05) + be(40, 8) + be(2, 4)))
        assertEquals(OmiStorage.Notification.Data(bytes(0xAA, 0xBB)), OmiStorage.Notification.from(bytes(0x03, 0xAA, 0xBB)))
        assertNull(OmiStorage.Notification.from(bytes(0x04, 0x00)))
        assertNull(OmiStorage.Notification.from(ByteArray(0)))
    }

    @Test fun parsesStatusRead() {
        val status = assertNotNullAndGet(OmiStorage.Status.from(le(888, 4) + le(2, 4) + le(5000, 4) + le(1, 4)))
        assertEquals(2L, status.unreadRecords)
        assertTrue(status.clockValid)
        assertNull(OmiStorage.Status.from(bytes(1, 2)))
    }

    /** Two 80-byte Opus frames, padding, one more, then the overflow marker at a block edge. */
    @Test fun unpacksRecordFrames() {
        val payload = ByteArray(OmiStorage.payloadSize) { 0x55 }
        payload[0] = 80
        payload[81] = 80
        payload[162] = 0
        payload[163] = 80
        payload[244] = 200.toByte()
        val parsed = OmiStorage.Record.from(be(1_760_000_000, 4) + payload)
        assertEquals(1_760_000_000L, parsed.timestamp)
        assertEquals(3, parsed.frames.size)
        assertTrue(parsed.frames.all { it.size == 80 })
    }

    @Test fun keepsAFrameThatFillsTheBlock() {
        val payload = ByteArray(OmiStorage.payloadSize)
        payload[0] = 200.toByte()
        payload[201] = 237.toByte()
        assertEquals(listOf(200, 237), OmiStorage.frames(payload).map { it.size })
    }

    @Test fun clockNotSetMeansNoTimestamp() {
        assertNull(OmiStorage.Record.from(ByteArray(OmiStorage.recordSize)).timestamp)
        assertNull(OmiStorage.Record.from(be(0x8000_0010L, 4) + ByteArray(OmiStorage.payloadSize)).timestamp)
    }

    @Test fun reassemblesUnalignedNotifications() {
        val reassembler = OmiStorage.Reassembler()
        val stream = (0 until 3).fold(ByteArray(0)) { acc, index ->
            acc + be(1_760_000_000L + index, 4) + bytes(10) + ByteArray(10) { 1 } + ByteArray(429)
        }
        val out = mutableListOf<OmiStorage.Record>()
        // 243-byte notifications: an MTU of 247 minus ATT header and opcode.
        var offset = 0
        while (offset < stream.size) {
            out += reassembler.append(stream.copyOfRange(offset, minOf(stream.size, offset + 243)))
            offset += 243
        }
        assertEquals(listOf(1_760_000_000L, 1_760_000_001L, 1_760_000_002L), out.map { it.timestamp })
        assertTrue(out.all { it.frames.size == 1 && it.frames[0].contentEquals(ByteArray(10) { 1 }) })
        assertEquals(0, reassembler.pendingBytes)
    }

    @Test fun timeSyncIsLittleEndianSeconds() {
        assertArrayEquals(bytes(0x02, 0x01, 0x00, 0x67), OmiStorage.timeSyncPayload(0x6700_0102L * 1000))
    }
}

private fun <T> assertNotNullAndGet(value: T?): T {
    assertNotNull(value)
    return value!!
}
