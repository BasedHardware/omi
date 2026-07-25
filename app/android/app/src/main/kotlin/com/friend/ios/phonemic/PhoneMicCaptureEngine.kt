package com.friend.ios.phonemic

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.SystemClock
import android.util.Log

/**
 * Owns one [AudioRecord] and one dedicated read thread. The read thread does the
 * minimum on its own thread: block in `read()`, stamp a liveness timestamp, and
 * hand an exact-size copy to [onChunk]. Control-plane methods ([start]/[teardown])
 * are called from the controller's single control context.
 *
 * One instance per bring-up: the controller discards the whole engine on every
 * rebuild (interruption resume, route/device change, or a detected stall), so no
 * stale AudioRecord or thread state can survive a capture generation. This mirrors
 * the iOS [PhoneMicCaptureEngine] which rebuilds its AVAudioEngine the same way.
 *
 * [onChunk] and [onReadError] are invoked on the "PhoneMicRead" thread; hopping to
 * whatever thread the encoder/emitter needs is the controller's responsibility.
 */
@SuppressLint("MissingPermission") // Controller gates on RECORD_AUDIO before start().
class PhoneMicCaptureEngine(
    private val onChunk: (ByteArray) -> Unit,
    private val onReadError: (Int) -> Unit,
) {
    companion object {
        private const val TAG = "PhoneMic"
        private const val SAMPLE_RATE = 16000
        /** 80ms @ 16kHz PCM16 = 2560 bytes; comparable to the iOS tap's ~85ms chunks. */
        const val CHUNK_BYTES = 2560
        private const val THREAD_JOIN_TIMEOUT_MS = 1000L
    }

    /**
     * Uptime of the last successful read, stamped by the read thread on every
     * non-empty read (and once at [start] as a baseline). The controller's
     * heartbeat watches this — a value that stops advancing for >= 2s is the real
     * liveness signal (see the read-loop note below on why in-loop stall counters
     * cannot work).
     */
    @Volatile
    var lastDataUptimeMs: Long = 0L
        private set

    /** AudioRecord capture-session id, valid after [start] succeeds. */
    @Volatile
    var audioSessionId: Int = AudioRecord.ERROR
        private set

    private var record: AudioRecord? = null
    private var readThread: Thread? = null

    /** Raised by [teardown]; the read loop checks it before treating a zero/negative
     *  read as an error, so [AudioRecord.stop] unblocking `read()` is not misreported. */
    @Volatile
    private var stopping = false

    /**
     * Builds and starts the AudioRecord and spins up the read thread. Throws
     * [IllegalStateException] on any bring-up failure; the controller maps a throw
     * to `engine_start_failed`.
     */
    fun start() {
        val minBuf = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )
        if (minBuf <= 0) {
            throw IllegalStateException("AudioRecord.getMinBufferSize failed: $minBuf")
        }
        // 2 * getMinBufferSize gives headroom over the HAL minimum, but on some devices
        // 2×min lands at exactly CHUNK_BYTES (one read's worth). If the ring buffer is only
        // one chunk deep, the HAL has nowhere to stage the next samples while we copy the
        // current chunk and silently drops them (overrun). Floor at 4 chunks so there is
        // always multi-chunk headroom regardless of the device minimum.
        val bufferSize = maxOf(2 * minBuf, 4 * CHUNK_BYTES)
        Log.i(TAG, "start: minBuf=$minBuf chosen=$bufferSize chunk=$CHUNK_BYTES")

        // Deliberately no NoiseSuppressor / AcousticEchoCanceler / AutomaticGainControl:
        // ASR wants the raw mic. And deliberately no audio-focus request — taking focus
        // would pause the user's music/podcast. The iOS analog is AVAudioSession's
        // .mixWithOthers; on Android "mix with others" is simply never requesting focus.
        val record = AudioRecord.Builder()
            .setAudioSource(MediaRecorder.AudioSource.MIC)
            .setAudioFormat(
                AudioFormat.Builder()
                    .setSampleRate(SAMPLE_RATE)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
                    .build()
            )
            .setBufferSizeInBytes(bufferSize)
            .build()

        // AudioRecord can fail to initialize (device busy, bad buffer) and only reports
        // it via getState() — construction never throws.
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            val state = record.state
            record.release()
            throw IllegalStateException("AudioRecord failed to initialize (state=$state)")
        }

        this.record = record
        this.audioSessionId = record.audioSessionId
        // Baseline the liveness timestamp before the first read so the controller
        // heartbeat has a valid reference during bring-up; without it a fresh engine
        // (lastDataUptimeMs == 0) would read as instantly stalled.
        this.lastDataUptimeMs = SystemClock.uptimeMillis()

        record.startRecording()
        // recordingState == RECORDING is necessary but not sufficient: it only confirms
        // the transport started, not that the HAL is delivering samples. Real liveness is
        // the controller heartbeat watching lastDataUptimeMs.
        if (record.recordingState != AudioRecord.RECORDSTATE_RECORDING) {
            val recState = record.recordingState
            teardown()
            throw IllegalStateException("AudioRecord did not enter RECORDING (recordingState=$recState)")
        }

        val thread = Thread({ readLoop(record) }, "PhoneMicRead")
        this.readThread = thread
        thread.start()
    }

    private fun readLoop(record: AudioRecord) {
        val buf = ByteArray(CHUNK_BYTES)
        while (true) {
            val n = try {
                record.read(buf, 0, CHUNK_BYTES)
            } catch (e: Throwable) {
                // read() only realistically throws if the record was released out from
                // under us during a teardown whose join() timed out; treat exactly like
                // the stop path so we never crash the read thread or misreport a shutdown.
                if (stopping) return
                Log.e(TAG, "read() threw; reporting as read error", e)
                onReadError(AudioRecord.ERROR)
                return
            }
            if (n > 0) {
                lastDataUptimeMs = SystemClock.uptimeMillis()
                onChunk(buf.copyOf(n))
                continue
            }
            // n <= 0: check the stop flag FIRST. AudioRecord.stop() interrupts a blocked
            // read() and it returns 0 — that IS the normal shutdown path, not an error.
            if (stopping) return
            if (n < 0) {
                onReadError(n)
                return
            }
            // n == 0 outside stop: spurious wake (rare); keep reading.
            //
            // Load-bearing platform fact: a starved-but-alive HAL BLOCKS inside read()
            // rather than returning 0, so an in-loop "consecutive zero reads" stall
            // counter would never trip — it is dead code. Stall detection therefore lives
            // entirely in the controller heartbeat (no fresh lastDataUptimeMs for >= 2s).
        }
    }

    /**
     * Idempotent, defensive teardown in a fixed order, each step isolated so one
     * failure cannot skip the next (mirrors the iOS engine / Granola teardown):
     * raise the stop flag, `stop()` to unblock the parked `read()`, `join()` the
     * read thread, `release()` the record, drop refs. `stop()` before `join()` is
     * what unblocks a thread parked in `read()`; `release()` after `join()` is what
     * keeps the read thread from touching a freed record.
     */
    fun teardown() {
        stopping = true
        val rec = record
        val thread = readThread
        try {
            rec?.stop()
        } catch (e: Exception) {
            Log.w(TAG, "teardown: stop() failed: ${e.message}")
        }
        try {
            thread?.join(THREAD_JOIN_TIMEOUT_MS)
        } catch (e: InterruptedException) {
            Log.w(TAG, "teardown: join interrupted")
            Thread.currentThread().interrupt()
        }
        try {
            rec?.release()
        } catch (e: Exception) {
            Log.w(TAG, "teardown: release() failed: ${e.message}")
        }
        record = null
        readThread = null
    }
}
