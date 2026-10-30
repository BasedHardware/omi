package com.friend.ios.device

import android.bluetooth.BluetoothDevice
import com.friend.ios.ble.BondPolicy
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BondPolicyTest {
    @Test fun onlyDevicesThatNeedItBond() {
        assertFalse(BondPolicy.requiresBond("omi"))
        assertTrue(BondPolicy.requiresBond("limitless"))
        assertTrue(BondPolicy.requiresBond("Limitless"))
    }

    @Test fun waitsForPairingStartedByThePeripheral() {
        assertTrue(BondPolicy.bondsBeforeSetUp(requiresBond = true, bondState = BluetoothDevice.BOND_NONE))
        assertTrue(BondPolicy.bondsBeforeSetUp(requiresBond = false, bondState = BluetoothDevice.BOND_BONDING))
        assertFalse(BondPolicy.bondsBeforeSetUp(requiresBond = false, bondState = BluetoothDevice.BOND_NONE))
        assertFalse(BondPolicy.bondsBeforeSetUp(requiresBond = true, bondState = BluetoothDevice.BOND_BONDED))
    }

    @Test fun readsTheRememberedDevice() {
        assertEquals("AA:BB" to true, BondPolicy.managedDevice("aa:bb|true"))
        assertEquals("AA:BB" to false, BondPolicy.managedDevice("AA:BB|false"))
        assertNull(BondPolicy.managedDevice("garbage"))
        assertNull(BondPolicy.managedDevice(null))
    }
}
