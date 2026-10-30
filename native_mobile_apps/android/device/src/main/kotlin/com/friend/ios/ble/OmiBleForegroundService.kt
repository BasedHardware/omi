package com.friend.ios.ble

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat

/**
 * The Flutter app's BLE foreground service, under the same component name (an in-place update
 * keeps it registered). In Flutter it owned the whole link (connect, retry, background audio);
 * natively `OmiDeviceManager` and `DeviceStore` own that, as on iOS, and this service only keeps
 * the process alive while an Omi is paired and connected or awaited (`connectedDevice` type), with
 * its ongoing notification. The `ble_config` preferences stay the Flutter ones so
 * `BleCompanionService` starts it the same way after a reboot or when the Omi comes into range.
 */
class OmiBleForegroundService : Service() {
    companion object {
        private const val TAG = "OmiBle.FgService"
        private const val CHANNEL_ID = "omi_ble_channel"
        private const val NOTIFICATION_ID = 2001
        internal const val PREFS_NAME = "ble_config"
        internal const val PREFS_KEY = "managed_device"
        internal const val PREFS_USER_DISCONNECTED = "user_disconnected"
        private const val EXTRA_ADDRESS = "address"

        @Volatile
        private var instance: OmiBleForegroundService? = null

        /** The app wakes its device store with this when the system starts the service on its own. */
        @Volatile
        var onStart: ((address: String) -> Unit)? = null

        /** The notification's line (the app passes its localized wording). */
        @Volatile
        var statusText: () -> String = { "" }

        fun isActive(): Boolean = instance != null

        /** Natively the link is always kept in the background (iOS does the same). */
        @Suppress("UNUSED_PARAMETER")
        fun isPersistentModeEnabled(context: Context): Boolean = true

        fun startService(context: Context, deviceAddress: String, requiresBond: Boolean = false, caller: String = "unknown") {
            remember(context, deviceAddress, requiresBond)
            val intent = Intent(context, OmiBleForegroundService::class.java).putExtra(EXTRA_ADDRESS, deviceAddress.uppercase())
            try {
                ContextCompat.startForegroundService(context, intent)
            } catch (e: Exception) {
                // Started from the background without a companion association: the link still works
                // while the app is open.
                Log.w(TAG, "startService($caller) refused: ${e.message}")
            }
        }

        /** The user let the Omi go (forget, firmware update): no restart on reboot or presence. */
        fun stopService(context: Context, userDisconnected: Boolean = false) {
            if (userDisconnected) {
                context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).edit()
                    .remove(PREFS_KEY).putBoolean(PREFS_USER_DISCONNECTED, true).apply()
            }
            instance?.let {
                it.stopForeground(STOP_FOREGROUND_REMOVE)
                it.stopSelf()
            }
        }

        /** Refreshes the notification line ([statusText]) while the service runs. */
        fun refresh() {
            instance?.updateNotification()
        }

        private fun remember(context: Context, address: String, requiresBond: Boolean) {
            context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).edit()
                .putString(PREFS_KEY, "${address.uppercase()}|$requiresBond")
                .putBoolean(PREFS_USER_DISCONNECTED, false)
                .apply()
        }
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Android 12+ throws when a foreground start is not allowed: stop instead of crashing.
        try {
            val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE else 0
            ServiceCompat.startForeground(this, NOTIFICATION_ID, buildNotification(), type)
        } catch (e: Exception) {
            Log.e(TAG, "startForeground failed; stopping service", e)
            stopSelf()
            return START_NOT_STICKY
        }
        val address = intent?.getStringExtra(EXTRA_ADDRESS)
            ?: getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).getString(PREFS_KEY, null)?.substringBefore("|")
        address?.let { onStart?.invoke(it) }
        return START_STICKY
    }

    override fun onDestroy() {
        instance = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun updateNotification() {
        try {
            getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, buildNotification())
        } catch (e: Exception) {
            Log.w(TAG, "updateNotification failed: ${e.message}")
        }
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(CHANNEL_ID, "Omi", NotificationManager.IMPORTANCE_LOW).apply { setShowBadge(false) }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun buildNotification(): Notification {
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
        val pendingIntent = launchIntent?.let { PendingIntent.getActivity(this, 0, it, PendingIntent.FLAG_IMMUTABLE) }
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Omi")
            .setContentText(statusText())
            .setSmallIcon(applicationInfo.icon)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .apply { if (pendingIntent != null) setContentIntent(pendingIntent) }
            .build()
    }
}
