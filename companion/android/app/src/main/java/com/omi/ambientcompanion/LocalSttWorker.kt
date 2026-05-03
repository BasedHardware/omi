package com.omi.ambientcompanion

import android.content.Context
import android.content.Intent
import android.media.AudioFormat
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import java.time.Instant
import kotlin.concurrent.thread

class LocalSttWorker(private val context: Context) {
    private val appContext = context.applicationContext
    private val prefs = AppPrefs(appContext)
    private val audit = AuditLog(appContext)
    private val spoolStore = CaptureSpoolStore(appContext)
    private val queue = FallbackSegmentQueue(appContext)
    private val mainHandler = Handler(Looper.getMainLooper())

    fun drainSpoolForLocalTranscripts() {
        if (!prefs.allowLocalSttFallback) return
        if (running) return
        running = true
        val pending = spoolStore.list("pending").filter { it.localSttStatus.isNullOrBlank() }.take(1)
        if (pending.isEmpty()) {
            running = false
            return
        }
        val meta = pending.first()
        spoolStore.updateMetadata(meta.filePath, mapOf("local_stt_status" to "processing"))
        transcribe(meta)
    }

    private fun transcribe(meta: SpoolMetadata) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            markUnavailable(meta, "requires_android_13")
            return
        }
        if (!SpeechRecognizer.isOnDeviceRecognitionAvailable(appContext)) {
            markUnavailable(meta, "on_device_recognizer_unavailable")
            return
        }
        mainHandler.post {
            val recognizer = SpeechRecognizer.createOnDeviceSpeechRecognizer(appContext)
            val pipe = ParcelFileDescriptor.createPipe()
            val readSide = pipe[0]
            val writeSide = pipe[1]
            val timeout = Runnable {
                runCatching { recognizer.cancel() }
                runCatching { recognizer.destroy() }
                runCatching { readSide.close() }
                runCatching { writeSide.close() }
                complete(meta, null, null, "timeout")
            }
            recognizer.setRecognitionListener(listener(meta, recognizer, readSide, writeSide, timeout))
            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                .putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
                .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
                .putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE, readSide)
                .putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_CHANNEL_COUNT, 1)
                .putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_ENCODING, AudioFormat.ENCODING_PCM_16BIT)
                .putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_SAMPLING_RATE, 16_000)
                .putExtra(RecognizerIntent.EXTRA_SEGMENTED_SESSION, RecognizerIntent.EXTRA_AUDIO_SOURCE)
            mainHandler.postDelayed(timeout, LOCAL_STT_TIMEOUT_MS)
            try {
                recognizer.startListening(intent)
                writePcmToPipe(meta, writeSide)
            } catch (e: Throwable) {
                runCatching { recognizer.destroy() }
                runCatching { readSide.close() }
                runCatching { writeSide.close() }
                mainHandler.removeCallbacks(timeout)
                complete(meta, null, null, "start_failed:${e.javaClass.simpleName}")
            }
        }
    }

    private fun writePcmToPipe(meta: SpoolMetadata, writeSide: ParcelFileDescriptor) {
        thread(name = "ambient-local-stt-audio") {
            try {
                ParcelFileDescriptor.AutoCloseOutputStream(writeSide).use { output ->
                    var bytesWritten = 0L
                    val maxBytes = MAX_LOCAL_STT_SECONDS * 16_000 * 2
                    spoolStore.readPlainChunks(meta).forEach { chunk ->
                        if (bytesWritten >= maxBytes) return@forEach
                        val allowed = minOf(chunk.size, (maxBytes - bytesWritten).toInt())
                        output.write(chunk, 0, allowed)
                        bytesWritten += allowed
                    }
                }
            } catch (e: Throwable) {
                audit.record("local_stt_audio_pipe_failed", mapOf("session_id" to meta.sessionId, "error" to e.javaClass.simpleName))
            }
        }
    }

    private fun listener(
        meta: SpoolMetadata,
        recognizer: SpeechRecognizer,
        readSide: ParcelFileDescriptor,
        writeSide: ParcelFileDescriptor,
        timeout: Runnable,
    ): RecognitionListener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) = Unit
        override fun onBeginningOfSpeech() = Unit
        override fun onRmsChanged(rmsdB: Float) = Unit
        override fun onBufferReceived(buffer: ByteArray?) = Unit
        override fun onEndOfSpeech() = Unit
        override fun onPartialResults(partialResults: Bundle?) = Unit
        override fun onEvent(eventType: Int, params: Bundle?) = Unit

        override fun onError(error: Int) {
            cleanup(recognizer, readSide, writeSide, timeout)
            complete(meta, null, null, "recognizer_error_$error")
        }

        override fun onResults(results: Bundle?) {
            val texts = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION).orEmpty()
            val confidence = results?.getFloatArray(SpeechRecognizer.CONFIDENCE_SCORES)?.firstOrNull()?.toDouble()
            cleanup(recognizer, readSide, writeSide, timeout)
            complete(meta, texts.firstOrNull(), confidence, "ok")
        }
    }

    private fun cleanup(
        recognizer: SpeechRecognizer,
        readSide: ParcelFileDescriptor,
        writeSide: ParcelFileDescriptor,
        timeout: Runnable,
    ) {
        mainHandler.removeCallbacks(timeout)
        runCatching { recognizer.destroy() }
        runCatching { readSide.close() }
        runCatching { writeSide.close() }
    }

    private fun complete(meta: SpoolMetadata, text: String?, confidence: Double?, reason: String) {
        val cleanText = text?.trim().orEmpty()
        if (cleanText.isNotBlank()) {
            val start = meta.startedAt
            val end = start.plusMillis((meta.durationEstimateSeconds * 1000).toLong().coerceAtLeast(1000))
            queue.enqueue(
                FallbackSegment(
                    text = cleanText,
                    source = FallbackSource.LOCAL_STT,
                    start = start,
                    end = end,
                    confidence = confidence,
                    healthState = AmbientHealthState.LOCAL_STT_ACTIVE,
                    rawAudioAvailable = true,
                    foregroundApp = ContextSignals.foregroundPackage,
                )
            )
            spoolStore.updateMetadata(meta.filePath, mapOf("local_stt_status" to "completed"))
            audit.record("local_stt_completed", mapOf("session_id" to meta.sessionId, "chars" to cleanText.length))
        } else {
            spoolStore.updateMetadata(meta.filePath, mapOf("local_stt_status" to "failed:$reason"))
            audit.record("local_stt_failed", mapOf("session_id" to meta.sessionId, "reason" to reason))
        }
        running = false
        SyncWorker.drainAsync(appContext)
    }

    private fun markUnavailable(meta: SpoolMetadata, reason: String) {
        spoolStore.updateMetadata(meta.filePath, mapOf("local_stt_status" to "unavailable:$reason"))
        audit.record("local_stt_unavailable", mapOf("session_id" to meta.sessionId, "reason" to reason))
        running = false
    }

    companion object {
        private const val LOCAL_STT_TIMEOUT_MS = 180_000L
        private const val MAX_LOCAL_STT_SECONDS = 120

        @Volatile private var running = false
    }
}
