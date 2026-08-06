package com.friend.ios.ble

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Regression for #5361: disconnect tap must tear down GATT and record user intent
 * even when the foreground service's managedDevices map is empty / desynced.
 */
class BleUnmanagePolicyTest {

    @Test
    fun plan_withoutManagedEntry_stillTearsDownGattAndPrefs() {
        val plan = BleUnmanagePolicy.plan(managedEntryPresent = false)

        assertFalse(plan.cancelManagedTimers)
        assertTrue(plan.tearDownGatt)
        assertTrue(plan.markUserDisconnected)
        assertTrue(plan.clearManagedDevicePref)
        assertTrue(plan.notifyFlutterDisconnected)
        assertTrue(plan.stopService)
    }

    @Test
    fun plan_withManagedEntry_cancelsTimersAndTearsDown() {
        val plan = BleUnmanagePolicy.plan(managedEntryPresent = true)

        assertTrue(plan.cancelManagedTimers)
        assertTrue(plan.tearDownGatt)
        assertTrue(plan.markUserDisconnected)
        assertTrue(plan.clearManagedDevicePref)
        assertTrue(plan.notifyFlutterDisconnected)
        assertTrue(plan.stopService)
    }
}
