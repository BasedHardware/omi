package com.omi.ambientcompanion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder

class MediaProjectionSessionService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        createChannel()
        startForeground(66042, notification("MediaProjection capture is ready for explicit sessions."))
        AuditLog(this).record("media_projection_session_placeholder")
        stopSelf()
        return START_NOT_STICKY
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            getSystemService(NotificationManager::class.java)
                .createNotificationChannel(NotificationChannel("omi_ambient_projection", "Omi Ambient Projection", NotificationManager.IMPORTANCE_LOW))
        }
    }

    private fun notification(text: String): Notification {
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) Notification.Builder(this, "omi_ambient_projection") else Notification.Builder(this)
        return builder
            .setContentTitle("Omi Ambient Companion")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.presence_audio_online)
            .build()
    }
}
