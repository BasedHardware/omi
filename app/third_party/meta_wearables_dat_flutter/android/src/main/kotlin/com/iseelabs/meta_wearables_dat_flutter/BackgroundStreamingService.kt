// Foreground service that keeps the camera/BLE pipeline alive while the
// host app is backgrounded / the screen is locked on Android.
//
// Without this service, Doze + App Standby suspend the app's network
// stack after a few minutes, which tears down Meta's `Wearables` BLE
// link and ends the stream. The plugin starts this service from
// `enableBackgroundStreaming(androidNotification:)` and stops it from
// `disableBackgroundStreaming()`.
//
// What it does:
//   1. Runs as a *foreground* service with
//      `FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE`, the strictest type
//      we can claim that still permits BLE access in the background.
//   2. Shows a low-importance notification (the host app supplies its
//      title / text via the [BackgroundNotification] Dart model).
//   3. Acquires a `PARTIAL_WAKE_LOCK` so the CPU keeps decoding video
//      frames even while the screen is off.
//
// The host app must declare the matching permissions
// (`FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_CONNECTED_DEVICE`,
// `WAKE_LOCK`, `POST_NOTIFICATIONS`) — these are merged from the
// plugin's `AndroidManifest.xml` automatically by the Android Gradle
// Plugin's manifest merger.

package com.iseelabs.meta_wearables_dat_flutter

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat

class BackgroundStreamingService : Service() {
    companion object {
        const val EXTRA_TITLE = "title"
        const val EXTRA_TEXT = "text"
        const val EXTRA_CHANNEL_ID = "channelId"
        const val EXTRA_CHANNEL_NAME = "channelName"
        const val EXTRA_ICON_RESOURCE_NAME = "iconResourceName"

        /** Fixed within the host-app process; arbitrary positive integer. */
        const val NOTIFICATION_ID = 0x4D454441
    }

    private var wakeLock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val args = intent?.extras
        val title = args?.getString(EXTRA_TITLE) ?: "Streaming in background"
        val text = args?.getString(EXTRA_TEXT)
            ?: "Your glasses are still sending frames to this app."
        val channelId = args?.getString(EXTRA_CHANNEL_ID)
            ?: "meta_wearables_dat_background"
        val channelName = args?.getString(EXTRA_CHANNEL_NAME)
            ?: "Wearables background streaming"
        val iconResourceName = args?.getString(EXTRA_ICON_RESOURCE_NAME)

        ensureNotificationChannel(channelId, channelName)
        val notification = buildNotification(
            title = title,
            text = text,
            channelId = channelId,
            iconResourceName = iconResourceName,
        )
        startForegroundCompat(notification)

        acquireWakeLockIfNeeded()
        return START_STICKY
    }

    override fun onDestroy() {
        releaseWakeLock()
        super.onDestroy()
    }

    private fun startForegroundCompat(notification: Notification) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE,
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun ensureNotificationChannel(channelId: String, channelName: String) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java)
            ?: return
        if (manager.getNotificationChannel(channelId) == null) {
            manager.createNotificationChannel(
                NotificationChannel(
                    channelId,
                    channelName,
                    NotificationManager.IMPORTANCE_LOW,
                ).apply {
                    description = "Shown while Meta Wearables DAT keeps a " +
                        "stream alive in the background."
                    setShowBadge(false)
                },
            )
        }
    }

    private fun buildNotification(
        title: String,
        text: String,
        channelId: String,
        iconResourceName: String?,
    ): Notification {
        val iconRes = iconResourceName?.let { name ->
            resources.getIdentifier(name, "drawable", packageName).takeIf {
                it != 0
            }
        } ?: applicationInfo.icon

        return NotificationCompat.Builder(this, channelId)
            .setContentTitle(title)
            .setContentText(text)
            .setSmallIcon(iconRes)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .build()
    }

    private fun acquireWakeLockIfNeeded() {
        if (wakeLock?.isHeld == true) return
        val power = getSystemService(Context.POWER_SERVICE) as? PowerManager
            ?: return
        val lock = power.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "MWDAT::StreamingWakeLock",
        )
        lock.setReferenceCounted(false)
        lock.acquire(10 * 60 * 60 * 1000L)
        wakeLock = lock
    }

    private fun releaseWakeLock() {
        wakeLock?.takeIf { it.isHeld }?.release()
        wakeLock = null
    }
}
