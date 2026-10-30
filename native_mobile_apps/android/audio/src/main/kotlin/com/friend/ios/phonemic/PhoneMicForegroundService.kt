package com.friend.ios.phonemic

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.content.ContextCompat
import com.friend.ios.phonemic.LiveCaptureNotification.Action

/**
 * Thin lifecycle shell that keeps native mic capture alive in the background (from the Flutter
 * app, MIT). It owns only the foreground-service promotion and its notification; the AudioRecord
 * engine and all capture policy live in [PhoneMicController].
 *
 * The notification is Android's stand-in for the iOS recording Live Activity
 * ([LiveCaptureNotification]): its content comes from the app (`CaptureStore`) through [update].
 *
 * No restart/resurrect policy of its own: [onStartCommand] returns START_NOT_STICKY and there is
 * no onTaskRemoved override; the controller owns when to [start]/[stop] this service.
 */
class PhoneMicForegroundService : Service() {

    companion object {
        private const val TAG = "PhoneMic.FgService"
        private const val NOTIFICATION_ID = 2002 // BLE uses 2001
        private const val EXTRA_ACTION = "com.friend.ios.phonemic.action"

        /** The latest content; shown when the service starts and re-posted on every [update]. */
        @Volatile
        private var content: LiveCaptureNotification.Content? = null

        @Volatile
        private var running = false

        /** The app's handler for the notification buttons (`CaptureStore.pause/resume/stop`). */
        @Volatile
        var onAction: ((Action) -> Unit)? = null

        /**
         * Promote the service to the foreground. Returns whether the OS accepted the
         * start; the controller surfaces a non-fatal error when it did not (rethrows
         * nothing: an uncaught throw from here would kill the process).
         */
        fun start(context: Context): Boolean {
            return try {
                ContextCompat.startForegroundService(
                    context,
                    Intent(context, PhoneMicForegroundService::class.java)
                )
                true
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start phone-mic foreground service", e)
                false
            }
        }

        /**
         * While a recording is paused the microphone is released but the conversation stays open:
         * the notification (Resume, Stop) stays, as the iOS Live Activity does. [release] ends it.
         */
        @Volatile
        var holdsWhilePaused = false

        fun stop(context: Context) {
            if (holdsWhilePaused) return
            try {
                context.stopService(Intent(context, PhoneMicForegroundService::class.java))
            } catch (e: Exception) {
                Log.w(TAG, "Failed to stop phone-mic foreground service: ${e.message}")
            }
        }

        /** The recording ended: drops a pause hold and stops the service. */
        fun release(context: Context) {
            holdsWhilePaused = false
            stop(context)
        }

        /** New words, pause state or time: re-posts the ongoing notification while the service runs. */
        fun update(context: Context, newContent: LiveCaptureNotification.Content) {
            if (newContent == content) return
            content = newContent
            if (!running) return
            val manager = context.getSystemService(NotificationManager::class.java) ?: return
            try {
                manager.notify(NOTIFICATION_ID, buildNotification(context, newContent))
            } catch (e: Exception) {
                Log.w(TAG, "notification update failed: ${e.message}")
            }
        }

        internal fun buildNotification(context: Context, content: LiveCaptureNotification.Content?): Notification =
            LiveCaptureNotification.build(context, content) { action ->
                val intent = Intent(context, PhoneMicForegroundService::class.java).putExtra(EXTRA_ACTION, action.name)
                PendingIntent.getService(
                    context, action.ordinal + 1, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
                )
            }
    }

    override fun onCreate() {
        super.onCreate()
        LiveCaptureNotification.createChannel(this)
        Log.d(TAG, "Service created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // A button on the notification: hand it to the app on the main thread.
        intent?.getStringExtra(EXTRA_ACTION)?.let { raw ->
            val action = runCatching { Action.valueOf(raw) }.getOrNull()
            if (action != null) Handler(Looper.getMainLooper()).post { onAction?.invoke(action) }
            return START_NOT_STICKY
        }
        // FIRST thing: promote to foreground with the microphone type. On Android 14+
        // startForeground(mic) without RECORD_AUDIO granted throws SecurityException, and
        // any uncaught throw here silently kills the whole process. Stop cleanly instead.
        //
        // Ordering is safe by construction: controller start (main turn T) -> onStartCommand
        // (T+1) -> any stop (later turn) are serialized by the main-thread FIFO, so the classic
        // "startForegroundService did not call startForeground in time" crash is unreachable.
        try {
            startForeground(
                NOTIFICATION_ID,
                buildNotification(this, content),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
            )
            running = true
        } catch (e: Exception) {
            Log.e(TAG, "startForeground failed; stopping service instead of crashing", e)
            stopSelf()
            return START_NOT_STICKY
        }
        // No resurrect path by design: the controller owns restart policy.
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        running = false
        content = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
