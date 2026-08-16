package com.friend.ios.phonemic

import com.friend.ios.batch.BaseBatchAudioWriter

import android.content.Context

/**
 * Batch (transcribe-later) capture sink for the phone microphone — the Kotlin peer of
 * iOS `PhoneMicBatchAudioWriter`. The file mechanics (length-prefixed layout, `.part`
 * promotion, fsync, crash recovery, free-space guard) live in [BaseBatchAudioWriter];
 * this class owns the same policy the BLE [com.friend.ios.batch.OmiBatchAudioWriter]
 * owns — mute/cut prefs, silence-gap finalize, size/duration rotation.
 *
 * What differs from OmiBatchAudioWriter, and why:
 *  - Packets arrive **already opus-encoded** from the module's own [PhoneMicOpusEncoder]
 *    (there is no per-device frame extraction or codec config to match); the caller just
 *    hands over finished packets to write.
 *  - The output [dirPath] is fixed once at session bring-up (a missing/empty
 *    `flutter.batchAudioDir` fails the session with `batch_dir_unavailable` before this
 *    writer is constructed), so it is never re-read per append.
 *  - There is **no `batchModeEnabled` gate**: automatic offline fallback runs this writer
 *    with that pref false, so gating on it would silently drop every offline recording.
 *
 * Confinement: [append], [closeNow] and [consumeStorageFullTransition] are all called
 * on the controller's single serial executor. Each takes [lock] for base-state access
 * exactly like the BLE sibling, so [closeNow] is a synchronous finalize by the time it
 * returns.
 *
 * The recovery prefix `audio_omibatchphone` has no trailing underscore intentionally: it
 * matches both the manual (`omibatchphone_…`) and automatic (`omibatchphoneauto_…`)
 * markers, and nothing else — it is disjoint from the BLE writer's `audio_omibatch_` and
 * the Limitless writer's `audio_omibatchlimitless_`.
 */
class PhoneMicBatchAudioWriter(context: Context, private val dirPath: String) :
    BaseBatchAudioWriter(context, TAG, "audio_omibatchphone") {

    /**
     * Session total of frames durably accepted by the writer (each = one 20ms opus
     * packet), driving `onBatchProgress`. Advanced only after [writeFramesLocked]
     * succeeds — pre-fsync, iOS-identical — so muted / storage-full / gapped periods
     * never move it.
     */
    var sessionFramesWritten: Long = 0
        private set

    private var lastFrameMs: Long = 0

    // Latched false->true storage-full edge, drained once per transition by the
    // controller's heartbeat so a single onCaptureError fires per storage-full event.
    private var pendingStorageFullReport = false
    private var wasStorageFull = false

    /**
     * Append the opus packets for one converted PCM chunk. Called on the writer's serial
     * executor. [marker] is session-constant (`omibatchphone` / `omibatchphoneauto`) and
     * only shapes the file name. Policy order mirrors iOS `PhoneMicBatchAudioWriter.append`
     * + `OmiBatchAudioWriter.handleCharacteristic`.
     */
    fun append(packets: List<ByteArray>, marker: String) {
        if (packets.isEmpty()) return
        synchronized(lock) {
            val now = System.currentTimeMillis()

            // Muted: drop packets but keep the open file's gap timer fresh so unmute
            // resumes the SAME file instead of opening a new one.
            if (boolPref("batchMuted", false)) {
                if (isOpenLocked) lastFrameMs = now
                return
            }
            // Manual "New recording": finalize the current file now; these packets then
            // open a fresh one.
            if (boolPref("batchCutRequested", false)) {
                prefs().edit().putBoolean("flutter.batchCutRequested", false).apply()
                closeCurrentLocked("manual")
            }
            // Lazy gap finalize: a pause longer than GAP_MS (computed here on the next
            // append, no timer) starts a new file so the backend places resumed audio as
            // a separate conversation.
            if (isOpenLocked && lastFrameMs > 0 && now - lastFrameMs > GAP_MS) {
                closeCurrentLocked("gap")
            }
            // Rotation: bound file size/duration (between packets, never mid-packet).
            if (isOpenLocked && (currentBytes >= MAX_FILE_BYTES || (now / 1000 - currentStartSec) >= MAX_FILE_SECONDS)) {
                closeCurrentLocked("rotate")
            }

            if (!isOpenLocked) {
                val startSec = now / 1000
                // codec opus_fs320 (20ms frames), 16kHz mono — mirrors the BLE/pendant
                // batch naming so the Dart scanner (`audio_omibatch*`) and backend both match.
                val name = "audio_${marker}_opus_fs320_16000_1_fs320_${startSec}.bin$PART_SUFFIX"
                if (!openLocked(dirPath, name, startSec, now)) {
                    noteStorageFullTransitionLocked() // open refused — likely the free-space guard
                    return
                }
                wasStorageFull = false // a successful open means storage recovered
            }

            if (!writeFramesLocked(packets)) return
            sessionFramesWritten += packets.size
            lastFrameMs = now
            maybeFsyncLocked(now)
        }
    }

    /**
     * Synchronous finalize (fsync + atomic `.part` -> `.bin` promote). The controller
     * calls this from its serial executor, so the file is ingestable by the time this
     * returns and the Pigeon stop() future can resolve.
     */
    fun closeNow(reason: String) {
        synchronized(lock) { closeCurrentLocked(reason) }
    }

    /**
     * Drain the latched storage-full transition. Called on the controller's ~1Hz
     * heartbeat (same executor) so at most one onCaptureError fires per false->true edge.
     */
    fun consumeStorageFullTransition(): Boolean =
        synchronized(lock) {
            val pending = pendingStorageFullReport
            pendingStorageFullReport = false
            pending
        }

    override fun onClosedLocked() {
        lastFrameMs = 0
    }

    /**
     * The base cannot report *why* an open failed, so read `flutter.batchStorageFull`
     * back — the base's `openLocked` just wrote it via `.apply()` (synchronous in-memory)
     * when the free-space guard tripped. Latch only the false->true edge; [wasStorageFull]
     * (reset on a successful open) keeps a sustained storage-full run from re-latching.
     */
    private fun noteStorageFullTransitionLocked() {
        if (boolPref("batchStorageFull", false) && !wasStorageFull) {
            wasStorageFull = true
            pendingStorageFullReport = true
        }
    }

    companion object {
        private const val TAG = "PhoneMic.BatchWriter"
        private const val MAX_FILE_BYTES = 32L * 1024 * 1024 // ~32 MB per file
        private const val MAX_FILE_SECONDS = 900L // 15 min per file
        private const val GAP_MS = 30_000L // start a new file after this silence gap
    }
}
