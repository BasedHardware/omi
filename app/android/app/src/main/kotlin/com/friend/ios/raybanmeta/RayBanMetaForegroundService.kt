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
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.content.ContextCompat
import androidx.core.app.NotificationCompat

/**
 * Keeps Ray-Ban Meta glasses capture alive while the app is backgrounded.
 *
 * Android silences an AudioRecord started from the foreground once the app
 * leaves it unless a microphone-type foreground service is running; the DAT
 * device session likewise needs a connectedDevice-type service. The caller
 * passes which of the two are actually in use, so a camera-only session never
 * asks for the microphone type (which Android 14+ rejects without RECORD_AUDIO)
 * and an audio-only session never claims connectedDevice. This shell owns only
 * the promotion + notification — [RayBanMetaHostApiImpl] decides when to
 * [update] or [stop] it.
 */
class RayBanMetaForegroundService : Service() {

    companion object {
        private const val TAG = "RayBanMeta.FgService"
        private const val CHANNEL_ID = "omi_rayban_meta_channel"
        private const val NOTIFICATION_ID = 2004 // BLE 2001, phone mic 2002
        private const val EXTRA_MICROPHONE = "microphone"
        private const val EXTRA_CONNECTED_DEVICE = "connectedDevice"

        /**
         * Reports a promotion the OS refused (missing runtime permission for the
         * requested type). Capture keeps running in the foreground, but Android
         * may silence it in the background, so the owner surfaces it to Dart.
         */
        @Volatile var onPromotionFailed: ((String) -> Unit)? = null

        /** Starts or re-promotes the service with the types currently in use. */
        fun update(context: Context, microphone: Boolean, connectedDevice: Boolean): Boolean {
            return try {
                val intent = Intent(context, RayBanMetaForegroundService::class.java)
                    .putExtra(EXTRA_MICROPHONE, microphone)
                    .putExtra(EXTRA_CONNECTED_DEVICE, connectedDevice)
                ContextCompat.startForegroundService(context, intent)
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

        /** Pure type selection, exposed for tests. 0 means no requested type is permitted. */
        internal fun serviceTypes(
            microphone: Boolean,
            connectedDevice: Boolean,
            hasRecordAudio: Boolean,
            hasBluetoothConnect: Boolean,
        ): Int {
            var types = 0
            if (microphone && hasRecordAudio) types = types or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
            if (connectedDevice && hasBluetoothConnect) {
                types = types or ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE
            }
            return types
        }
    }

    override fun onCreate() {
        super.onCreate()
        val channel = NotificationChannel(CHANNEL_ID, "Omi Glasses Recording", NotificationManager.IMPORTANCE_LOW)
            .apply { setShowBadge(false) }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val microphone = intent?.getBooleanExtra(EXTRA_MICROPHONE, false) ?: false
        val connectedDevice = intent?.getBooleanExtra(EXTRA_CONNECTED_DEVICE, false) ?: false
        val types = serviceTypes(
            microphone = microphone,
            connectedDevice = connectedDevice,
            hasRecordAudio = granted(Manifest.permission.RECORD_AUDIO),
            hasBluetoothConnect = Build.VERSION.SDK_INT < Build.VERSION_CODES.S ||
                granted(Manifest.permission.BLUETOOTH_CONNECT),
        )
        // Promote first, with nothing that can throw before it: every
        // startForegroundService() must be answered by startForeground() or
        // Android kills the process with ForegroundServiceDidNotStartInTimeException.
        try {
            if (types == 0) throw SecurityException("no permitted foreground service type for this session")
            startForeground(NOTIFICATION_ID, buildNotification(), types)
            Log.i(TAG, "promoted types=$types (microphone=$microphone connectedDevice=$connectedDevice)")
        } catch (e: Exception) {
            Log.e(TAG, "startForeground(types=$types) refused; satisfying the start contract before stopping", e)
            satisfyStartContractThenStop()
            onPromotionFailed?.invoke(e.message ?: e.javaClass.simpleName)
        }
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun granted(permission: String): Boolean =
        ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED

    /**
     * Stopping without ever calling startForeground() still trips the start
     * timeout on Android 12+. shortService needs no runtime permission, so it
     * always promotes; we then stop immediately.
     */
    private fun satisfyStartContractThenStop() {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                startForeground(NOTIFICATION_ID, buildNotification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_SHORT_SERVICE)
            } else {
                // Before Android 14, the untyped call uses the manifest types and
                // enforces no runtime permission, so it satisfies the contract.
                startForeground(NOTIFICATION_ID, buildNotification())
            }
        } catch (e: Exception) {
            Log.e(TAG, "fallback promotion failed", e)
        }
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

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
