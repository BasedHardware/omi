package com.friend.ios.audio

import android.app.Application
import com.friend.ios.phonemic.PhoneMicCaptureMode
import com.friend.ios.phonemic.PhoneMicCaptureState
import com.friend.ios.phonemic.PhoneMicController
import com.friend.ios.phonemic.PhoneMicControllerPorts
import com.friend.ios.phonemic.PhoneMicError
import com.friend.ios.phonemic.PhoneMicEventSink
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.math.sqrt

/** Asks for the microphone (and, on Android 13+, notifications) the first time a recording starts. */
fun interface MicrophonePermission {
    /** True when RECORD_AUDIO is granted (already, or after the system prompt). */
    suspend fun request(): Boolean
}

/**
 * Port of `PhoneMicCapture.swift`: the phone microphone as 16 kHz mono PCM16 chunks plus a 0...1
 * input level. Android: the Flutter app's [PhoneMicController] (AudioRecord, interruption and
 * self-heal state machine, microphone foreground service) in stream mode; this class turns its
 * event sink into flows, one capture session at a time.
 */
class PhoneMicCapture internal constructor(private val controller: PhoneMicController) : PhoneMicEventSink {
    constructor(application: Application) : this(PhoneMicController.create(PhoneMicControllerPorts.production(application)))

    class Output(
        /** PCM16 little-endian mono 16 kHz, ~80 ms per chunk. */
        val pcm16: Flow<ByteArray>,
        /** 0...1 input level for the live UI. */
        val level: Flow<Float>,
    )

    private var sessionID = 0L
    private var pcm: Channel<ByteArray>? = null
    private var level: Channel<Float>? = null

    /** The controller's last state for this consumer: RUNNING is the only one that delivers audio. */
    @Volatile
    private var captureState = PhoneMicCaptureState.IDLE

    /**
     * True while the controller actually captures for this consumer (`PhoneCaptureEngine.isRunning`
     * on iOS). A session the system silenced reads false, so a health probe can tell a stalled
     * capture from a live one, and the store never rebuilds a capture that was never stopped.
     */
    val isRunning: Boolean
        get() = captureState == PhoneMicCaptureState.RUNNING

    /**
     * The controller still holds a session for this consumer (it is not IDLE): it parks a session
     * the system silenced, rebuilds a starved one, and comes back on its own
     * (`PhoneCaptureEngine.recoversItself`). False once it has given up and a start is needed again.
     */
    val recoversItself: Boolean
        get() = captureState != PhoneMicCaptureState.IDLE

    init {
        controller.bindEventSink(this)
    }

    /** Starts the microphone; throws [PhoneMicError] (`permission_denied`, `engine_start_failed`, ...). */
    suspend fun start(): Output {
        finish()
        sessionID += 1
        val session = sessionID
        val pcm = Channel<ByteArray>(256, BufferOverflow.DROP_OLDEST)
        val level = Channel<Float>(1, BufferOverflow.DROP_OLDEST)
        this.pcm = pcm
        this.level = level
        val result = suspendCancellableCoroutine { cont ->
            controller.start(PhoneMicCaptureMode.STREAM, session) { cont.resume(it) }
        }
        result.exceptionOrNull()?.let { error ->
            if (session == sessionID) finish()
            throw error
        }
        return Output(pcm.receiveAsFlow(), level.receiveAsFlow())
    }

    fun stop() {
        // Not RUNNING from here on: the drain below is asynchronous, and a probe reading this in
        // between must not see a capture that was already asked to stop.
        captureState = PhoneMicCaptureState.IDLE
        finish()
        controller.stop {}
    }

    private fun finish() {
        pcm?.close()
        level?.close()
        pcm = null
        level = null
    }

    // MARK: PhoneMicEventSink (main thread)

    override fun onAudioFrame(pcm16leMono16k: ByteArray, sessionId: Long) {
        if (sessionId != sessionID) return
        pcm?.trySend(pcm16leMono16k)
        level?.trySend(rms(pcm16leMono16k))
    }

    override fun onStateChanged(state: PhoneMicCaptureState, sessionId: Long) {
        captureState = state
        // The controller ended the session itself (engine death after every retry): the streams end.
        if (sessionId == sessionID && state == PhoneMicCaptureState.IDLE) finish()
    }

    override fun onCaptureError(code: String, message: String, sessionId: Long) {}

    override fun onBatchProgress(capturedSeconds: Double, sessionId: Long) {}

    companion object {
        /** The iOS formula: RMS of the samples (-1...1), times 8, capped at 1. */
        fun rms(pcm16: ByteArray): Float {
            val count = pcm16.size / 2
            if (count == 0) return 0f
            var sum = 0.0
            for (index in 0 until count) {
                val sample = ((pcm16[2 * index + 1].toInt() shl 8) or (pcm16[2 * index].toInt() and 0xFF)).toShort() / 32768.0
                sum += sample * sample
            }
            return minOf(1f, sqrt(sum / count).toFloat() * 8)
        }
    }
}
