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
 * Files are named `audio_omibatch_{codec}_{sampleRate}_{channel}_fs{frameSize}_{startSec}.bin`
 * (the `omibatch` device marker distinguishes these from offline-sync WAL files,
 * which share this directory; the backend treats the device segment as a label.)
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
        private const val PART_SUFFIX = ".part" // active (still-being-written) files end .bin.part
        private const val MAX_FILE_BYTES = 32L * 1024 * 1024 // ~32 MB per file
        private const val MAX_FILE_SECONDS = 900L // 15 min per file
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
    private var recovered = false

    @Volatile
    private var wasEnabled = false

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
            // Offline mode is off (the common case). Finalize an in-progress file only on the
            // enabled->disabled edge — don't take the lock on every packet when batch mode is off.
            if (wasEnabled) {
                wasEnabled = false
                closeCurrent("disabled")
            }
            return
        }
        wasEnabled = true
        if (!config.deviceId.equals(address, ignoreCase = true)) return
        if (!matches(config, serviceUuid, characteristicUuid)) return

        // Muted: drop the packet but keep the open file's gap timer alive so unmute
        // resumes the same recording instead of starting a new one.
        if (boolPref("batchMuted", false)) {
            synchronized(lock) { if (raf != null) lastFrameMs = System.currentTimeMillis() }
            return
        }
        // Manual "New recording": finalize the current file now; this packet opens a fresh one.
        if (boolPref("batchCutRequested", false)) {
            prefs().edit().putBoolean("flutter.batchCutRequested", false).apply()
            closeCurrent("manual")
        }

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
        // Recover from a previous process that died mid-write: any leftover .bin.part
        // is a finalized-by-crash orphan — promote it to .bin so it becomes ingestable.
        if (!recovered) {
            recovered = true
            recoverStalePartFiles(dir)
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
        // Tag the device segment as `omibatch` so the Dart scanner can tell batch
        // recordings apart from offline-sync WAL flushes, which share this directory
        // and the same audio_*.bin naming. The backend ignores this segment; keep it
        // in sync with Dart's `batchRecordingDevice`.
        // Write to a .bin.part file while active; rename to .bin only once finalized so
        // Flutter (which scans *.bin) never picks up a half-written file.
        val name = "audio_omibatch_${config.codec}_${config.sampleRate}_1_fs${frameSize}_${startSec}.bin$PART_SUFFIX"
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
        val partFile = currentFile
        try {
            out.fd.sync()
        } catch (_: Exception) {
        }
        try {
            out.close()
        } catch (_: Exception) {
        }
        if (partFile != null) {
            if (currentBytes > 0) {
                // Atomically promote .bin.part -> .bin so it becomes ingestable.
                val finalFile = File(partFile.parentFile, partFile.name.removeSuffix(PART_SUFFIX))
                val renamed = partFile.renameTo(finalFile)
                if (!renamed) Log.w(TAG, "failed to finalize ${partFile.name}")
                Log.i(TAG, "finalized ${finalFile.name} ($currentFrames frames, $currentBytes bytes, reason=$reason)")
                if (renamed) notifyFinalized(finalFile.name)
            } else {
                partFile.delete() // nothing written — drop the empty placeholder
            }
        }
        raf = null
        currentFile = null
        currentStartSec = 0
        currentBytes = 0
        currentFrames = 0
        lastFrameMs = 0
    }

    /** Notify Dart (when the engine is alive) that a file finalized, so the
     *  recordings list rescans without waiting for a BLE disconnect. */
    private fun notifyFinalized(fileName: String) {
        if (!OmiBleManager.isFlutterAlive) return
        val mgr = OmiBleManager.instance
        mgr.mainHandler.post { mgr.flutterApi?.onBatchRecordingFinalized(fileName) {} }
    }

    // ── Crash recovery ──

    /** Promote any leftover `*.bin.part` from a previous (crashed) process to `.bin`
     *  so finalized-by-crash recordings are not lost. Empty placeholders are deleted. */
    private fun recoverStalePartFiles(dir: File) {
        try {
            val parts = dir.listFiles { f ->
                f.isFile && f.name.startsWith("audio_") && f.name.endsWith(".bin$PART_SUFFIX")
            } ?: return
            for (p in parts) {
                if (p.length() > 0L) {
                    val finalFile = File(dir, p.name.removeSuffix(PART_SUFFIX))
                    if (p.renameTo(finalFile)) Log.i(TAG, "recovered stale batch file -> ${finalFile.name}")
                } else {
                    p.delete()
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "recoverStalePartFiles failed: ${e.message}")
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
