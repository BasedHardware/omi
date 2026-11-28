package com.friend.ios.phonecalls

import android.annotation.SuppressLint
import android.media.AudioAttributes
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import com.twilio.voice.AudioDevice
import com.twilio.voice.AudioDeviceContext
import java.nio.ByteBuffer
import com.twilio.voice.AudioFormat as TwilioAudioFormat

/**
 * Port of `CallRecordingAudioDevice.swift`, on the Flutter app's Android `OmiRecordingAudioDevice`
 * (MIT): a Twilio audio device that also hands both sides of the call to the transcript. The record
 * loop captures the microphone for Twilio (channel 1, unless muted), the render loop pulls the
 * remote side from Twilio, plays it and taps it (channel 2). 48 kHz mono PCM16, 10 ms buffers.
 *
 * Twilio calls the `AudioDevice` methods on its own threads; each loop runs on its own handler
 * thread, so the tap and the mute flag are volatile.
 */
class CallRecordingAudioDevice : AudioDevice {
    /** Both sides of the call, from the audio threads (the coalescer batches them). */
    @Volatile
    var tap: ((ByteArray, CallAudioChannel) -> Unit)? = null

    /** Muted: the microphone side is not transcribed (Twilio mutes the call itself). */
    @Volatile
    var micMuted: Boolean = false

    private val capturerFormat = TwilioAudioFormat(SAMPLE_RATE, CHANNELS)
    private val rendererFormat = TwilioAudioFormat(SAMPLE_RATE, CHANNELS)

    private var audioRecord: AudioRecord? = null
    private var audioTrack: AudioTrack? = null

    private var captureThread: HandlerThread? = null
    private var captureHandler: Handler? = null
    private var capturingContext: AudioDeviceContext? = null
    private var captureBuffer: ByteBuffer? = null

    private var renderThread: HandlerThread? = null
    private var renderHandler: Handler? = null
    private var renderingContext: AudioDeviceContext? = null
    private var renderBuffer: ByteBuffer? = null

    // MARK: Capturer (the microphone)

    override fun getCapturerFormat(): TwilioAudioFormat = capturerFormat

    @SuppressLint("MissingPermission") // RECORD_AUDIO is granted before a call starts (PhoneCallEngine).
    override fun onInitCapturer(): Boolean {
        val minBufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, android.media.AudioFormat.CHANNEL_IN_MONO, android.media.AudioFormat.ENCODING_PCM_16BIT)
        if (minBufferSize == AudioRecord.ERROR || minBufferSize == AudioRecord.ERROR_BAD_VALUE) {
            Log.e(TAG, "onInitCapturer: invalid min buffer size $minBufferSize")
            return false
        }
        // A previous call's recorder is released, not leaked.
        audioRecord?.release()
        val record = AudioRecord(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION, SAMPLE_RATE,
            android.media.AudioFormat.CHANNEL_IN_MONO, android.media.AudioFormat.ENCODING_PCM_16BIT,
            maxOf(BUFFER_SIZE_BYTES, minBufferSize),
        )
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            Log.e(TAG, "onInitCapturer: AudioRecord failed to initialize")
            record.release()
            audioRecord = null
            return false
        }
        audioRecord = record
        captureBuffer = ByteBuffer.allocateDirect(BUFFER_SIZE_BYTES)
        return true
    }

    override fun onStartCapturing(context: AudioDeviceContext): Boolean {
        capturingContext = context
        val thread = HandlerThread("OmiCallCapture").also { it.start() }
        captureThread = thread
        captureHandler = Handler(thread.looper)
        audioRecord?.startRecording()
        captureHandler?.post(captureRunnable)
        return true
    }

    override fun onStopCapturing(): Boolean {
        captureHandler?.removeCallbacksAndMessages(null)
        runCatching { audioRecord?.stop() }.onFailure { Log.e(TAG, "onStopCapturing: ${it.message}") }
        captureThread?.quitSafely()
        captureThread = null
        captureHandler = null
        capturingContext = null
        return true
    }

    private val captureRunnable = object : Runnable {
        override fun run() {
            val record = audioRecord ?: return
            val buffer = captureBuffer ?: return
            val context = capturingContext ?: return
            try {
                buffer.clear()
                val bytesRead = record.read(buffer, BUFFER_SIZE_BYTES)
                if (bytesRead > 0) {
                    buffer.limit(bytesRead)
                    AudioDevice.audioDeviceWriteCaptureData(context, buffer)
                    val tap = if (micMuted) null else tap
                    if (tap != null) {
                        val pcm = ByteArray(bytesRead)
                        buffer.rewind()
                        buffer.get(pcm)
                        tap(pcm, CallAudioChannel.Microphone)
                    }
                }
            } catch (error: Exception) {
                Log.e(TAG, "capture: ${error.message}")
            }
            captureHandler?.post(this)
        }
    }

    // MARK: Renderer (the other side)

    override fun getRendererFormat(): TwilioAudioFormat = rendererFormat

    override fun onInitRenderer(): Boolean {
        val minBufferSize = AudioTrack.getMinBufferSize(SAMPLE_RATE, android.media.AudioFormat.CHANNEL_OUT_MONO, android.media.AudioFormat.ENCODING_PCM_16BIT)
        if (minBufferSize == AudioTrack.ERROR || minBufferSize == AudioTrack.ERROR_BAD_VALUE) {
            Log.e(TAG, "onInitRenderer: invalid min buffer size $minBufferSize")
            return false
        }
        audioTrack?.release()
        val track = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build(),
            )
            .setAudioFormat(
                android.media.AudioFormat.Builder()
                    .setSampleRate(SAMPLE_RATE)
                    .setChannelMask(android.media.AudioFormat.CHANNEL_OUT_MONO)
                    .setEncoding(android.media.AudioFormat.ENCODING_PCM_16BIT)
                    .build(),
            )
            .setBufferSizeInBytes(maxOf(BUFFER_SIZE_BYTES, minBufferSize))
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
        if (track.state != AudioTrack.STATE_INITIALIZED) {
            Log.e(TAG, "onInitRenderer: AudioTrack failed to initialize")
            track.release()
            audioTrack = null
            return false
        }
        audioTrack = track
        renderBuffer = ByteBuffer.allocateDirect(BUFFER_SIZE_BYTES)
        return true
    }

    override fun onStartRendering(context: AudioDeviceContext): Boolean {
        renderingContext = context
        val thread = HandlerThread("OmiCallRender").also { it.start() }
        renderThread = thread
        renderHandler = Handler(thread.looper)
        audioTrack?.play()
        renderHandler?.post(renderRunnable)
        return true
    }

    override fun onStopRendering(): Boolean {
        renderHandler?.removeCallbacksAndMessages(null)
        runCatching { audioTrack?.stop() }.onFailure { Log.e(TAG, "onStopRendering: ${it.message}") }
        renderThread?.quitSafely()
        renderThread = null
        renderHandler = null
        renderingContext = null
        return true
    }

    private val renderRunnable = object : Runnable {
        override fun run() {
            val track = audioTrack ?: return
            val buffer = renderBuffer ?: return
            val context = renderingContext ?: return
            try {
                buffer.clear()
                AudioDevice.audioDeviceReadRenderData(context, buffer)
                val bytes = buffer.limit()
                if (bytes > 0) {
                    tap?.let { tap ->
                        val pcm = ByteArray(bytes)
                        buffer.rewind()
                        buffer.get(pcm)
                        tap(pcm, CallAudioChannel.Remote)
                    }
                    buffer.rewind()
                    // Blocking: the track's pace is the render loop's clock.
                    track.write(buffer, bytes, AudioTrack.WRITE_BLOCKING)
                }
            } catch (error: Exception) {
                Log.e(TAG, "render: ${error.message}")
            }
            renderHandler?.post(this)
        }
    }

    /** Frees the recorder and the track (the next call initializes new ones). */
    fun release() {
        onStopCapturing()
        onStopRendering()
        audioRecord?.release()
        audioRecord = null
        audioTrack?.release()
        audioTrack = null
        captureBuffer = null
        renderBuffer = null
    }

    companion object {
        private const val TAG = "CallRecordingAudioDevice"
        const val SAMPLE_RATE = 48000
        private const val CHANNELS = 1
        private const val CALLBACK_BUFFER_MS = 10
        private const val BYTES_PER_FRAME = 2
        private const val BUFFER_SIZE_BYTES = SAMPLE_RATE * CALLBACK_BUFFER_MS / 1000 * BYTES_PER_FRAME
    }
}
