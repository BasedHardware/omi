package com.friend.ios.batch

import com.friend.ios.ble.OmiBleManager

import android.content.Context
import android.content.SharedPreferences
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
abstract class BaseBatchAudioWriter internal constructor(
    private val recoveryPrefix: String,
    private val preferences: () -> SharedPreferences,
    private val notifyFinalized: (String) -> Unit,
    private val log: (Int, String) -> Unit,
    private val openFile: (File) -> RandomAccessFile = { RandomAccessFile(it, "rw") },
) {
    constructor(context: Context, tag: String, recoveryPrefix: String) : this(
        recoveryPrefix,
        { context.getSharedPreferences(FLUTTER_PREFS, Context.MODE_PRIVATE) },
        { fileName ->
            if (OmiBleManager.isFlutterAlive) {
                val mgr = OmiBleManager.instance
                mgr.mainHandler.post { mgr.flutterApi?.onBatchRecordingFinalized(fileName) {} }
            }
        },
        { priority, message -> Log.println(priority, tag, message) },
    )

    companion object {
        const val FLUTTER_PREFS = "FlutterSharedPreferences"
        const val PART_SUFFIX = ".part" // active (still-being-written) files end .bin.part
        private const val FSYNC_INTERVAL_MS = 2_000L
        private const val MIN_FREE_BYTES = 200L * 1024 * 1024 // stop writing below 200 MB free
    }

    protected val lock = Any()
    private var raf: RandomAccessFile? = null
    private val frameEncoder = BatchFrameEncoder()
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
    private var contentsTrusted = true

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
            log(Log.ERROR, "cannot create batch dir $dirPath")
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
                log(Log.WARN, "storage low (${dir.usableSpace} bytes free) — pausing batch capture")
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
            val out = openFile(file)
            try {
                if (out.length() > 0) {
                    BatchFrameEncoder.recover(out)
                    out.fd.sync()
                }
            } catch (error: Exception) {
                runCatching { out.close() }
                throw error
            }
            raf = out
            currentFile = file
            currentStartSec = startSec
            currentBytes = out.length()
            contentsTrusted = true
            currentFrames = 0
            lastFsyncMs = nowMs
            runCatching { onOpenedLocked(file) }
                .onFailure { error -> log(Log.WARN, "metadata hook failed: ${error.javaClass.simpleName}") }
            log(Log.INFO, "opened batch file $fileName")
            true
        } catch (e: Exception) {
            log(Log.ERROR, "open failed for $fileName: ${e.message}")
            raf = null
            currentFile = null
            false
        }
    }

    /** Append frames with the length-prefixed layout. On failure the current file is
     *  finalized after successful rollback, or held for repair if rollback fails. */
    protected fun writeFramesLocked(frames: List<ByteArray>): Boolean {
        val out = raf ?: return false
        return try {
            for (frame in frames) {
                currentBytes += frameEncoder.write(out, frame, currentBytes)
                currentFrames++
            }
            true
        } catch (e: Exception) {
            log(Log.ERROR, "write failed: ${e.message}")
            if (e is BatchFrameRollbackException) contentsTrusted = false
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
            log(Log.WARN, "fsync failed: ${e.message}")
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
                if (!contentsTrusted) {
                    closeSyncFailed = true
                    log(Log.WARN, "rollback failed — leaving ${partFile.name} pending repair")
                } else if (currentBytes > 0 && synced) {
                    // Atomically promote .bin.part -> .bin so it becomes ingestable.
                    val finalFile = File(partFile.parentFile, partFile.name.removeSuffix(PART_SUFFIX))
                    if (partFile.renameTo(finalFile)) {
                        log(Log.INFO, "finalized ${finalFile.name} ($currentFrames frames, $currentBytes bytes, reason=$reason)")
                        notifyFinalized(finalFile.name)
                    } else {
                        log(Log.WARN, "failed to finalize ${partFile.name}")
                    }
                } else if (currentBytes > 0) {
                    // Durability unconfirmed — hold the ACK barrier and leave the
                    // .part for stale-part recovery instead of publishing it.
                    closeSyncFailed = true
                    log(Log.WARN, "close fsync failed — leaving ${partFile.name} unfinalized")
                } else {
                    partFile.delete() // nothing written — drop the empty placeholder
                    deleteRecordingGeolocationSidecars(partFile)
                }
            }
            raf = null
            currentFile = null
            currentStartSec = 0
            currentBytes = 0
            currentFrames = 0
            contentsTrusted = true
        }
        onClosedLocked()
    }

    /** Hook for subclasses to reset their gap/session tracking when a file closes. */
    protected open fun onClosedLocked() {}

    /** Hook for recording-owned metadata that must be copied beside a new file. */
    protected open fun onOpenedLocked(partFile: File) {}

    // ── Crash recovery ──

    /** Validate and durably repair stale parts before publishing their complete prefix.
     *  Failed repairs remain pending; empty placeholders are deleted. */
    private fun recoverStalePartFiles(dir: File) {
        try {
            val parts = dir.listFiles { f ->
                f.isFile && f.name.startsWith(recoveryPrefix) && f.name.endsWith(".bin$PART_SUFFIX")
            } ?: return
            for (p in parts) {
                val completeBytes = try {
                    openFile(p).use { out ->
                        BatchFrameEncoder.recover(out).also { out.fd.sync() }
                    }
                } catch (error: Exception) {
                    log(Log.WARN, "batch recovery failed: ${error.javaClass.simpleName}")
                    continue
                }
                if (completeBytes > 0L) {
                    val finalFile = File(dir, p.name.removeSuffix(PART_SUFFIX))
                    if (p.renameTo(finalFile)) log(Log.INFO, "recovered stale batch file -> ${finalFile.name}")
                } else {
                    p.delete()
                    deleteRecordingGeolocationSidecars(p)
                }
            }
        } catch (e: Exception) {
            log(Log.WARN, "recoverStalePartFiles failed: ${e.message}")
        }
    }

    private fun deleteRecordingGeolocationSidecars(partFile: File) {
        val audioPath = partFile.path.removeSuffix(PART_SUFFIX)
        if (File(audioPath).exists()) return
        File(audioPath + NATIVE_BATCH_GEOLOCATION_SIDECAR_SUFFIX).delete()
        File(audioPath + NATIVE_BATCH_GEOLOCATION_SIDECAR_SUFFIX + PART_SUFFIX).delete()
    }

    // ── Config + prefs ──

    private fun setStorageFullFlag(full: Boolean) {
        try {
            prefs().edit().putBoolean("flutter.batchStorageFull", full).apply()
        } catch (_: Exception) {
        }
    }

    protected fun prefs() = preferences()

    private val preferenceValues by lazy { SharedPreferencesValues(prefs()) }

    protected fun stringPref(key: String, defaultValue: String = ""): String =
        preferenceValues.string(key, defaultValue)

    protected fun boolPref(key: String, defaultValue: Boolean): Boolean =
        preferenceValues.boolean(key, defaultValue)
}
