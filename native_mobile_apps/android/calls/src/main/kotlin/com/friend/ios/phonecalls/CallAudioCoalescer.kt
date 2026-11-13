package com.friend.ios.phonecalls

import com.friend.ios.service.phonecalls.PhoneCallAudio
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executor
import java.util.concurrent.Executors

/**
 * Port of `CallAudioCoalescer.swift`. Batches the audio device's ~10 ms buffers into ~100 ms per
 * channel before they become transcript frames (Flutter `AudioEventCoalescer`). Appends hop to a
 * serial executor; a starved executor drops new audio at the enqueue cap, an overfull channel drops
 * its oldest bytes, so the freshest audio flows.
 */
class CallAudioCoalescer(
    private val queue: Executor = Executors.newSingleThreadExecutor { Thread(it, "omi.phonecalls.audio") },
    private val emit: (PhoneCallAudio) -> Unit,
) {
    private val lock = Any()
    private var queuedBytes = 0
    private var flushed = false

    /** Only touched on [queue]. */
    private val pending = HashMap<CallAudioChannel, ByteArrayOutputStream>()

    /** From the audio threads. */
    fun append(pcm: ByteArray, channel: CallAudioChannel) {
        val accepted = synchronized(lock) {
            if (flushed || queuedBytes + pcm.size > MAX_QUEUED_BYTES) {
                false
            } else {
                queuedBytes += pcm.size
                true
            }
        }
        if (!accepted) return
        queue.execute {
            synchronized(lock) { queuedBytes -= pcm.size }
            val buffer = pending.getOrPut(channel) { ByteArrayOutputStream(FLUSH_BYTES) }
            buffer.write(pcm)
            if (buffer.size() > MAX_PENDING_BYTES) {
                // Keep the newest FLUSH_BYTES.
                val bytes = buffer.toByteArray()
                buffer.reset()
                buffer.write(bytes, bytes.size - FLUSH_BYTES, FLUSH_BYTES)
            }
            if (buffer.size() >= FLUSH_BYTES) {
                pending.remove(channel)
                emit(audio(buffer.toByteArray(), channel))
            }
        }
    }

    /** The call is over: the last partial buffers go out (the final ~100 ms is not lost), nothing after. */
    fun flush() {
        synchronized(lock) { flushed = true }
        queue.execute {
            for ((channel, buffer) in pending) {
                if (buffer.size() > 0) emit(audio(buffer.toByteArray(), channel))
            }
            pending.clear()
        }
    }

    companion object {
        /** 100 ms of 48 kHz PCM16 mono. */
        const val FLUSH_BYTES = 9600
        const val MAX_PENDING_BYTES = FLUSH_BYTES * 4
        const val MAX_QUEUED_BYTES = FLUSH_BYTES * 16

        private fun audio(pcm: ByteArray, channel: CallAudioChannel) =
            PhoneCallAudio(if (channel == CallAudioChannel.Microphone) PhoneCallAudio.Channel.You else PhoneCallAudio.Channel.Them, pcm)
    }
}

/** Which side of the call a buffer is: the microphone (you) or what Twilio plays (them). */
enum class CallAudioChannel(val rawValue: Int) { Microphone(1), Remote(2) }
