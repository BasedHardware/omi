package com.omi.ambientcompanion

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import java.time.Instant
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

class AmbientForegroundMicService : Service() {
    private lateinit var spoolStore: CaptureSpoolStore
    private lateinit var sessionStore: CaptureSessionStore
    private lateinit var audit: AuditLog
    private lateinit var pluginClient: PluginClient
    private lateinit var communicationMonitor: CommunicationStateMonitor
    private lateinit var prefs: AppPrefs
    private var recorder: AudioRecord? = null
    private var captureThread: Thread? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private val capturing = AtomicBoolean(false)
    private val paused = AtomicBoolean(false)
    private val privateMode = AtomicBoolean(false)
    private var vad = VadWatchEngine()
    private var lastHealth = HealthEvent(AmbientHealthState.IDLE_CONTEXT_WATCH, "created")
    private var speechSessionActive = false
    private var lastAudioAt = 0L
    private val mainHandler = Handler(Looper.getMainLooper())
    private var policyLoop: Runnable? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
        prefs = AppPrefs(this)
        spoolStore = CaptureSpoolStore(this)
        sessionStore = CaptureSessionStore(this)
        audit = AuditLog(this)
        pluginClient = PluginClient(this)
        communicationMonitor = CommunicationStateMonitor(this) { health -> updateHealth(health) }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action ?: ACTION_START) {
            ACTION_START -> startCapture(intent?.getStringExtra(EXTRA_REASON) ?: "manual")
            ACTION_PAUSE -> pauseCapture()
            ACTION_RESUME -> resumeCapture()
            ACTION_STOP -> stopCapture(stopSelf = true)
            ACTION_PRIVATE -> enterPrivateMode()
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        stopCapture(stopSelf = false)
        super.onDestroy()
    }

    private fun startCapture(reason: String) {
        if (capturing.get()) return
        configureVadFromPrefs()
        startForeground(NOTIFICATION_ID, buildNotification("VAD watch"))
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            updateHealth(HealthEvent(AmbientHealthState.PERMISSION_MISSING, "record_audio_missing"))
            return
        }
        prefs.explicitSessionStarted = true
        sessionStore.start(reason)
        ContextSignals.lastTriggerReason = reason
        paused.set(false)
        privateMode.set(false)
        capturing.set(true)
        updateHealth(HealthEvent(AmbientHealthState.VAD_WATCH, reason, ContextSignals.foregroundPackage))
        communicationMonitor.start()
        startPolicyLoop()
        captureThread = thread(name = "ambient-vad-capture") { captureLoop() }
        audit.record("capture_started", mapOf("reason" to reason))
        pluginClient.sendTelemetry("capture_started", lastHealth, ContextSignals.snapshot())
    }

    private fun captureLoop() {
        val minBuffer = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT)
        val frameBytes = 960 // 30 ms @ 16 kHz mono PCM16
        val bufferBytes = maxOf(minBuffer, frameBytes * 4)
        recorder = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            SAMPLE_RATE,
            CHANNEL_CONFIG,
            AUDIO_FORMAT,
            bufferBytes,
        )
        val localRecorder = recorder ?: return
        try {
            localRecorder.startRecording()
        } catch (e: Throwable) {
            updateHealth(HealthEvent(AmbientHealthState.RECOVERY_NEEDED, "audio_record_start_failed:${e.javaClass.simpleName}"))
            return
        }
        val buffer = ByteArray(frameBytes)
        while (capturing.get()) {
            if (paused.get() || privateMode.get()) {
                Thread.sleep(250)
                continue
            }
            val read = localRecorder.read(buffer, 0, buffer.size)
            if (read <= 0) {
                updateHealth(HealthEvent(AmbientHealthState.RECOVERY_NEEDED, "audio_read_$read", ContextSignals.foregroundPackage))
                Thread.sleep(50)
                continue
            }
            lastAudioAt = System.currentTimeMillis()
            val chunk = buffer.copyOf(read)
            val result = vad.accept(chunk)
            communicationMonitor.evaluate()
            if (!speechSessionActive && vad.activeSpeech) {
                speechSessionActive = true
                acquireWakeLock()
                spoolStore.startSession()
                vad.drainPreRoll().forEach { spoolStore.writeChunk(it) }
                updateHealth(HealthEvent(AmbientHealthState.SPEECH_DETECTED, "vad_triggered", ContextSignals.foregroundPackage, result.dbfs, result.zeroRatio))
                updateNotification("Speech detected")
                pluginClient.sendTelemetry("speech_detected", lastHealth, ContextSignals.snapshot())
            }
            if (speechSessionActive) {
                val write = spoolStore.writeChunk(chunk)
                if (!write.ok) {
                    updateHealth(HealthEvent(AmbientHealthState.STORAGE_LIMIT_REACHED, write.reason, ContextSignals.foregroundPackage))
                    pauseCapture()
                } else if (result.speech) {
                    updateHealth(HealthEvent(AmbientHealthState.AUDIO_OK, "speech_audio", ContextSignals.foregroundPackage, result.dbfs, result.zeroRatio))
                }
            }
            if (speechSessionActive && !vad.activeSpeech) {
                speechSessionActive = false
                spoolStore.closeSession()
                releaseWakeLock()
                updateHealth(HealthEvent(AmbientHealthState.VAD_WATCH, "silence_timeout", ContextSignals.foregroundPackage, result.dbfs, result.zeroRatio))
                updateNotification("VAD watch")
                LocalSttWorker(applicationContext).drainSpoolForLocalTranscripts()
                SyncWorker.drainAsync(applicationContext)
            }
            if (System.currentTimeMillis() - lastAudioAt > 30_000) {
                updateHealth(HealthEvent(AmbientHealthState.RECOVERY_NEEDED, "no_audio_chunks_received"))
            }
        }
        runCatching { localRecorder.stop() }
        localRecorder.release()
    }

    private fun pauseCapture() {
        paused.set(true)
        sessionStore.update("paused", AmbientHealthState.VAD_WATCH)
        if (speechSessionActive) spoolStore.closeSession()
        speechSessionActive = false
        releaseWakeLock()
        updateHealth(HealthEvent(AmbientHealthState.VAD_WATCH, "paused"))
        updateNotification("Paused")
        audit.record("capture_paused")
        pluginClient.sendTelemetry("capture_paused", lastHealth)
    }

    private fun resumeCapture() {
        paused.set(false)
        privateMode.set(false)
        sessionStore.update("running", AmbientHealthState.VAD_WATCH)
        updateHealth(HealthEvent(AmbientHealthState.VAD_WATCH, "resumed"))
        updateNotification("VAD watch")
        audit.record("capture_resumed")
        pluginClient.sendTelemetry("capture_resumed", lastHealth)
    }

    private fun enterPrivateMode() {
        privateMode.set(true)
        paused.set(true)
        sessionStore.finish("private")
        if (speechSessionActive) spoolStore.closeSession("private")
        speechSessionActive = false
        releaseWakeLock()
        updateHealth(HealthEvent(AmbientHealthState.PRIVATE_MODE, "private_mode"))
        updateNotification("Private mode")
        audit.record("private_mode_enabled")
        pluginClient.sendTelemetry("private_mode_enabled", lastHealth)
    }

    private fun stopCapture(stopSelf: Boolean) {
        if (!capturing.getAndSet(false)) {
            if (stopSelf) stopSelf()
            return
        }
        if (speechSessionActive) spoolStore.closeSession()
        speechSessionActive = false
        releaseWakeLock()
        communicationMonitor.stop()
        stopPolicyLoop()
        recorder = null
        sessionStore.finish("stopped")
        updateHealth(HealthEvent(AmbientHealthState.IDLE_CONTEXT_WATCH, "stopped"))
        audit.record("capture_stopped")
        pluginClient.sendTelemetry("capture_stopped", lastHealth)
        SyncWorker.drainAsync(applicationContext)
        stopForeground(STOP_FOREGROUND_REMOVE)
        if (stopSelf) stopSelf()
    }

    private fun startPolicyLoop() {
        policyLoop?.let { mainHandler.removeCallbacks(it) }
        policyLoop = Runnable {
            val result = pluginClient.fetchPolicy()
            if (result.accepted) {
                configureVadFromPrefs()
                audit.record("policy_applied")
            } else {
                audit.record("policy_rejected", mapOf("reason" to result.reason))
                pluginClient.sendTelemetry("policy_rejected", lastHealth, org.json.JSONObject().put("reason", result.reason))
            }
            policyLoop?.let { mainHandler.postDelayed(it, 60_000) }
        }
        policyLoop?.run()
    }

    private fun stopPolicyLoop() {
        policyLoop?.let { mainHandler.removeCallbacks(it) }
        policyLoop = null
    }

    private fun configureVadFromPrefs() {
        vad = VadWatchEngine(
            rmsSpeechDbfsThreshold = prefs.rmsSilenceDbfsThreshold.toDouble(),
            zeroRatioSilenceThreshold = prefs.zeroFrameThreshold.toDouble(),
            silenceFramesToEnd = (prefs.silenceDetectionSeconds * 1000 / 30).coerceAtLeast(10),
        )
    }

    private fun updateHealth(event: HealthEvent) {
        lastHealth = event
        lastState = event.state
        DiagnosticsStore(this).write("health:${event.state.name}")
        if (event.state == AmbientHealthState.AUDIO_SILENCED_BY_SYSTEM ||
            event.state == AmbientHealthState.COMMUNICATION_MODE_DEGRADED
        ) {
            FallbackSegmentQueue(this).enqueue(
                FallbackSegment(
                    text = "[${event.reason}]",
                    source = FallbackSource.GAP_MARKER,
                    start = Instant.now(),
                    end = Instant.now(),
                    healthState = event.state,
                    rawAudioAvailable = false,
                    foregroundApp = ContextSignals.foregroundPackage,
                )
            )
        }
        sendBroadcast(Intent(ACTION_HEALTH_CHANGED).putExtra("health", event.toJson().toString()))
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        wakeLock = (getSystemService(POWER_SERVICE) as PowerManager)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "OmiAmbient:activeCapture")
            .apply { acquire(10 * 60 * 1000L) }
    }

    private fun releaseWakeLock() {
        runCatching { if (wakeLock?.isHeld == true) wakeLock?.release() }
        wakeLock = null
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Omi Ambient Companion", NotificationManager.IMPORTANCE_LOW)
        )
    }

    private fun updateNotification(status: String) {
        (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(NOTIFICATION_ID, buildNotification(status))
    }

    private fun buildNotification(status: String): Notification {
        val open = PendingIntent.getActivity(
            this,
            10,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) Notification.Builder(this, CHANNEL_ID) else Notification.Builder(this)
        return builder
            .setContentTitle("Omi Ambient Companion")
            .setContentText(status)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setOngoing(true)
            .setContentIntent(open)
            .addAction(Notification.Action.Builder(0, "Pause", serviceIntent(ACTION_PAUSE, 1)).build())
            .addAction(Notification.Action.Builder(0, "Resume", serviceIntent(ACTION_RESUME, 2)).build())
            .addAction(Notification.Action.Builder(0, "Stop", serviceIntent(ACTION_STOP, 3)).build())
            .addAction(Notification.Action.Builder(0, "Private", serviceIntent(ACTION_PRIVATE, 4)).build())
            .build()
    }

    private fun serviceIntent(action: String, requestCode: Int): PendingIntent {
        val intent = Intent(this, AmbientForegroundMicService::class.java).setAction(action)
        return PendingIntent.getService(this, requestCode, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }

    companion object {
        private const val SAMPLE_RATE = 16_000
        private const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
        private const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
        private const val CHANNEL_ID = "omi_ambient_companion"
        private const val NOTIFICATION_ID = 55042
        const val ACTION_HEALTH_CHANGED = "com.omi.ambientcompanion.HEALTH_CHANGED"
        const val ACTION_START = "com.omi.ambientcompanion.START"
        const val ACTION_PAUSE = "com.omi.ambientcompanion.PAUSE"
        const val ACTION_RESUME = "com.omi.ambientcompanion.RESUME"
        const val ACTION_STOP = "com.omi.ambientcompanion.STOP"
        const val ACTION_PRIVATE = "com.omi.ambientcompanion.PRIVATE"
        private const val EXTRA_REASON = "reason"
        @Volatile private var lastState: AmbientHealthState = AmbientHealthState.IDLE_CONTEXT_WATCH

        fun start(context: Context, reason: String = "manual") {
            val intent = Intent(context, AmbientForegroundMicService::class.java)
                .setAction(ACTION_START)
                .putExtra(EXTRA_REASON, reason)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) context.startForegroundService(intent) else context.startService(intent)
        }

        fun command(context: Context, action: String) {
            context.startService(Intent(context, AmbientForegroundMicService::class.java).setAction(action))
        }

        fun lastHealthState(): AmbientHealthState = lastState
    }
}
