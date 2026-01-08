package com.friend.ios

import android.companion.AssociationInfo
import android.companion.CompanionDeviceService
import android.os.Build
import android.util.Log
import androidx.annotation.RequiresApi

/**
 * Background service that receives device presence events from CompanionDeviceManager.
 *
 * This service is bound by the system when a companion device appears or disappears,
 * even when the app is not running.
 */
@RequiresApi(Build.VERSION_CODES.S)
class CompanionDeviceBackgroundService : CompanionDeviceService() {

    companion object {
        private const val TAG = "CompanionBgService"

        // Track whether the app is in the foreground (set by MainActivity)
        @Volatile
        var isAppInForeground: Boolean = false
    }

    override fun onDeviceAppeared(associationInfo: AssociationInfo) {
        val deviceAddress = associationInfo.deviceMacAddress?.toString()
        Log.d(TAG, "Device appeared (service): $deviceAddress, appInForeground=$isAppInForeground")

        if (deviceAddress != null) {
            // Store the event for Flutter to pick up
            storePresenceEvent(deviceAddress, true)

            // Only show notification and launch app if app is NOT in foreground
            // When app is open, user can see the device reconnecting - no notification needed
            if (!isAppInForeground) {
                showDeviceNotification(deviceAddress)
                launchApp()
            }
        }
    }

    override fun onDeviceDisappeared(associationInfo: AssociationInfo) {
        val deviceAddress = associationInfo.deviceMacAddress?.toString()
        Log.d(TAG, "Device disappeared (service): $deviceAddress")

        if (deviceAddress != null) {
            storePresenceEvent(deviceAddress, false)
        }
    }

    private fun storePresenceEvent(deviceAddress: String, appeared: Boolean) {
        val prefs = getSharedPreferences("companion_device_presence", MODE_PRIVATE)
        prefs.edit().apply {
            putString("last_device_address", deviceAddress)
            putBoolean("last_device_appeared", appeared)
            putLong("last_event_timestamp", System.currentTimeMillis())
            apply()
        }
    }

    private fun showDeviceNotification(deviceAddress: String) {
        val notificationManager = getSystemService(NOTIFICATION_SERVICE) as android.app.NotificationManager

        // Create notification channel
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = android.app.NotificationChannel(
                "companion_device_presence",
                "Device Connection",
                android.app.NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notifications when your Omi device is detected"
            }
            notificationManager.createNotificationChannel(channel)
        }

        // Create intent to launch app
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)?.apply {
            flags = android.content.Intent.FLAG_ACTIVITY_NEW_TASK or
                    android.content.Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("from_companion_device", true)
            putExtra("device_address", deviceAddress)
        }

        val pendingIntent = android.app.PendingIntent.getActivity(
            this,
            0,
            launchIntent,
            android.app.PendingIntent.FLAG_UPDATE_CURRENT or android.app.PendingIntent.FLAG_IMMUTABLE
        )

        val notification = androidx.core.app.NotificationCompat.Builder(this, "companion_device_presence")
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentTitle("Omi Device Detected")
            .setContentText("Your Omi device is nearby. Tap to connect.")
            .setPriority(androidx.core.app.NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .build()

        notificationManager.notify(9001, notification)
    }

    private fun launchApp() {
        try {
            val launchIntent = packageManager.getLaunchIntentForPackage(packageName)?.apply {
                flags = android.content.Intent.FLAG_ACTIVITY_NEW_TASK or
                        android.content.Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra("from_companion_device", true)
            }
            if (launchIntent != null) {
                startActivity(launchIntent)
                Log.d(TAG, "Launched app from companion device service")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to launch app: ${e.message}")
        }
    }
}
