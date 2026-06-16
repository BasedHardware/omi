package com.friend.ios

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.io.RandomAccessFile
import java.util.Locale

/**
 * Batch (offline) capture sink. When the user enables "batch mode", incoming BLE
 * audio is NOT streamed to the transcription socket — instead each opus/pcm frame
 * is appended to a local `.bin` file with the exact length-prefixed layout the
 * Omi offline-sync backend (`POST /v2/sync-local-files`) expects:
 *
 *     [4-byte little-endian uint32 frame_length][frame bytes] ... repeated
 *
 * Files are named `audio_{device}_{codec}_{sampleRate}_{channel}_fs{frameSize}_{startSec}.bin`
 * so the backend can parse the codec, frame size and start timestamp. Flutter later
 * scans the directory, registers each finalized file as a WAL and uploads it.
 *
 * This runs entirely native (called from [OmiBleForegroundService]'s characteristic
 * listener) so the Flutter engine does no per-packet work while the app is
 * minimized/closed. It self-gates on the `batchModeEnabled` pref and is mutually
 * exclusive with [OmiBackgroundAudioStreamer] (which is disabled in batch mode via
 * `nativeBleStreamingEnabled=false`).
 *
 * Durability (improving on fieldy, which has none): frames are written with a
 * periodic `fsync`, a `.batch_journal` names the file currently being appended so
 * Flutter never ingests a half-written file, and a free-space guard stops writing
 * (rather than crashing) when storage runs low.
 */
class OmiBatchAudioWriter(private val context: Context) {
    companion object {
        private const val TAG = "OmiBle.BatchWriter"
        private const val FLUTTER_PREFS = "FlutterSharedPreferences"
        private const val JOURNAL_NAME = ".batch_journal"
        private const val MAX_FILE_BYTES = 32L * 1024 * 1024 // ~32 MB per file
        private const val MAX_FILE_SECONDS = 1800L // 30 min per file
        private const val GAP_MS = 30_000L // close current file after this silence gap
        private const val FSYNC_INTERVAL_MS = 2_000L
        private const val MIN_FREE_BYTES = 200L * 1024 * 1024 // stop writing below 200 MB free
    }

    private data class Config(
        val deviceId: String,
        val codec: String,
        val sampleRate: Int,
        val serviceUuid: String,
        val characteristicUuid: String,
        val deviceType: String,
        val dir: String,
    )

    private val lock = Any()
    private var raf: RandomAccessFile? = null
    private var currentFile: File? = null
    private var currentStartSec: Long = 0
    private var currentBytes: Long = 0
    private var currentFrames: Long = 0
    private var lastFrameMs: Long = 0
    private var lastFsyncMs: Long = 0
    private var storageFull = false

    /** Audio target for this device if batch mode is on — used by the foreground
     *  service to subscribe to the audio characteristic when Flutter is dead. */
    fun configuredAudioTargetFor(address: String): Pair<String, String>? {
        val config = loadConfig() ?: return null
        if (!config.deviceId.equals(address, ignoreCase = true)) return null
        return config.serviceUuid to config.characteristicUuid
    }

    fun handleCharacteristic(address: String, serviceUuid: String, characteristicUuid: String, value: ByteArray) {
        val config = loadConfig()
        if (config == null) {
            // Batch mode disabled — finalize any open file so it can be ingested.
            closeCurrent("disabled")
            return
        }
        if (!config.deviceId.equals(address, ignoreCase = true)) return
        if (!matches(config, serviceUuid, characteristicUuid)) return

        val frames = transformFrames(config.deviceType, value)
        if (frames.isEmpty()) return

        synchronized(lock) {
            val now = System.currentTimeMillis()

            // Gap finalize: a pause longer than GAP_MS starts a new file (so the
            // backend places resumed audio as a separate conversation).
            if (raf != null && lastFrameMs > 0 && now - lastFrameMs > GAP_MS) {
                closeCurrentLocked("gap")
            }
            // Rotation: bound file size/duration (between packets, never mid-packet).
            if (raf != null && (currentBytes >= MAX_FILE_BYTES || (now / 1000 - currentStartSec) >= MAX_FILE_SECONDS)) {
                closeCurrentLocked("rotate")
            }

            ensureOpenLocked(config, now)
            val out = raf ?: return // storage full or open failed — drop this packet

            try {
                for (frame in frames) {
                    writeFrameLocked(out, frame)
                }
            } catch (e: Exception) {
                Log.e(TAG, "write failed: ${e.message}")
                closeCurrentLocked("write_error")
                return
            }

            lastFrameMs = now
            if (now - lastFsyncMs >= FSYNC_INTERVAL_MS) {
                fsyncLocked()
                lastFsyncMs = now
            }
        }
    }

    /** Finalize + fsync the current file (e.g. on service destroy). */
    fun stop(reason: String) {
        synchronized(lock) { closeCurrentLocked(reason) }
    }

    private fun closeCurrent(reason: String) {
        synchronized(lock) { closeCurrentLocked(reason) }
    }

    // ── File lifecycle (caller holds lock) ──

    private fun ensureOpenLocked(config: Config, nowMs: Long) {
        if (raf != null) return

        val dir = File(config.dir)
        if (!dir.exists() && !dir.mkdirs()) {
            Log.e(TAG, "cannot create batch dir ${config.dir}")
            return
        }
        if (dir.usableSpace < MIN_FREE_BYTES) {
            if (!storageFull) {
                Log.w(TAG, "storage low (${dir.usableSpace} bytes free) — pausing batch capture")
                setStorageFullFlag(true)
                storageFull = true
            }
            return
        }
        if (storageFull) {
            storageFull = false
            setStorageFullFlag(false)
        }

        val startSec = nowMs / 1000
        val frameSize = if (config.codec == "opus_fs320") 320 else 160
        val deviceToken = config.deviceType.lowercase(Locale.US).filter { it.isLetterOrDigit() }.ifEmpty { "omi" }
        val name = "audio_${deviceToken}_${config.codec}_${config.sampleRate}_1_fs${frameSize}_${startSec}.bin"
        val file = File(dir, name)

        try {
            val out = RandomAccessFile(file, "rw")
            out.seek(out.length()) // append-safe (same-second restart reuses the file)
            raf = out
            currentFile = file
            currentStartSec = startSec
            currentBytes = file.length()
            currentFrames = 0
            lastFsyncMs = nowMs
            writeJournal(dir, name)
            Log.i(TAG, "opened batch file $name")
        } catch (e: Exception) {
            Log.e(TAG, "open failed for $name: ${e.message}")
            raf = null
            currentFile = null
        }
    }

    private fun writeFrameLocked(out: RandomAccessFile, frame: ByteArray) {
        val len = frame.size
        val header = byteArrayOf(
            (len and 0xFF).toByte(),
            ((len shr 8) and 0xFF).toByte(),
            ((len shr 16) and 0xFF).toByte(),
            ((len shr 24) and 0xFF).toByte(),
        )
        out.write(header)
        out.write(frame)
        currentBytes += 4 + len
        currentFrames++
    }

    private fun fsyncLocked() {
        try {
            raf?.fd?.sync()
        } catch (e: Exception) {
            Log.w(TAG, "fsync failed: ${e.message}")
        }
    }

    private fun closeCurrentLocked(reason: String) {
        val out = raf ?: return
        try {
            out.fd.sync()
        } catch (_: Exception) {
        }
        try {
            out.close()
        } catch (_: Exception) {
        }
        Log.i(TAG, "closed batch file ${currentFile?.name} ($currentFrames frames, $currentBytes bytes, reason=$reason)")
        raf = null
        currentFile = null
        currentStartSec = 0
        currentBytes = 0
        currentFrames = 0
        lastFrameMs = 0
        clearJournal()
    }

    // ── Journal (so Flutter never ingests the file being written) ──

    private fun writeJournal(dir: File, filename: String) {
        try {
            File(dir, JOURNAL_NAME).writeText(filename)
        } catch (e: Exception) {
            Log.w(TAG, "journal write failed: ${e.message}")
        }
    }

    private fun clearJournal() {
        try {
            val dir = currentFile?.parentFile ?: loadConfig()?.dir?.let { File(it) }
            if (dir != null) File(dir, JOURNAL_NAME).delete()
        } catch (_: Exception) {
        }
    }

    // ── Frame extraction (mirrors OmiBackgroundAudioStreamer.transformFrames) ──

    private fun transformFrames(deviceType: String, value: ByteArray): List<ByteArray> =
        when (deviceType) {
            "omi", "openglass" -> if (value.size <= 3) emptyList() else listOf(value.copyOfRange(3, value.size))
            "friendPendant" -> {
                if (value.size <= 5) {
                    emptyList()
                } else {
                    val payload = value.copyOfRange(0, value.size - 5)
                    val frames = mutableListOf<ByteArray>()
                    var offset = 0
                    while (offset + 30 <= payload.size) {
                        frames.add(payload.copyOfRange(offset, offset + 30))
                        offset += 30
                    }
                    frames
                }
            }
            else -> {
                Log.w(TAG, "unsupported batch device type: $deviceType")
                emptyList()
            }
        }

    private fun matches(config: Config, serviceUuid: String, characteristicUuid: String): Boolean =
        config.serviceUuid.equals(serviceUuid, ignoreCase = true) &&
            config.characteristicUuid.equals(characteristicUuid, ignoreCase = true)

    // ── Config + prefs ──

    private fun loadConfig(): Config? {
        if (!boolPref("batchModeEnabled", false)) return null
        val dir = stringPref("batchAudioDir")
        if (dir.isEmpty()) return null
        val raw = stringPref("nativeBleStreamConfig")
        if (raw.isEmpty()) return null
        return try {
            val json = JSONObject(raw)
            val deviceId = json.optString("deviceId")
            val serviceUuid = json.optString("serviceUuid").lowercase(Locale.US)
            val characteristicUuid = json.optString("characteristicUuid").lowercase(Locale.US)
            if (deviceId.isEmpty() || serviceUuid.isEmpty() || characteristicUuid.isEmpty()) return null
            Config(
                deviceId = deviceId,
                codec = json.optString("codec", "opus"),
                sampleRate = json.optInt("sampleRate", 16000),
                serviceUuid = serviceUuid,
                characteristicUuid = characteristicUuid,
                deviceType = json.optString("deviceType", "omi"),
                dir = dir,
            )
        } catch (e: Exception) {
            Log.w(TAG, "invalid batch config: ${e.message}")
            null
        }
    }

    private fun setStorageFullFlag(full: Boolean) {
        try {
            prefs().edit().putBoolean("flutter.batchStorageFull", full).apply()
        } catch (_: Exception) {
        }
    }

    private fun prefs() = context.getSharedPreferences(FLUTTER_PREFS, Context.MODE_PRIVATE)

    private fun prefValue(key: String): Any? = prefs().all["flutter.$key"]

    private fun stringPref(key: String, defaultValue: String = ""): String =
        when (val value = prefValue(key)) {
            is String -> value
            null -> defaultValue
            else -> value.toString()
        }

    private fun boolPref(key: String, defaultValue: Boolean): Boolean =
        when (val value = prefValue(key)) {
            is Boolean -> value
            is String -> value.toBooleanStrictOrNull() ?: defaultValue
            else -> defaultValue
        }
}
