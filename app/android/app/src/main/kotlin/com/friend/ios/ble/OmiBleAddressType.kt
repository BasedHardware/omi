package com.friend.ios.ble

import android.bluetooth.BluetoothDevice

/**
 * Determine the BLE address type (Random vs Public) for a given MAC address.
 *
 * In Bluetooth Core Specification (Vol 6, Part B, Section 1.3):
 * - Static Random Device Address (Section 1.3.2.1): The two most significant bits of the
 *   address shall be equal to 1 (0b11, i.e. 0xC0..0xFF in the most significant octet).
 * - Resolvable Private Address (Section 1.3.2.3): The two most significant bits of the
 *   address shall be equal to 0 and 1 (0b01, i.e. 0x40..0x7F).
 * - Connectable peripherals with MSBs 00 or 10 are IEEE Public addresses (e.g. Espressif
 *   OMI Glass 10:B4:1D:..., Nordic OUIs F4:CE:... when bit 1 is universal, etc.).
 *   Non-resolvable private addresses (MSBs 00) are reserved for non-connectable beacons only.
 *
 * Defaults to ADDRESS_TYPE_RANDOM if parsing fails to preserve autoConnect behavior for
 * unbonded Omi DevKit pendants after Bluetooth toggle.
 */
fun determineBleAddressType(address: String): Int {
    val firstOctetStr = address.trim().split(":", "-").firstOrNull()
    val firstOctet = firstOctetStr?.toIntOrNull(16)
        ?: return BluetoothDevice.ADDRESS_TYPE_RANDOM
    val topTwoBits = (firstOctet and 0xC0) ushr 6
    return if (topTwoBits == 0b11 || topTwoBits == 0b01) {
        BluetoothDevice.ADDRESS_TYPE_RANDOM
    } else {
        BluetoothDevice.ADDRESS_TYPE_PUBLIC
    }
}
