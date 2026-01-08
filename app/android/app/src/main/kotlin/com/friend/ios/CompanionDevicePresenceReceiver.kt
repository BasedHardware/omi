package com.friend.ios

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.companion.CompanionDeviceManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat

/**
 * BroadcastReceiver that receives device presence events from CompanionDeviceManager.
 *
 * This receiver is called by the system when an associated companion device
 * appears or disappears, even when the app is not running.
 */
class CompanionDevicePresenceReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "CompanionPresence"
        private const val CHANNEL_ID = "companion_device_presence"
        private const val NOTIFICATION_ID = 9001

        // Listener for presence events (only works when app is running)
        private var presenceListener: PresenceListener? = null

        fun setPresenceListener(listener: PresenceListener?) {
            presenceListener = listener
        }

        interface PresenceListener {
            fun onDeviceAppeared(deviceAddress: String)
            fun onDeviceDisappeared(deviceAddress: String)
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        Log.d(TAG, "onReceive called with action: ${intent.action}")

        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            Log.d(TAG, "API level too low: ${Build.VERSION.SDK_INT}")
            return
        }

        val action = intent.action ?: run {
            Log.d(TAG, "Action is null")
            return
        }

        // Extract device address from the intent
        val deviceAddress = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val association = intent.getParcelableExtra(
                CompanionDeviceManager.EXTRA_ASSOCIATION,
                android.companion.AssociationInfo::class.java
            )
            Log.d(TAG, "Association info: $association")
            association?.deviceMacAddress?.toString()
        } else {
            null
        }

        Log.d(TAG, "Device address extracted: $deviceAddress")

        when (action) {
            "android.companion.CompanionDeviceManager.ACTION_DEVICE_APPEARED" -> {
                Log.d(TAG, "Device appeared: $deviceAddress")
                deviceAddress?.let {
                    // Store event for Flutter
                    storePresenceEvent(context, it, true)

                    // Notify listener if app is running
                    presenceListener?.onDeviceAppeared(it)

                    // Show notification and launch app
                    showDeviceAppearedNotification(context, it)
                    launchApp(context)
                }
            }
            "android.companion.CompanionDeviceManager.ACTION_DEVICE_DISAPPEARED" -> {
                Log.d(TAG, "Device disappeared: $deviceAddress")
                deviceAddress?.let {
                    // Store event for Flutter
                    storePresenceEvent(context, it, false)

                    // Notify listener if app is running
                    presenceListener?.onDeviceDisappeared(it)
                }
            }
        }
    }

    /**
     * Show a notification when the companion device appears.
     */
    private fun showDeviceAppearedNotification(context: Context, deviceAddress: String) {
        val notificationManager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        // Create notification channel (required for Android 8+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Device Connection",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notifications when your Omi device is detected"
            }
            notificationManager.createNotificationChannel(channel)
        }

        // Create intent to launch app when notification is tapped
        val launchIntent = context.packageManager.getLaunchIntentForPackage(context.packageName)?.apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("from_companion_device", true)
            putExtra("device_address", deviceAddress)
        }

        val pendingIntent = PendingIntent.getActivity(
            context,
            0,
            launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // Build and show notification
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentTitle("Omi Device Detected")
            .setContentText("Your Omi device is nearby. Tap to connect.")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .build()

        notificationManager.notify(NOTIFICATION_ID, notification)
    }

    /**
     * Launch the app when device appears (brings it to foreground or starts it).
     */
    private fun launchApp(context: Context) {
        try {
            val launchIntent = context.packageManager.getLaunchIntentForPackage(context.packageName)?.apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra("from_companion_device", true)
            }
            if (launchIntent != null) {
                context.startActivity(launchIntent)
                Log.d(TAG, "Launched app from companion device presence")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to launch app: ${e.message}")
        }
    }

    /**
     * Store presence event in SharedPreferences so Flutter can read it on next launch.
     */
    private fun storePresenceEvent(context: Context, deviceAddress: String, appeared: Boolean) {
        val prefs = context.getSharedPreferences("companion_device_presence", Context.MODE_PRIVATE)
        prefs.edit().apply {
            putString("last_device_address", deviceAddress)
            putBoolean("last_device_appeared", appeared)
            putLong("last_event_timestamp", System.currentTimeMillis())
            apply()
        }
    }
}
