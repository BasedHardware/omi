package com.friend.ios.batch

import com.friend.ios.ble.OmiBleManager
import com.friend.ios.limitless.LimitlessPageDeduplicator

import android.content.Context
import java.io.File
import java.io.RandomAccessFile
import java.util.Locale
import kotlin.math.abs

/**
 * Batch (offline) capture sink for the Limitless pendant. Unlike [OmiBatchAudioWriter]
 * (which is fed live BLE notifications), this writer is fed opus frames extracted from
 * the pendant's onboard flash pages by the native flash-drain engine — the pendant
 * records on its own and the phone periodically drains its storage.
 *
 * Differences in policy, enabled by the flash-page metadata:
 *  - Files are named and segmented by the **pendant-clock capture time** of the first
 *    page (`timestamp_ms`), not by phone wall-clock at open — recordings carry their
 *    true start time even when drained minutes or hours after capture.
 *  - A new file starts when consecutive pages are more than [SESSION_GAP_MS] apart
 *    (the pendant wasn't recording in between) or after [MAX_AUDIO_SECONDS] of audio
 *    (frames/50 — opus_fs320 is 50 frames per second), mirroring the Omi 15-min cap.
 *  - The device marker is `omibatchlimitless`: the `omibatch` prefix keeps the Dart
 *    recordings scanner matching, and the `limitless` substring makes the backend tag
 *    the resulting conversation `source=limitless`.
 *
 * ACK safety: each page append fsyncs its audio and synchronously persists a
 * per-device/session page watermark. A redrain after an ambiguous ACK therefore
 * recognizes the durable page instead of appending it twice. The drain engine also
 * calls [sync] before sending the cumulative pendant-deletion ACK.
 */
class LimitlessBatchAudioWriter(context: Context) : BaseBatchAudioWriter(context, TAG, "audio_${DEVICE_MARKER}_") {
    companion object {
        private const val TAG = "OmiBle.LimitlessWriter"
        const val DEVICE_MARKER = "omibatchlimitless"
        private const val SESSION_GAP_MS = 120_000L // >120s between page timestamps = new session
        private const val MAX_AUDIO_SECONDS = 900L // 15 min of audio per file
        private const val FRAMES_PER_SECOND = 50L // opus_fs320 = 20 ms frames
        private const val MIN_VALID_TS_MS = 1_577_836_800_000L // 2020-01-01: pendant clock sanity gate
        private const val PENDING_PATH_KEY = "limitlessPendingAppend.path"
        private const val PENDING_OFFSET_KEY = "limitlessPendingAppend.offset"
    }

    private var lastPageTimestampMs: Long = 0

    /**
     * Append the opus frames extracted from one flash page. [pageTimestampMs] is the
     * pendant-clock capture time of that page. Returns true once the frames are
     * written and its durable identity is committed.
     */
    fun append(
        deviceId: String,
        pageIndex: Int,
        session: Int,
        frames: List<ByteArray>,
        pageTimestampMs: Long,
    ): Boolean {
        if (frames.isEmpty()) return true
        val now = System.currentTimeMillis()

        synchronized(lock) {
            if (!recoverPendingAppendLocked()) return false
            val watermarkKey = pageWatermarkKey(deviceId, session)
            val deduplicator = LimitlessPageDeduplicator(
                readWatermark = { prefs().getInt(it, Int.MIN_VALUE) },
                writeWatermark = { key, value ->
                    prefs().edit()
                        .putInt(key, value)
                        .remove(PENDING_PATH_KEY)
                        .remove(PENDING_OFFSET_KEY)
                        .commit()
                },
            )
            if (deduplicator.isDurable(watermarkKey, pageIndex)) return true

            // Pendant clock sanity: pages recorded before the first msg6 time-sync carry
            // a bogus epoch. Inside an open session inherit the last valid timestamp so a
            // bogus page can't fake a session gap; otherwise fall back to drain wall-clock.
            val ts = when {
                pageTimestampMs > MIN_VALID_TS_MS -> pageTimestampMs
                lastPageTimestampMs > 0 -> lastPageTimestampMs
                else -> now
            }
            if (isOpenLocked && lastPageTimestampMs > 0 && abs(ts - lastPageTimestampMs) > SESSION_GAP_MS) {
                closeCurrentLocked("session_gap")
            }
            if (isOpenLocked && currentFrames >= MAX_AUDIO_SECONDS * FRAMES_PER_SECOND) {
                closeCurrentLocked("rotate")
            }

            if (!isOpenLocked) {
                val dir = stringPref("batchAudioDir")
                if (dir.isEmpty()) return false
                var startSec = ts / 1000
                // A finalize replaces an existing same-name .bin — never reuse a taken name.
                while (File(dir, "audio_${DEVICE_MARKER}_opus_fs320_16000_1_fs320_${startSec}.bin").exists()) {
                    startSec++
                }
                val name = "audio_${DEVICE_MARKER}_opus_fs320_16000_1_fs320_${startSec}.bin$PART_SUFFIX"
                if (!openLocked(dir, name, startSec, now)) return false // storage full or open failed
            }

            val checkpoint = checkpointLocked()
            val path = currentFilePathLocked() ?: return false
            if (!prefs().edit()
                    .putString(PENDING_PATH_KEY, path)
                    .putLong(PENDING_OFFSET_KEY, checkpoint.first)
                    .commit()
            ) {
                return false
            }
            val appended = deduplicator.appendOnce(
                watermarkKey,
                pageIndex,
                appendDurably = { writeFramesLocked(frames) && fsyncLocked() },
                rollback = { rollbackLocked(checkpoint) },
            )
            if (!appended) {
                clearPendingAppend()
                return false
            }
            lastPageTimestampMs = ts
            return true
        }
    }

    private fun pageWatermarkKey(deviceId: String, session: Int): String =
        "limitlessPageWatermark.${deviceId.uppercase(Locale.US)}.session$session"

    private fun recoverPendingAppendLocked(): Boolean {
        val path = prefs().getString(PENDING_PATH_KEY, null) ?: return true
        val offset = prefs().getLong(PENDING_OFFSET_KEY, -1L)
        if (offset < 0L) return clearPendingAppend()
        return try {
            val file = File(path)
            if (file.exists()) {
                RandomAccessFile(file, "rw").use {
                    it.setLength(offset)
                    it.fd.sync()
                }
            }
            clearPendingAppend()
        } catch (_: Exception) {
            false
        }
    }

    private fun clearPendingAppend(): Boolean =
        prefs().edit().remove(PENDING_PATH_KEY).remove(PENDING_OFFSET_KEY).commit()

    /** Fsync barrier: returns true when everything appended so far is durable on disk.
     *  The drain engine must get `true` here before ACKing the covered pages. */
    fun sync(): Boolean = synchronized(lock) { !consumeCloseSyncFailureLocked() && (!isOpenLocked || fsyncLocked()) }

    override fun onClosedLocked() {
        lastPageTimestampMs = 0
    }
}
