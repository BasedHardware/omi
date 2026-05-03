package com.omi.ambientcompanion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioPlaybackCaptureConfiguration
import android.media.AudioRecord
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

class MediaProjectionSessionService : Service() {
    private val running = AtomicBoolean(false)
    private var recorder: AudioRecord? = null
    private var projection: MediaProjection? = null
    private lateinit var spoolStore: CaptureSpoolStore
    private lateinit var audit: AuditLog

    override fun onCreate() {
        super.onCreate()
        spoolStore = CaptureSpoolStore(this)
        audit = AuditLog(this)
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        createChannel()
        when (intent?.action) {
            ACTION_STOP -> stopProjection()
            else -> startProjection(intent)
        }
        return START_STICKY
    }

    override fun onDestroy() {
        stopProjection()
        super.onDestroy()
    }

    private fun startProjection(intent: Intent?) {
        if (running.get()) return
        val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, 0) ?: 0
        val resultData = intent?.getParcelableExtra<Intent>(EXTRA_RESULT_DATA)
        if (resultCode == 0 || resultData == null) {
            audit.record("media_projection_missing_grant")
            stopSelf()
            return
        }
        startForeground(NOTIFICATION_ID, notification("Capturing permitted screen audio"))
        val manager = getSystemService(MediaProjectionManager::class.java)
        projection = manager.getMediaProjection(resultCode, resultData)
        val localProjection = projection ?: run {
            audit.record("media_projection_unavailable")
            stopSelf()
            return
        }
        running.set(true)
        spoolStore.startSession()
        audit.record("media_projection_started")
        thread(name = "ambient-media-projection-audio") { captureLoop(localProjection) }
    }

    private fun captureLoop(mediaProjection: MediaProjection) {
        val config = AudioPlaybackCaptureConfiguration.Builder(mediaProjection)
            .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
            .addMatchingUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
            .addMatchingUsage(AudioAttributes.USAGE_GAME)
            .build()
        val format = AudioFormat.Builder()
            .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
            .setSampleRate(SAMPLE_RATE)
            .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
            .build()
        val minBuffer = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val bufferSize = maxOf(minBuffer, 4096)
        recorder = AudioRecord.Builder()
            .setAudioPlaybackCaptureConfig(config)
            .setAudioFormat(format)
            .setBufferSizeInBytes(bufferSize)
            .build()
        val localRecorder = recorder ?: return
        try {
            localRecorder.startRecording()
        } catch (e: Throwable) {
            audit.record("media_projection_audio_start_failed", mapOf("error" to e.javaClass.simpleName))
            stopProjection()
            return
        }
        val buffer = ByteArray(1920)
        while (running.get()) {
            val read = localRecorder.read(buffer, 0, buffer.size)
            if (read > 0) {
                val write = spoolStore.writeChunk(buffer.copyOf(read))
                if (!write.ok) {
                    audit.record("media_projection_storage_limit", mapOf("reason" to write.reason))
                    stopProjection()
                    break
                }
            } else {
                Thread.sleep(50)
            }
        }
    }

    private fun stopProjection() {
        if (!running.getAndSet(false)) {
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return
        }
        runCatching { recorder?.stop() }
        runCatching { recorder?.release() }
        recorder = null
        runCatching { projection?.stop() }
        projection = null
        spoolStore.closeSession("pending")
        audit.record("media_projection_stopped")
        LocalSttWorker(applicationContext).drainSpoolForLocalTranscripts()
        SyncWorker.drainAsync(applicationContext)
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            getSystemService(NotificationManager::class.java)
                .createNotificationChannel(NotificationChannel(CHANNEL_ID, "Omi Ambient Projection", NotificationManager.IMPORTANCE_LOW))
        }
    }

    private fun notification(text: String): Notification {
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) Notification.Builder(this, CHANNEL_ID) else Notification.Builder(this)
        return builder
            .setContentTitle("Omi Ambient Companion")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.presence_audio_online)
            .setOngoing(true)
            .addAction(Notification.Action.Builder(0, "Stop", stopIntent()).build())
            .build()
    }

    private fun stopIntent(): PendingIntent {
        return PendingIntent.getService(
            this,
            88,
            Intent(this, MediaProjectionSessionService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
    }

    companion object {
        private const val SAMPLE_RATE = 16_000
        private const val CHANNEL_ID = "omi_ambient_projection"
        private const val NOTIFICATION_ID = 66042
        private const val EXTRA_RESULT_CODE = "result_code"
        private const val EXTRA_RESULT_DATA = "result_data"
        private const val ACTION_STOP = "com.omi.ambientcompanion.PROJECTION_STOP"

        fun start(context: Context, resultCode: Int, resultData: Intent) {
            val intent = Intent(context, MediaProjectionSessionService::class.java)
                .putExtra(EXTRA_RESULT_CODE, resultCode)
                .putExtra(EXTRA_RESULT_DATA, resultData)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) context.startForegroundService(intent) else context.startService(intent)
        }

        fun stop(context: Context) {
            context.startService(Intent(context, MediaProjectionSessionService::class.java).setAction(ACTION_STOP))
        }
    }
}
