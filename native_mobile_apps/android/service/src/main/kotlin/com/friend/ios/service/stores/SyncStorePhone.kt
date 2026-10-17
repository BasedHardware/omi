package com.friend.ios.service.stores

import com.friend.ios.device.OmiGATT
import com.friend.ios.network.listen.ListenSocket
import com.friend.ios.service.PendingRecording
import com.friend.ios.service.PhoneAudioFile
import com.friend.ios.service.voice.PCM16
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/*
 * Port of `SyncStore+Phone.swift`. Swift makes `SyncStore` itself conform to
 * `PhoneAudioBuffering`; Kotlin cannot add a conformance in another file, so [SyncStorePhoneAudio]
 * is that conformance, over the same file queue. `audioFile(for:)` is [audioFile] below: an Omi
 * recording's Opus goes through the platform decoder the app supplies ([SyncStore.decodeOpus]).
 */

/**
 * `extension SyncStore: PhoneAudioBuffering`: the phone mic records to a file when it cannot
 * stream (offline, Transcribe later), and Store audio on phone keeps a copy of live audio.
 */
class SyncStorePhoneAudio(private val sync: SyncStore, private val nowSeconds: () -> Double = { System.currentTimeMillis() / 1000.0 }) :
    PhoneAudioBuffering {
    private var phoneFile: PhoneAudioFile? = null
    private var keptFile: PhoneAudioFile? = null

    override fun beginPhoneAudio(manual: Boolean) {
        if (phoneFile != null) return
        val file = PhoneAudioFile(sync.files.directory, PhoneAudioFile.Kind.Phone(manual), sync.userID(), nowSeconds())
        phoneFile = file
        sync.files.update { it.copy(phoneOpen = file.recording) }
    }

    override fun appendPhoneAudio(pcm: ByteArray) {
        val file = phoneFile ?: return
        if (!file.append(pcm)) return
        sync.files.update { it.copy(phoneOpen = file.recording) }
    }

    /** The file joins the queue; one recorded offline uploads right away (Transcribe later waits). */
    override fun endPhoneAudio() {
        val file = phoneFile ?: return
        file.close()
        phoneFile = null
        sync.files.adopt(file.recording)
        sync.refresh()
        if (file.recording.manual != true) sync.uploadSoon()
    }

    override fun beginKeptCopy(source: KeptAudioSource) {
        if (keptFile != null) return
        val kind = when (source) {
            KeptAudioSource.Phone -> PhoneAudioFile.Kind.KeptPhone
            is KeptAudioSource.Device -> {
                val codec = when (source.codec) {
                    ListenSocket.Options.Codec.Opus -> OmiGATT.Codec.Opus
                    ListenSocket.Options.Codec.OpusFS320 -> OmiGATT.Codec.OpusFS320
                    else -> return
                }
                PhoneAudioFile.Kind.KeptDevice(sync.link?.storageDeviceID ?: "omi", codec)
            }
        }
        val file = PhoneAudioFile(sync.files.directory, kind, sync.userID(), nowSeconds())
        keptFile = file
        sync.files.update { it.copy(keptOpen = file.recording) }
    }

    override fun appendKeptCopy(audio: ByteArray) {
        val file = keptFile ?: return
        if (!file.append(audio)) return
        sync.files.update { it.copy(keptOpen = file.recording) }
    }

    /** The copy joins the recordings on the phone (nothing uploads). */
    override fun endKeptCopy() {
        val file = keptFile ?: return
        file.close()
        keptFile = null
        sync.files.adopt(file.recording)
        sync.refresh()
    }
}

/**
 * A phone recording as a WAV (to play or share), read right away; null for an Omi recording
 * (Opus, decoded by [audioFile]) or one that is gone.
 */
fun SyncStore.audioWav(filename: String): ByteArray? {
    val recording = files.state.recordings.firstOrNull { it.filename == filename } ?: return null
    if (!recording.isPCM) return null
    val data = files.data(recording) ?: return null
    val pcm = java.io.ByteArrayOutputStream()
    syncFrames(data).forEach { pcm.write(it) }
    if (pcm.size() == 0) return null
    return PCM16.wav(pcm.toByteArray(), 16000)
}

/** Recordings made with the phone's microphone and still on the phone, oldest first. */
val SyncStore.phoneRecordings: List<PendingRecording> get() = recordings.filter { it.isPhone }

/** Recordings the Omi kept and still on the phone. */
val SyncStore.deviceRecordings: List<PendingRecording> get() = recordings.filter { !it.isPhone }

/**
 * "Process now": this recording uploads at once (a Transcribe later one stops waiting). A kept
 * copy is already on the backend: uploading it again would duplicate the conversation.
 */
suspend fun SyncStore.process(filename: String) {
    if (files.state.recordings.firstOrNull { it.filename == filename }?.isKept == true) return
    files.update { state ->
        state.copy(
            recordings = state.recordings.map {
                if (it.filename != filename) it else it.copy(manual = null, failedJobs = if (it.jobID == null) 0 else it.failedJobs)
            },
        )
    }
    refresh()
    uploadPending()
}

/** Splits `[u32 LE length][frame]...`; stops at a frame cut short. */
fun syncFrames(data: ByteArray): List<ByteArray> {
    val frames = mutableListOf<ByteArray>()
    var offset = 0
    while (offset + 4 <= data.size) {
        val length = (data[offset].toInt() and 0xFF) or ((data[offset + 1].toInt() and 0xFF) shl 8) or
            ((data[offset + 2].toInt() and 0xFF) shl 16) or ((data[offset + 3].toInt() and 0xFF) shl 24)
        if (length <= 0 || offset + 4 + length > data.size) break
        frames += data.copyOfRange(offset + 4, offset + 4 + length)
        offset += 4 + length
    }
    return frames
}

/**
 * A recording as a WAV, decoded on demand (recordings are at most five minutes), to play or
 * share; null when it is gone or cannot be decoded (`audioFile(for:)`).
 */
suspend fun SyncStore.audioFile(filename: String): ByteArray? {
    val recording = files.state.recordings.firstOrNull { it.filename == filename } ?: return null
    val decode = decodeOpus
    return withContext(Dispatchers.IO) {
        val data = files.data(recording) ?: return@withContext null
        val frames = syncFrames(data)
        val pcm = if (recording.isPCM) {
            java.io.ByteArrayOutputStream().apply { frames.forEach { write(it) } }.toByteArray()
        } else {
            decode?.invoke(frames) ?: return@withContext null
        }
        if (pcm.isEmpty()) null else PCM16.wav(pcm, 16000)
    }
}
