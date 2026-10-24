package com.friend.ios.voice

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
import com.friend.ios.service.voice.LiveRecognizer
import com.friend.ios.service.voice.LiveSegment
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import java.io.IOException
import java.io.OutputStream
import java.util.concurrent.Executors

/**
 * Port of `AppleLiveRecognizer` (`VoiceInput.swift`) on Android's SpeechRecognizer: live words on
 * the phone itself, fed with the same PCM the voice sample records (Android 13's
 * `EXTRA_AUDIO_SOURCE`, so the microphone is not opened twice). Older Android has no way to feed
 * the recognizer, so it reports unavailable and the server socket (or speech alone) stands in.
 *
 * Each recognizer session is one utterance; when it ends (a pause, or [startNewUtterance]) the
 * next one starts on a fresh pipe under a new segment id.
 */
class AndroidLiveRecognizer(private val context: Context) : LiveRecognizer {
    private val main = Handler(Looper.getMainLooper())
    private val writer = Executors.newSingleThreadExecutor()
    private var recognizer: SpeechRecognizer? = null
    private var output: OutputStream? = null
    private var segments: Channel<LiveSegment>? = null
    private var language = "en"
    private var utterance = 0
    private var session = 0

    override suspend fun start(language: String): Flow<LiveSegment>? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return null
        if (!SpeechRecognizer.isRecognitionAvailable(context)) return null
        stop()
        this.language = language
        val channel = Channel<LiveSegment>(Channel.UNLIMITED)
        segments = channel
        main.post { listen() }
        return channel.receiveAsFlow()
    }

    override fun feed(pcm16: ByteArray) {
        val stream = output ?: return
        writer.execute {
            try {
                stream.write(pcm16)
            } catch (_: IOException) {
                // The session ended; the next one has its own pipe.
            }
        }
    }

    override fun startNewUtterance() {
        main.post {
            if (segments == null) return@post
            utterance += 1
            listen()
        }
    }

    override fun stop() {
        session += 1
        segments?.close()
        segments = null
        main.post { teardown() }
    }

    private fun teardown() {
        recognizer?.let {
            runCatching { it.cancel() }
            it.destroy()
        }
        recognizer = null
        output?.let { stream -> writer.execute { runCatching { stream.close() } } }
        output = null
    }

    private fun listen() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        teardown()
        val current = session
        val id = "android-$current-$utterance"
        val pipe = ParcelFileDescriptor.createPipe()
        output = ParcelFileDescriptor.AutoCloseOutputStream(pipe[1])
        val speech = SpeechRecognizer.createSpeechRecognizer(context)
        recognizer = speech
        speech.setRecognitionListener(object : RecognitionListener {
            override fun onPartialResults(partialResults: Bundle?) = emit(partialResults)
            override fun onResults(results: Bundle?) {
                emit(results)
                // A pause ended this utterance: carry on with the next one.
                if (session == current) {
                    utterance += 1
                    listen()
                }
            }

            override fun onError(error: Int) {
                if (session != current) return
                when (error) {
                    SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> listen()
                    else -> segments?.close()
                }
            }

            private fun emit(bundle: Bundle?) {
                val text = bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.trim().orEmpty()
                if (text.isNotEmpty() && session == current) segments?.trySend(LiveSegment(id = id, text = text))
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
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, language)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE, pipe[0])
            putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_CHANNEL_COUNT, 1)
            putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_ENCODING, AudioFormat.ENCODING_PCM_16BIT)
            putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_SAMPLING_RATE, PhoneVoiceInput.SAMPLE_RATE)
        }
        runCatching { speech.startListening(intent) }.onFailure { segments?.close() }
    }
}
