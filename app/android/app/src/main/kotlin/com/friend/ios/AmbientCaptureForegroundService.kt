package com.friend.ios

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

class AmbientCaptureForegroundService : Service() {
    private var recorder: AmbientAudioRecorder? = null
    private var healthMonitor: AmbientCaptureHealthMonitor? = null
    private var spoolStore: AmbientSpoolStore? = null
    private var policyClient: AmbientPolicyClient? = null
    private val mainHandler = Handler(Looper.getMainLooper())
    private var policyLoop: Runnable? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        createNotificationChannel()
        spoolStore = AmbientSpoolStore(this)
        policyClient = AmbientPolicyClient(this)
        AmbientPolicyVerifier.configure(this, emptyMap<String, Any>())
        healthMonitor = AmbientCaptureHealthMonitor(this) { event ->
            lastHealth = event
            AmbientCaptureMethodChannel.emitHealth(event)
            emitTelemetry(event["state"].toString().lowercase())
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action ?: ACTION_START
        when (action) {
            ACTION_START -> startCapture(intent?.getBooleanExtra(EXTRA_LOCAL_MANUAL_OVERRIDE, false) == true)
            ACTION_PAUSE -> if (isRunning) pauseCapture() else safeNoop(action)
            ACTION_RESUME -> if (isRunning) resumeCapture() else safeNoop(action)
            ACTION_STOP -> if (isRunning) stopCapture() else safeNoop(action)
            ACTION_PRIVATE_MODE -> if (isRunning) enablePrivateMode() else safeNoop(action)
        }
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        recorder?.stop()
        spoolStore?.closeSession()
        stopPolicyLoop()
        healthMonitor?.setServiceKilled()
        healthMonitor?.stop()
        isRunning = false
        instance = null
        super.onDestroy()
    }

    private fun startCapture(localManualOverride: Boolean) {
        if (isRunning) return
        try {
            startForeground(NOTIFICATION_ID, buildNotification("Starting..."))
        } catch (e: Exception) {
            Log.w(TAG, "Unable to enter foreground for ambient capture", e)
            healthMonitor?.setPermissionMissing()
            emitTelemetry("foreground_start_failed")
            stopSelf()
            return
        }
        val startDecision = canStartCapture(localManualOverride)
        if (startDecision != "ok") {
            Log.w(TAG, "Refusing ambient capture start: $startDecision")
            healthMonitor?.setPolicyDisabled(startDecision)
            AmbientCaptureAudit.record(this, "capture_start_rejected", mapOf("reason" to startDecision))
            emitTelemetry("capture_start_rejected_$startDecision")
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return
        }
        isRunning = true
        isPaused = false
        privateMode = false
        updateNotification("Recording")
        spoolStore?.startSession()
        spoolStore?.enforceRetention()
        healthMonitor?.start()
        startPolicyLoop(active = true)
        recorder = AmbientAudioRecorder(
            this,
            onChunk = { bytes -> handleAudioChunk(bytes) },
            onLevel = { dbfs, zero -> healthMonitor?.updateAudioLevel(dbfs, zero) },
            onError = { error ->
                if (error == "permission_missing") healthMonitor?.setPermissionMissing()
                emitTelemetry(error)
                isRunning = false
                isPaused = false
                privateMode = false
                spoolStore?.closeSession()
                stopPolicyLoop()
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            },
        )
        if (recorder?.start() == true) {
            emitTelemetry("capture_started")
        } else {
            recorder = null
            spoolStore?.closeSession()
            stopPolicyLoop()
            healthMonitor?.stop()
            isRunning = false
            isPaused = false
            privateMode = false
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    private fun canStartCapture(localManualOverride: Boolean): String {
        val prefs = getSharedPreferences("FlutterSharedPreferences", MODE_PRIVATE)
        if (!prefs.getBoolean("flutter.advanced_ambient_capture_enabled", false)) return "master_disabled"
        if (!prefs.getBoolean("flutter.ambient_capture_plugin_control_enabled", false)) return "ok"
        if (localManualOverride) return "ok"
        val validUntil = prefs.getString("flutter.ambient_capture_last_policy_valid_until", "") ?: ""
        val captureMode = prefs.getString("flutter.ambient_capture_last_policy_capture_mode", "off") ?: "off"
        if (validUntil.isBlank()) return "fresh_policy_required"
        return try {
            val policyFresh = java.time.Instant.parse(validUntil).isAfter(java.time.Instant.now())
            if (!policyFresh || captureMode == "off" || captureMode == "private") "fresh_policy_required" else "ok"
        } catch (_: Exception) {
            "fresh_policy_required"
        }
    }

    private fun handleAudioChunk(bytes: ByteArray) {
        val result = spoolStore?.writeChunk(bytes) ?: AmbientSpoolWriteResult(false, "spool_unavailable")
        if (!result.written) {
            Log.w(TAG, "Pausing ambient capture: ${result.reason}")
            recorder?.pause()
            isPaused = true
            healthMonitor?.setStorageLimitReached(result.reason)
            updateNotification("Storage limit reached")
            emitTelemetry("storage_limit_reached")
            return
        }

        if (AmbientCaptureMethodChannel.hasAudioListener()) {
            AmbientCaptureMethodChannel.emitAudio(bytes)
        } else {
            healthMonitor?.setNoFlutterListener()
            emitTelemetry("native_spool_no_flutter_listener")
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
        spoolStore?.closeSession()
        stopPolicyLoop()
        healthMonitor?.stop()
        isRunning = false
        isPaused = false
        privateMode = false
        emitTelemetry("capture_stopped")
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun safeNoop(action: String?) {
        Log.i(TAG, "Ignoring ambient command while service is not running: $action")
        emitTelemetry("command_ignored_service_not_running")
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
        return PendingIntent.getBroadcast(
            this,
            requestCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
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

    private fun startPolicyLoop(active: Boolean) {
        stopPolicyLoop()
        val intervalMs = if (active) POLICY_ACTIVE_INTERVAL_MS else POLICY_IDLE_INTERVAL_MS
        policyLoop = Runnable {
            policyClient?.fetchVerifyAndApply { policy ->
                healthMonitor?.applyPolicy(policy)
                applyPolicySettings(policy)
                AmbientCaptureMethodChannel.emitPolicy(
                    mapOf("type" to "policy_applied", "timestamp" to System.currentTimeMillis()),
                )
            }
            policyLoop?.let { mainHandler.postDelayed(it, intervalMs) }
        }
        policyLoop?.run()
    }

    private fun stopPolicyLoop() {
        policyLoop?.let { mainHandler.removeCallbacks(it) }
        policyLoop = null
    }

    private fun applyPolicySettings(policy: Map<String, Any?>) {
        val prefs = getSharedPreferences("FlutterSharedPreferences", MODE_PRIVATE)
        val editor = prefs.edit()
        policy["capture_mode"]?.toString()?.let { editor.putString("flutter.ambient_capture_mode", it) }
        policy["sensitivity"]?.toString()?.let { editor.putString("flutter.ambient_capture_sensitivity", it) }
        policy["communication_mode"]?.toString()?.let {
            editor.putString("flutter.ambient_capture_communication_mode", it)
        }
        policy["raw_audio_retention"]?.toString()?.let {
            editor.putString("flutter.ambient_capture_raw_audio_retention", it)
        }
        (policy["allow_local_stt_fallback"] as? Boolean)?.let {
            editor.putBoolean("flutter.ambient_capture_local_stt_fallback_enabled", it)
        }
        if ((policy["allow_accessibility_mode"] as? Boolean) == true &&
            !prefs.getBoolean("flutter.ambient_capture_accessibility_mode_enabled", false)
        ) {
            AmbientCaptureAudit.record(this, "accessibility_request_clamped_by_local_setting")
        }
        if ((policy["allow_caption_fallback"] as? Boolean) == true &&
            !prefs.getBoolean("flutter.ambient_capture_caption_fallback_enabled", false)
        ) {
            AmbientCaptureAudit.record(this, "accessibility_request_clamped_by_local_setting")
        }
        (policy["allow_audio_upload"] as? Boolean)?.let {
            if (prefs.getBoolean("flutter.ambient_capture_raw_audio_upload_enabled", false)) {
                editor.putBoolean("flutter.ambient_capture_raw_audio_upload_enabled", it)
            }
        }
        editor.apply()
    }

    companion object {
        const val ACTION_START = "com.friend.ios.ambient.START"
        const val ACTION_STOP = "com.friend.ios.ambient.STOP"
        const val ACTION_PAUSE = "com.friend.ios.ambient.PAUSE"
        const val ACTION_RESUME = "com.friend.ios.ambient.RESUME"
        const val ACTION_PRIVATE_MODE = "com.friend.ios.ambient.PRIVATE_MODE"
        private const val CHANNEL_ID = "ambient_capture"
        private const val NOTIFICATION_ID = 44072
        private const val EXTRA_LOCAL_MANUAL_OVERRIDE = "localManualOverride"

        private const val TAG = "AmbientCapture"
        private const val POLICY_ACTIVE_INTERVAL_MS = 60_000L
        private const val POLICY_IDLE_INTERVAL_MS = 5L * 60L * 1000L
        private var instance: AmbientCaptureForegroundService? = null
        private var isRunning = false
        private var isPaused = false
        private var privateMode = false
        private var lastHealth: Map<String, Any?> = mapOf("state" to AmbientHealthState.UNKNOWN_DEGRADED.name)

        fun start(context: Context, localManualOverride: Boolean = true) {
            val intent = Intent(context, AmbientCaptureForegroundService::class.java)
                .setAction(ACTION_START)
                .putExtra(EXTRA_LOCAL_MANUAL_OVERRIDE, localManualOverride)
            ContextCompat.startForegroundService(context, intent)
        }

        fun stop(context: Context) = command(context, ACTION_STOP)

        fun command(context: Context, action: String) {
            val service = instance
            if (service == null || !isRunning) {
                Log.i(TAG, "Ignoring ambient command while service is not running: $action")
                return
            }
            service.onStartCommand(Intent(context, AmbientCaptureForegroundService::class.java).setAction(action), 0, 0)
        }

        fun updateFlutterState(socketConnected: Boolean?, networkAvailable: Boolean?, walQueueDepth: Int?) {
            instance?.healthMonitor?.updateFlutterState(socketConnected, networkAvailable, walQueueDepth)
        }

        fun onFlutterAudioListenerChanged(active: Boolean) {
            if (!active && isRunning) instance?.healthMonitor?.setNoFlutterListener()
        }

        fun applyPolicyConfig(config: Map<*, *>) {
            instance?.healthMonitor?.applyPolicy(config.entries.associate { it.key.toString() to it.value })
        }

        fun listSpoolFiles(context: Context): List<Map<String, Any?>> = AmbientSpoolStore(context).listMetadata()

        fun spoolStats(context: Context): Map<String, Any?> = AmbientSpoolStore(context).stats()

        fun markSpoolFiles(context: Context, paths: List<String>, status: String) {
            AmbientSpoolStore(context).markStatus(paths, status)
        }

        fun deleteSpoolFiles(context: Context, status: String?) {
            AmbientSpoolStore(context).deleteByStatus(status)
        }

        fun statusMap(): Map<String, Any?> = mapOf(
            "running" to isRunning,
            "paused" to isPaused,
            "privateMode" to privateMode,
        )

        fun healthMap(): Map<String, Any?> = lastHealth
    }
}
