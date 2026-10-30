package com.friend.ios.service

import com.friend.ios.audio.AudioFileCapture
import com.friend.ios.audio.MicrophonePermission
import com.friend.ios.audio.OnDeviceTranscriber
import com.friend.ios.audio.PhoneMicCapture
import com.friend.ios.network.listen.LiveSegment
import com.friend.ios.phonemic.PhoneMicError
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.onEach

/** Phone microphone plus optional on-device transcription, as the capture store sees it. */
interface PhoneCaptureEngine {
    /** The phone can transcribe on device (Android: an on-device SpeechRecognizer it can feed). */
    val supportsOnDevice: Boolean get() = true

    /**
     * True while the microphone actually delivers audio. The health probe reads it to notice an
     * engine that died without saying so; a fake that does not model liveness answers true.
     */
    val isRunning: Boolean get() = true

    /**
     * True while the capture holds a session of its own and brings it back without a start.
     *
     * Android's capture controller parks a session the system silenced and rebuilds a starved one
     * on its own ticker, keeping the engine alive ([PhoneMicController]); it is IDLE only once it
     * has given up for good. The health probe then leaves it alone instead of opening the
     * microphone again every tick, which would fight that recovery and re-acquire the microphone
     * three seconds at a time for the length of a call. iOS's engine is dead after an interruption
     * and only a fresh start brings it back, which is why a fake that does not model a controller
     * answers false.
     */
    val recoversItself: Boolean get() = false

    suspend fun start(transcribeOnDevice: Boolean): PhoneCaptureStreams

    fun stop()
}

class PhoneCaptureStreams(
    val pcm16: Flow<ByteArray>,
    val level: Flow<Float>,
    /** Present in on-device mode: partial and final transcript segments. */
    val transcript: Flow<TranscriptUpdate>?,
)

/** One line from an on-device recognizer (`(segment: LiveSegment, isFinal: Bool)` on iOS). */
data class TranscriptUpdate(val segment: LiveSegment, val isFinal: Boolean)

sealed class CaptureFailure(message: String) : Exception(message) {
    data object MicrophonePermission : CaptureFailure("microphone")
    data object SpeechPermission : CaptureFailure("speech")
    data object SpeechUnavailable : CaptureFailure("speechUnavailable")
    data class Engine(val detail: String) : CaptureFailure(detail)
}

/**
 * The real engine: the phone microphone through the Flutter app's phone-mic controller
 * (AudioRecord, microphone foreground service), plus the phone's recognizer on the same audio
 * ([OnDeviceTranscriber]) in on-device mode or as the live preview. Without a recognizer the
 * start reports it unavailable and the store falls back to the server's transcript, as iOS does
 * without speech permission.
 */
class LivePhoneCaptureEngine(
    private val microphone: PhoneMicCapture,
    private val permission: MicrophonePermission,
    /** Debug/CI (`omiCaptureAudioFile`): play this file instead of the microphone, read at each start. */
    private val audioFile: () -> java.io.File? = { null },
    /** The phone's recognizer for a recording (null: none on this phone); the language is read at each start. */
    private val makeTranscriber: (() -> OnDeviceTranscriber?)? = null,
    private val onDeviceSupported: () -> Boolean = { makeTranscriber != null },
) : PhoneCaptureEngine {
    private var fileCapture: AudioFileCapture? = null
    private var transcriber: OnDeviceTranscriber? = null

    /** The playback of a debug audio file runs, where the controller (and its state) is not used. */
    @Volatile
    private var fileRunning = false

    override val supportsOnDevice: Boolean
        get() = onDeviceSupported()

    override val isRunning: Boolean
        get() = fileRunning || microphone.isRunning

    override val recoversItself: Boolean
        get() = fileRunning || microphone.recoversItself

    override suspend fun start(transcribeOnDevice: Boolean): PhoneCaptureStreams {
        val recognizer = if (transcribeOnDevice) makeTranscriber?.invoke() ?: throw CaptureFailure.SpeechUnavailable else null
        val output = startAudio()
        if (recognizer == null) return PhoneCaptureStreams(output.pcm16, output.level, null)
        transcriber = recognizer
        val transcript = recognizer.start().map { segment ->
            TranscriptUpdate(
                LiveSegment(
                    id = segment.id, text = segment.text, speaker = "SPEAKER_00", speakerID = 0, isUser = true,
                    start = segment.start, end = segment.end,
                ),
                segment.isFinal,
            )
        }
        return PhoneCaptureStreams(output.pcm16.onEach { recognizer.feed(it) }, output.level, transcript)
    }

    private suspend fun startAudio(): PhoneMicCapture.Output {
        audioFile()?.let { file ->
            val capture = AudioFileCapture(file)
            fileCapture = capture
            return try {
                capture.start().also { fileRunning = true }
            } catch (error: Exception) {
                fileCapture = null
                throw CaptureFailure.Engine(error.toString())
            }
        }
        if (!permission.request()) throw CaptureFailure.MicrophonePermission
        return try {
            microphone.start()
        } catch (error: PhoneMicError) {
            throw if (error.code == "permission_denied") CaptureFailure.MicrophonePermission else CaptureFailure.Engine(error.toString())
        }
    }

    override fun stop() {
        transcriber?.stop()
        transcriber = null
        fileCapture?.let {
            it.stop()
            fileCapture = null
            fileRunning = false
            return
        }
        microphone.stop()
    }
}

/** On-device transcription of the Omi wearable's opus audio (no cloud speech-to-text needed). */
interface DeviceTranscriptionEngine {
    suspend fun start(): DeviceTranscription

    fun stop()
}

class DeviceTranscription(
    /** Hands one opus frame (header already stripped) to the decoder. */
    val feed: (ByteArray) -> Unit,
    val transcript: Flow<TranscriptUpdate>,
)

/** No on-device recognizer for the Omi (tests, a phone without one): the server transcribes. */
class UnavailableDeviceTranscriptionEngine : DeviceTranscriptionEngine {
    override suspend fun start(): DeviceTranscription = throw CaptureFailure.SpeechUnavailable

    override fun stop() {}
}

/**
 * iOS `OpusPCM16Decoder`: the Omi's Opus frames, one at a time and in order, to 16 kHz PCM16. The
 * app supplies the platform decoder (`audio/opus`), which decodes off the main thread and hands
 * each frame's PCM to the callback it was made with, on the main thread (MediaCodec waits for its
 * output, which would hold up the UI at 50 frames a second).
 */
interface OpusPCM16Decoding {
    fun decode(frame: ByteArray)

    fun release()
}

/** Makes a decoder that hands its PCM to the callback; null when the phone cannot decode Opus. */
typealias OpusDecoderFactory = (onPCM: (ByteArray) -> Unit) -> OpusPCM16Decoding?

/**
 * Port of `LiveDeviceTranscriptionEngine`: the Omi's opus, decoded on the phone, through the
 * phone's recognizer ([OnDeviceTranscriber]), for on-device mode and the live preview. The
 * recognizer needs the microphone permission even when it is fed audio (iOS asks for speech
 * recognition here). Android only checks it: the Omi often starts recording with the app in the
 * background, where no prompt can show (the phone's own recording asks).
 */
class LiveDeviceTranscriptionEngine(
    private val isPermitted: () -> Boolean,
    /** The phone's recognizer (null: none on this phone); the language is read at each start. */
    private val makeTranscriber: () -> OnDeviceTranscriber?,
    private val makeDecoder: OpusDecoderFactory,
) : DeviceTranscriptionEngine {
    private var transcriber: OnDeviceTranscriber? = null
    private var decoder: OpusPCM16Decoding? = null

    override suspend fun start(): DeviceTranscription {
        if (!isPermitted()) throw CaptureFailure.SpeechPermission
        val recognizer = makeTranscriber() ?: throw CaptureFailure.SpeechUnavailable
        val decoder = makeDecoder { pcm -> recognizer.feed(pcm) } ?: throw CaptureFailure.SpeechUnavailable
        transcriber = recognizer
        this.decoder = decoder
        val transcript = recognizer.start().map { segment ->
            TranscriptUpdate(
                LiveSegment(
                    id = segment.id, text = segment.text, speaker = "SPEAKER_00", speakerID = 0, isUser = true,
                    start = segment.start, end = segment.end,
                ),
                segment.isFinal,
            )
        }
        return DeviceTranscription(feed = decoder::decode, transcript = transcript)
    }

    override fun stop() {
        decoder?.release()
        decoder = null
        transcriber?.stop()
        transcriber = null
    }
}
