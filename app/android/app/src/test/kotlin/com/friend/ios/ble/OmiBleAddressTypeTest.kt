package com.friend.ios.ble

import android.bluetooth.BluetoothDevice
import org.junit.Assert.assertEquals
import org.junit.Test

class OmiBleAddressTypeTest {

    @Test
    fun `public addresses with MSB 00 are classified as ADDRESS_TYPE_PUBLIC`() {
        // OMI Glass (Seeed XIAO ESP32-S3 Sense) from issue #21526
        assertEquals(
            BluetoothDevice.ADDRESS_TYPE_PUBLIC,
            determineBleAddressType("10:B4:1D:E9:FF:15"),
        )
        // Standard IEEE OUIs starting with 0x00..0x3F
        assertEquals(
            BluetoothDevice.ADDRESS_TYPE_PUBLIC,
            determineBleAddressType("00:1A:7D:DA:71:13"),
        )
        assertEquals(
            BluetoothDevice.ADDRESS_TYPE_PUBLIC,
            determineBleAddressType("24:6F:28:AB:CD:EF"),
        )
    }

    @Test
    fun `public addresses with MSB 10 are classified as ADDRESS_TYPE_PUBLIC`() {
        // Espressif public OUIs starting with 0x80..0xBF (top two bits 10)
        assertEquals(
            BluetoothDevice.ADDRESS_TYPE_PUBLIC,
            determineBleAddressType("84:CC:A8:12:34:56"),
        )
        assertEquals(
            BluetoothDevice.ADDRESS_TYPE_PUBLIC,
            determineBleAddressType("94:B9:7E:AA:BB:CC"),
        )
    }

    @Test
    fun `static random addresses with MSB 11 are classified as ADDRESS_TYPE_RANDOM`() {
        // Omi DevKit pendant static random addresses
        assertEquals(
            BluetoothDevice.ADDRESS_TYPE_RANDOM,
            determineBleAddressType("C0:DE:FE:ED:00:01"),
        )
        assertEquals(
            BluetoothDevice.ADDRESS_TYPE_RANDOM,
            determineBleAddressType("EB:8A:23:45:67:89"),
        )
        assertEquals(
            BluetoothDevice.ADDRESS_TYPE_RANDOM,
            determineBleAddressType("FF:11:22:33:44:55"),
        )
    }

    @Test
    fun `resolvable private addresses with MSB 01 are classified as ADDRESS_TYPE_RANDOM`() {
        assertEquals(
            BluetoothDevice.ADDRESS_TYPE_RANDOM,
            determineBleAddressType("40:11:22:33:44:55"),
        )
        assertEquals(
            BluetoothDevice.ADDRESS_TYPE_RANDOM,
            determineBleAddressType("7E:AA:BB:CC:DD:EE"),
        )
    }

    @Test
    fun `formatting variations and malformed addresses fall back safely`() {
        // Delimiter with dashes
        assertEquals(
            BluetoothDevice.ADDRESS_TYPE_PUBLIC,
            determineBleAddressType("10-B4-1D-E9-FF-15"),
        )
        // Lowercase
        assertEquals(
            BluetoothDevice.ADDRESS_TYPE_PUBLIC,
            determineBleAddressType("10:b4:1d:e9:ff:15"),
        )
        // Whitespace padding
        assertEquals(
            BluetoothDevice.ADDRESS_TYPE_PUBLIC,
            determineBleAddressType("  10:B4:1D:E9:FF:15  "),
        )
        // Malformed or empty string defaults safely to RANDOM for Omi DevKit
        assertEquals(
            BluetoothDevice.ADDRESS_TYPE_RANDOM,
            determineBleAddressType(""),
        )
        assertEquals(
            BluetoothDevice.ADDRESS_TYPE_RANDOM,
            determineBleAddressType("not-a-mac"),
        )
    }
}
