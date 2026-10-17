package com.friend.ios

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.friend.ios.design.Strings

/** Port of `DeviceNotifications.swift`: local notifications about the Omi wearable itself. */
object DeviceNotifications {
    private const val CHANNEL_ID = "omi.device"
    private const val LOW_BATTERY_ID = 3001

    /** Once per discharge (`LowBatteryAlert`); replaces an earlier one still on screen. */
    fun lowBattery(context: Context, level: Int, deviceName: String?) {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "Omi", NotificationManager.IMPORTANCE_DEFAULT))
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(context.applicationInfo.icon)
            .setContentTitle(Strings.get(context, "nativeOmiBatteryLowTitle", deviceName ?: "Omi"))
            .setContentText(Strings.get(context, "nativeOmiBatteryLowBody", level.toString()))
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(LOW_BATTERY_ID, notification)
    }
}
