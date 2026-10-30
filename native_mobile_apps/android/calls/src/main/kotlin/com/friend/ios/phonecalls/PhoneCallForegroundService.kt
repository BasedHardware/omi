package com.friend.ios.phonecalls

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Person
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * Keeps a call alive while the app is in the background (iOS: CallKit's audio session and the
 * green status pill): a `phoneCall` + `microphone` foreground service with an ongoing call
 * notification (CallStyle) whose Hang up button ends the call and whose tap returns to it.
 */
class PhoneCallForegroundService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_HANG_UP) {
            onHangUp?.invoke()
            return START_NOT_STICKY
        }
        val name = intent?.getStringExtra(EXTRA_NAME).orEmpty()
        val notification = notification(this, name)
        try {
            val types = ServiceInfo.FOREGROUND_SERVICE_TYPE_PHONE_CALL or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
            startForeground(NOTIFICATION_ID, notification, types)
        } catch (error: Exception) {
            // Not allowed now (no Telecom call yet, background start): the call goes on in the foreground.
            Log.w(TAG, "startForeground: ${error.message}")
            stopSelf()
        }
        return START_NOT_STICKY
    }

    companion object {
        private const val TAG = "PhoneCallService"
        private const val CHANNEL_ID = "phone_calls"
        private const val NOTIFICATION_ID = 4711
        private const val EXTRA_NAME = "name"
        private const val ACTION_HANG_UP = "com.friend.ios.phonecalls.HANG_UP"

        /** The notification's hang-up button (the engine ends the call). */
        @Volatile
        var onHangUp: (() -> Unit)? = null

        /** Localized texts, set by the app: the channel name and the "ongoing call" line. */
        @Volatile
        var channelName: () -> String = { "Phone calls" }

        @Volatile
        var hangUpTitle: () -> String = { "Hang up" }

        /** The app's status bar icon. */
        @Volatile
        var smallIcon: Int = android.R.drawable.sym_call_outgoing

        fun start(context: Context, name: String) {
            val intent = Intent(context, PhoneCallForegroundService::class.java).putExtra(EXTRA_NAME, name)
            runCatching { ContextCompat.startForegroundService(context, intent) }
                .onFailure { Log.w(TAG, "start: ${it.message}") }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, PhoneCallForegroundService::class.java))
        }

        private fun notification(context: Context, name: String): Notification {
            val manager = context.getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, channelName(), NotificationManager.IMPORTANCE_LOW))
            val open = context.packageManager.getLaunchIntentForPackage(context.packageName)?.let {
                PendingIntent.getActivity(context, 0, it, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            }
            val hangUp = PendingIntent.getService(
                context, 1, Intent(context, PhoneCallForegroundService::class.java).setAction(ACTION_HANG_UP),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
            val person = Person.Builder().setName(name.ifEmpty { channelName() }).setImportant(true).build()
            val builder = Notification.Builder(context, CHANNEL_ID)
                .setSmallIcon(smallIcon)
                .setOngoing(true)
                .setCategory(Notification.CATEGORY_CALL)
                .setContentIntent(open)
                .setUsesChronometer(true)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                builder.setStyle(Notification.CallStyle.forOngoingCall(person, hangUp))
            } else {
                builder.setContentTitle(name)
                    .addAction(Notification.Action.Builder(null, hangUpTitle(), hangUp).build())
            }
            return builder.build()
        }
    }
}
