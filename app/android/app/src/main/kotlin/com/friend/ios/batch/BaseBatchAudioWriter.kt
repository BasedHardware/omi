package com.friend.ios.batch

import com.friend.ios.ble.OmiBleManager

import android.content.Context
import android.util.Log
import java.io.File
import java.io.RandomAccessFile

/**
 * Shared file mechanics for native batch (offline) capture sinks. Subclasses decide
 * *policy* — which frames to write, file naming, and when to rotate/finalize — while
 * this base owns the *mechanics* every sink must get right identically:
 *
 *  - length-prefixed frame layout: [4-byte LE uint32 frame_length][frame bytes] ...
 *  - writing to a `.bin.part` file, atomically renamed to `.bin` on finalize so the
 *    Dart scanner (which only ingests `*.bin`) never sees a half-written file
 *  - periodic fsync for crash durability, plus an explicit fsync barrier
 *  - stale `.bin.part` recovery after a crashed process
 *  - free-space guard (pause + `flutter.batchStorageFull` flag instead of failing)
 *  - `onBatchRecordingFinalized` Pigeon notify so the recordings list rescans
 *
 * Implementations: [OmiBatchAudioWriter] (BLE-notification-driven, wall-clock files)
 * and [LimitlessBatchAudioWriter] (flash-drain-driven, pendant-timestamped files).
 */
abstract class BaseBatchAudioWriter(
    protected val context: Context,
    private val tag: String,
    private val recoveryPrefix: String,
) {
    companion object {
        const val FLUTTER_PREFS = "FlutterSharedPreferences"
        const val PART_SUFFIX = ".part" // active (still-being-written) files end .bin.part
        private const val FSYNC_INTERVAL_MS = 2_000L
        private const val MIN_FREE_BYTES = 200L * 1024 * 1024 // stop writing below 200 MB free
    }

    protected val lock = Any()
    private var raf: RandomAccessFile? = null
    private var currentFile: File? = null

    protected var currentStartSec: Long = 0
        private set
    protected var currentBytes: Long = 0
        private set
    protected var currentFrames: Long = 0
        private set

    private var lastFsyncMs: Long = 0
    private var storageFull = false
    private var recovered = false
    private var closeSyncFailed = false

    protected val isOpenLocked: Boolean
        get() = raf != null

    /** Finalize + fsync the current file (e.g. on disconnect or service destroy). */
    fun stop(reason: String) {
        synchronized(lock) { closeCurrentLocked(reason) }
    }

    // ── File lifecycle (caller holds [lock]) ──

    /**
     * Open [fileName] (a `.bin.part` name produced by the subclass) inside [dirPath]
     * for appending. Returns false when the directory can't be created, storage is
     * low (guard engaged), or the open fails — the caller drops the frames.
     */
    protected fun openLocked(dirPath: String, fileName: String, startSec: Long, nowMs: Long): Boolean {
        if (raf != null) return true

        val dir = File(dirPath)
        if (!dir.exists() && !dir.mkdirs()) {
            Log.e(tag, "cannot create batch dir $dirPath")
            return false
        }
        // Recover from a previous process that died mid-write: any leftover .bin.part
        // is a finalized-by-crash orphan — promote it to .bin so it becomes ingestable.
        if (!recovered) {
            recovered = true
            recoverStalePartFiles(dir)
        }
        if (dir.usableSpace < MIN_FREE_BYTES) {
            if (!storageFull) {
                Log.w(tag, "storage low (${dir.usableSpace} bytes free) — pausing batch capture")
                setStorageFullFlag(true)
                storageFull = true
            }
            return false
        }
        if (storageFull) {
            storageFull = false
            setStorageFullFlag(false)
        }

        val file = File(dir, fileName)
        return try {
            val out = RandomAccessFile(file, "rw")
            out.seek(out.length()) // append-safe (same-second restart reuses the file)
            raf = out
            currentFile = file
            currentStartSec = startSec
            currentBytes = file.length()
            currentFrames = 0
            lastFsyncMs = nowMs
            Log.i(tag, "opened batch file $fileName")
            true
        } catch (e: Exception) {
            Log.e(tag, "open failed for $fileName: ${e.message}")
            raf = null
            currentFile = null
            false
        }
    }

    /** Append frames with the length-prefixed layout. On failure the current file is
     *  finalized (what was written so far stays durable) and false is returned. */
    protected fun writeFramesLocked(frames: List<ByteArray>): Boolean {
        val out = raf ?: return false
        return try {
            for (frame in frames) {
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
            true
        } catch (e: Exception) {
            Log.e(tag, "write failed: ${e.message}")
            try {
                out.setLength(currentBytes) // drop a torn frame tail; keep only complete frames
            } catch (_: Exception) {
            }
            closeCurrentLocked("write_error")
            false
        }
    }

    protected fun maybeFsyncLocked(nowMs: Long) {
        if (nowMs - lastFsyncMs >= FSYNC_INTERVAL_MS) {
            fsyncLocked()
            lastFsyncMs = nowMs
        }
    }

    protected fun fsyncLocked(): Boolean =
        try {
            raf?.fd?.sync()
            true
        } catch (e: Exception) {
            Log.w(tag, "fsync failed: ${e.message}")
            false
        }

    protected fun consumeCloseSyncFailureLocked(): Boolean {
        val failed = closeSyncFailed
        closeSyncFailed = false
        return failed
    }

    protected fun closeCurrentLocked(reason: String) {
        val out = raf
        if (out != null) {
            val partFile = currentFile
            var synced = true
            try {
                out.fd.sync()
            } catch (_: Exception) {
                synced = false
            }
            try {
                out.close()
            } catch (_: Exception) {
            }
            if (partFile != null) {
                if (currentBytes > 0 && synced) {
                    // Atomically promote .bin.part -> .bin so it becomes ingestable.
                    val finalFile = File(partFile.parentFile, partFile.name.removeSuffix(PART_SUFFIX))
                    if (partFile.renameTo(finalFile)) {
                        Log.i(tag, "finalized ${finalFile.name} ($currentFrames frames, $currentBytes bytes, reason=$reason)")
                        notifyFinalized(finalFile.name)
                    } else {
                        Log.w(tag, "failed to finalize ${partFile.name}")
                    }
                } else if (currentBytes > 0) {
                    // Durability unconfirmed — hold the ACK barrier and leave the
                    // .part for stale-part recovery instead of publishing it.
                    closeSyncFailed = true
                    Log.w(tag, "close fsync failed — leaving ${partFile.name} unfinalized")
                } else {
                    partFile.delete() // nothing written — drop the empty placeholder
                }
            }
            raf = null
            currentFile = null
            currentStartSec = 0
            currentBytes = 0
            currentFrames = 0
        }
        onClosedLocked()
    }

    /** Hook for subclasses to reset their gap/session tracking when a file closes. */
    protected open fun onClosedLocked() {}

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
                f.isFile && f.name.startsWith(recoveryPrefix) && f.name.endsWith(".bin$PART_SUFFIX")
            } ?: return
            for (p in parts) {
                if (p.length() > 0L) {
                    val finalFile = File(dir, p.name.removeSuffix(PART_SUFFIX))
                    if (p.renameTo(finalFile)) Log.i(tag, "recovered stale batch file -> ${finalFile.name}")
                } else {
                    p.delete()
                }
            }
        } catch (e: Exception) {
            Log.w(tag, "recoverStalePartFiles failed: ${e.message}")
        }
    }

    // ── Config + prefs ──

    private fun setStorageFullFlag(full: Boolean) {
        try {
            prefs().edit().putBoolean("flutter.batchStorageFull", full).apply()
        } catch (_: Exception) {
        }
    }

    protected fun prefs() = context.getSharedPreferences(FLUTTER_PREFS, Context.MODE_PRIVATE)

    private fun prefValue(key: String): Any? = prefs().all["flutter.$key"]

    protected fun stringPref(key: String, defaultValue: String = ""): String =
        when (val value = prefValue(key)) {
            is String -> value
            null -> defaultValue
            else -> value.toString()
        }

    protected fun boolPref(key: String, defaultValue: Boolean): Boolean =
        when (val value = prefValue(key)) {
            is Boolean -> value
            is String -> value.toBooleanStrictOrNull() ?: defaultValue
            else -> defaultValue
        }
}
