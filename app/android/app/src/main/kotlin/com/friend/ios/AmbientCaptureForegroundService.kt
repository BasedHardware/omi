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
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

class AmbientCaptureForegroundService : Service() {
    private var recorder: AmbientAudioRecorder? = null
    private var healthMonitor: AmbientCaptureHealthMonitor? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        createNotificationChannel()
        healthMonitor = AmbientCaptureHealthMonitor(this) { event ->
            lastHealth = event
            AmbientCaptureMethodChannel.emitHealth(event)
            emitTelemetry(event["state"].toString().lowercase())
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action ?: ACTION_START) {
            ACTION_START -> startCapture()
            ACTION_PAUSE -> pauseCapture()
            ACTION_RESUME -> resumeCapture()
            ACTION_STOP -> stopCapture()
            ACTION_PRIVATE_MODE -> enablePrivateMode()
        }
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        recorder?.stop()
        healthMonitor?.setServiceKilled()
        healthMonitor?.stop()
        isRunning = false
        instance = null
        super.onDestroy()
    }

    private fun startCapture() {
        if (isRunning) return
        isRunning = true
        isPaused = false
        privateMode = false
        startForeground(NOTIFICATION_ID, buildNotification("Recording"))
        healthMonitor?.start()
        recorder = AmbientAudioRecorder(
            this,
            onChunk = { bytes -> AmbientCaptureMethodChannel.emitAudio(bytes) },
            onLevel = { dbfs, zero -> healthMonitor?.updateAudioLevel(dbfs, zero) },
            onError = { error ->
                if (error == "permission_missing") healthMonitor?.setPermissionMissing()
                emitTelemetry(error)
                stopSelf()
            },
        )
        if (recorder?.start() == true) {
            emitTelemetry("capture_started")
        }
    }

    private fun pauseCapture() {
        if (!isRunning) return
        recorder?.pause()
        isPaused = true
        privateMode = false
        healthMonitor?.setPaused()
        updateNotification("Paused")
        emitTelemetry("capture_paused")
    }

    private fun resumeCapture() {
        if (!isRunning) return
        recorder?.resume()
        isPaused = false
        privateMode = false
        updateNotification("Recording")
        emitTelemetry("capture_resumed")
    }

    private fun enablePrivateMode() {
        if (!isRunning) return
        recorder?.pause()
        isPaused = true
        privateMode = true
        healthMonitor?.setPrivateMode()
        updateNotification("Private Mode")
        emitTelemetry("private_mode_enabled")
    }

    private fun stopCapture() {
        recorder?.stop()
        recorder = null
        healthMonitor?.stop()
        isRunning = false
        isPaused = false
        privateMode = false
        emitTelemetry("capture_stopped")
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun updateNotification(text: String) {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIFICATION_ID, buildNotification(text))
    }

    private fun buildNotification(status: String): Notification {
        val openIntent = packageManager.getLaunchIntentForPackage(packageName)
            ?.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
            ?: Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val openPendingIntent = PendingIntent.getActivity(
            this,
            10,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(applicationInfo.icon)
            .setContentTitle("Advanced Ambient Capture")
            .setContentText(status)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setContentIntent(openPendingIntent)
            .addAction(0, "Pause", actionIntent(ACTION_PAUSE, 1))
            .addAction(0, "Resume", actionIntent(ACTION_RESUME, 2))
            .addAction(0, "Stop", actionIntent(ACTION_STOP, 3))
            .addAction(0, "Private Mode", actionIntent(ACTION_PRIVATE_MODE, 4))
            .addAction(0, "Open Omi", openPendingIntent)
            .build()
    }

    private fun actionIntent(action: String, requestCode: Int): PendingIntent {
        val intent = Intent(this, CaptureNotificationActionReceiver::class.java).setAction(action)
        return PendingIntent.getBroadcast(this, requestCode, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(CHANNEL_ID, "Advanced Ambient Capture", NotificationManager.IMPORTANCE_LOW)
        channel.description = "Visible controls for optional Android ambient microphone capture"
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(channel)
    }

    private fun emitTelemetry(type: String) {
        AmbientCaptureMethodChannel.emitTelemetry(
            mapOf(
                "type" to type,
                "timestamp" to System.currentTimeMillis(),
                "state" to statusMap(),
            ),
        )
    }

    companion object {
        const val ACTION_START = "com.friend.ios.ambient.START"
        const val ACTION_STOP = "com.friend.ios.ambient.STOP"
        const val ACTION_PAUSE = "com.friend.ios.ambient.PAUSE"
        const val ACTION_RESUME = "com.friend.ios.ambient.RESUME"
        const val ACTION_PRIVATE_MODE = "com.friend.ios.ambient.PRIVATE_MODE"
        private const val CHANNEL_ID = "ambient_capture"
        private const val NOTIFICATION_ID = 44072

        private var instance: AmbientCaptureForegroundService? = null
        private var isRunning = false
        private var isPaused = false
        private var privateMode = false
        private var lastHealth: Map<String, Any?> = mapOf("state" to AmbientHealthState.UNKNOWN_DEGRADED.name)

        fun start(context: Context) {
            val intent = Intent(context, AmbientCaptureForegroundService::class.java).setAction(ACTION_START)
            ContextCompat.startForegroundService(context, intent)
        }

        fun stop(context: Context) = command(context, ACTION_STOP)

        fun command(context: Context, action: String) {
            val intent = Intent(context, AmbientCaptureForegroundService::class.java).setAction(action)
            ContextCompat.startForegroundService(context, intent)
        }

        fun updateFlutterState(socketConnected: Boolean?, networkAvailable: Boolean?, walQueueDepth: Int?) {
            instance?.healthMonitor?.updateFlutterState(socketConnected, networkAvailable, walQueueDepth)
        }

        fun statusMap(): Map<String, Any?> = mapOf(
            "running" to isRunning,
            "paused" to isPaused,
            "privateMode" to privateMode,
        )

        fun healthMap(): Map<String, Any?> = lastHealth
    }
}
