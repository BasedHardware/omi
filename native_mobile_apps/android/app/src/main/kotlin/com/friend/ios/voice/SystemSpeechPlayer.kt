package com.friend.ios.voice

import android.content.Context
import android.media.MediaPlayer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import com.friend.ios.service.stores.SpeechAudioPlaying
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import java.util.UUID
import kotlin.coroutines.resume

/**
 * Port of `SystemSpeechPlayer` (`SpeechPlayer.swift`): backend audio through MediaPlayer, the
 * system voice through TextToSpeech.
 */
class SystemSpeechPlayer(private val context: Context) : SpeechAudioPlaying {
    private var tts: TextToSpeech? = null
    private var ready: CompletableDeferred<Boolean>? = null
    private var player: MediaPlayer? = null

    private suspend fun engine(): TextToSpeech? {
        val pending = ready ?: CompletableDeferred<Boolean>().also { deferred ->
            ready = deferred
            tts = TextToSpeech(context.applicationContext) { status -> deferred.complete(status == TextToSpeech.SUCCESS) }
        }
        return if (pending.await()) tts else null
    }

    override suspend fun speak(text: String) {
        val engine = engine() ?: return
        val id = UUID.randomUUID().toString()
        suspendCancellableCoroutine { continuation ->
            engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) = Unit
                override fun onDone(utteranceId: String?) {
                    if (utteranceId == id && continuation.isActive) continuation.resume(Unit)
                }

                @Deprecated("Deprecated in Java")
                override fun onError(utteranceId: String?) {
                    if (utteranceId == id && continuation.isActive) continuation.resume(Unit)
                }

                override fun onStop(utteranceId: String?, interrupted: Boolean) {
                    if (utteranceId == id && continuation.isActive) continuation.resume(Unit)
                }
            })
            continuation.invokeOnCancellation { engine.stop() }
            engine.speak(text, TextToSpeech.QUEUE_FLUSH, null, id)
        }
    }

    override suspend fun play(audio: ByteArray) {
        val file = withContext(Dispatchers.IO) {
            File.createTempFile("omi-voice", ".mp3", context.cacheDir).apply { writeBytes(audio) }
        }
        try {
            suspendCancellableCoroutine { continuation ->
                val media = MediaPlayer()
                player = media
                media.setDataSource(file.path)
                media.setOnCompletionListener { if (continuation.isActive) continuation.resume(Unit) }
                media.setOnErrorListener { _, _, _ ->
                    if (continuation.isActive) continuation.resumeWith(Result.failure(IllegalStateException("playback failed")))
                    true
                }
                continuation.invokeOnCancellation { runCatching { media.stop() } }
                media.prepare()
                media.start()
            }
        } finally {
            player?.release()
            player = null
            file.delete()
        }
    }

    override fun stop() {
        tts?.stop()
        player?.let { runCatching { it.stop() } }
    }
}
