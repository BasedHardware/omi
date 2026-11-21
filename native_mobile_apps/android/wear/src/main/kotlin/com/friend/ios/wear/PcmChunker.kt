package com.friend.ios.wear

import com.friend.ios.core.watch.WatchAudioChunk

/**
 * The chunking of `WatchMicrophone.swift`: the microphone's PCM16 is cut into 1.5 s chunks
 * (`WatchAudioChunk.BYTES_PER_CHUNK`), numbered from 0; at the end what is left goes out, then the
 * empty last chunk. Not thread-safe: `WatchMicrophone` serializes the calls.
 */
class PcmChunker(private val bytesPerChunk: Int = WatchAudioChunk.BYTES_PER_CHUNK) {
    private var pending = ByteArray(bytesPerChunk)
    private var filled = 0
    private var index = 0

    /** Takes [count] bytes of [pcm]; returns the chunks that are full now. */
    fun append(pcm: ByteArray, count: Int = pcm.size): List<WatchAudioChunk> {
        var chunks: MutableList<WatchAudioChunk>? = null
        var offset = 0
        while (offset < count) {
            val take = minOf(count - offset, bytesPerChunk - filled)
            System.arraycopy(pcm, offset, pending, filled, take)
            filled += take
            offset += take
            if (filled == bytesPerChunk) {
                (chunks ?: mutableListOf<WatchAudioChunk>().also { chunks = it }) += WatchAudioChunk(pending, index, isLast = false)
                index += 1
                pending = ByteArray(bytesPerChunk)
                filled = 0
            }
        }
        return chunks.orEmpty()
    }

    /** What is left (if anything), then the empty last chunk; starts over afterwards. */
    fun finish(): List<WatchAudioChunk> {
        val chunks = mutableListOf<WatchAudioChunk>()
        var last = index
        if (filled > 0) {
            chunks += WatchAudioChunk(pending.copyOf(filled), last, isLast = false)
            last += 1
        }
        chunks += WatchAudioChunk(ByteArray(0), last, isLast = true)
        pending = ByteArray(bytesPerChunk)
        filled = 0
        index = 0
        return chunks
    }
}

/** SwiftUI `Text(date, style: .timer)`: `0:05`, `12:34`, `1:02:03`. */
fun timerText(elapsedMillis: Long): String {
    val total = (elapsedMillis / 1000).coerceAtLeast(0)
    val hours = total / 3600
    val minutes = (total % 3600) / 60
    val seconds = total % 60
    return if (hours > 0) "%d:%02d:%02d".format(hours, minutes, seconds) else "%d:%02d".format(minutes, seconds)
}
