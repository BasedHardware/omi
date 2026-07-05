import Foundation

/// Batch (offline) capture sink for the Limitless pendant. Unlike `OmiBatchAudioWriter`
/// (which is fed live BLE notifications), this writer is fed opus frames extracted from
/// the pendant's onboard flash pages by the native flash-drain engine — the pendant
/// records on its own and the phone periodically drains its storage.
///
/// Differences in policy, enabled by the flash-page metadata:
///  - Files are named and segmented by the **pendant-clock capture time** of the first
///    page (`timestamp_ms`), not by phone wall-clock at open — recordings carry their
///    true start time even when drained minutes or hours after capture.
///  - A new file starts when consecutive pages are more than `sessionGapMs` apart
///    (the pendant wasn't recording in between) or after `maxAudioSeconds` of audio
///    (frames/50 — opus_fs320 is 50 frames per second), mirroring the Omi 15-min cap.
///  - The device marker is `omibatchlimitless`: the `omibatch` prefix keeps the Dart
///    recordings scanner matching, and the `limitless` substring makes the backend tag
///    the resulting conversation `source=limitless`.
///
/// ACK safety: the drain engine must call `syncToDisk()` (fsync barrier) and get `true`
/// back BEFORE ACKing pages to the pendant — an ACK deletes the pendant's copy, so
/// bytes must be durable on phone storage first. `append` itself only fsyncs
/// periodically.
final class LimitlessBatchAudioWriter: BaseBatchAudioWriter {
    static let deviceMarker = "omibatchlimitless"

    private let sessionGapMs: Int64 = 120_000 // >120s between page timestamps = new session
    private let maxAudioSeconds: Int64 = 900 // 15 min of audio per file
    private let framesPerSecond: Int64 = 50 // opus_fs320 = 20 ms frames
    private let minValidTsMs: Int64 = 1_577_836_800_000 // 2020-01-01: pendant clock sanity gate

    private var lastPageTimestampMs: Int64 = 0

    init() {
        super.init(
            tag: "LimitlessWriter",
            queueLabel: "com.omi.limitlessBatchWriter",
            recoveryPrefix: "audio_\(LimitlessBatchAudioWriter.deviceMarker)_"
        )
    }

    /// Append the opus frames extracted from one flash page. `pageTimestampMs` is the
    /// pendant-clock capture time of that page. Runs synchronously on the writer queue
    /// (call from the drain engine's queue, never from `queue` itself). Returns true
    /// once the frames are written (durability requires a subsequent `syncToDisk`
    /// before ACK).
    func append(_ frames: [Data], pageTimestampMs: Int64) -> Bool {
        if frames.isEmpty { return true }
        return queue.sync { self.appendLocked(frames, pageTimestampMs: pageTimestampMs) }
    }

    /// Fsync barrier: returns true when everything appended so far is durable on disk.
    /// The drain engine must get `true` here before ACKing the covered pages.
    func syncToDisk() -> Bool {
        return queue.sync { !self.consumeCloseSyncFailureLocked() && (!self.isOpen || self.fsyncLocked()) }
    }

    override func onClosedLocked() {
        lastPageTimestampMs = 0
    }

    // MARK: - Writing (on `queue`)

    private func appendLocked(_ frames: [Data], pageTimestampMs: Int64) -> Bool {
        let nowMs = Int64(Date().timeIntervalSince1970 * 1000)
        // Pendant clock sanity: pages recorded before the first msg6 time-sync carry
        // a bogus epoch. Inside an open session inherit the last valid timestamp so a
        // bogus page can't fake a session gap; otherwise fall back to drain wall-clock.
        let ts: Int64
        if pageTimestampMs > minValidTsMs {
            ts = pageTimestampMs
        } else if lastPageTimestampMs > 0 {
            ts = lastPageTimestampMs
        } else {
            ts = nowMs
        }

        if isOpen, lastPageTimestampMs > 0, abs(ts - lastPageTimestampMs) > sessionGapMs {
            closeCurrentLocked("session_gap")
        }
        if isOpen, currentFrames >= maxAudioSeconds * framesPerSecond {
            closeCurrentLocked("rotate")
        }

        if !isOpen {
            guard let dir = UserDefaults.standard.string(forKey: "flutter.batchAudioDir"), !dir.isEmpty else {
                return false
            }
            var startSec = ts / 1000
            // A finalize replaces an existing same-name .bin — never reuse a taken name.
            while FileManager.default.fileExists(
                atPath: "\(dir)/audio_\(Self.deviceMarker)_opus_fs320_16000_1_fs320_\(startSec).bin"
            ) {
                startSec += 1
            }
            let name = "audio_\(Self.deviceMarker)_opus_fs320_16000_1_fs320_\(startSec).bin.\(partSuffix)"
            guard openLocked(dirPath: dir, fileName: name, startSec: startSec, nowMs: nowMs) else {
                return false // storage full or open failed
            }
        }

        guard writeFramesLocked(frames) else { return false }
        lastPageTimestampMs = ts
        maybeFsyncLocked(nowMs: nowMs)
        return true
    }
}
