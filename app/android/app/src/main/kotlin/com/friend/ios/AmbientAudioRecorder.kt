package com.friend.ios

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import androidx.core.content.ContextCompat
import java.util.concurrent.atomic.AtomicBoolean

class AmbientAudioRecorder(
    private val context: Context,
    private val onChunk: (ByteArray) -> Unit,
    private val onLevel: (Double, Double) -> Unit,
    private val onError: (String) -> Unit,
) {
    private val running = AtomicBoolean(false)
    private val paused = AtomicBoolean(false)
    private var audioRecord: AudioRecord? = null
    private var readThread: Thread? = null

    fun start(): Boolean {
        if (running.get()) return true
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            onError("permission_missing")
            return false
        }

        val format = AudioFormat.Builder()
            .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
            .setSampleRate(SAMPLE_RATE)
            .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
            .build()
        val minBuffer = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val bufferSize = maxOf(minBuffer, FRAME_BYTES * 8)
        audioRecord = AudioRecord.Builder()
            .setAudioSource(MediaRecorder.AudioSource.MIC)
            .setAudioFormat(format)
            .setBufferSizeInBytes(bufferSize)
            .build()

        if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
            onError("audio_record_init_failed")
            release()
            return false
        }

        running.set(true)
        paused.set(false)
        audioRecord?.startRecording()
        readThread = Thread(::readLoop, "AmbientAudioRecorder").also { it.start() }
        return true
    }

    fun pause() {
        paused.set(true)
    }

    fun resume() {
        paused.set(false)
    }

    fun stop() {
        running.set(false)
        readThread?.join(750)
        readThread = null
        release()
    }

    private fun readLoop() {
        val buffer = ByteArray(FRAME_BYTES * 4)
        while (running.get()) {
            val read = audioRecord?.read(buffer, 0, buffer.size) ?: break
            if (read <= 0) continue
            val chunk = buffer.copyOf(read)
            val level = measure(chunk)
            onLevel(level.first, level.second)
            if (!paused.get()) {
                onChunk(chunk)
            }
        }
    }

    private fun measure(bytes: ByteArray): Pair<Double, Double> {
        if (bytes.isEmpty()) return Pair(-120.0, 1.0)
        var sumSquares = 0.0
        var zeroSamples = 0
        var samples = 0
        var i = 0
        while (i + 1 < bytes.size) {
            val sample = ((bytes[i + 1].toInt() shl 8) or (bytes[i].toInt() and 0xff)).toShort().toInt()
            if (sample == 0) zeroSamples++
            sumSquares += sample.toDouble() * sample.toDouble()
            samples++
            i += 2
        }
        if (samples == 0) return Pair(-120.0, 1.0)
        val rms = kotlin.math.sqrt(sumSquares / samples)
        val dbfs = if (rms <= 0.0) -120.0 else 20.0 * kotlin.math.log10(rms / 32768.0)
        return Pair(dbfs, zeroSamples.toDouble() / samples.toDouble())
    }

    private fun release() {
        try {
            audioRecord?.stop()
        } catch (_: Exception) {
        }
        audioRecord?.release()
        audioRecord = null
    }

    companion object {
        const val SAMPLE_RATE = 16000
        const val FRAME_BYTES = 320
    }
}
