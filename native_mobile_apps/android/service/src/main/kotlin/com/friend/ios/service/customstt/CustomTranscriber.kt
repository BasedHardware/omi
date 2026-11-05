package com.friend.ios.service.customstt

import com.friend.ios.network.customstt.CustomSTTConfig
import com.friend.ios.network.customstt.CustomSTTError
import com.friend.ios.network.customstt.CustomSTTRequests
import com.friend.ios.network.customstt.CustomSTTSegment
import com.friend.ios.network.customstt.CustomSTTSocket
import com.friend.ios.network.customstt.CustomSTTTransport
import com.friend.ios.network.customstt.PCMWave
import com.friend.ios.network.listen.LiveSegment
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.IOException
import java.util.UUID

/**
 * Port of `CustomTranscribing`: turns live 16 kHz PCM16 into transcript segments with the user's
 * own provider (Flutter `PurePollingSocket` for the HTTP ones, `PureStreamingStt` for Deepgram).
 * Capture shows the segments and forwards them to `/v4/listen` as `suggested_transcript`.
 */
interface CustomTranscribing {
    /** The provider name sent with each `suggested_transcript` (`stt_provider`). */
    val providerName: String
    fun start(): Flow<LiveSegment>
    fun feed(pcm16: ByteArray)
    fun stop()
}

/** Port of `CustomTranscriber.swift`. Runs on [scope] (the main thread, like `@MainActor`). */
class CustomTranscriber(
    private val config: CustomSTTConfig,
    private val transport: CustomSTTTransport,
    private val scope: CoroutineScope,
    /** Transcription events (Settings > Developer, the transcription log): warning or not, message. */
    private val log: ((warning: Boolean, message: String) -> Unit)? = null,
    private val intervalMillis: Long = 3_000,
    private val clock: () -> Long = System::currentTimeMillis,
) : CustomTranscribing {
    override val providerName: String get() = config.provider.rawValue

    private var output: Channel<LiveSegment>? = null
    private var buffer = ByteArray(0)
    /** Seconds of audio already transcribed: offsets the provider's times into the recording's. */
    private var offset = 0.0
    private var loop: Job? = null
    private var socket: CustomSTTSocket? = null
    private var failures = 0
    private var nextConnect = 0L

    override fun start(): Flow<LiveSegment> {
        val channel = Channel<LiveSegment>(Channel.UNLIMITED)
        output = channel
        log?.invoke(false, "custom STT started (${config.provider.displayName})")
        if (config.provider.isLive) {
            openSocket()
        } else {
            loop = scope.launch {
                while (isActive) {
                    delay(intervalMillis)
                    flush()
                }
            }
        }
        return channel.receiveAsFlow()
    }

    override fun feed(pcm16: ByteArray) {
        if (config.provider.isLive) {
            // Dropped (a pause, the network): reconnect, at most every five seconds.
            if (socket == null && output != null && clock() >= nextConnect) openSocket()
            socket?.sendAudio(pcm16)
            return
        }
        if (loop == null) return
        buffer += pcm16
        trim()
    }

    override fun stop() {
        loop?.cancel()
        loop = null
        socket?.sendText("""{"type":"CloseStream"}""")
        socket?.close()
        socket = null
        // What is still buffered goes out once more, then the stream ends.
        val rest = buffer
        buffer = ByteArray(0)
        val channel = output
        output = null
        if (config.provider.isLive || rest.size < MIN_CHUNK_BYTES) {
            channel?.close()
            return
        }
        scope.launch {
            send(rest, channel)
            channel?.close()
        }
    }

    /** Sends what has gathered (at least [MIN_CHUNK_BYTES]); on failure it stays for the next try. */
    internal suspend fun flush() {
        if (buffer.size < MIN_CHUNK_BYTES) return
        val chunk = buffer
        buffer = ByteArray(0)
        if (!send(chunk, output)) {
            buffer = chunk + buffer
            trim()
        }
    }

    private fun trim() {
        if (buffer.size > MAX_BUFFER_BYTES) buffer = buffer.copyOfRange(buffer.size - MAX_BUFFER_BYTES, buffer.size)
    }

    private suspend fun send(chunk: ByteArray, channel: Channel<LiveSegment>?): Boolean {
        val duration = chunk.size / BYTES_PER_SECOND
        return try {
            val request = CustomSTTRequests.upload(config, PCMWave.wav(chunk))
            val (data, status) = transport.send(request)
            if (status !in 200..299) throw CustomSTTError.Http(status)
            val segments = CustomSTTRequests.segments(data, duration)
            emit(segments, offset, channel)
            offset += duration
            failures = 0
            log?.invoke(false, "custom STT: ${"%.1f".format(duration)} s, ${segments.size} segment(s)")
            true
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            failures += 1
            // Only the status or error kind: never the request (it carries the key).
            log?.invoke(true, "custom STT request failed: ${describe(error)}")
            false
        }
    }

    private fun openSocket() {
        val request = try {
            CustomSTTRequests.deepgramSocket(config)
        } catch (error: Exception) {
            log?.invoke(true, "custom STT not configured")
            output?.close()
            return
        }
        nextConnect = clock() + 5_000
        val socket = transport.openSocket(request)
        this.socket = socket
        loop = scope.launch {
            socket.messages.collect { message ->
                CustomSTTRequests.deepgramSegments(message)?.let { emit(it, 0.0, output) }
            }
            socketEnded(socket)
        }
    }

    private fun socketEnded(ended: CustomSTTSocket) {
        if (socket !== ended) return
        log?.invoke(true, "custom STT connection closed")
        socket = null
    }

    private fun emit(segments: List<CustomSTTSegment>, base: Double, channel: Channel<LiveSegment>?) {
        for (segment in segments) {
            val speaker = segment.speaker ?: 0
            channel?.trySend(
                LiveSegment(
                    id = UUID.randomUUID().toString().lowercase(), text = segment.text, speaker = "SPEAKER_%02d".format(speaker),
                    speakerID = speaker, isUser = false, start = base + segment.start, end = base + segment.end,
                ),
            )
        }
    }

    companion object {
        /** Audio per HTTP request, and the least worth sending (Flutter `AudioPollingConfig`). */
        const val MIN_CHUNK_BYTES = 8000
        /** About ten minutes of audio waits while the provider is unreachable; older audio is dropped. */
        const val MAX_BUFFER_BYTES = 19_200_000
        const val BYTES_PER_SECOND = 32000.0

        fun describe(error: Throwable): String = when (error) {
            is CustomSTTError.Http -> "HTTP ${error.status}"
            CustomSTTError.Undecodable -> "unreadable answer"
            CustomSTTError.Incomplete -> "not configured"
            is IOException -> "network"
            else -> "error"
        }
    }
}
