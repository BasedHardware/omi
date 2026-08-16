import Foundation

/// Shared file mechanics for native batch (offline) capture sinks. Subclasses decide
/// *policy* — which frames to write, file naming, and when to rotate/finalize — while
/// this base owns the *mechanics* every sink must get right identically:
///
///  - length-prefixed frame layout: [4-byte LE uint32 frame_length][frame bytes] ...
///  - writing to a `.bin.part` file, atomically renamed to `.bin` on finalize so the
///    Dart scanner (which only ingests `*.bin`) never sees a half-written file
///  - periodic fsync for crash durability, plus an explicit fsync barrier
///  - stale `.bin.part` recovery after a crashed process
///  - free-space guard (pause + `flutter.batchStorageFull` flag instead of failing)
///  - `onBatchRecordingFinalized` Pigeon notify so the recordings list rescans
///
/// Implementations: `OmiBatchAudioWriter` (BLE-notification-driven, wall-clock files)
/// and `LimitlessBatchAudioWriter` (flash-drain-driven, pendant-timestamped files).
/// All state is confined to `queue`; primitives must only be called on it.
class BaseBatchAudioWriter {
    let queue: DispatchQueue
    private let tag: String
    private let recoveryPrefix: String

    // Active-file state (only touched on `queue`).
    private var fileHandle: FileHandle?
    private var currentURL: URL?
    private(set) var currentStartSec: Int64 = 0
    private(set) var currentBytes: Int64 = 0
    private(set) var currentFrames: Int64 = 0
    private var lastFsyncMs: Int64 = 0
    private var storageFull = false
    private var recovered = false
    private var closeSyncFailed = false

    private let fsyncIntervalMs: Int64 = 2_000
    private let minFreeBytes: Int64 = 200 * 1024 * 1024 // stop below 200 MB free
    let partSuffix = "part"

    /// `queue` lets a caller share an existing serial queue instead of owning one:
    /// the phone-mic writer runs on the controller's audio queue so encode+write
    /// stay on a single queue and `audioQueue.sync {}` genuinely drains pending
    /// writes. When nil (the BLE subclasses) the writer creates its own.
    init(tag: String, queueLabel: String, recoveryPrefix: String, queue: DispatchQueue? = nil) {
        self.tag = tag
        self.queue = queue ?? DispatchQueue(label: queueLabel)
        self.recoveryPrefix = recoveryPrefix
    }

    /// Whether a part file is currently open (only meaningful on `queue`).
    var isOpen: Bool { fileHandle != nil }

    /// Finalize the current file (e.g. on disconnect or app teardown).
    func stop(_ reason: String) {
        queue.async { self.closeCurrentLocked(reason) }
    }

    // MARK: - Primitives (on `queue`)

    /// Open `fileName` (a `.bin.part` name produced by the subclass) inside `dirPath`
    /// for appending. Returns false when storage is low (guard engaged) or the open
    /// fails — the caller drops the frames.
    func openLocked(dirPath: String, fileName: String, startSec: Int64, nowMs: Int64) -> Bool {
        if fileHandle != nil { return true }

        let dir = URL(fileURLWithPath: dirPath, isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

        // Recover from a previous process that died mid-write: any leftover .bin.part
        // is a finalized-by-crash orphan — promote it to .bin so it becomes ingestable.
        if !recovered {
            recovered = true
            recoverStalePartFiles(dir)
        }

        if freeBytes(at: dir) < minFreeBytes {
            if !storageFull {
                NSLog("[\(tag)] storage low — pausing batch capture")
                setStorageFullFlag(true)
                storageFull = true
            }
            return false
        }
        if storageFull {
            storageFull = false
            setStorageFullFlag(false)
        }

        let url = dir.appendingPathComponent(fileName)
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        guard let fh = try? FileHandle(forWritingTo: url) else {
            NSLog("[\(tag)] open failed for \(fileName)")
            return false
        }
        let end = (try? fh.seekToEnd()) ?? 0 // append-safe (same-second restart reuses the file)
        fileHandle = fh
        currentURL = url
        currentStartSec = startSec
        currentBytes = Int64(end)
        currentFrames = 0
        lastFsyncMs = nowMs
        NSLog("[\(tag)] opened \(fileName)")
        return true
    }

    /// Append frames with the length-prefixed layout. On failure the current file is
    /// finalized (what was written so far stays durable) and false is returned.
    func writeFramesLocked(_ frames: [Data]) -> Bool {
        guard let fh = fileHandle else { return false }
        do {
            for frame in frames {
                var len = UInt32(frame.count).littleEndian
                let header = Data(bytes: &len, count: 4)
                try fh.write(contentsOf: header)
                try fh.write(contentsOf: frame)
                currentBytes += Int64(4 + frame.count)
                currentFrames += 1
            }
            return true
        } catch {
            NSLog("[\(tag)] write failed: \(error)")
            try? fh.truncate(atOffset: UInt64(currentBytes)) // drop a torn frame tail
            closeCurrentLocked("write_error")
            return false
        }
    }

    func maybeFsyncLocked(nowMs: Int64) {
        if nowMs - lastFsyncMs >= fsyncIntervalMs {
            fsyncLocked()
            lastFsyncMs = nowMs
        }
    }

    @discardableResult
    func fsyncLocked() -> Bool {
        guard let fh = fileHandle else { return true }
        do {
            try fh.synchronize()
            return true
        } catch {
            NSLog("[\(tag)] fsync failed: \(error)")
            return false
        }
    }

    func consumeCloseSyncFailureLocked() -> Bool {
        let failed = closeSyncFailed
        closeSyncFailed = false
        return failed
    }

    func closeCurrentLocked(_ reason: String) {
        if let fh = fileHandle {
            var synced = true
            do {
                try fh.synchronize()
            } catch {
                synced = false
            }
            try? fh.close()
            if let part = currentURL {
                if currentBytes > 0, synced {
                    // Atomically promote .bin.part -> .bin so it becomes ingestable.
                    let finalURL = part.deletingPathExtension() // strip ".part" -> "....bin"
                    try? FileManager.default.removeItem(at: finalURL)
                    do {
                        try FileManager.default.moveItem(at: part, to: finalURL)
                        NSLog("[\(tag)] finalized \(finalURL.lastPathComponent) (\(currentFrames) frames, \(currentBytes) bytes, reason=\(reason))")
                        notifyFinalized(finalURL.lastPathComponent)
                    } catch {
                        NSLog("[\(tag)] finalize failed: \(error)")
                    }
                } else if currentBytes > 0 {
                    // Durability unconfirmed — hold the ACK barrier and leave the
                    // .part for stale-part recovery instead of publishing it.
                    closeSyncFailed = true
                    NSLog("[\(tag)] close fsync failed — leaving \(part.lastPathComponent) unfinalized")
                } else {
                    try? FileManager.default.removeItem(at: part) // nothing written — drop the placeholder
                }
            }
            fileHandle = nil
            currentURL = nil
            currentStartSec = 0
            currentBytes = 0
            currentFrames = 0
        }
        onClosedLocked()
    }

    /// Hook for subclasses to reset their gap/session tracking when a file closes.
    func onClosedLocked() {}

    /// Notify Dart that a file finalized, so the recordings list rescans without
    /// waiting for a BLE disconnect.
    private func notifyFinalized(_ fileName: String) {
        DispatchQueue.main.async {
            OmiBleManager.shared.flutterApi?.onBatchRecordingFinalized(fileName: fileName) { _ in }
        }
    }

    // MARK: - Crash recovery

    /// Promote any leftover `*.bin.part` from a previous (crashed) process to `.bin`
    /// so finalized-by-crash recordings are not lost. Empty placeholders are deleted.
    private func recoverStalePartFiles(_ dir: URL) {
        guard let items = try? FileManager.default.contentsOfDirectory(
            at: dir, includingPropertiesForKeys: [.fileSizeKey]
        ) else { return }
        for url in items {
            let name = url.lastPathComponent
            guard name.hasPrefix(recoveryPrefix), name.hasSuffix(".bin.\(partSuffix)") else { continue }
            let size = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
            if size > 0 {
                let finalURL = url.deletingPathExtension()
                try? FileManager.default.moveItem(at: url, to: finalURL)
                NSLog("[\(tag)] recovered stale batch file -> \(finalURL.lastPathComponent)")
            } else {
                try? FileManager.default.removeItem(at: url)
            }
        }
    }

    // MARK: - Helpers

    private func freeBytes(at dir: URL) -> Int64 {
        if let vals = try? dir.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey]),
            let cap = vals.volumeAvailableCapacityForImportantUsage {
            return cap
        }
        return Int64.max
    }

    private func setStorageFullFlag(_ full: Bool) {
        UserDefaults.standard.set(full, forKey: "flutter.batchStorageFull")
    }
}
