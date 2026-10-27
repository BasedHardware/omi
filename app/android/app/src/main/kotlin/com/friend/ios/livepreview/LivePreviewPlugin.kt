package com.friend.ios.livepreview

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.speech.RecognitionPart
import android.speech.RecognitionListener
import android.speech.RecognitionSupport
import android.speech.RecognitionSupportCallback
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import androidx.annotation.RequiresApi
import androidx.core.content.ContextCompat
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.OutputStream
import java.util.Locale
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger

/**
 * On-device live transcript preview for local-preview listen sessions.
 *
 * Display only: Dart feeds a decoded COPY of capture audio (16 kHz mono PCM16)
 * and receives provisional text. Nothing here stores, uploads or owns audio,
 * downloads a model, prompts for a permission or uses a cloud recognizer.
 * Separate from the single-flight on-device overflow work on purpose.
 *
 * Channels: `com.omi/live_preview` (start/feed/stop) and
 * `com.omi/live_preview/events` ({segmentId, text, isFinal}). All recognizer
 * calls run on the main looper, as SpeechRecognizer requires; PCM is written
 * to the recognizer's pipe on one background thread with a bounded queue, so
 * the capture path is never blocked and overload drops preview audio.
 */
class LivePreviewPlugin private constructor(private val context: Context) :
    MethodChannel.MethodCallHandler, EventChannel.StreamHandler {

    companion object {
        private const val TAG = "OmiLivePreview"
        private const val SUPPORT_TIMEOUT_MS = 3_000L

        fun register(context: Context, engine: FlutterEngine) {
            val plugin = LivePreviewPlugin(context.applicationContext)
            val messenger = engine.dartExecutor.binaryMessenger
            MethodChannel(messenger, "com.omi/live_preview").setMethodCallHandler(plugin)
            EventChannel(messenger, "com.omi/live_preview/events").setStreamHandler(plugin)
        }
    }

    private val main = Handler(Looper.getMainLooper())
    private var sink: EventChannel.EventSink? = null
    private var session: OnDeviceSession? = null
    private var generation = 0

    override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
        sink = events
    }

    override fun onCancel(arguments: Any?) {
        sink = null
    }

    private fun emit(mine: Int, segmentId: String, text: String, isFinal: Boolean, spans: List<Map<String, Any>>) {
        main.post {
            if (mine != generation) return@post
            sink?.success(mapOf("segmentId" to "$mine:$segmentId", "text" to text, "isFinal" to isFinal,
                "startMs" to spans.firstOrNull()?.get("startMs"),
                "endMs" to spans.lastOrNull()?.get("endMs"), "spans" to spans))
        }
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "start" -> {
                generation++
                session?.stop()
                session = null
                val exclude = call.argument<List<String>>("exclude").orEmpty()
                if ("android_on_device" in exclude) {
                    // Failed at runtime earlier in this session; Dart tries the next engine.
                    result.success(LivePreviewPolicy.none("engine_error"))
                } else {
                    start(call.argument<String>("language") ?: "multi", generation, result)
                }
            }
            "feed" -> {
                val pcm = call.argument<ByteArray>("pcm")
                val startMs = call.argument<Number>("startMs")?.toLong()
                result.success(pcm?.let { session?.offer(it, startMs) } ?: false)
            }
            "stop" -> {
                generation++
                session?.stop()
                session = null
                result.success(null)
            }
            else -> result.notImplemented()
        }
    }

    /** A running session gave up: tell Dart (closed reason) and release it. */
    private fun runtimeFailure(failed: Int) {
        main.post {
            if (failed != generation || session == null) return@post
            Log.w(TAG, "runtime failure engine=android_on_device")
            session?.stop()
            session = null
            sink?.success(mapOf("failure" to "engine_error", "engine" to "android_on_device"))
        }
    }

    private fun start(language: String, mine: Int, result: MethodChannel.Result) {
        val refused = LivePreviewPolicy.preflight(
            Build.VERSION.SDK_INT,
            ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED,
        ) { SpeechRecognizer.isOnDeviceRecognitionAvailable(context) }
        if (refused != null || Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            result.success(LivePreviewPolicy.none(refused ?: "os_too_old"))
            return
        }
        val recognizer = try {
            SpeechRecognizer.createOnDeviceSpeechRecognizer(context)
        } catch (error: Exception) {
            Log.w(TAG, "on-device recognizer unavailable: ${error.javaClass.simpleName}")
            result.success(LivePreviewPolicy.none("os_engine_unavailable"))
            return
        }
        val device = Locale.getDefault()
        val code = LivePreviewPolicy.languageCode(language, device.language)
        var answered = false
        fun answer(value: Map<String, Any>, keep: OnDeviceSession?) {
            if (answered) return
            answered = true
            if (mine != generation) {
                keep?.stop() ?: runCatching { recognizer.destroy() }
                result.success(LivePreviewPolicy.none("engine_error"))
                return
            }
            if (keep == null) runCatching { recognizer.destroy() }
            session = keep
            Log.i(TAG, "engine=${value["engine"]} reason=${value["reason"]}")
            result.success(value)
        }
        main.postDelayed({ answer(LivePreviewPolicy.none("engine_error"), null) }, SUPPORT_TIMEOUT_MS)
        try {
            // Installed-language check only; never triggerModelDownload.
            recognizer.checkRecognitionSupport(
                OnDeviceSession.baseIntent(code),
                ContextCompat.getMainExecutor(context),
                object : RecognitionSupportCallback {
                    override fun onSupportResult(support: RecognitionSupport) {
                        if (answered) return // Timed out already; nothing may start now.
                        val pick = LivePreviewPolicy.pickLanguage(
                            code,
                            support.installedOnDeviceLanguages,
                            support.pendingOnDeviceLanguages,
                            support.supportedOnDeviceLanguages,
                            device.toLanguageTag(),
                        )
                        val tag = pick.tag
                        if (tag == null) {
                            answer(LivePreviewPolicy.none(pick.reason), null)
                            return
                        }
                        val candidate = OnDeviceSession(recognizer, tag, { id, text, isFinal, spans -> emit(mine, id, text, isFinal, spans) }) { runtimeFailure(mine) }
                        val started = try {
                            candidate.also { it.begin() }
                        } catch (error: Exception) {
                            // begin() already closed both pipe ends; release the rest.
                            Log.w(TAG, "on-device session failed: ${error.javaClass.simpleName}")
                            candidate.stop()
                            null
                        }
                        answer(started?.let { LivePreviewPolicy.running() } ?: LivePreviewPolicy.none("engine_error"), started)
                    }

                    override fun onError(error: Int) {
                        Log.w(TAG, "recognition support check failed: $error")
                        answer(LivePreviewPolicy.none("os_engine_unavailable"), null)
                    }
                },
            )
        } catch (error: Exception) {
            Log.w(TAG, "recognition support check threw: ${error.javaClass.simpleName}")
            answer(LivePreviewPolicy.none("engine_error"), null)
        }
    }
}

/**
 * One segmented on-device session fed through a pipe (EXTRA_AUDIO_SOURCE),
 * reopened when the recognizer ends or fails, with a bounded restart rate.
 */
@RequiresApi(Build.VERSION_CODES.TIRAMISU)
private class OnDeviceSession(
    private val recognizer: SpeechRecognizer,
    private val languageTag: String,
    private val emit: (String, String, Boolean, List<Map<String, Any>>) -> Unit,
    private val onFailure: () -> Unit,
) {
    companion object {
        private const val TAG = "OmiLivePreview"
        private const val MAX_QUEUED_CHUNKS = 16
        private const val RESTART_DELAY_MS = 1_000L
        private const val MAX_RESTARTS_PER_MINUTE = 6

        fun baseIntent(language: String): Intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, language)
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
        }
    }

    private val main = Handler(Looper.getMainLooper())
    private val writer: ExecutorService = Executors.newSingleThreadExecutor { Thread(it, "omi-live-preview-pcm") }
    private val queued = AtomicInteger(0)
    private val ids = LivePreviewSegmentIds("g")
    private val restarts = ArrayDeque<Long>()

    @Volatile private var output: OutputStream? = null
    @Volatile private var stopped = false
    private var restartPending = false
    private var audioOriginMs: Long? = null

    private val listener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {}
        override fun onBeginningOfSpeech() {}
        override fun onRmsChanged(rmsdB: Float) {}
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() {}
        override fun onEvent(eventType: Int, params: Bundle?) {}

        override fun onPartialResults(partialResults: Bundle?) {
            text(partialResults)?.let { emit(ids.current, it, false, timedParts(partialResults)) }
        }

        override fun onSegmentResults(segmentResults: Bundle) {
            text(segmentResults)?.let { emit(ids.id(isFinal = true), it, true, timedParts(segmentResults)) }
        }

        override fun onResults(results: Bundle?) {
            text(results)?.let { emit(ids.id(isFinal = true), it, true, timedParts(results)) }
            restartLater(counted = false)
        }

        override fun onEndOfSegmentedSession() = restartLater(counted = false)

        override fun onError(error: Int) {
            Log.w(TAG, "on-device recognizer error $error")
            restartLater(counted = LivePreviewPolicy.isRuntimeFailure(error))
        }
    }

    // Android exposes word starts, not word durations. A one-millisecond
    // interval identifies that word; absent/unsupported timing stays unknown.
    private fun timedParts(bundle: Bundle?): List<Map<String, Any>> {
        val origin = audioOriginMs ?: return emptyList()
        if (Build.VERSION.SDK_INT < 34) return emptyList()
        val parts = bundle?.getParcelableArrayList(SpeechRecognizer.RECOGNITION_PARTS, RecognitionPart::class.java)
            ?: return emptyList()
        return LivePreviewPolicy.timedSpans(origin, parts.map { (it.formattedText ?: it.rawText) to it.timestampMillis })
    }

    private fun text(bundle: Bundle?): String? =
        bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()

    /** Main looper only. */
    /** Main looper only. Throws (with both pipe ends closed) when the recognizer cannot start. */
    fun begin() {
        if (stopped) return
        val pipe = ParcelFileDescriptor.createPipe()
        val write = LivePreviewPolicy.startOnPipe(pipe[0], pipe[1]) { read ->
            val intent = baseIntent(languageTag).apply {
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                if (Build.VERSION.SDK_INT >= 34) putExtra(RecognizerIntent.EXTRA_REQUEST_WORD_TIMING, true)
                putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE, read)
                putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_CHANNEL_COUNT, 1)
                putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_ENCODING, AudioFormat.ENCODING_PCM_16BIT)
                putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_SAMPLING_RATE, 16_000)
                // One session for as long as the pipe stays open; results arrive per segment.
                putExtra(RecognizerIntent.EXTRA_SEGMENTED_SESSION, RecognizerIntent.EXTRA_AUDIO_SOURCE)
            }
            recognizer.setRecognitionListener(listener)
            recognizer.startListening(intent)
        }
        audioOriginMs = null
        val previous = output
        output = ParcelFileDescriptor.AutoCloseOutputStream(write)
        previous?.let { stale -> writer.execute { runCatching { stale.close() } } }
    }

    private fun restartLater(counted: Boolean) {
        if (stopped || restartPending) return
        val now = System.currentTimeMillis()
        while (restarts.isNotEmpty() && now - restarts.first() > 60_000) restarts.removeFirst()
        if (counted && restarts.size >= MAX_RESTARTS_PER_MINUTE) {
            Log.w(TAG, "on-device recognizer keeps failing; reporting a runtime failure")
            onFailure()
            return
        }
        if (counted) restarts.addLast(now)
        restartPending = true
        main.postDelayed({
            restartPending = false
            if (stopped) return@postDelayed
            runCatching { recognizer.cancel() }
            runCatching { begin() }.onFailure {
                // A dead recognizer must not look running: Dart falls back.
                Log.w(TAG, "restart failed: ${it.javaClass.simpleName}")
                onFailure()
            }
        }, RESTART_DELAY_MS)
    }

    /** Any thread; never blocks. False when the chunk was dropped. */
    fun offer(pcm: ByteArray, startedAtMs: Long?): Boolean {
        if (stopped || queued.get() >= MAX_QUEUED_CHUNKS) return false
        if (audioOriginMs == null) audioOriginMs = startedAtMs ?: (System.currentTimeMillis() - pcm.size / 32)
        queued.incrementAndGet()
        writer.execute {
            try {
                output?.write(pcm)
            } catch (error: Exception) {
                // The recognizer closed its end; restartLater reopens the pipe.
            } finally {
                queued.decrementAndGet()
            }
        }
        return true
    }

    /** Main looper only. */
    fun stop() {
        if (stopped) return
        stopped = true
        main.removeCallbacksAndMessages(null)
        val stream = output
        output = null
        writer.execute { runCatching { stream?.close() } }
        writer.shutdown()
        runCatching { recognizer.cancel() }
        runCatching { recognizer.destroy() }
    }
}
