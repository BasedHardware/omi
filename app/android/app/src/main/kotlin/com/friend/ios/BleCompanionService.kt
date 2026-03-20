package com.friend.ios

import android.companion.AssociationInfo
import android.companion.CompanionDeviceManager
import android.companion.CompanionDeviceService
import android.companion.DevicePresenceEvent
import android.os.Build
import android.util.Log
import androidx.core.content.ContextCompat
import java.util.Locale

/**
 * CompanionDeviceService that receives device appear/disappear events from the OS,
 * even when the app is not running. This is how the app auto-connects when the
 * Omi device comes into BLE range — no polling timer needed.
 *
 * Enables zero-polling reconnection via OS-level BLE presence monitoring.
 */
class BleCompanionService : CompanionDeviceService() {

    companion object {
        private const val TAG = "OmiBle.CompanionSvc"

        @Volatile
        private var appearCount = 0
    }

    private fun hasBluetoothPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            applicationContext, "android.permission.BLUETOOTH_CONNECT"
        ) == 0
    }

    private fun findAssociation(assocId: Int): AssociationInfo? {
        val cdm = getSystemService("companiondevice") as? CompanionDeviceManager ?: return null
        return cdm.myAssociations.find { it.id == assocId }
    }

    private fun handleDeviceAppeared(address: String) {
        Log.i(TAG, "Device appeared: $address")
        if (OmiBleManager.instance.appClosed) {
            Log.i(TAG, "App is closed, skipping reconnect")
            return
        }
        if (!hasBluetoothPermission()) {
            Log.w(TAG, "No Bluetooth permission, cannot start foreground service")
            return
        }
        OmiBleForegroundService.startService(applicationContext, address, shouldConnect = true)
    }

    private fun handleDeviceDisappeared() {
        Log.i(TAG, "Device disappeared")
        // Keep service running for reconnect — don't stop it
    }

    /**
     * Fallback: on create, start foreground service with first associated device.
     */
    private fun startForegroundServiceFallback() {
        if (!hasBluetoothPermission()) return

        val cdm = getSystemService("companiondevice") as? CompanionDeviceManager ?: return
        val association = cdm.myAssociations.firstOrNull() ?: return
        val address = association.deviceMacAddress?.toString()?.uppercase(Locale.ROOT) ?: return

        Log.i(TAG, "Fallback: starting foreground service with $address")
        OmiBleForegroundService.startService(applicationContext, address, shouldConnect = true)
    }

    // ---- Lifecycle ----

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "onCreate")
        if (hasBluetoothPermission() && !OmiBleManager.instance.appClosed) {
            startForegroundServiceFallback()
        }
    }

    // ---- API 31-35: String-based callbacks ----

    override fun onDeviceAppeared(address: String) {
        super.onDeviceAppeared(address)
        if (Build.VERSION.SDK_INT >= 36) return

        if (OmiBleForegroundService.isActive()) {
            appearCount++
            return
        }

        appearCount = 1
        handleDeviceAppeared(address)
    }

    override fun onDeviceDisappeared(address: String) {
        super.onDeviceDisappeared(address)
        if (Build.VERSION.SDK_INT >= 36) return

        appearCount--
        if (appearCount == 0) {
            handleDeviceDisappeared()
        }
    }

    // ---- API 36+: DevicePresenceEvent-based callback ----

    override fun onDevicePresenceEvent(event: DevicePresenceEvent) {
        val association = findAssociation(event.associationId)
        val address = association?.deviceMacAddress?.toString()?.uppercase(Locale.ROOT)

        when (event.event) {
            0 -> { // BLE_APPEARED
                if (address != null) handleDeviceAppeared(address)
            }
            1 -> { // BLE_DISAPPEARED
                handleDeviceDisappeared()
            }
        }

        super.onDevicePresenceEvent(event)
    }
}
