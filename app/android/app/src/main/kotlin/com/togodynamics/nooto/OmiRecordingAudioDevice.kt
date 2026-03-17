package com.friend.ios

import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import com.twilio.voice.AudioDevice
import com.twilio.voice.AudioDeviceContext
import com.twilio.voice.AudioFormat as TwilioAudioFormat
import java.nio.ByteBuffer

/**
 * Custom Twilio AudioDevice that captures both local (mic) and remote (speaker) audio streams.
 *
 *
 * channel 1 = local (mic), channel 2 = remote (speaker)
 */
class OmiRecordingAudioDevice : AudioDevice {

    companion object {
        private const val TAG = "OmiRecordingAudioDevice"
        private const val SAMPLE_RATE = 48000 // TwilioAudioFormat.AUDIO_SAMPLE_RATE_48000
        private const val CHANNELS = 1 // TwilioAudioFormat.AUDIO_SAMPLE_MONO
        private const val CALLBACK_BUFFER_SIZE_MS = 10
        private const val BITS_PER_SAMPLE = 16
        private const val BYTES_PER_FRAME = CHANNELS * (BITS_PER_SAMPLE / 8)
        private const val BUFFER_SIZE_FRAMES = SAMPLE_RATE * CALLBACK_BUFFER_SIZE_MS / 1000
        private const val BUFFER_SIZE_BYTES = BUFFER_SIZE_FRAMES * BYTES_PER_FRAME
    }

    // Callback to stream captured audio data to Flutter
    // channel: 1 = mic (local), 2 = speaker (remote)
    var onAudioData: ((ByteArray, Int) -> Unit)? = null

    // When true, mic audio is not streamed to Flutter
    var isMicStreamMuted: Boolean = false

    // Audio format reported to Twilio
    private val capturerFormat = TwilioAudioFormat(SAMPLE_RATE, CHANNELS)
    private val rendererFormat = TwilioAudioFormat(SAMPLE_RATE, CHANNELS)

    // Android audio primitives
    private var audioRecord: AudioRecord? = null
    private var audioTrack: AudioTrack? = null

    // Capture thread
    private var captureThread: HandlerThread? = null
    private var captureHandler: Handler? = null
    private var capturingContext: AudioDeviceContext? = null
    private var captureBuffer: ByteBuffer? = null

    // Render thread
    private var renderThread: HandlerThread? = null
    private var renderHandler: Handler? = null
    private var renderingContext: AudioDeviceContext? = null
    private var renderBuffer: ByteBuffer? = null

    // ****************************************************
    // ************ AudioDeviceCapturer *******************
    // ****************************************************

    override fun getCapturerFormat(): TwilioAudioFormat = capturerFormat

    override fun onInitCapturer(): Boolean {
        val minBufferSize = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            android.media.AudioFormat.CHANNEL_IN_MONO,
            android.media.AudioFormat.ENCODING_PCM_16BIT
        )
        if (minBufferSize == AudioRecord.ERROR || minBufferSize == AudioRecord.ERROR_BAD_VALUE) {
            Log.e(TAG, "onInitCapturer: invalid min buffer size: $minBufferSize")
            return false
        }

        val bufferSize = maxOf(BUFFER_SIZE_BYTES, minBufferSize)

        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            SAMPLE_RATE,
            android.media.AudioFormat.CHANNEL_IN_MONO,
            android.media.AudioFormat.ENCODING_PCM_16BIT,
            bufferSize
        )

        captureBuffer = ByteBuffer.allocateDirect(BUFFER_SIZE_BYTES)

        if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
            Log.e(TAG, "onInitCapturer: AudioRecord failed to initialize")
            audioRecord?.release()
            audioRecord = null
            return false
        }

        Log.d(TAG, "onInitCapturer: ready (${SAMPLE_RATE}Hz mono 16-bit, buffer=${bufferSize})")
        return true
    }

    override fun onStartCapturing(context: AudioDeviceContext): Boolean {
        capturingContext = context

        captureThread = HandlerThread("OmiAudioCapture").also { it.start() }
        captureHandler = Handler(captureThread!!.looper)

        audioRecord?.startRecording()
        captureHandler?.post(captureRunnable)

        Log.d(TAG, "onStartCapturing")
        return true
    }

    override fun onStopCapturing(): Boolean {
        Log.d(TAG, "onStopCapturing")

        captureHandler?.removeCallbacksAndMessages(null)

        try {
            audioRecord?.stop()
        } catch (e: IllegalStateException) {
            Log.e(TAG, "onStopCapturing: AudioRecord.stop() failed: ${e.message}")
        }

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
            val ctx = capturingContext ?: return

            try {
                buffer.clear()
                val bytesRead = record.read(buffer, BUFFER_SIZE_BYTES)

                if (bytesRead > 0) {
                    // Send captured mic audio to Twilio's media engine
                    buffer.limit(bytesRead)
                    AudioDevice.audioDeviceWriteCaptureData(ctx, buffer)

                    // Stream mic audio to Flutter (channel 1) — skip when muted
                    if (!isMicStreamMuted) {
                        val audioData = ByteArray(bytesRead)
                        buffer.rewind()
                        buffer.get(audioData)
                        onAudioData?.invoke(audioData, 1)
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "captureRunnable: read failed: ${e.message}")
            }

            // Schedule next capture
            captureHandler?.post(this)
        }
    }

    // ****************************************************
    // ************* AudioDeviceRenderer ******************
    // ****************************************************

    override fun getRendererFormat(): TwilioAudioFormat = rendererFormat

    override fun onInitRenderer(): Boolean {
        val minBufferSize = AudioTrack.getMinBufferSize(
            SAMPLE_RATE,
            android.media.AudioFormat.CHANNEL_OUT_MONO,
            android.media.AudioFormat.ENCODING_PCM_16BIT
        )
        if (minBufferSize == AudioTrack.ERROR || minBufferSize == AudioTrack.ERROR_BAD_VALUE) {
            Log.e(TAG, "onInitRenderer: invalid min buffer size: $minBufferSize")
            return false
        }

        val bufferSize = maxOf(BUFFER_SIZE_BYTES, minBufferSize)

        audioTrack = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            AudioTrack.Builder()
                .setAudioAttributes(
                    android.media.AudioAttributes.Builder()
                        .setUsage(android.media.AudioAttributes.USAGE_VOICE_COMMUNICATION)
                        .setContentType(android.media.AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                .setAudioFormat(
                    android.media.AudioFormat.Builder()
                        .setSampleRate(SAMPLE_RATE)
                        .setChannelMask(android.media.AudioFormat.CHANNEL_OUT_MONO)
                        .setEncoding(android.media.AudioFormat.ENCODING_PCM_16BIT)
                        .build()
                )
                .setBufferSizeInBytes(bufferSize)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()
        } else {
            @Suppress("DEPRECATION")
            AudioTrack(
                AudioManager.STREAM_VOICE_CALL,
                SAMPLE_RATE,
                android.media.AudioFormat.CHANNEL_OUT_MONO,
                android.media.AudioFormat.ENCODING_PCM_16BIT,
                bufferSize,
                AudioTrack.MODE_STREAM
            )
        }

        renderBuffer = ByteBuffer.allocateDirect(BUFFER_SIZE_BYTES)

        if (audioTrack?.state != AudioTrack.STATE_INITIALIZED) {
            Log.e(TAG, "onInitRenderer: AudioTrack failed to initialize")
            audioTrack?.release()
            audioTrack = null
            return false
        }

        Log.d(TAG, "onInitRenderer: ready (${SAMPLE_RATE}Hz mono 16-bit, buffer=${bufferSize})")
        return true
    }

    override fun onStartRendering(context: AudioDeviceContext): Boolean {
        renderingContext = context

        renderThread = HandlerThread("OmiAudioRender").also { it.start() }
        renderHandler = Handler(renderThread!!.looper)

        audioTrack?.play()
        renderHandler?.post(renderRunnable)

        Log.d(TAG, "onStartRendering")
        return true
    }

    override fun onStopRendering(): Boolean {
        Log.d(TAG, "onStopRendering")

        renderHandler?.removeCallbacksAndMessages(null)

        try {
            audioTrack?.stop()
        } catch (e: IllegalStateException) {
            Log.e(TAG, "onStopRendering: AudioTrack.stop() failed: ${e.message}")
        }

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
            val ctx = renderingContext ?: return

            try {
                buffer.clear()
                // Pull remote audio from Twilio's media engine
                AudioDevice.audioDeviceReadRenderData(ctx, buffer)

                val bytesToWrite = buffer.limit()
                if (bytesToWrite > 0) {
                    // Stream remote audio to Flutter (channel 2)
                    val audioData = ByteArray(bytesToWrite)
                    buffer.rewind()
                    buffer.get(audioData)
                    onAudioData?.invoke(audioData, 2)

                    // Play to speaker
                    buffer.rewind()
                    track.write(buffer, bytesToWrite, AudioTrack.WRITE_BLOCKING)
                }
            } catch (e: Exception) {
                Log.e(TAG, "renderRunnable: render failed: ${e.message}")
            }

            // Schedule next render
            renderHandler?.post(this)
        }
    }

    // ****************************************************
    // ****************** Cleanup *************************
    // ****************************************************

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
}
