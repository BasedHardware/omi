package com.friend.ios.ble

import org.json.JSONArray
import org.json.JSONObject

/** The append-only 25-byte Omi Diagnostics characteristic (contract v1). */
internal object FirmwareDiagnosticsParser {
    private val flags = listOf(
        "RESET_PIN", "RESET_SOFTWARE", "RESET_BROWNOUT", "RESET_POR",
        "RESET_WATCHDOG", "RESET_DEBUG", "RESET_SECURITY", "RESET_LOW_POWER_WAKE",
        "RESET_CPU_LOCKUP", "RESET_PARITY", "RESET_PLL", "RESET_CLOCK", "RESET_HARDWARE",
        "RESET_USER", "RESET_TEMPERATURE", "RESET_BOOTLOADER", "RESET_FLASH"
    )

    fun parse(data: ByteArray, nowMs: Long): JSONObject? {
        if (data.size < 25 || data[0].toInt() == 0) return null
        fun u8(offset: Int) = data[offset].toInt() and 0xff
        fun u16(offset: Int) = u8(offset) or (u8(offset + 1) shl 8)
        fun u32(offset: Int): Long = u8(offset).toLong() or
            (u8(offset + 1).toLong() shl 8) or
            (u8(offset + 2).toLong() shl 16) or
            (u8(offset + 3).toLong() shl 24)
        val reset = u32(1)
        val names = JSONArray()
        if (reset != 0xffffffffL) flags.forEachIndexed { bit, name ->
            if (reset and (1L shl bit) != 0L) names.put(name)
        }
        fun known32(offset: Int): Any = u32(offset).takeUnless { it == 0xffffffffL } ?: JSONObject.NULL
        return JSONObject()
            .put("ts", nowMs)
            .put("version", u8(0))
            .put("reset_cause_raw", if (reset == 0xffffffffL) JSONObject.NULL else reset)
            .put("reset_cause_names", names)
            .put("uptime_s", u32(5))
            .put("battery_mv", u16(9).takeUnless { it == 0xffff } ?: JSONObject.NULL)
            .put("charging", when (u8(11)) { 0 -> false; 1 -> true; else -> JSONObject.NULL })
            .put("mic_overrun_count", known32(13))
            .put("ble_tx_drop_count", known32(17))
            .put("storage_error_count", known32(21))
    }
}
