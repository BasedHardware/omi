package com.friend.ios

import android.companion.AssociationInfo
import android.companion.CompanionDeviceManager
import android.companion.CompanionDeviceService
import android.companion.DevicePresenceEvent
import android.content.Context
import android.os.Build
import android.util.Log
import androidx.core.content.ContextCompat
import java.util.Locale

/**
 * CompanionDeviceService that receives device appear/disappear events from the OS,
 * even when the app is not running.
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

        if (!hasBluetoothPermission()) return
        if (!OmiBleForegroundService.isBackgroundModeEnabled(applicationContext)) {
            Log.i(TAG, "Device appeared but Background Mode is off; not starting service")
            return
        }

        val prefs = applicationContext.getSharedPreferences("ble_config", Context.MODE_PRIVATE)
        if (prefs.getBoolean("user_disconnected", false)) return

        val saved = prefs.getString("managed_device", null)
        val requiresBond = if (saved != null) {
            val parts = saved.split("|")
            parts.size == 2 && parts[0].equals(address, ignoreCase = true) && parts[1].toBoolean()
        } else false

        OmiBleForegroundService.startService(
            applicationContext, address,
            requiresBond = requiresBond,
            caller = "CompanionSvc.deviceAppeared"
        )
    }

    private fun handleDeviceDisappeared() {
        // Intentionally a no-op. Omi holds a live connection, and a connected BLE peripheral stops
        // advertising — so the OS fires BLE_DISAPPEARED while we are connected and streaming.
        // Stopping the service here tears down a healthy link (and then flaps). A genuinely off /
        // out-of-range device is handled by the parked autoConnect, which is low power and
        // auto-reconnects when it returns.
        Log.i(TAG, "Device disappeared (ignored; live-connection model)")
    }

    // ---- Lifecycle ----

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "onCreate")

        if (!hasBluetoothPermission()) return
        if (!OmiBleForegroundService.isBackgroundModeEnabled(applicationContext)) return

        val prefs = applicationContext.getSharedPreferences("ble_config", Context.MODE_PRIVATE)
        if (prefs.getBoolean("user_disconnected", false)) return

        val saved = prefs.getString("managed_device", null) ?: return
        val parts = saved.split("|")
        if (parts.size != 2) return

        OmiBleForegroundService.startService(
            applicationContext, parts[0],
            requiresBond = parts[1].toBoolean(),
            caller = "CompanionSvc.onCreateFallback"
        )
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
            DevicePresenceEvent.EVENT_BLE_APPEARED -> {
                if (address != null) handleDeviceAppeared(address)
            }
            DevicePresenceEvent.EVENT_BLE_DISAPPEARED -> {
                handleDeviceDisappeared()
            }
        }

        super.onDevicePresenceEvent(event)
    }
}
