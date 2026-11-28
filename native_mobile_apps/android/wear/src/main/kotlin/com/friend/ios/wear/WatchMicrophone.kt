package com.friend.ios.wear

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import com.friend.ios.core.watch.WatchAudioChunk

/**
 * Port of `WatchMicrophone.swift`: the watch microphone as 16 kHz mono PCM16, in 1.5 s chunks
 * (`WatchAudioChunk`), the iOS (and Flutter) watch app's format. AudioRecord records the format
 * directly, so there is no converter. Chunks are handed over on the recording thread.
 */
class WatchMicrophone(private val onChunk: (WatchAudioChunk) -> Unit) {
    class NoInput : Exception("no microphone input")

    private val lock = Any()
    private val chunker = PcmChunker()
    private var record: AudioRecord? = null
    private var thread: Thread? = null
    @Volatile private var running = false

    /** The caller checked RECORD_AUDIO. */
    @SuppressLint("MissingPermission")
    fun start() {
        val minimum = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL, ENCODING)
        if (minimum <= 0) throw NoInput()
        val record = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, SAMPLE_RATE, CHANNEL, ENCODING, maxOf(minimum, READ_BYTES * 4))
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            record.release()
            throw NoInput()
        }
        try {
            record.startRecording()
        } catch (error: IllegalStateException) {
            record.release()
            throw NoInput()
        }
        if (record.recordingState != AudioRecord.RECORDSTATE_RECORDING) {
            record.release()
            throw NoInput()
        }
        synchronized(lock) { chunker.finish() } // a fresh count for this recording
        this.record = record
        running = true
        thread = Thread({ read(record) }, "omi-watch-mic").also { it.start() }
    }

    /** Stops and hands over what is left, then the empty last chunk. */
    fun stop() {
        running = false
        val record = record ?: return
        this.record = null
        runCatching { record.stop() }
        thread?.join(JOIN_MILLIS)
        thread = null
        record.release()
        synchronized(lock) { chunker.finish() }.forEach(onChunk)
    }

    private fun read(record: AudioRecord) {
        val buffer = ByteArray(READ_BYTES)
        while (running) {
            val count = record.read(buffer, 0, buffer.size)
            if (count <= 0) {
                if (count < 0 && running) Thread.sleep(10)
                continue
            }
            synchronized(lock) { chunker.append(buffer, count) }.forEach(onChunk)
        }
    }

    companion object {
        private const val SAMPLE_RATE = WatchAudioChunk.SAMPLE_RATE.toInt()
        private const val CHANNEL = AudioFormat.CHANNEL_IN_MONO
        private const val ENCODING = AudioFormat.ENCODING_PCM_16BIT
        /** 100 ms per read. */
        private const val READ_BYTES = 3200
        private const val JOIN_MILLIS = 500L
    }
}
