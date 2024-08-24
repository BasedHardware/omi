package com.friend.ios

import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import androidx.annotation.RequiresApi
import androidx.core.app.NotificationCompat
import io.flutter.Log
import android.graphics.BitmapFactory

class NotificationOnKillService: Service() {
    private lateinit var title: String
    private lateinit var description: String

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        title = intent?.getStringExtra("title") ?: ""
        description = intent?.getStringExtra("description") ?: ""

        return START_STICKY
    }

    @RequiresApi(Build.VERSION_CODES.O)
    override fun onTaskRemoved(rootIntent: Intent?) {
        try {
            
            if (title.isBlank() || description.isBlank()) {
                Log.d("NotificationOnKillService", "Title or description is empty, notification will not be shown")
                return
            }
            val notificationIntent = packageManager.getLaunchIntentForPackage(packageName)
            val pendingIntent = PendingIntent.getActivity(this, 0, notificationIntent, PendingIntent.FLAG_IMMUTABLE)
    
            val notificationBuilder = NotificationCompat.Builder(this, "com.friend.ios")
                .setSmallIcon(getSmallIconForNotification())
                .setContentTitle(title)
                .setContentText(description)
                .setAutoCancel(true)
                .setPriority(NotificationCompat.PRIORITY_MAX)
                .setContentIntent(pendingIntent)
                .setSound(Settings.System.DEFAULT_NOTIFICATION_URI)

            val name = "Notification permission"
            val descriptionText = "You need to enable notifications to receive your pro-active feedback."
            val importance = NotificationManager.IMPORTANCE_DEFAULT
            val channel = NotificationChannel("com.friend.ios", name, importance).apply {
                description = descriptionText
            }

            val notificationManager: NotificationManager =
                getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            notificationManager.createNotificationChannel(channel)
            notificationManager.notify(123, notificationBuilder.build())
        } catch (e: Exception) {
            Log.d("NotificationOnKillService", "Error showing notification", e)
        }
        super.onTaskRemoved(rootIntent)
        

    }
    private fun getSmallIconForNotification(): Int {
        return if (Build.VERSION.SDK_INT > Build.VERSION_CODES.LOLLIPOP) {
            R.mipmap.ic_stat_launcher
        } else {
            R.mipmap.ic_launcher
        }
    }
    override fun onBind(intent: Intent?): IBinder? {
        return null
    }
}