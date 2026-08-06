package com.friend.ios.ble

/**
 * Pure contract for user-initiated BLE disconnect (#5361).
 *
 * The foreground service's `managedDevices` map can desync from a live GATT
 * (strict BG/BLE policy, GrapheneOS, FGS restart races). Unmanage must still
 * tear down GATT and record user intent — never no-op just because the map
 * entry is missing.
 */
object BleUnmanagePolicy {
    data class Plan(
        /** Cancel scheduled reconnect / stability timers if a managed entry existed. */
        val cancelManagedTimers: Boolean,
        /** Always call disconnectGatt then closeGatt for the address. */
        val tearDownGatt: Boolean,
        /** Persist user_disconnected=true so companion / sticky restart do not reconnect. */
        val markUserDisconnected: Boolean,
        /** Remove managed_device so sticky restore cannot revive the session. */
        val clearManagedDevicePref: Boolean,
        /** Notify Flutter that the peripheral disconnected. */
        val notifyFlutterDisconnected: Boolean,
        /** Stop the foreground service after a manual unmanage. */
        val stopService: Boolean,
    )

    /**
     * @param managedEntryPresent whether [address] was present in `managedDevices`
     *        before removal. Does not change teardown / prefs / notify / stop —
     *        those always run for a user disconnect tap.
     */
    fun plan(managedEntryPresent: Boolean): Plan = Plan(
        cancelManagedTimers = managedEntryPresent,
        tearDownGatt = true,
        markUserDisconnected = true,
        clearManagedDevicePref = true,
        notifyFlutterDisconnected = true,
        stopService = true,
    )
}
