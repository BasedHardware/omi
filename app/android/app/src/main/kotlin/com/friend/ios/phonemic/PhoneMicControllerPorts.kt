package com.friend.ios.phonemic

/**
 * Narrow execution/environment ports for the phone-mic controller policy
 * (SCA-491 / C5).
 *
 * The controller owns every capture lifecycle decision; these interfaces are
 * the only Android surface it touches. The production wiring
 * ([PhoneMicControllerPorts.production]) lives at the bottom of this file and
 * compiles everywhere the app compiles; the JVM replay test
 * (PhoneMicLifecycleReplayTest) injects fakes and replays the canonical
 * `phone-mic-native-events/v1` vectors through the PRODUCTION controller with
 * a virtual main loop — only OS audio/radio I/O is faked, never policy.
 *
 * No policy lives in this file: signatures and production adapters only.
 */

/** Everything the controller emits toward Dart. */
interface PhoneMicEventSink {
    fun onAudioFrame(pcm16leMono16k: ByteArray, sessionId: Long)

    fun onStateChanged(state: PhoneMicCaptureState, sessionId: Long)

    fun onCaptureError(code: String, message: String, sessionId: Long)

    fun onBatchProgress(capturedSeconds: Double, sessionId: Long)
}

/** The single "main" execution context: posting, delayed posting, uptime. */
interface PhoneMicMainLoop {
    /** Serial, FIFO — same guarantee as the Android main thread. */
    fun post(block: () -> Unit)

    /** Schedule [block] after [delayMs]; cancellable by [token] identity. */
    fun postDelayed(token: Any, delayMs: Long, block: () -> Unit)

    fun cancel(token: Any)

    fun uptimeMillis(): Long

    /** True while executing on the loop itself (Looper.myLooper() parity). */
    val isCurrent: Boolean
}

/** The engine surface the controller drives (one instance per bring-up). */
interface PhoneMicEngineHandle {
    @Throws(Throwable::class)
    fun start()

    fun teardown()

    val audioSessionId: Int
    val lastDataUptimeMs: Long
}

/** Policy-neutral recording-config snapshot (client silencing detection). */
data class PhoneMicRecordingConfig(
    val clientAudioSessionId: Int,
    val clientSilenced: Boolean,
)

/** Batch (Transcribe Later) opus encoder surface. */
interface PhoneMicEncoderHandle {
    fun encode(pcm: ByteArray): List<ByteArray>

    fun discardPartial()

    fun destroy()
}

/** Batch WAL-compatible writer surface. */
interface PhoneMicWriterHandle {
    fun append(packets: List<ByteArray>, marker: String)

    fun closeNow(reason: String)

    val sessionFramesWritten: Long

    fun consumeStorageFullTransition(): Boolean
}

/** Serial task queue for chunk encode/write + close (one thread in production). */
interface PhoneMicTaskQueue {
    fun execute(task: () -> Unit)
}

/** Log level used by [PhoneMicControllerPorts.log]. */
enum class PhoneMicLogLevel { INFO, WARN }

/**
 * Every Android/OS effect the controller depends on. Constructed once per
 * controller; [production] wires the real stack.
 */
class PhoneMicControllerPorts internal constructor(
    val main: PhoneMicMainLoop,
    val audioQueue: PhoneMicTaskQueue,
    val checkRecordAudioPermission: () -> Boolean,
    /** Current AudioManager mode int (compare with AudioManager.MODE_* constants). */
    val audioMode: () -> Int,
    val activeRecordingConfigs: () -> List<PhoneMicRecordingConfig>,
    /** Register (non-null) / unregister (null) the recording-config listener. */
    val setRecordingConfigListener: (((List<PhoneMicRecordingConfig>) -> Unit)?) -> Unit,
    val startForegroundService: () -> Boolean,
    val stopForegroundService: () -> Unit,
    val makeEngine: (onChunk: (ByteArray) -> Unit, onReadError: (Int) -> Unit) -> PhoneMicEngineHandle,
    val batchDirectory: () -> String?,
    val batchAutoMarker: () -> Boolean,
    val makeEncoder: () -> PhoneMicEncoderHandle?,
    val makeWriter: (directory: String) -> PhoneMicWriterHandle,
    val log: (level: PhoneMicLogLevel, tag: String, message: String, error: Throwable?) -> Unit,
) {
    companion object {
        /** The real Android stack: Handler main loop, AudioRecord engines, mic FGS. */
        fun production(application: android.app.Application): PhoneMicControllerPorts {
            val mainHandler = android.os.Handler(android.os.Looper.getMainLooper())
            val main = object : PhoneMicMainLoop {
                override fun post(block: () -> Unit) {
                    mainHandler.post(block)
                }

                override fun postDelayed(token: Any, delayMs: Long, block: () -> Unit) {
                    mainHandler.postDelayed(Runnable(block), delayMs)
                }

                override fun cancel(token: Any) {
                    if (token is Runnable) mainHandler.removeCallbacks(token)
                }

                override fun uptimeMillis(): Long = android.os.SystemClock.uptimeMillis()

                override val isCurrent: Boolean
                    get() = android.os.Looper.myLooper() == android.os.Looper.getMainLooper()
            }
            val audioManager =
                application.getSystemService(android.content.Context.AUDIO_SERVICE) as android.media.AudioManager
            var registeredCallback: android.media.AudioManager.AudioRecordingCallback? = null

            fun toSnapshot(config: android.media.AudioRecordingConfiguration) =
                PhoneMicRecordingConfig(config.clientAudioSessionId, config.isClientSilenced)

            return PhoneMicControllerPorts(
                main = main,
                audioQueue = object : PhoneMicTaskQueue {
                    private val executor = java.util.concurrent.Executors.newSingleThreadExecutor { runnable ->
                        Thread(runnable, "PhoneMicAudio")
                    }

                    override fun execute(task: () -> Unit) {
                        executor.execute(task)
                    }
                },
                checkRecordAudioPermission = {
                    androidx.core.content.ContextCompat.checkSelfPermission(
                        application,
                        android.Manifest.permission.RECORD_AUDIO,
                    ) == android.content.pm.PackageManager.PERMISSION_GRANTED
                },
                audioMode = { audioManager.mode },
                activeRecordingConfigs = { audioManager.activeRecordingConfigurations.map(::toSnapshot) },
                setRecordingConfigListener = { listener ->
                    registeredCallback?.let { audioManager.unregisterAudioRecordingCallback(it) }
                    registeredCallback = null
                    if (listener != null) {
                        val callback = object : android.media.AudioManager.AudioRecordingCallback() {
                            override fun onRecordingConfigChanged(configs: MutableList<android.media.AudioRecordingConfiguration>) {
                                listener(configs.map(::toSnapshot))
                            }
                        }
                        audioManager.registerAudioRecordingCallback(callback, mainHandler)
                        registeredCallback = callback
                    }
                },
                startForegroundService = { PhoneMicForegroundService.start(application) },
                stopForegroundService = { PhoneMicForegroundService.stop(application) },
                makeEngine = { onChunk, onReadError ->
                    val engine = PhoneMicCaptureEngine(onChunk = onChunk, onReadError = onReadError)
                    object : PhoneMicEngineHandle {
                        override fun start() = engine.start()

                        override fun teardown() = engine.teardown()

                        override val audioSessionId: Int
                            get() = engine.audioSessionId

                        override val lastDataUptimeMs: Long
                            get() = engine.lastDataUptimeMs
                    }
                },
                batchDirectory = {
                    val prefs = application.getSharedPreferences("FlutterSharedPreferences", android.content.Context.MODE_PRIVATE)
                    prefs.getString("flutter.batchAudioDir", null)?.takeIf { it.isNotEmpty() }
                },
                batchAutoMarker = {
                    application
                        .getSharedPreferences("FlutterSharedPreferences", android.content.Context.MODE_PRIVATE)
                        .getBoolean("flutter.phoneBatchAuto", false)
                },
                makeEncoder = { PhoneMicOpusEncoder.create()?.let(::OpusEncoderAdapter) },
                makeWriter = { directory -> WriterAdapter(PhoneMicBatchAudioWriter(application, directory)) },
                log = { level, tag, message, error ->
                    when (level) {
                        PhoneMicLogLevel.INFO -> android.util.Log.i(tag, message, error)
                        PhoneMicLogLevel.WARN -> android.util.Log.w(tag, message, error)
                    }
                },
            )
        }
    }
}

private class OpusEncoderAdapter(private val encoder: PhoneMicOpusEncoder) : PhoneMicEncoderHandle {
    override fun encode(pcm: ByteArray): List<ByteArray> = encoder.encode(pcm)

    override fun discardPartial() = encoder.discardPartial()

    override fun destroy() = encoder.destroy()
}

private class WriterAdapter(private val writer: PhoneMicBatchAudioWriter) : PhoneMicWriterHandle {
    override fun append(packets: List<ByteArray>, marker: String) = writer.append(packets, marker)

    override fun closeNow(reason: String) = writer.closeNow(reason)

    override val sessionFramesWritten: Long
        get() = writer.sessionFramesWritten

    override fun consumeStorageFullTransition(): Boolean = writer.consumeStorageFullTransition()
}

/** Adapts the Pigeon [PhoneMicFlutterApi] onto [PhoneMicEventSink]. */
class PhoneMicFlutterApiEventSink(private val api: PhoneMicFlutterApi) : PhoneMicEventSink {
    override fun onAudioFrame(pcm16leMono16k: ByteArray, sessionId: Long) {
        api.onAudioFrame(pcm16leMono16k, sessionId) {}
    }

    override fun onStateChanged(state: PhoneMicCaptureState, sessionId: Long) {
        api.onStateChanged(state, sessionId) {}
    }

    override fun onCaptureError(code: String, message: String, sessionId: Long) {
        api.onCaptureError(code, message, sessionId) {}
    }

    override fun onBatchProgress(capturedSeconds: Double, sessionId: Long) {
        api.onBatchProgress(capturedSeconds, sessionId) {}
    }
}
