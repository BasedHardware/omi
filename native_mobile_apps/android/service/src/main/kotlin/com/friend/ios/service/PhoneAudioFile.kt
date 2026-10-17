package com.friend.ios.service

import com.friend.ios.device.OmiGATT
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import kotlin.math.roundToInt

/**
 * Port of `PhoneAudioFile` (`SyncStore+Phone.swift`): live audio written to disk in the WAL format
 * the backend decodes (`utils/sync/files.py` `decode_pcm_file_to_wav`): `[u32 LE length][frame]...`.
 *
 * Phone mic: 320 bytes of PCM16 per frame (10 ms), named `audio_phonemic_pcm16_16000_1_fs160_<epoch>.bin`
 * (dropped connection, or a kept copy: Flutter's phone-mic WAL) or `audio_omibatchphone_...`
 * (Transcribe later). Both mark the conversation as recorded by the phone. The Omi (kept copies
 * only): one opus packet per frame, named like the Omi's own offline recordings.
 */
class PhoneAudioFile(directory: File, kind: Kind, owner: String?, startedAtSeconds: Double) {
    sealed interface Kind {
        /** Waits for upload; [manual] is Transcribe later (uploaded when asked). */
        data class Phone(val manual: Boolean) : Kind

        /** Store audio on phone: a copy of phone audio that also streamed. */
        data object KeptPhone : Kind

        /** Store audio on phone: a copy of the Omi's live audio ([device] is its id). */
        data class KeptDevice(val device: String, val codec: OmiGATT.Codec) : Kind
    }

    var recording: PendingRecording
        private set
    private val handle: FileOutputStream?
    /** Phone PCM is cut into fixed frames; the Omi's packets are frames already. */
    private val fixedFrames: Boolean = kind !is Kind.KeptDevice
    private var remainder = ByteArray(0)
    private var unsavedFrames = 0

    init {
        var frameDuration = FRAME_SECONDS
        val prefix = when (kind) {
            is Kind.Phone -> "audio_${if (kind.manual) "omibatchphone" else "phonemic"}_pcm16_16000_1_fs160_"
            Kind.KeptPhone -> "audio_phonemic_pcm16_16000_1_fs160_"
            is Kind.KeptDevice -> {
                frameDuration = OfflineRecordings.frameDuration(kind.codec)
                val samples = (frameDuration * kind.codec.sampleRate).roundToInt()
                val name = kind.device.lowercase().filter { it.isLetterOrDigit() }
                "audio_${name.ifEmpty { "omi" }}_${kind.codec.listenValue}_${kind.codec.sampleRate}_1_fs${samples}_"
            }
        }
        directory.mkdirs()
        val filename = OfflineRecordings.uniqueName(directory, prefix, startedAtSeconds)
        val file = File(directory, filename)
        file.createNewFile()
        handle = runCatching { FileOutputStream(file, true) }.getOrNull()
        recording = PendingRecording(
            filename = filename, startedAt = startedAtSeconds, frames = 0, frameDuration = frameDuration, owner = owner,
            manual = if (kind == Kind.Phone(manual = true)) true else null,
            kept = if (kind is Kind.Phone) null else true,
        )
    }

    /** Appends audio; returns true about every two seconds of it (time to save the queue state). */
    fun append(audio: ByteArray): Boolean {
        val bytes = ByteArrayOutputStream()
        var frames = 0
        if (fixedFrames) {
            val pending = remainder + audio
            var offset = 0
            while (pending.size - offset >= FRAME_BYTES) {
                bytes.write(OfflineRecordings.littleEndian(FRAME_BYTES))
                bytes.write(pending, offset, FRAME_BYTES)
                offset += FRAME_BYTES
                frames += 1
            }
            remainder = pending.copyOfRange(offset, pending.size)
        } else if (audio.isNotEmpty()) {
            bytes.write(OfflineRecordings.littleEndian(audio.size))
            bytes.write(audio)
            frames = 1
        }
        if (frames == 0) return false
        runCatching { handle?.write(bytes.toByteArray()) }
        recording = recording.copy(frames = recording.frames + frames)
        unsavedFrames += frames
        if (unsavedFrames * recording.frameDuration < 2) return false
        unsavedFrames = 0
        runCatching { handle?.fd?.sync() }
        return true
    }

    fun close() {
        runCatching {
            handle?.fd?.sync()
            handle?.close()
        }
    }

    companion object {
        const val FRAME_BYTES = 320
        const val FRAME_SECONDS = 0.01
    }
}
