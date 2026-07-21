import Foundation

/// Batch (transcribe-later) capture sink for the phone microphone. The BLE
/// `OmiBatchAudioWriter` is fed live device notifications; this writer is fed
/// programmatically by `PhoneMicController` with opus packets already produced by
/// `PhoneMicOpusEncoder`. It owns the same policy as the BLE writer — mute/cut
/// prefs, silence-gap finalize, size/duration rotation — while the shared
/// file mechanics (length-prefixed layout, `.part` promotion, fsync, crash
/// recovery, free-space guard) live in `BaseBatchAudioWriter`.
///
/// Queue: constructed with the controller's audio queue, so `append` and the
/// controller's synchronous close both run on that one queue. Everything here is
/// `queue`-confined; callers must already be on it (the controller calls append
/// from the tap's audioQueue block and close from `audioQueue.sync`).
final class PhoneMicBatchAudioWriter: BaseBatchAudioWriter {
    private let dir: String

    private let maxFileBytes: Int64 = 32 * 1024 * 1024 // ~32 MB per file
    private let maxFileSeconds: Int64 = 900 // 15 min per file
    private let gapMs: Int64 = 30_000 // start a new file after this silence gap

    private var lastAppendMs: Int64 = 0
    /// Session total of frames durably written (each = one 20ms opus packet). Drives
    /// onBatchProgress; muted/interrupted/storage-full periods never advance it.
    private(set) var sessionFramesWritten: Int64 = 0
    /// Latched false->true storage-full edge, drained once by the controller so it
    /// emits a single onCaptureError per session transition.
    private var pendingStorageFullReport = false
    private var wasStorageFull = false

    /// `dir` is resolved once at bring-up (a missing/empty `flutter.batchAudioDir`
    /// fails the session with batch_dir_unavailable before this writer is created),
    /// so it is never re-checked per append. The recovery prefix `audio_omibatchphone`
    /// intentionally matches both the manual (`omibatchphone`) and auto
    /// (`omibatchphoneauto`) markers, and nothing else.
    init(dir: String, queue: DispatchQueue) {
        self.dir = dir
        super.init(
            tag: "PhoneBatchWriter",
            queueLabel: "com.omi.phoneBatchWriter",
            recoveryPrefix: "audio_omibatchphone",
            queue: queue
        )
    }

    // MARK: - Writing (on `queue`)

    /// Append the opus packets for one converted PCM chunk. Must be called on the
    /// writer's queue (the controller's audio queue). `marker` is session-constant
    /// (`omibatchphone` / `omibatchphoneauto`) and only shapes the file name.
    func append(opusPackets: [Data], marker: String) {
        if opusPackets.isEmpty { return }
        let d = UserDefaults.standard
        let nowMs = Int64(Date().timeIntervalSince1970 * 1000)

        // Muted: drop packets but keep the open file's gap timer fresh so unmute
        // resumes the same recording instead of opening a new file.
        if d.bool(forKey: "flutter.batchMuted") {
            if isOpen { lastAppendMs = nowMs }
            return
        }
        // Manual "New recording": finalize now so these packets open a fresh file.
        if d.bool(forKey: "flutter.batchCutRequested") {
            d.set(false, forKey: "flutter.batchCutRequested")
            closeCurrentLocked("manual")
        }

        // Lazy gap finalize: a pause longer than gapMs (computed here on the next
        // append, no timer) starts a new file so the backend places resumed audio
        // as a separate conversation.
        if isOpen, lastAppendMs > 0, nowMs - lastAppendMs > gapMs {
            closeCurrentLocked("gap")
        }
        // Rotation: bound file size/duration (between packets, never mid-packet).
        if isOpen, currentBytes >= maxFileBytes || (nowMs / 1000 - currentStartSec) >= maxFileSeconds {
            closeCurrentLocked("rotate")
        }

        if !isOpen {
            let startSec = nowMs / 1000
            // codec opus_fs320 (20ms frames), 16kHz mono — mirrors the BLE/pendant
            // batch naming so the Dart scanner (`audio_omibatch*`) and backend both match.
            let name = "audio_\(marker)_opus_fs320_16000_1_fs320_\(startSec).bin.\(partSuffix)"
            guard openLocked(dirPath: dir, fileName: name, startSec: startSec, nowMs: nowMs) else {
                noteStorageFullTransition() // open refused — most likely the free-space guard tripped
                return
            }
            wasStorageFull = false // a successful open means storage recovered
        }

        guard writeFramesLocked(opusPackets) else { return }
        sessionFramesWritten += Int64(opusPackets.count)
        lastAppendMs = nowMs
        maybeFsyncLocked(nowMs: nowMs)
    }

    /// Synchronous finalize (fsync + atomic `.part` -> `.bin` promote) used by the
    /// controller inside `audioQueue.sync` so the file is ingestable before the
    /// Pigeon stop() future resolves. Distinct from the base's async `stop(_:)`.
    func closeNowLocked(_ reason: String) {
        closeCurrentLocked(reason)
    }

    /// Drain the latched storage-full transition. Called by the controller on its
    /// 1Hz progress tick (inside `audioQueue.sync`) so at most one onCaptureError
    /// fires per false->true edge.
    func consumeStorageFullTransitionLocked() -> Bool {
        let pending = pendingStorageFullReport
        pendingStorageFullReport = false
        return pending
    }

    override func onClosedLocked() {
        lastAppendMs = 0
    }

    private func noteStorageFullTransition() {
        // The base sets flutter.batchStorageFull when the free-space guard trips;
        // read it back to distinguish a storage-full refusal from a transient open
        // failure, and latch only the false->true edge.
        if UserDefaults.standard.bool(forKey: "flutter.batchStorageFull"), !wasStorageFull {
            wasStorageFull = true
            pendingStorageFullReport = true
        }
    }
}
