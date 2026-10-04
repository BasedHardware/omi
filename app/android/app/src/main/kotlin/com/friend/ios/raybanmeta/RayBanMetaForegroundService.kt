package com.friend.ios.raybanmeta

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

/**
 * Keeps Ray-Ban Meta glasses capture alive while the app is backgrounded.
 *
 * Android silences an AudioRecord started from the foreground once the app
 * leaves it unless a microphone-type foreground service is running; the DAT
 * device session likewise needs a connectedDevice-type service. This shell owns
 * only the promotion + notification — [RayBanMetaHostApiImpl] decides when to
 * [start]/[stop] it (audio capture running, camera session active).
 */
class RayBanMetaForegroundService : Service() {

    companion object {
        private const val TAG = "RayBanMeta.FgService"
        private const val CHANNEL_ID = "omi_rayban_meta_channel"
        private const val NOTIFICATION_ID = 2004 // BLE 2001, phone mic 2002

        fun start(context: Context): Boolean {
            return try {
                ContextCompat.startForegroundService(context, Intent(context, RayBanMetaForegroundService::class.java))
                true
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start Ray-Ban Meta foreground service", e)
                false
            }
        }

        fun stop(context: Context) {
            try {
                context.stopService(Intent(context, RayBanMetaForegroundService::class.java))
            } catch (e: Exception) {
                Log.w(TAG, "Failed to stop Ray-Ban Meta foreground service: ${e.message}")
            }
        }
    }

    override fun onCreate() {
        super.onCreate()
        val channel = NotificationChannel(CHANNEL_ID, "Omi Glasses Recording", NotificationManager.IMPORTANCE_LOW)
            .apply { setShowBadge(false) }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Promote first: an uncaught throw here (e.g. a missing runtime permission
        // for a requested type on Android 14+) would kill the whole process.
        var types = ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED) {
            types = types or ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE
        }
        try {
            startForeground(NOTIFICATION_ID, buildNotification(), types)
        } catch (e: Exception) {
            Log.e(TAG, "startForeground failed; stopping service instead of crashing", e)
            stopSelf()
        }
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun buildNotification(): Notification {
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
        val pendingIntent = launchIntent?.let {
            PendingIntent.getActivity(this, 0, it, PendingIntent.FLAG_IMMUTABLE)
        }
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Omi")
            .setContentText("Listening through your glasses")
            .setSmallIcon(applicationInfo.icon)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .apply { if (pendingIntent != null) setContentIntent(pendingIntent) }
            .build()
    }
}
