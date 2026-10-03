package com.friend.ios.sync

import android.annotation.SuppressLint
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
import android.os.PowerManager
import android.util.Log
import androidx.annotation.MainThread
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.friend.ios.fgs.ForegroundStartContract

/**
 * Thin lifecycle shell that keeps Dart WAL file transfers alive when the
 * screen turns off. It owns the immediate shortService promotion, the
 * dataSync upgrade, notification, and a PARTIAL_WAKE_LOCK. BLE GATT stays with
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
        private const val ACTION_STOP = "com.friend.ios.sync.STOP"
        @Volatile private var cancellationRequested = false

        /**
         * Promote the service to the foreground and hold a partial wake lock.
         * Returns whether the OS accepted the start; Dart treats a rejection
         * as non-fatal (transfer continues without OS keep-alive).
         */
        @MainThread
        fun start(context: Context, text: String? = null): Boolean {
            return try {
                val intent = Intent(context, SyncTransferForegroundService::class.java)
                if (!text.isNullOrBlank()) {
                    intent.putExtra(EXTRA_TEXT, text)
                }
                ContextCompat.startForegroundService(context, intent)
                cancellationRequested = false
                true
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start sync-transfer foreground service", e)
                false
            }
        }

        @MainThread
        fun stop(context: Context) {
            // Retain cancellation even if a background-policy change rejects
            // the queued command. A pending START still promotes before it
            // observes this flag and shuts down without acquiring a wake lock.
            cancellationRequested = true
            try {
                // stopService can cancel an accepted foreground start before
                // its callbacks run. Android 16 then crashes the process even
                // if onCreate subsequently calls startForeground. Deliver stop
                // in the same command queue so promotion always precedes it.
                context.startService(
                    Intent(context, SyncTransferForegroundService::class.java).setAction(ACTION_STOP)
                )
            } catch (e: Exception) {
                Log.w(TAG, "Failed to stop sync-transfer foreground service: ${e.message}")
            }
        }
    }

    private var wakeLock: PowerManager.WakeLock? = null

    override fun onCreate() {
        super.onCreate()
        // startForegroundService's deadline also runs on a background cold
        // start. Satisfy it before intent extras, the launch intent, or the
        // transfer notification can delay the first promotion.
        promoteColdStart()
        Log.d(TAG, "Service created")
    }

    private fun promoteColdStart() {
        try {
            createNotificationChannel()
            val notification = Notification.Builder(this, SyncTransferKeepAlivePolicy.NOTIFICATION_CHANNEL_ID)
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setContentTitle(SyncTransferKeepAlivePolicy.DEFAULT_NOTIFICATION_TITLE)
                .setContentText(SyncTransferKeepAlivePolicy.DEFAULT_NOTIFICATION_TEXT)
                .setOngoing(true)
                .build()
            val type = ForegroundStartContract.coldStartType(Build.VERSION.SDK_INT)
            if (type != null) {
                startForeground(SyncTransferKeepAlivePolicy.NOTIFICATION_ID, notification, type)
            } else {
                startForeground(SyncTransferKeepAlivePolicy.NOTIFICATION_ID, notification)
            }
            Log.d(TAG, "Foreground promotion accepted")
        } catch (e: Exception) {
            Log.e(TAG, "Cold-start startForeground failed", e)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Each accepted start has a foreground obligation, including a start
        // delivered to an existing instance or immediately followed by stop.
        promoteColdStart()
        if (intent?.action == ACTION_STOP || cancellationRequested) {
            // A newer queued start owns the service; an older cancellation
            // must not tear down its notification or wake lock.
            stopSelfResult(startId)
            return START_NOT_STICKY
        }
        // Replace the immediate shortService notification with dataSync for
        // the transfer lifetime. A rejected type retries shortService before
        // stopping, including when the early promotion could not complete.
        val notification = buildNotification(intent?.getStringExtra(EXTRA_TEXT))
        if (!promoteToForeground(notification)) {
            stopSelfResult(startId)
            return START_NOT_STICKY
        }
        acquireWakeLock()
        return START_NOT_STICKY
    }

    @SuppressLint("InlinedApi")
    private fun promoteToForeground(notification: Notification): Boolean {
        try {
            startForeground(
                SyncTransferKeepAlivePolicy.NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            )
            return true
        } catch (e: Exception) {
            Log.e(TAG, "startForeground(dataSync) rejected", e)
            if (ForegroundStartContract.mustPromoteShortServiceBeforeStop(Build.VERSION.SDK_INT)) {
                try {
                    startForeground(
                        SyncTransferKeepAlivePolicy.NOTIFICATION_ID,
                        notification,
                        ServiceInfo.FOREGROUND_SERVICE_TYPE_SHORT_SERVICE
                    )
                } catch (fallback: Exception) {
                    Log.e(TAG, "startForeground(shortService) failed", fallback)
                }
            }
            return false
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onTaskRemoved(rootIntent: Intent?) {
        // Flutter dies with the task; do not leave a sync notification behind.
        stop(this)
        super.onTaskRemoved(rootIntent)
    }

    // Android 14+ limits shortService to about 3 minutes and Android 15+ limits dataSync to about
    // 6 hours a day. When a limit is reached the system calls onTimeout and, if the service is still
    // running a few seconds later, crashes the process with ForegroundServiceDidNotStopInTimeException.
    // Stop here; the Dart transfer continues without the keep-alive, as it does when a start is refused.
    override fun onTimeout(startId: Int) {
        stopForTimeout()
    }

    override fun onTimeout(startId: Int, fgsType: Int) {
        stopForTimeout()
    }

    private fun stopForTimeout() {
        Log.w(TAG, "Foreground service time limit reached; stopping sync keep-alive")
        releaseWakeLock()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
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
            .setSmallIcon(ForegroundStartContract.notificationIcon(applicationInfo.icon))
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .apply { if (pendingIntent != null) setContentIntent(pendingIntent) }
            .build()
    }
}
