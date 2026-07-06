import Foundation

/// Batch (offline) capture sink for iOS. When the user enables "batch mode",
/// incoming BLE audio is stored to local `.bin` files instead of being forwarded
/// to Dart for realtime transcription. Mirrors the Android `OmiBatchAudioWriter`.
///
/// On-disk format (what `POST /v2/sync-local-files` decodes):
///   [4-byte little-endian uint32 frame_length][frame bytes] ... repeated
/// File name: audio_omibatch_{codec}_{sampleRate}_{channel}_fs{frameSize}_{startSec}.bin
/// (the `omibatch` device marker distinguishes these from offline-sync WAL files,
/// which share this directory; the backend treats the device segment as a label.)
///
/// Hooked from `OmiBleManager.peripheral(_:didUpdateValueFor:)`. When it consumes a
/// packet it returns `true`, and the manager skips the Dart forward — so the Flutter
/// engine does no per-packet work (the iOS battery win).
///
/// Durability: frames are written to a `.bin.part` file with periodic `fsync`, and
/// the file is atomically renamed to `.bin` only once finalized (rotation / silence
/// gap / stop) so a half-written file is never ingested. A stale `.bin.part` left by
/// a crashed process is recovered (promoted to `.bin`) on the next writer start. A
/// free-space guard stops writing (and flags Flutter) rather than failing hard.
final class BatchAudioWriter {
    static let shared = BatchAudioWriter()
    private init() {}

    private let queue = DispatchQueue(label: "com.omi.batchAudioWriter")

    // Active-file state (only touched on `queue`).
    private var fileHandle: FileHandle?
    private var currentURL: URL?
    private var currentStartSec: Int64 = 0
    private var currentBytes: Int64 = 0
    private var currentFrames: Int64 = 0
    private var lastFrameMs: Int64 = 0
    private var lastFsyncMs: Int64 = 0
    private var storageFull = false
    private var recovered = false
    private var wasEnabled = false
    private var diagLoggedMatch = false

    private let maxFileBytes: Int64 = 32 * 1024 * 1024 // ~32 MB per file
    private let maxFileSeconds: Int64 = 900 // 15 min per file
    private let gapMs: Int64 = 30_000 // start a new file after this silence gap
    private let fsyncIntervalMs: Int64 = 2_000
    private let minFreeBytes: Int64 = 200 * 1024 * 1024 // stop below 200 MB free
    private let partSuffix = "part"

    private struct Config {
        let deviceId: String
        let codec: String
        let sampleRate: Int
        let serviceUuid: String
        let characteristicUuid: String
        let deviceType: String
        let dir: String
    }

    /// Returns true if the packet was consumed for batch capture (caller must then
    /// skip forwarding it to Dart). Returns false to let realtime forwarding proceed.
    @discardableResult
    func handle(peripheralUuid: String, serviceUuid: String, characteristicUuid: String, value: Data) -> Bool {
        guard let config = loadConfig() else {
            // Offline mode is off (the common case). Finalize an in-progress file only on the
            // enabled->disabled edge — never schedule per-packet work on the BLE hot path.
            if wasEnabled {
                wasEnabled = false
                queue.async { self.closeCurrentLocked("disabled") }
            }
            return false
        }
        wasEnabled = true
        guard config.deviceId.lowercased() == peripheralUuid.lowercased() else { return false }
        guard config.serviceUuid == serviceUuid.lowercased(),
            config.characteristicUuid == characteristicUuid.lowercased() else { return false }

        if !diagLoggedMatch {
            diagLoggedMatch = true
            NSLog("[BatchWriter] matched audio characteristic — batch capture active (device=\(peripheralUuid), dir=\(config.dir))")
        }

        let d = UserDefaults.standard
        // Muted: drop the packet but keep the open file's gap timer alive so unmute
        // resumes the same recording instead of starting a new one.
        if d.bool(forKey: "flutter.batchMuted") {
            queue.async { self.touchKeepAlive() }
            return true
        }
        // Manual "New recording": finalize the current file now; this packet opens a fresh one.
        if d.bool(forKey: "flutter.batchCutRequested") {
            d.set(false, forKey: "flutter.batchCutRequested")
            queue.async { self.closeCurrentLocked("manual") }
        }

        let frames = transformFrames(deviceType: config.deviceType, value: value)
        if !frames.isEmpty {
            queue.async { self.writeFrames(frames, config: config) }
        }
        // Audio packet on the configured characteristic: consume it (do not forward
        // to Dart) even if it carried no payload, to keep the engine idle.
        return true
    }

    /// Finalize the current file (e.g. on disconnect or app teardown).
    func stop(_ reason: String) {
        queue.async { self.closeCurrentLocked(reason) }
    }

    // MARK: - Writing (on `queue`)

    /// Keep the open file's gap timer fresh while muted so unmute resumes it.
    private func touchKeepAlive() {
        if fileHandle != nil {
            lastFrameMs = Int64(Date().timeIntervalSince1970 * 1000)
        }
    }

    private func writeFrames(_ frames: [Data], config: Config) {
        let nowMs = Int64(Date().timeIntervalSince1970 * 1000)

        if fileHandle != nil, lastFrameMs > 0, nowMs - lastFrameMs > gapMs {
            closeCurrentLocked("gap")
        }
        if fileHandle != nil, currentBytes >= maxFileBytes || (nowMs / 1000 - currentStartSec) >= maxFileSeconds {
            closeCurrentLocked("rotate")
        }

        ensureOpen(config: config, nowMs: nowMs)
        guard let fh = fileHandle else { return } // storage full or open failed — drop packet

        do {
            for frame in frames {
                var len = UInt32(frame.count).littleEndian
                let header = Data(bytes: &len, count: 4)
                try fh.write(contentsOf: header)
                try fh.write(contentsOf: frame)
                currentBytes += Int64(4 + frame.count)
                currentFrames += 1
            }
        } catch {
            NSLog("[BatchWriter] write failed: \(error)")
            closeCurrentLocked("write_error")
            return
        }

        lastFrameMs = nowMs
        if nowMs - lastFsyncMs >= fsyncIntervalMs {
            try? fh.synchronize()
            lastFsyncMs = nowMs
        }
    }

    private func ensureOpen(config: Config, nowMs: Int64) {
        if fileHandle != nil { return }

        let dir = URL(fileURLWithPath: config.dir, isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

        if !recovered {
            recovered = true
            recoverStalePartFiles(dir)
        }

        if freeBytes(at: dir) < minFreeBytes {
            if !storageFull {
                NSLog("[BatchWriter] storage low — pausing batch capture")
                setStorageFullFlag(true)
                storageFull = true
            }
            return
        }
        if storageFull {
            storageFull = false
            setStorageFullFlag(false)
        }

        let startSec = nowMs / 1000
        let frameSize = config.codec == "opus_fs320" ? 320 : 160
        // Tag the device segment as `omibatch` so the Dart scanner can tell batch
        // recordings apart from offline-sync WAL flushes, which share this directory
        // and the same audio_*.bin naming. The backend ignores this segment; keep it
        // in sync with Dart's `batchRecordingDevice`.
        let name = "audio_omibatch_\(config.codec)_\(config.sampleRate)_1_fs\(frameSize)_\(startSec).bin.\(partSuffix)"
        let url = dir.appendingPathComponent(name)

        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        guard let fh = try? FileHandle(forWritingTo: url) else {
            NSLog("[BatchWriter] open failed for \(name)")
            return
        }
        let end = (try? fh.seekToEnd()) ?? 0
        fileHandle = fh
        currentURL = url
        currentStartSec = startSec
        currentBytes = Int64(end)
        currentFrames = 0
        lastFsyncMs = nowMs
        NSLog("[BatchWriter] opened \(name)")
    }

    private func closeCurrentLocked(_ reason: String) {
        guard let fh = fileHandle else { return }
        try? fh.synchronize()
        try? fh.close()
        if let part = currentURL {
            if currentBytes > 0 {
                let finalURL = part.deletingPathExtension() // strip ".part" -> "....bin"
                try? FileManager.default.removeItem(at: finalURL)
                do {
                    try FileManager.default.moveItem(at: part, to: finalURL)
                    NSLog("[BatchWriter] finalized \(finalURL.lastPathComponent) (\(currentFrames) frames, \(currentBytes) bytes, reason=\(reason))")
                    let finalizedName = finalURL.lastPathComponent
                    DispatchQueue.main.async {
                        OmiBleManager.shared.flutterApi?.onBatchRecordingFinalized(fileName: finalizedName) { _ in }
                    }
                } catch {
                    NSLog("[BatchWriter] finalize failed: \(error)")
                }
            } else {
                try? FileManager.default.removeItem(at: part)
            }
        }
        fileHandle = nil
        currentURL = nil
        currentStartSec = 0
        currentBytes = 0
        currentFrames = 0
        lastFrameMs = 0
    }

    // MARK: - Crash recovery

    private func recoverStalePartFiles(_ dir: URL) {
        guard let items = try? FileManager.default.contentsOfDirectory(
            at: dir, includingPropertiesForKeys: [.fileSizeKey]
        ) else { return }
        for url in items {
            let name = url.lastPathComponent
            guard name.hasPrefix("audio_"), name.hasSuffix(".bin.\(partSuffix)") else { continue }
            let size = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
            if size > 0 {
                let finalURL = url.deletingPathExtension()
                try? FileManager.default.moveItem(at: url, to: finalURL)
                NSLog("[BatchWriter] recovered stale batch file -> \(finalURL.lastPathComponent)")
            } else {
                try? FileManager.default.removeItem(at: url)
            }
        }
    }

    // MARK: - Frame extraction (mirrors Android transformFrames)

    private func transformFrames(deviceType: String, value: Data) -> [Data] {
        switch deviceType {
        case "omi", "openglass":
            return value.count <= 3 ? [] : [value.subdata(in: 3 ..< value.count)]
        case "friendPendant":
            if value.count <= 5 { return [] }
            let payload = value.subdata(in: 0 ..< (value.count - 5))
            var frames: [Data] = []
            var offset = 0
            while offset + 30 <= payload.count {
                frames.append(payload.subdata(in: offset ..< (offset + 30)))
                offset += 30
            }
            return frames
        default:
            return []
        }
    }

    // MARK: - Config + helpers

    private func loadConfig() -> Config? {
        let d = UserDefaults.standard
        guard d.bool(forKey: "flutter.batchModeEnabled") else { return nil }
        guard let dir = d.string(forKey: "flutter.batchAudioDir"), !dir.isEmpty else { return nil }
        guard let raw = d.string(forKey: "flutter.nativeBleStreamConfig"),
            let data = raw.data(using: .utf8),
            let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        guard let deviceId = json["deviceId"] as? String, !deviceId.isEmpty,
            let serviceUuid = json["serviceUuid"] as? String, !serviceUuid.isEmpty,
            let charUuid = json["characteristicUuid"] as? String, !charUuid.isEmpty else { return nil }
        return Config(
            deviceId: deviceId,
            codec: (json["codec"] as? String) ?? "opus",
            sampleRate: (json["sampleRate"] as? Int) ?? 16000,
            serviceUuid: serviceUuid.lowercased(),
            characteristicUuid: charUuid.lowercased(),
            deviceType: (json["deviceType"] as? String) ?? "omi",
            dir: dir
        )
    }

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
