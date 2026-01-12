package com.friend.ios

import android.companion.AssociationInfo
import android.companion.CompanionDeviceService
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.os.Build
import android.util.Log
import androidx.annotation.RequiresApi
import androidx.core.content.edit

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
        private const val NOTIFICATION_ID = 9001
        private const val PREFS_NAME = "companion_device_presence"

        // Track whether the app is in the foreground (set by MainActivity)
        @Volatile
        var isAppInForeground: Boolean = false

        // Cooldown period after user ignores/dismisses notification
        internal const val NOTIFICATION_COOLDOWN_MS = 30 * 60 * 1000L // 30 minutes

        /**
         * Call this from MainActivity when app comes to foreground via notification tap.
         * This resets the "ignored" state so future notifications will work normally.
         */
        fun onUserRespondedToNotification(context: Context, deviceAddress: String) {
            context.getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit {
                putBoolean("notification_pending_$deviceAddress", false)
                putLong("notification_cooldown_until_$deviceAddress", 0)
            }
            Log.d(TAG, "User responded to notification for $deviceAddress, reset cooldown")
        }

        /**
         * Call this from MainActivity when app comes to foreground (any way, not just from notification).
         * This resets cooldown and cancels any pending notification since user is now in the app.
         */
        fun onAppCameToForeground(context: Context) {
            val prefs = context.getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
            val lastDeviceAddress = prefs.getString("last_device_address", null)

            if (lastDeviceAddress != null) {
                clearNotificationState(prefs, lastDeviceAddress)
                Log.d(TAG, "App came to foreground, reset cooldown for $lastDeviceAddress")
            }

            // Cancel any pending notification since user is now in the app
            val notificationManager = context.getSystemService(NOTIFICATION_SERVICE) as android.app.NotificationManager
            notificationManager.cancel(NOTIFICATION_ID)
        }

        /**
         * Clears notification pending state and resets cooldown for a device.
         */
        private fun clearNotificationState(prefs: SharedPreferences, deviceAddress: String) {
            prefs.edit {
                putBoolean("notification_pending_$deviceAddress", false)
                putLong("notification_cooldown_until_$deviceAddress", 0)
            }
        }

        /**
         * Sets the cooldown state for a device after user ignores/dismisses notification.
         */
        fun enterCooldown(context: Context, deviceAddress: String) {
            context.getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit {
                putBoolean("notification_pending_$deviceAddress", false)
                putLong("notification_cooldown_until_$deviceAddress", System.currentTimeMillis() + NOTIFICATION_COOLDOWN_MS)
            }
            Log.d(TAG, "Entered cooldown for $deviceAddress")
        }
    }

    override fun onDeviceAppeared(associationInfo: AssociationInfo) {
        val deviceAddress = associationInfo.deviceMacAddress?.toString()
        Log.d(TAG, "Device appeared (service): $deviceAddress, appInForeground=$isAppInForeground")

        if (deviceAddress != null) {
            // Store the event for Flutter to pick up
            storePresenceEvent(deviceAddress, true)

            // Forward to presence listener (for Flutter event channel when app is running)
            CompanionDevicePresenceReceiver.notifyDeviceAppeared(deviceAddress)

            // Only show notification if:
            // 1. App is NOT in foreground
            // 2. We're not in a cooldown period (user previously ignored notification)
            if (!isAppInForeground && shouldShowNotification(deviceAddress)) {
                showDeviceNotification(deviceAddress)
            }
            // Note: We no longer auto-launch the app - user must tap notification
        }
    }

    override fun onDeviceDisappeared(associationInfo: AssociationInfo) {
        val deviceAddress = associationInfo.deviceMacAddress?.toString()
        Log.d(TAG, "Device disappeared (service): $deviceAddress")

        if (deviceAddress != null) {
            storePresenceEvent(deviceAddress, false)

            // Forward to presence listener (for Flutter event channel when app is running)
            CompanionDevicePresenceReceiver.notifyDeviceDisappeared(deviceAddress)

            // If notification was pending (shown but not acted upon), user ignored it
            // Enter cooldown so we don't spam them
            val prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
            val wasPending = prefs.getBoolean("notification_pending_$deviceAddress", false)
            if (wasPending) {
                Log.d(TAG, "Device disappeared while notification pending - user ignored it, entering cooldown")
                enterCooldown(this, deviceAddress)
                // Cancel the notification since device is gone
                val notificationManager = getSystemService(NOTIFICATION_SERVICE) as android.app.NotificationManager
                notificationManager.cancel(NOTIFICATION_ID)
            }
        }
    }

    /**
     * Check if we should show a notification or if we're in cooldown
     */
    private fun shouldShowNotification(deviceAddress: String): Boolean {
        val prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
        val now = System.currentTimeMillis()

        val cooldownUntil = prefs.getLong("notification_cooldown_until_$deviceAddress", 0)
        if (now < cooldownUntil) {
            val remainingMin = (cooldownUntil - now) / 60000
            Log.d(TAG, "In notification cooldown, $remainingMin minutes remaining")
            return false
        }

        return true
    }

    private fun storePresenceEvent(deviceAddress: String, appeared: Boolean) {
        getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit {
            putString("last_device_address", deviceAddress)
            putBoolean("last_device_appeared", appeared)
            putLong("last_event_timestamp", System.currentTimeMillis())
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

        // Create intent to launch app when notification is tapped
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

        // Create intent for when notification is dismissed (swiped away)
        val dismissIntent = Intent(this, NotificationDismissedReceiver::class.java).apply {
            action = "com.friend.ios.NOTIFICATION_DISMISSED"
            putExtra("device_address", deviceAddress)
        }
        val dismissPendingIntent = android.app.PendingIntent.getBroadcast(
            this,
            1,
            dismissIntent,
            android.app.PendingIntent.FLAG_UPDATE_CURRENT or android.app.PendingIntent.FLAG_IMMUTABLE
        )

        val notification = androidx.core.app.NotificationCompat.Builder(this, "companion_device_presence")
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentTitle("Omi Device Detected")
            .setContentText("Your Omi device is nearby. Tap to connect.")
            .setPriority(androidx.core.app.NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .setDeleteIntent(dismissPendingIntent) // Called when user dismisses notification
            .build()

        notificationManager.notify(NOTIFICATION_ID, notification)

        // Mark that we have a pending notification
        getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit {
            putBoolean("notification_pending_$deviceAddress", true)
        }

        Log.d(TAG, "Showed notification for $deviceAddress")
    }
}

/**
 * Receiver for when user explicitly dismisses (swipes away) the notification
 */
class NotificationDismissedReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == "com.friend.ios.NOTIFICATION_DISMISSED") {
            val deviceAddress = intent.getStringExtra("device_address") ?: return
            Log.d("NotificationDismissed", "User dismissed notification for $deviceAddress, entering cooldown")
            CompanionDeviceBackgroundService.enterCooldown(context, deviceAddress)
        }
    }
}
