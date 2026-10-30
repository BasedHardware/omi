package com.friend.ios.ble

/**
 * Scan-time naming shared with the manufacturer-data fallback in `OmiBleManager`.
 *
 * `ScanResult.device.name` is often empty until the phone has connected once, while
 * NotePin S puts "NotePin" only in the advertisement (#18705). Android's
 * `ScanRecord.getManufacturerSpecificData(id)` already strips the 16-bit id, so the
 * payload starts at index 0. Mirrors iOS (`OmiBleDiscoveryNaming`) and macOS discovery.
 */
const val PLAUD_MANUFACTURER_ID = 93

const val NOTE_PIN_FALLBACK_NAME = "NotePin"

private val NOTE_PIN_PAYLOAD = byteArrayOf(0x04, 0x56, 0xCF.toByte(), 0x00)

fun isNotePinAdvertisement(manufacturerData: ByteArray?): Boolean {
    if (manufacturerData == null || manufacturerData.size < NOTE_PIN_PAYLOAD.size) return false
    return manufacturerData.copyOfRange(0, NOTE_PIN_PAYLOAD.size).contentEquals(NOTE_PIN_PAYLOAD)
}

/**
 * Resolve the scan-time name, preferring what the advertisement carries over the cached
 * device name, then the NotePin fallback.
 */
fun discoveredPeripheralName(
    advertisedName: String?,
    cachedName: String?,
    manufacturerData: ByteArray?,
): String {
    advertisedName?.trim()?.takeIf { it.isNotEmpty() }?.let { return it }
    cachedName?.trim()?.takeIf { it.isNotEmpty() }?.let { return it }
    if (isNotePinAdvertisement(manufacturerData)) return NOTE_PIN_FALLBACK_NAME
    return ""
}
