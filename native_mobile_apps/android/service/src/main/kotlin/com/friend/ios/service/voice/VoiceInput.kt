package com.friend.ios.service.voice

import com.friend.ios.network.endpoints.ListenAPI
import com.friend.ios.network.listen.ListenEvent
import com.friend.ios.network.listen.LiveTranscriptionChannel as ListenChannel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.mapNotNull
import kotlin.math.sqrt

/**
 * Port of `VoiceInput.swift`'s protocols: where onboarding hears the user, the phone microphone
 * or the Omi. Both deliver 16 kHz mono PCM16. The Android implementations (AudioRecord,
 * SpeechRecognizer) live in the app module.
 */
interface VoiceInput {
    /** Throws when the input cannot start (no microphone permission, no Omi audio). */
    suspend fun start(): Flow<ByteArray>
    fun stop()
}

/** One line of live words (`LiveSegment` of the listen socket, the fields onboarding reads). */
data class LiveSegment(
    val id: String,
    val text: String,
    val speaker: String = "SPEAKER_00",
    val speakerID: Int = 0,
    val isUser: Boolean = true,
    val start: Double = 0.0,
    val end: Double = 0.0,
)

/** Live words on the phone itself: onboarding's first choice (instant, works offline). */
interface LiveRecognizer {
    /** Null when recognition cannot run (no permission, language not supported). */
    suspend fun start(language: String): Flow<LiveSegment>?
    fun feed(pcm16: ByteArray)
    /** What is said from now on arrives as a new segment (onboarding: one per sentence). */
    fun startNewUtterance()
    fun stop()
}

/**
 * The server's transcription-only socket (`api.openTranscribeStream`), the stand-in when the
 * phone cannot recognize the language: the words and the socket's state, as onboarding reads them.
 * The listen socket's own channel becomes one with [asVoiceChannel].
 */
interface LiveTranscriptionChannel {
    sealed interface Event {
        data class Segments(val segments: List<LiveSegment>) : Event
        data class Status(val status: String) : Event
    }

    val events: Flow<Event>
    fun send(audio: ByteArray)
    fun close(reason: String)
}

/** The listen socket's channel as onboarding reads it: its segments and its status, nothing else. */
fun ListenChannel.asVoiceChannel(): LiveTranscriptionChannel = object : LiveTranscriptionChannel {
    override val events: Flow<LiveTranscriptionChannel.Event> = this@asVoiceChannel.events.mapNotNull { event ->
        when (event) {
            is ListenEvent.Segments -> LiveTranscriptionChannel.Event.Segments(
                event.segments.map { LiveSegment(it.id, it.text, it.speaker ?: "SPEAKER_00", it.speakerID ?: 0, it.isUser, it.start, it.end) },
            )
            is ListenEvent.Status -> LiveTranscriptionChannel.Event.Status(event.status)
            else -> null
        }
    }

    override fun send(audio: ByteArray) = this@asVoiceChannel.send(audio)

    override fun close(reason: String) = this@asVoiceChannel.close(reason)
}

/** Opens the server's transcription-only socket (`api.openTranscribeStream`) as onboarding's channel. */
suspend fun ListenAPI.openVoiceChannel(language: String): LiveTranscriptionChannel = openTranscribeStream(language).asVoiceChannel()

/** A recognizer that never runs: the steps go by speech alone. */
object NoLiveRecognizer : LiveRecognizer {
    override suspend fun start(language: String): Flow<LiveSegment>? = null
    override fun feed(pcm16: ByteArray) = Unit
    override fun startNewUtterance() = Unit
    override fun stop() = Unit
}

/** PCM16 helpers for onboarding's voice sample. */
object PCM16 {
    /** Root mean square, 0...1. */
    fun level(chunk: ByteArray): Float {
        val count = chunk.size / 2
        if (count == 0) return 0f
        var sum = 0.0
        for (index in 0 until count) {
            val sample = ((chunk[2 * index + 1].toInt() shl 8) or (chunk[2 * index].toInt() and 0xFF)).toShort()
            val value = sample / 32767.0
            sum += value * value
        }
        return sqrt(sum / count).toFloat()
    }

    /** A 16 kHz mono WAV around raw PCM16. */
    fun wav(pcm: ByteArray, sampleRate: Int = 16000): ByteArray {
        val header = java.nio.ByteBuffer.allocate(44).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        header.put("RIFF".toByteArray()).putInt(36 + pcm.size).put("WAVE".toByteArray())
        header.put("fmt ".toByteArray()).putInt(16).putShort(1).putShort(1)
        header.putInt(sampleRate).putInt(sampleRate * 2).putShort(2).putShort(16)
        header.put("data".toByteArray()).putInt(pcm.size)
        return header.array() + pcm
    }
}
