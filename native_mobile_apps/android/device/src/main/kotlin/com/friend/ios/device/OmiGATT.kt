package com.friend.ios.device

import java.util.UUID

/**
 * Port of `OmiGATT.swift`: the Omi wearable's GATT profile. Source: upstream
 * `app/lib/services/devices/models.dart`, `connectors/omi_connection.dart`, firmware
 * `omi/firmware/omi/src/lib/core/config.h`.
 */
object OmiGATT {
    val audioService: UUID = UUID.fromString("19b10000-e8f2-537e-4f6c-d104768a1214")
    val audioData: UUID = UUID.fromString("19b10001-e8f2-537e-4f6c-d104768a1214")
    val audioCodec: UUID = UUID.fromString("19b10002-e8f2-537e-4f6c-d104768a1214")
    val buttonService: UUID = UUID.fromString("23ba7924-0000-1000-7450-346eac492e92")
    val buttonData: UUID = UUID.fromString("23ba7925-0000-1000-7450-346eac492e92")
    val batteryService: UUID = short(0x180F)
    val batteryLevel: UUID = short(0x2A19)
    val deviceInfoService: UUID = short(0x180A)
    val modelNumber: UUID = short(0x2A24)
    val firmwareRevision: UUID = short(0x2A26)
    val hardwareRevision: UUID = short(0x2A27)
    val manufacturerName: UUID = short(0x2A29)

    /** MCUmgr's SMP service (firmware updates). `McuFirmwareUpdater` speaks it, not this driver. */
    val smpService: UUID = UUID.fromString("8D53DC1D-1DB7-4CD3-868B-8A527460AA84")

    /** The Bluetooth base UUID for a 16-bit assigned number (`CBUUID(string: "180F")`). */
    fun short(value: Int): UUID = UUID.fromString(String.format("0000%04x-0000-1000-8000-00805f9b34fb", value))

    /** Codec ids from the codec characteristic (`omi_connection.dart:416-438`). */
    enum class Codec(val rawValue: Int) {
        Pcm16(0),
        Pcm8(1),
        Opus(20),
        OpusFS320(21);

        /** The `/v4/listen` `codec` query value. */
        val listenValue: String
            get() = when (this) {
                Pcm16 -> "pcm16"
                Pcm8 -> "pcm8"
                Opus -> "opus"
                OpusFS320 -> "opus_fs320"
            }

        val sampleRate: Int get() = if (this == Pcm8) 8000 else 16000

        companion object {
            fun fromRaw(raw: Int): Codec? = entries.firstOrNull { it.rawValue == raw }
        }
    }

    /**
     * Button notifications: a little-endian `int` state (firmware `core/button.c`). A long press
     * powers the Omi off in firmware; press/release only matter for push-to-talk.
     */
    enum class ButtonEvent(val rawValue: Long) {
        SingleTap(1),
        DoubleTap(2),
        LongPress(3),
        Press(4),
        Release(5);

        companion object {
            fun from(value: ByteArray): ButtonEvent? {
                if (value.size < 4) return null
                val raw = littleEndianU32(value, 0)
                return entries.firstOrNull { it.rawValue == raw }
            }
        }
    }

    /** One audio notification with its 3-byte header taken apart. */
    class AudioFrame(val packetID: Int, val payload: ByteArray)

    /** Audio notifications carry `[id_lo, id_hi, sub_index]` then the codec payload. */
    fun audioPayload(packet: ByteArray): AudioFrame? {
        if (packet.size <= 3) return null
        val id = (packet[0].toInt() and 0xFF) or ((packet[1].toInt() and 0xFF) shl 8)
        return AudioFrame(id, packet.copyOfRange(3, packet.size))
    }

    /** Whether an advertisement is an Omi-family wearable. */
    fun isOmi(name: String?, advertisedServices: List<UUID>): Boolean {
        if (advertisedServices.contains(audioService)) return true
        val lower = name?.lowercase() ?: return false
        return lower.contains("omi") || lower.contains("friend")
    }

    // The types of `OmiControls.swift` (`public extension OmiGATT`); Kotlin cannot nest types from
    // another file, so they live here and the UUIDs and helpers in `OmiControls.kt`.

    /**
     * What this firmware supports (`omi_feature_t`). Old firmware without the features service
     * reports nothing, so its controls stay hidden.
     */
    data class Features(val rawValue: Long) {
        fun contains(other: Features): Boolean = rawValue and other.rawValue == other.rawValue

        operator fun plus(other: Features) = Features(rawValue or other.rawValue)

        companion object {
            val speaker = Features(1L shl 0)
            val accelerometer = Features(1L shl 1)
            val button = Features(1L shl 2)
            val battery = Features(1L shl 3)
            val usb = Features(1L shl 4)
            val haptic = Features(1L shl 5)
            val offlineStorage = Features(1L shl 6)
            val ledDimming = Features(1L shl 7)
            val micGain = Features(1L shl 8)

            fun of(vararg features: Features) = Features(features.fold(0L) { acc, f -> acc or f.rawValue })

            /** A read shorter than four bytes is an empty set (Flutter returns 0). */
            fun from(value: ByteArray): Features = if (value.size < 4) Features(0) else Features(littleEndianU32(value, 0))
        }
    }

    /** A haptic pulse; the firmware maps 1/2/3 to 100/300/500 ms. */
    enum class Haptic(val rawValue: Int) {
        Short(1),
        Medium(2),
        Long(3);

        val payload: ByteArray get() = byteArrayOf(rawValue.toByte())
    }

    /** The writable controls, for `DeviceDriving.write(control, payload)`. */
    enum class Control {
        LedBrightness,
        MicGain,
        Haptic;

        val characteristic: UUID
            get() = when (this) {
                LedBrightness -> OmiGATT.ledDimRatio
                MicGain -> OmiGATT.micGain
                Haptic -> OmiGATT.haptic
            }
    }
}

/** `value.prefix(4).reversed().reduce`: an unsigned little-endian `u32`, as a Long. */
internal fun littleEndianU32(bytes: ByteArray, index: Int): Long {
    var raw = 0L
    for (i in 3 downTo 0) raw = (raw shl 8) or (bytes[index + i].toLong() and 0xFF)
    return raw
}

internal fun bigEndianU32(bytes: ByteArray, index: Int): Long {
    var raw = 0L
    for (i in 0 until 4) raw = (raw shl 8) or (bytes[index + i].toLong() and 0xFF)
    return raw
}

/** Unsigned big-endian `u64`; sequence numbers stay far below `Long.MAX_VALUE`. */
internal fun bigEndianU64(bytes: ByteArray, index: Int): Long {
    var raw = 0L
    for (i in 0 until 8) raw = (raw shl 8) or (bytes[index + i].toLong() and 0xFF)
    return raw
}

internal fun Long.bigEndianBytes(count: Int): ByteArray = ByteArray(count) { i -> (this ushr (8 * (count - 1 - i))).toByte() }

internal fun Long.littleEndianBytes(count: Int): ByteArray = ByteArray(count) { i -> (this ushr (8 * i)).toByte() }
