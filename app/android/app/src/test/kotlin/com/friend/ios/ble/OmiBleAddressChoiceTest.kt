package com.friend.ios.ble

import android.bluetooth.BluetoothDevice
import org.junit.Assert.assertEquals
import org.junit.Test

class OmiBleAddressChoiceTest {

    @Test
    fun `discovered device type takes precedence over persisted and default`() {
        val resolved = resolveAddressTypeForConnect(
            discoveredType = BluetoothDevice.ADDRESS_TYPE_PUBLIC,
            persistedType = BluetoothDevice.ADDRESS_TYPE_RANDOM,
        )
        assertEquals(BluetoothDevice.ADDRESS_TYPE_PUBLIC, resolved)
    }

    @Test
    fun `reconnect after app restart uses persisted public address type when scan missed`() {
        val resolved = resolveAddressTypeForConnect(
            discoveredType = null,
            persistedType = BluetoothDevice.ADDRESS_TYPE_PUBLIC,
        )
        assertEquals(BluetoothDevice.ADDRESS_TYPE_PUBLIC, resolved)
    }

    @Test
    fun `reconnect after app restart uses persisted random address type when scan missed`() {
        val resolved = resolveAddressTypeForConnect(
            discoveredType = null,
            persistedType = BluetoothDevice.ADDRESS_TYPE_RANDOM,
        )
        assertEquals(BluetoothDevice.ADDRESS_TYPE_RANDOM, resolved)
    }

    @Test
    fun `reconnect with no discovery and no persistence defaults to random for legacy pendants`() {
        val resolved = resolveAddressTypeForConnect(
            discoveredType = null,
            persistedType = null,
        )
        assertEquals(BluetoothDevice.ADDRESS_TYPE_RANDOM, resolved)
    }
}
