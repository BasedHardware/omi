package com.friend.ios.device

import java.util.UUID

/*
 * Port of `OmiControls.swift`: the Omi's settings, feature flags, haptic motor and serial number.
 * Firmware `lib/core/transport.c` (settings + features services), `haptic.c`,
 * `lib/core/features.h`; Flutter `connectors/omi_connection.dart:1186-1290`,
 * `device_connection.dart:404-430`. The types (`Features`, `Haptic`, `Control`) are in OmiGATT.kt.
 */

val OmiGATT.settingsService: UUID get() = UUID.fromString("19b10010-e8f2-537e-4f6c-d104768a1214")

/** LED brightness, one byte 0...100 (read/write). */
val OmiGATT.ledDimRatio: UUID get() = UUID.fromString("19b10011-e8f2-537e-4f6c-d104768a1214")

/** Microphone gain level, one byte 0 (mute) ... 8 (+40 dB) (read/write). */
val OmiGATT.micGain: UUID get() = UUID.fromString("19b10012-e8f2-537e-4f6c-d104768a1214")

/** One byte, 1 while on the charger (read/notify). */
val OmiGATT.chargingStatus: UUID get() = UUID.fromString("19b10013-e8f2-537e-4f6c-d104768a1214")
val OmiGATT.featuresService: UUID get() = UUID.fromString("19b10020-e8f2-537e-4f6c-d104768a1214")

/** `uint32` little-endian bitmask of `Features` (read). */
val OmiGATT.features: UUID get() = UUID.fromString("19b10021-e8f2-537e-4f6c-d104768a1214")

/** The haptic service shares its UUID with the (empty) speaker service in firmware. */
val OmiGATT.hapticService: UUID get() = UUID.fromString("cab1ab95-2ea5-4f4d-bb56-874b72cfc984")
val OmiGATT.haptic: UUID get() = UUID.fromString("cab1ab96-2ea5-4f4d-bb56-874b72cfc984")
val OmiGATT.serialNumber: UUID get() = OmiGATT.short(0x2A25)

/** Mic gain levels the firmware accepts (higher values are capped at 8). */
val OmiGATT.micGainLevels: IntRange get() = 0..8

fun OmiGATT.ledBrightnessPayload(percent: Int): ByteArray = byteArrayOf(percent.coerceIn(0, 100).toByte())

fun OmiGATT.micGainPayload(level: Int): ByteArray = byteArrayOf(level.coerceIn(micGainLevels.first, micGainLevels.last).toByte())

/** One-byte settings reads (brightness, gain); `null` for an empty read. */
fun OmiGATT.settingValue(value: ByteArray): Int? = value.firstOrNull()?.let { it.toInt() and 0xFF }

fun OmiGATT.isCharging(value: ByteArray): Boolean? = value.firstOrNull()?.let { it.toInt() == 1 }

/**
 * The DIS serial when it is a real per-unit id: CV1 publishes its nRF FICR id as exactly 16
 * hex characters; constants ("unknown") and an unset FICR (one repeated digit) are dropped.
 */
fun OmiGATT.serialNumber(value: ByteArray): String? {
    val text = runCatching { value.toString(Charsets.UTF_8) }.getOrNull() ?: return null
    val serial = text.replace("\u0000", "").trim().uppercase()
    if (serial.length != 16 || !serial.all { it in '0'..'9' || it in 'A'..'F' } || serial.toSet().size <= 1) return null
    return serial
}

/** Find my Omi: three long pulses, 750 ms apart (`device_connection.dart:409`). */
val OmiGATT.findPattern: List<OmiGATT.Haptic> get() = listOf(OmiGATT.Haptic.Long, OmiGATT.Haptic.Long, OmiGATT.Haptic.Long)
val OmiGATT.findPulseGapMillis: Long get() = 750
