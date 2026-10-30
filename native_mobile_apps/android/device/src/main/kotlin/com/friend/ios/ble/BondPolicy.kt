package com.friend.ios.ble

import android.bluetooth.BluetoothDevice

/**
 * When the phone bonds with the wearable before using it, as the Flutter app decided it
 * (`DeviceConnectionFactory`: `needsBond = device.type == limitless`, then
 * `OmiBleForegroundService.onGattServicesDiscovered` -> `OmiBleManager.requestBond`). Pure, so
 * the decision is unit tested.
 */
object BondPolicy {
    /** The paired device's type (`btDevice.type`) asks for a bond (Limitless pendants do; Omi does not). */
    fun requiresBond(type: String): Boolean = type.equals("limitless", ignoreCase = true)

    /**
     * Wait for the bond before the set-up (MTU, notifications): when the device requires one, or
     * when the peripheral already started pairing itself (firmware's `bt_conn_set_security`), so
     * the first writes do not race the pairing. Never for a device already bonded.
     */
    fun bondsBeforeSetUp(requiresBond: Boolean, bondState: Int): Boolean =
        bondState != BluetoothDevice.BOND_BONDED && (requiresBond || bondState == BluetoothDevice.BOND_BONDING)

    /** The service's remembered device (`"ADDRESS|requiresBond"`, Flutter's `managed_device`). */
    fun managedDevice(saved: String?): Pair<String, Boolean>? {
        val parts = saved?.split("|") ?: return null
        if (parts.size != 2 || parts[0].isEmpty()) return null
        return parts[0].uppercase() to parts[1].toBoolean()
    }
}
