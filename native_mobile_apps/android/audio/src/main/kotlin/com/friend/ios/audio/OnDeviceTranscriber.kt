package com.friend.ios.audio

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
import android.util.Log
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import java.io.IOException
import java.io.OutputStream
import java.util.UUID
import java.util.concurrent.Executors

/**
 * Port of `OnDeviceTranscriber.swift`: speech recognition on the captured audio, for Omi's
 * on-device transcription mode (`custom_stt=enabled` on the listen socket: the client sends
 * `suggested_transcript`).
 *
 * Android: `SpeechRecognizer.createOnDeviceSpeechRecognizer` (Android 12), fed with the capture's
 * own 16 kHz PCM16 through Android 13's `EXTRA_AUDIO_SOURCE`, so the microphone is opened once.
 * Strictly on-device first; the system's regular recognizer if the phone has no offline model for
 * the language (as iOS falls back to Apple's server recognizer).
 *
 * An Android recognition session ends after a pause; the next one starts right away under a new
 * segment id, so each spoken stretch is one segment (iOS rolls its requests every ~50 s and splits
 * them into parts after pauses: the same result for the capture store).
 */
class OnDeviceTranscriber(private val context: Context, language: String) {
    data class Segment(val id: String, val text: String, val start: Double, val end: Double, val isFinal: Boolean)

    private val locale = locale(language)
    private val main = Handler(Looper.getMainLooper())
    private val writer = Executors.newSingleThreadExecutor()
    private var recognizer: SpeechRecognizer? = null
    private var output: OutputStream? = null
    /** The read end handed to the recognizer; closed with its session (the service holds its own copy). */
    private var input: ParcelFileDescriptor? = null
    private var segments: Channel<Segment>? = null
    /** Seconds of audio fed so far: the segments' clock (it starts with the recording). */
    @Volatile private var elapsed = 0.0
    private var segmentIndex = 0
    private val prefix = "ondevice-${UUID.randomUUID().toString().take(8)}"
    private var prefersOnDevice = true
    private var stopped = false
    /** Sessions that failed in a row without a word; a few are replaced, then recognition rests. */
    private var failuresInARow = 0

    /** Partial and final segments (partial ones repeat the same id until final). */
    fun start(): Flow<Segment> {
        val channel = Channel<Segment>(Channel.UNLIMITED)
        segments = channel
        main.post { startRequest() }
        return channel.receiveAsFlow()
    }

    /** 16 kHz mono PCM16 from the capture. */
    fun feed(pcm16: ByteArray) {
        elapsed += pcm16.size / BYTES_PER_SECOND
        val stream = output ?: return
        writer.execute {
            try {
                stream.write(pcm16)
            } catch (_: IOException) {
                // The session ended; the next one has its own pipe.
            }
        }
    }

    fun stop() {
        stopped = true
        main.post {
            teardown()
            // What the recognizer still says after the end of the audio arrives within a moment.
            main.postDelayed({
                segments?.close()
                segments = null
            }, 300)
        }
    }

    private fun teardown() {
        recognizer?.let {
            runCatching { it.cancel() }
            it.destroy()
        }
        recognizer = null
        output?.let { stream -> writer.execute { runCatching { stream.close() } } }
        output = null
        input?.let { runCatching { it.close() } }
        input = null
    }

    private fun startRequest() {
        if (stopped || Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        teardown()
        segmentIndex += 1
        val id = "$prefix-$segmentIndex"
        val requestStart = elapsed
        var wordsStart: Double? = null
        val onDevice = prefersOnDevice && SpeechRecognizer.isOnDeviceRecognitionAvailable(context)
        val pipe = ParcelFileDescriptor.createPipe()
        output = ParcelFileDescriptor.AutoCloseOutputStream(pipe[1])
        val speech = if (onDevice) SpeechRecognizer.createOnDeviceSpeechRecognizer(context) else SpeechRecognizer.createSpeechRecognizer(context)
        recognizer = speech
        speech.setRecognitionListener(object : RecognitionListener {
            override fun onPartialResults(partialResults: Bundle?) = emit(partialResults, isFinal = false)

            override fun onResults(results: Bundle?) {
                emit(results, isFinal = true)
                // A pause ended this session while the user may go on talking.
                if (recognizer === speech) startRequest()
            }

            override fun onError(error: Int) {
                if (recognizer !== speech || stopped) return
                Log.w(TAG, "recognition failed (onDevice=$onDevice): $error")
                when (error) {
                    // Silence: listen on with a new session.
                    SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> startRequest()
                    SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED, SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE ->
                        if (onDevice) {
                            // No offline model for this language yet: ask the system to fetch it
                            // for next time, and use its regular recognizer now.
                            runCatching {
                                speech.triggerModelDownload(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).putExtra(RecognizerIntent.EXTRA_LANGUAGE, locale))
                            }
                            prefersOnDevice = false
                            startRequest()
                        } else {
                            restartAfterFailure()
                        }
                    else -> restartAfterFailure()
                }
            }

            private fun emit(bundle: Bundle?, isFinal: Boolean) {
                if (recognizer !== speech) return
                val text = bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.trim().orEmpty()
                if (text.isEmpty()) return
                failuresInARow = 0
                val end = elapsed
                // The first words arrive about a second after they were said.
                val start = wordsStart ?: maxOf(requestStart, end - 1).also { wordsStart = it }
                segments?.trySend(Segment(id, text, start, end, isFinal))
            }

            override fun onReadyForSpeech(params: Bundle?) = Unit
            override fun onBeginningOfSpeech() = Unit
            override fun onRmsChanged(rmsdB: Float) = Unit
            override fun onBufferReceived(buffer: ByteArray?) = Unit
            override fun onEndOfSpeech() = Unit
            override fun onEvent(eventType: Int, params: Bundle?) = Unit
        })
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, locale)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, onDevice)
            putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE, pipe[0])
            putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_CHANNEL_COUNT, 1)
            putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_ENCODING, AudioFormat.ENCODING_PCM_16BIT)
            putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_SAMPLING_RATE, SAMPLE_RATE)
        }
        input = pipe[0]
        runCatching { speech.startListening(intent) }.onFailure { restartAfterFailure() }
    }

    /** A session failed: try again shortly, unless it keeps failing. */
    private fun restartAfterFailure() {
        failuresInARow += 1
        if (failuresInARow > MAXIMUM_FAILURES_IN_A_ROW) {
            teardown()
            return
        }
        main.postDelayed({ if (!stopped) startRequest() }, 300)
    }

    companion object {
        private const val TAG = "omi.transcriber"
        const val SAMPLE_RATE = 16000
        private const val BYTES_PER_SECOND = 32000.0
        internal const val MAXIMUM_FAILURES_IN_A_ROW = 4

        /**
         * The phone can transcribe capture audio itself: Android 13 (to feed the recognizer) and a
         * recognizer to feed, on-device or the system's own.
         */
        fun isSupported(context: Context): Boolean {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return false
            return SpeechRecognizer.isOnDeviceRecognitionAvailable(context) || SpeechRecognizer.isRecognitionAvailable(context)
        }

        /**
         * `locale(for:)`: a BCP 47 tag for the language the user speaks (`de` -> `de-DE`), the
         * usual region when only the language is known.
         */
        fun locale(language: String): String {
            val wanted = language.replace('_', '-')
            if (wanted.contains('-')) return wanted
            val base = wanted.lowercase()
            return mapOf(
                "en" to "en-US", "de" to "de-DE", "es" to "es-ES", "fr" to "fr-FR", "pt" to "pt-BR", "it" to "it-IT", "nl" to "nl-NL",
            )[base] ?: base
        }
    }
}
