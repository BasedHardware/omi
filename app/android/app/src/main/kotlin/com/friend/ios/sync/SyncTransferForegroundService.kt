package com.friend.ios.sync

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

/**
 * Thin lifecycle shell that keeps Dart WAL file transfers alive when the
 * screen turns off. It owns only the dataSync foreground-service promotion,
 * notification, and a PARTIAL_WAKE_LOCK. BLE GATT stays with
 * [com.friend.ios.ble.OmiBleForegroundService]; upload/drain loops stay in Dart.
 *
 * Dart [SyncTransferKeepAlive] starts this for the transfer lifetime and
 * stops it on complete or cancel. No restart policy: [onStartCommand] returns
 * START_NOT_STICKY so a killed process does not resurrect an orphaned sync.
 */
class SyncTransferForegroundService : Service() {

    companion object {
        private const val TAG = "SyncTransfer.FgService"
        private const val EXTRA_TEXT = "notification_text"

        /**
         * Promote the service to the foreground and hold a partial wake lock.
         * Returns whether the OS accepted the start; Dart treats a rejection
         * as non-fatal (transfer continues without OS keep-alive).
         */
        fun start(context: Context, text: String? = null): Boolean {
            return try {
                val intent = Intent(context, SyncTransferForegroundService::class.java)
                if (!text.isNullOrBlank()) {
                    intent.putExtra(EXTRA_TEXT, text)
                }
                ContextCompat.startForegroundService(context, intent)
                true
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start sync-transfer foreground service", e)
                false
            }
        }

        fun stop(context: Context) {
            try {
                context.stopService(Intent(context, SyncTransferForegroundService::class.java))
            } catch (e: Exception) {
                Log.w(TAG, "Failed to stop sync-transfer foreground service: ${e.message}")
            }
        }
    }

    private var wakeLock: PowerManager.WakeLock? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        Log.d(TAG, "Service created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // FIRST thing: promote to foreground. An uncaught throw here silently
        // kills the process (same contract as PhoneMicForegroundService).
        try {
            startForeground(
                SyncTransferKeepAlivePolicy.NOTIFICATION_ID,
                buildNotification(intent?.getStringExtra(EXTRA_TEXT)),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            )
        } catch (e: Exception) {
            Log.e(TAG, "startForeground failed; stopping service instead of crashing", e)
            stopSelf()
            return START_NOT_STICKY
        }
        acquireWakeLock()
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onTaskRemoved(rootIntent: Intent?) {
        // Flutter dies with the task; do not leave a sync notification behind.
        stopSelf()
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        releaseWakeLock()
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }

    private fun acquireWakeLock() {
        if (!SyncTransferKeepAlivePolicy.shouldHoldPartialWakeLock(true)) return
        if (wakeLock?.isHeld == true) return
        val pm = getSystemService(PowerManager::class.java) ?: return
        wakeLock = pm.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            SyncTransferKeepAlivePolicy.WAKE_LOCK_TAG
        ).apply {
            setReferenceCounted(false)
            acquire()
        }
    }

    private fun releaseWakeLock() {
        val held = wakeLock
        if (held?.isHeld == true) {
            held.release()
        }
        wakeLock = null
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            SyncTransferKeepAlivePolicy.NOTIFICATION_CHANNEL_ID,
            SyncTransferKeepAlivePolicy.NOTIFICATION_CHANNEL_NAME,
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            setShowBadge(false)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun buildNotification(requestedText: String?): Notification {
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
        val pendingIntent = if (launchIntent != null) {
            PendingIntent.getActivity(this, 0, launchIntent, PendingIntent.FLAG_IMMUTABLE)
        } else null

        return NotificationCompat.Builder(this, SyncTransferKeepAlivePolicy.NOTIFICATION_CHANNEL_ID)
            .setContentTitle(SyncTransferKeepAlivePolicy.DEFAULT_NOTIFICATION_TITLE)
            .setContentText(SyncTransferKeepAlivePolicy.resolveNotificationText(requestedText))
            .setSmallIcon(applicationInfo.icon)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .apply { if (pendingIntent != null) setContentIntent(pendingIntent) }
            .build()
    }
}
