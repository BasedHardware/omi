package com.friend.ios

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

/**
 * Foreground service specifically for keeping BLE connections alive.
 *
 * This service runs with foregroundServiceType="connectedDevice" which tells
 * Android to prioritize keeping Bluetooth connections stable.
 */
class ConnectionForegroundService : Service() {

    companion object {
        private const val TAG = "ConnectionFgService"
        private const val CHANNEL_ID = "omi_connection_service"
        private const val NOTIFICATION_ID = 8001
        private const val METHOD_CHANNEL = "com.omi.connection_foreground_service"

        private var methodChannel: MethodChannel? = null
        private var instance: ConnectionForegroundService? = null

        /**
         * Register method channel with Flutter engine
         */
        fun register(flutterEngine: FlutterEngine, context: Context) {
            methodChannel = MethodChannel(
                flutterEngine.dartExecutor.binaryMessenger,
                METHOD_CHANNEL
            ).apply {
                setMethodCallHandler { call, result -> handleMethodCall(context, call, result) }
            }
        }

        private fun handleMethodCall(context: Context, call: MethodCall, result: MethodChannel.Result) {
            when (call.method) {
                "start" -> {
                    val deviceName = call.argument<String>("deviceName") ?: "Omi"
                    startService(context, deviceName)
                    result.success(true)
                }
                "stop" -> {
                    stopService(context)
                    result.success(true)
                }
                "isRunning" -> {
                    result.success(instance != null)
                }
                "updateNotification" -> {
                    val deviceName = call.argument<String>("deviceName") ?: "Omi"
                    val batteryLevel = call.argument<Int>("batteryLevel")
                    instance?.updateNotification(deviceName, batteryLevel)
                    result.success(true)
                }
                else -> {
                    result.notImplemented()
                }
            }
        }

        fun startService(context: Context, deviceName: String) {
            val intent = Intent(context, ConnectionForegroundService::class.java).apply {
                putExtra("device_name", deviceName)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
            Log.d(TAG, "Starting connection foreground service for $deviceName")
        }

        fun stopService(context: Context) {
            val intent = Intent(context, ConnectionForegroundService::class.java)
            context.stopService(intent)
            Log.d(TAG, "Stopping connection foreground service")
        }
    }

    private var wakeLock: PowerManager.WakeLock? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        createNotificationChannel()
        acquireWakeLock()
        Log.d(TAG, "Service created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val deviceName = intent?.getStringExtra("device_name") ?: "Omi"

        val notification = createNotification(deviceName, null)
        startForeground(NOTIFICATION_ID, notification)

        Log.d(TAG, "Service started in foreground for $deviceName")

        // Restart if killed
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        releaseWakeLock()
        instance = null
        Log.d(TAG, "Service destroyed")
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Omi Connection",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Keeps your Omi device connected"
                setShowBadge(false)
            }

            val notificationManager = getSystemService(NotificationManager::class.java)
            notificationManager.createNotificationChannel(channel)
        }
    }

    private fun createNotification(deviceName: String, batteryLevel: Int?): Notification {
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)?.apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
        }

        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val contentText = if (batteryLevel != null) {
            "$deviceName connected • Battery: $batteryLevel%"
        } else {
            "$deviceName connected"
        }

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentTitle("Omi")
            .setContentText(contentText)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .setContentIntent(pendingIntent)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .build()
    }

    fun updateNotification(deviceName: String, batteryLevel: Int?) {
        val notification = createNotification(deviceName, batteryLevel)
        val notificationManager = getSystemService(NotificationManager::class.java)
        notificationManager.notify(NOTIFICATION_ID, notification)
    }

    private fun acquireWakeLock() {
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = powerManager.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "omi:connection_service"
        ).apply {
            acquire()
        }
        Log.d(TAG, "Wake lock acquired")
    }

    private fun releaseWakeLock() {
        wakeLock?.let {
            if (it.isHeld) {
                it.release()
                Log.d(TAG, "Wake lock released")
            }
        }
        wakeLock = null
    }
}
