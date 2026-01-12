package com.friend.ios

import android.companion.CompanionDeviceManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log

/**
 * BroadcastReceiver for device presence events from CompanionDeviceManager.
 *
 * Note: On Android 12+ (API 31+), the system primarily uses CompanionDeviceService
 * (CompanionDeviceBackgroundService) for presence callbacks. This receiver serves
 * as a fallback and for notifying in-app listeners when the app is already running.
 *
 * The CompanionDeviceBackgroundService handles notifications and app launching
 * to avoid duplicate actions.
 */
class CompanionDevicePresenceReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "CompanionPresence"

        // Listener for presence events (only works when app is running)
        private var presenceListener: PresenceListener? = null

        fun setPresenceListener(listener: PresenceListener?) {
            presenceListener = listener
        }

        /**
         * Called by CompanionDeviceBackgroundService to forward device appeared events
         * to the Flutter event channel via the presence listener.
         */
        fun notifyDeviceAppeared(deviceAddress: String) {
            Log.d(TAG, "notifyDeviceAppeared: $deviceAddress, listener=${presenceListener != null}")
            presenceListener?.onDeviceAppeared(deviceAddress)
        }

        /**
         * Called by CompanionDeviceBackgroundService to forward device disappeared events
         * to the Flutter event channel via the presence listener.
         */
        fun notifyDeviceDisappeared(deviceAddress: String) {
            Log.d(TAG, "notifyDeviceDisappeared: $deviceAddress, listener=${presenceListener != null}")
            presenceListener?.onDeviceDisappeared(deviceAddress)
        }

        interface PresenceListener {
            fun onDeviceAppeared(deviceAddress: String)
            fun onDeviceDisappeared(deviceAddress: String)
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            return
        }

        val action = intent.action ?: return

        // Extract device address from the intent
        val deviceAddress = intent.getParcelableExtra(
            CompanionDeviceManager.EXTRA_ASSOCIATION,
            android.companion.AssociationInfo::class.java
        )?.deviceMacAddress?.toString() ?: return

        when (action) {
            "android.companion.CompanionDeviceManager.ACTION_DEVICE_APPEARED" -> {
                Log.d(TAG, "Device appeared: $deviceAddress")
                // Notify in-app listener if registered
                presenceListener?.onDeviceAppeared(deviceAddress)
            }
            "android.companion.CompanionDeviceManager.ACTION_DEVICE_DISAPPEARED" -> {
                Log.d(TAG, "Device disappeared: $deviceAddress")
                // Notify in-app listener if registered
                presenceListener?.onDeviceDisappeared(deviceAddress)
            }
        }
    }
}
