package com.friend.ios.service

import com.friend.ios.device.OmiGATT
import com.friend.ios.device.OmiStorage
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.File
import java.io.FileOutputStream
import java.io.RandomAccessFile
import kotlin.math.roundToInt

/** A recording from the Omi's storage, on disk until the backend has it. */
@Serializable
data class PendingRecording(
    val filename: String,
    /** Epoch seconds of the first frame. */
    val startedAt: Double,
    val frames: Int,
    val frameDuration: Double,
    /** Set once uploaded (HTTP 202); the file stays until the job completes. */
    val jobID: String? = null,
    val failedJobs: Int = 0,
    /** Who was signed in when the Omi recorded it: it is only ever uploaded to that account. */
    val owner: String? = null,
    /** Recorded with Transcribe later: waits for "Process now" instead of uploading by itself. */
    val manual: Boolean? = null,
    /**
     * Store audio on phone: a copy of audio the backend already got live. It stays here (to play
     * or share) and is never uploaded.
     */
    val kept: Boolean? = null,
) {
    /** A copy kept by Store audio on phone (nothing to upload). */
    val isKept: Boolean get() = kept == true

    val seconds: Double get() = frames * frameDuration

    /** Recorded by the phone's microphone (offline or Transcribe later), not by the Omi. */
    val isPhone: Boolean get() = filename.contains("_phonemic_") || filename.contains("_omibatchphone_")

    /** The format of its frames: Opus from the Omi, PCM16 from the phone. */
    val isPCM: Boolean get() = filename.contains("_pcm16_")
}

/**
 * What survives an app relaunch: recordings waiting for upload, the one being written, and how
 * far the Omi's storage has been saved here.
 */
@Serializable
data class OfflineSyncState(
    val recordings: List<PendingRecording> = emptyList(),
    val open: PendingRecording? = null,
    /** Records below `durableSeq` of ring `ringID` are on disk here (custody firmware only). */
    val ringID: Long? = null,
    val durableSeq: Long? = null,
    /** Unread records on the Omi when last seen. */
    val devicePending: Long = 0,
    val secondsPerRecord: Double = 0.1,
    /** An Omi with offline storage has been seen: the status row has something to say. */
    val known: Boolean = false,
    /** The phone-mic file being written (`SyncStore+Phone.swift`). */
    val phoneOpen: PendingRecording? = null,
    /** The kept copy of live audio being written (Store audio on phone). */
    val keptOpen: PendingRecording? = null,
)

/**
 * Port of `OfflineRecordings.swift`: the files behind offline sync, in Flutter's WAL format
 * `[u32 LE length][frame]...`, named `audio_<device>_<codec>_<rate>_1_fs<samples>_<epoch>.bin`
 * (`wal.dart` `getFileNameByTimeStarts`) so `v2/sync-local-files` can decode and date them.
 */
class OfflineRecordings(val directory: File) {
    var state: OfflineSyncState
        private set
    private var handle: FileOutputStream? = null

    init {
        directory.mkdirs()
        state = File(directory, STATE_FILE).takeIf { it.exists() }
            ?.let { runCatching { json.decodeFromString(OfflineSyncState.serializer(), it.readText()) }.getOrNull() }
            ?: OfflineSyncState()
        // Killed mid-transfer: keep what reached the disk.
        if (state.open != null) closeOpen()
        state.phoneOpen?.let { adopt(it) }
        state.keptOpen?.let { adopt(it) }
    }

    /** A finished file joins the queue with the frames it really holds (none: it is dropped). */
    fun adopt(recording: PendingRecording) {
        if (state.phoneOpen?.filename == recording.filename) state = state.copy(phoneOpen = null)
        if (state.keptOpen?.filename == recording.filename) state = state.copy(keptOpen = null)
        val file = File(directory, recording.filename)
        val frames = validate(file)
        if (frames > 0) state = state.copy(recordings = state.recordings + recording.copy(frames = frames)) else file.delete()
        save()
    }

    fun update(change: (OfflineSyncState) -> OfflineSyncState) {
        state = change(state)
        save()
    }

    fun save() {
        val target = File(directory, STATE_FILE)
        val temp = File(directory, "$STATE_FILE.tmp")
        runCatching {
            temp.writeText(json.encodeToString(OfflineSyncState.serializer(), state))
            temp.renameTo(target)
        }
    }

    /** Appends one record's frames. Returns true when this closed a finished recording. */
    fun append(record: OmiStorage.Record, deviceID: String, codec: OmiGATT.Codec, owner: String?, nowSeconds: Double): Boolean {
        if (record.frames.isEmpty()) return false
        val duration = frameDuration(codec)
        val expected = state.open?.let { it.startedAt + it.seconds }
        val time = record.timestamp?.toDouble() ?: expected ?: nowSeconds
        var closed = false
        val open = state.open
        if (open != null && expected != null &&
            (time > expected + GAP_SECONDS || time + GAP_SECONDS < expected || open.seconds >= MAX_SECONDS)
        ) {
            closeOpen()
            closed = true
        }
        if (state.open == null) openRecording(time, deviceID, codec, duration, owner)
        val bytes = java.io.ByteArrayOutputStream()
        for (frame in record.frames) {
            bytes.write(littleEndian(frame.size))
            bytes.write(frame)
        }
        runCatching { handle?.write(bytes.toByteArray()) }
        state = state.copy(
            open = state.open?.let { it.copy(frames = it.frames + record.frames.size) },
            secondsPerRecord = state.secondsPerRecord * 0.98 + record.frames.size * duration * 0.02,
        )
        return closed
    }

    /** Flushes the open file to storage (before the Omi is told it may free those records). */
    fun sync() {
        runCatching { handle?.fd?.sync() }
        save()
    }

    /** Finishes the open recording: it joins the upload queue (an empty one is dropped). */
    fun closeOpen() {
        runCatching {
            handle?.fd?.sync()
            handle?.close()
        }
        handle = null
        val open = state.open ?: return
        state = state.copy(open = null)
        val file = File(directory, open.filename)
        val frames = validate(file)
        if (frames > 0) state = state.copy(recordings = state.recordings + open.copy(frames = frames)) else file.delete()
        save()
    }

    fun data(recording: PendingRecording): ByteArray? = File(directory, recording.filename).takeIf { it.exists() }?.readBytes()

    fun remove(filename: String) {
        File(directory, filename).delete()
        update { it.copy(recordings = it.recordings.filter { recording -> recording.filename != filename }) }
    }

    fun setJob(jobID: String?, filename: String, failed: Boolean = false) {
        update { state ->
            state.copy(
                recordings = state.recordings.map {
                    if (it.filename != filename) it else it.copy(jobID = jobID, failedJobs = it.failedJobs + if (failed) 1 else 0)
                },
            )
        }
    }

    private fun openRecording(time: Double, deviceID: String, codec: OmiGATT.Codec, frameDuration: Double, owner: String?) {
        val filename = uniqueName(directory, fileNamePrefix(deviceID, codec, frameDuration), time)
        val file = File(directory, filename)
        file.createNewFile()
        handle = runCatching { FileOutputStream(file, true) }.getOrNull()
        state = state.copy(open = PendingRecording(filename = filename, startedAt = time, frames = 0, frameDuration = frameDuration, owner = owner))
    }

    companion object {
        /** Longer stretches are cut so one upload stays small (~1.2 MB of Opus). */
        const val MAX_SECONDS = 300.0

        /** A jump in the record clock this large starts a new recording: the Omi was off or asleep. */
        const val GAP_SECONDS = 10.0
        private const val STATE_FILE = "state.json"
        private val json = Json { ignoreUnknownKeys = true }

        fun frameDuration(codec: OmiGATT.Codec): Double = if (codec == OmiGATT.Codec.OpusFS320) 0.02 else 0.01

        /** `audio_<device>_<codec>_<rate>_1_fs<samples>_`; the device id keeps only letters and digits. */
        fun fileNamePrefix(deviceID: String, codec: OmiGATT.Codec, frameDuration: Double): String {
            val device = deviceID.lowercase().filter { it.isLetterOrDigit() }
            val samples = (frameDuration * codec.sampleRate).roundToInt()
            return "audio_${device}_${codec.listenValue}_${codec.sampleRate}_1_fs${samples}_"
        }

        /** Same second as an earlier file: milliseconds keep the name unique and still parse as a time. */
        fun uniqueName(directory: File, prefix: String, time: Double): String {
            var filename = prefix + "${time.toLong()}.bin"
            var millis = (time * 1000).toLong()
            while (File(directory, filename).exists()) {
                millis += 1
                filename = prefix + "$millis.bin"
            }
            return filename
        }

        fun littleEndian(value: Int): ByteArray = byteArrayOf(value.toByte(), (value shr 8).toByte(), (value shr 16).toByte(), (value shr 24).toByte())

        /** Counts whole frames and cuts off a frame the app was killed in the middle of writing. */
        fun validate(file: File): Int {
            val bytes = runCatching { file.readBytes() }.getOrNull() ?: return 0
            var offset = 0
            var frames = 0
            while (offset + 4 <= bytes.size) {
                val length = (bytes[offset].toInt() and 0xFF) or ((bytes[offset + 1].toInt() and 0xFF) shl 8) or
                    ((bytes[offset + 2].toInt() and 0xFF) shl 16) or ((bytes[offset + 3].toInt() and 0xFF) shl 24)
                if (length <= 0 || offset + 4 + length > bytes.size) break
                offset += 4 + length
                frames += 1
            }
            if (offset < bytes.size) runCatching { RandomAccessFile(file, "rw").use { it.setLength(offset.toLong()) } }
            return frames
        }
    }
}
