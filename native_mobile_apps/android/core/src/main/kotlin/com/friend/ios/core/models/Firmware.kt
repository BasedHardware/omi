package com.friend.ios.core.models

import kotlinx.serialization.Serializable

/**
 * Port of `Firmware.swift`: an Omi firmware version, compared like the backend does
 * (`backend/routers/firmware.py` `_parse_firmware_version`): an optional `v`, dot-separated
 * integers, padded to three parts.
 */
class FirmwareVersion private constructor(val parts: List<Int>) : Comparable<FirmwareVersion> {
    override fun compareTo(other: FirmwareVersion): Int {
        val count = maxOf(parts.size, other.parts.size)
        for (i in 0 until count) {
            val left = parts.getOrElse(i) { 0 }
            val right = other.parts.getOrElse(i) { 0 }
            if (left != right) return left.compareTo(right)
        }
        return 0
    }

    override fun equals(other: Any?) = other is FirmwareVersion && compareTo(other) == 0

    override fun hashCode(): Int = parts.dropLastWhile { it == 0 }.hashCode()

    override fun toString() = parts.joinToString(".")

    companion object {
        /**
         * `null` for anything that is not plain numbers ("", "Unknown", "3.0.x"): an unknown
         * version never counts as older than a release.
         */
        fun parse(string: String?): FirmwareVersion? {
            var text = string?.trim()?.lowercase()?.takeIf { it.isNotEmpty() } ?: return null
            if (text.startsWith("v")) text = text.drop(1)
            val parts = mutableListOf<Int>()
            for (piece in text.split(".")) {
                val number = piece.toIntOrNull()?.takeIf { it >= 0 && piece.all(Char::isDigit) } ?: return null
                parts += number
            }
            while (parts.size < 3) parts += 0
            return FirmwareVersion(parts)
        }
    }
}

/** The newest firmware the backend offers for a device (`GET v2/firmware/latest`). */
@Serializable
data class FirmwareRelease(
    val version: String,
    /** The device must already run at least this version to take the update. */
    val minVersion: String?,
    /** An MCUboot OTA package (zip with `manifest.json` + images) on GitHub releases. */
    val zipURL: String,
    /** `true`: the old Nordic Secure DFU bootloader (DevKit), which this app does not flash. */
    val isLegacySecureDFU: Boolean,
    /** One line of release notes, when the release has any. */
    val notes: String?,
) {
    /**
     * Whether a device on `current` should be offered this release: strictly newer, the device
     * meets the minimum, and the bootloader speaks SMP (MCUboot).
     */
    fun isUpdate(current: String?): Boolean {
        val running = FirmwareVersion.parse(current) ?: return false
        val latest = FirmwareVersion.parse(version) ?: return false
        if (isLegacySecureDFU) return false
        FirmwareVersion.parse(minVersion)?.let { if (running < it) return false }
        return latest > running
    }
}
