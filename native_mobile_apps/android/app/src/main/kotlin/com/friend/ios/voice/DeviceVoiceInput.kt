package com.friend.ios.voice

import android.media.MediaCodec
import android.media.MediaFormat
import com.friend.ios.device.OmiGATT
import com.friend.ios.service.stores.DeviceStore
import com.friend.ios.service.voice.VoiceInput
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Port of `DeviceVoiceInput` (`VoiceInput.swift`): the Omi's audio, decoded on the phone. Reads
 * frames through `DeviceStore.audioTap`; Opus goes through the platform's Opus decoder
 * (MediaCodec, iOS `OpusFrameDecoder`), PCM16 passes as it is.
 */
class DeviceVoiceInput(private val devices: DeviceStore) : VoiceInput {
    override suspend fun start(): Flow<ByteArray> {
        val codec = devices.codec ?: throw IllegalStateException("no Omi audio")
        if (devices.connection != DeviceStore.Connection.Connected) throw IllegalStateException("Omi not connected")
        return callbackFlow {
            val decoder = when (codec) {
                OmiGATT.Codec.Opus, OmiGATT.Codec.OpusFS320 -> OpusFrameDecoder(codec.sampleRate)
                OmiGATT.Codec.Pcm16 -> null
                // 8 kHz audio is not what the voice sample wants; old firmware only.
                OmiGATT.Codec.Pcm8 -> throw IllegalStateException("pcm8 is not supported")
            }
            devices.audioTap = { frame ->
                val pcm = if (decoder != null) decoder.decode(frame) else frame
                if (pcm != null && pcm.isNotEmpty()) trySend(pcm)
            }
            awaitClose {
                devices.audioTap = null
                decoder?.release()
            }
        }
    }

    override fun stop() {
        devices.audioTap = null
    }

    companion object {
        /** One platform decoder for every question (a MediaCodec per question would pile up). */
        private var askDecoder: OpusFrameDecoder? = null

        /**
         * `AskOmiStore.pcmDecoder` on Android: the Omi's frames as 16 kHz PCM16 for the phone's
         * recognizer; null for a codec it cannot use.
         */
        @Synchronized
        fun frameDecoder(codec: OmiGATT.Codec): ((ByteArray) -> ByteArray?)? = when (codec) {
            OmiGATT.Codec.Opus, OmiGATT.Codec.OpusFS320 -> {
                val decoder = askDecoder ?: runCatching { OpusFrameDecoder(codec.sampleRate) }.getOrNull()?.also { askDecoder = it }
                decoder?.let { shared -> { frame: ByteArray -> shared.decode(frame) } }
            }
            OmiGATT.Codec.Pcm16 -> { frame -> frame }
            OmiGATT.Codec.Pcm8 -> null
        }
    }
}

/**
 * Port of `OpusFileDecoder.swift`: a whole Omi recording's Opus frames to 16 kHz PCM16 (to play or
 * share it), with the platform decoder; null when the phone cannot decode Opus.
 */
object OpusFileDecoder {
    fun decode(frames: List<ByteArray>): ByteArray? {
        val decoder = runCatching { OpusFrameDecoder(16000) }.getOrNull() ?: return null
        return try {
            val out = java.io.ByteArrayOutputStream()
            for (frame in frames) decoder.decode(frame)?.let(out::write)
            out.write(decoder.finish())
            out.toByteArray().takeIf { it.isNotEmpty() }
        } finally {
            decoder.release()
        }
    }
}

/**
 * iOS `OpusPCM16Decoder` for a live recording (the phone's recognizer, the user's own provider):
 * a decoder of its own per recording, decoding on a worker thread and handing the PCM back on the
 * main thread, in order. Null when the phone has no Opus decoder.
 */
class PlatformOpusDecoder private constructor(
    private val decoder: OpusFrameDecoder,
    private val onPCM: (ByteArray) -> Unit,
) : com.friend.ios.service.OpusPCM16Decoding {
    private val worker = java.util.concurrent.Executors.newSingleThreadExecutor()
    private val main = android.os.Handler(android.os.Looper.getMainLooper())

    @Volatile
    private var released = false

    override fun decode(frame: ByteArray) {
        if (released) return
        runCatching {
            worker.execute {
                val pcm = decoder.decode(frame)?.takeIf { it.isNotEmpty() } ?: return@execute
                main.post { if (!released) onPCM(pcm) }
            }
        }
    }

    override fun release() {
        if (released) return
        released = true
        runCatching { worker.execute { decoder.release() } }
        worker.shutdown()
    }

    companion object {
        /** `OpusDecoderFactory`: the Omi's 16 kHz Opus (every current Omi). */
        fun make(onPCM: (ByteArray) -> Unit): com.friend.ios.service.OpusPCM16Decoding? =
            runCatching { OpusFrameDecoder(16000) }.getOrNull()?.let { PlatformOpusDecoder(it, onPCM) }
    }
}

/** One Opus frame at a time to 16-bit mono PCM, with the platform decoder (`audio/opus`). */
internal class OpusFrameDecoder(sampleRate: Int) {
    private val codec: MediaCodec = MediaCodec.createDecoderByType(MediaFormat.MIMETYPE_AUDIO_OPUS)
    private var presentationUs = 0L

    init {
        val format = MediaFormat.createAudioFormat(MediaFormat.MIMETYPE_AUDIO_OPUS, sampleRate, 1)
        format.setByteBuffer("csd-0", ByteBuffer.wrap(opusHead(sampleRate)))
        // Codec delay and seek pre-roll in nanoseconds (both zero: raw frames, no Ogg container).
        format.setByteBuffer("csd-1", ByteBuffer.allocate(8).order(ByteOrder.nativeOrder()).putLong(0).flip() as ByteBuffer)
        format.setByteBuffer("csd-2", ByteBuffer.allocate(8).order(ByteOrder.nativeOrder()).putLong(0).flip() as ByteBuffer)
        codec.configure(format, null, null, 0)
        codec.start()
    }

    fun decode(frame: ByteArray): ByteArray? = try {
        val input = codec.dequeueInputBuffer(TIMEOUT_US)
        if (input >= 0) {
            codec.getInputBuffer(input)?.apply {
                clear()
                put(frame)
            }
            codec.queueInputBuffer(input, 0, frame.size, presentationUs, 0)
            presentationUs += 20_000
        }
        val out = java.io.ByteArrayOutputStream()
        val info = MediaCodec.BufferInfo()
        while (true) {
            val index = codec.dequeueOutputBuffer(info, TIMEOUT_US)
            if (index < 0) break
            codec.getOutputBuffer(index)?.let { buffer ->
                val bytes = ByteArray(info.size)
                buffer.position(info.offset)
                buffer.get(bytes)
                out.write(bytes)
            }
            codec.releaseOutputBuffer(index, false)
        }
        out.toByteArray()
    } catch (e: IllegalStateException) {
        null
    }

    /** The end of a recording: what the decoder still holds (a whole file; never for live audio). */
    fun finish(): ByteArray = try {
        val input = codec.dequeueInputBuffer(TIMEOUT_US * 20)
        if (input >= 0) codec.queueInputBuffer(input, 0, 0, presentationUs, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
        val out = java.io.ByteArrayOutputStream()
        val info = MediaCodec.BufferInfo()
        var waits = 0
        while (waits < 20) {
            val index = codec.dequeueOutputBuffer(info, TIMEOUT_US)
            if (index < 0) {
                waits += 1
                continue
            }
            codec.getOutputBuffer(index)?.let { buffer ->
                val bytes = ByteArray(info.size)
                buffer.position(info.offset)
                buffer.get(bytes)
                out.write(bytes)
            }
            codec.releaseOutputBuffer(index, false)
            if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) break
        }
        out.toByteArray()
    } catch (e: IllegalStateException) {
        ByteArray(0)
    }

    fun release() {
        runCatching { codec.stop() }
        runCatching { codec.release() }
    }

    private companion object {
        const val TIMEOUT_US = 5_000L

        /** RFC 7845 identification header for one channel, no pre-skip. */
        fun opusHead(sampleRate: Int): ByteArray = ByteBuffer.allocate(19).order(ByteOrder.LITTLE_ENDIAN).apply {
            put("OpusHead".toByteArray(Charsets.US_ASCII))
            put(1) // version
            put(1) // channels
            putShort(0) // pre-skip
            putInt(sampleRate)
            putShort(0) // output gain
            put(0) // channel mapping family
        }.array()
    }
}
