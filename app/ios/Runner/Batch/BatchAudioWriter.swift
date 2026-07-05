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
/// File mechanics (durability, .part promotion, recovery) live in `BaseBatchAudioWriter`;
/// this class owns the notification-driven policy: config matching, mute/cut prefs,
/// per-device frame extraction, silence-gap finalize and wall-clock rotation.
final class OmiBatchAudioWriter: BaseBatchAudioWriter {
    static let shared = OmiBatchAudioWriter()
    private init() {
        super.init(tag: "BatchWriter", queueLabel: "com.omi.batchAudioWriter", recoveryPrefix: "audio_omibatch_")
    }

    // Policy state. `lastFrameMs` is queue-confined; the two flags below are only
    // touched on the BLE callback thread (same as before the base extraction).
    private var lastFrameMs: Int64 = 0
    private var wasEnabled = false
    private var diagLoggedMatch = false

    private let maxFileBytes: Int64 = 32 * 1024 * 1024 // ~32 MB per file
    private let maxFileSeconds: Int64 = 900 // 15 min per file
    private let gapMs: Int64 = 30_000 // start a new file after this silence gap

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
                stop("disabled")
            }
            return false
        }
        wasEnabled = true
        guard config.deviceType != "limitless" else { return false } // LimitlessFlashDrainEngine owns that device
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
            stop("manual")
        }

        let frames = transformFrames(deviceType: config.deviceType, value: value)
        if !frames.isEmpty {
            queue.async { self.writeFrames(frames, config: config) }
        }
        // Audio packet on the configured characteristic: consume it (do not forward
        // to Dart) even if it carried no payload, to keep the engine idle.
        return true
    }

    // MARK: - Writing (on `queue`)

    /// Keep the open file's gap timer fresh while muted so unmute resumes it.
    private func touchKeepAlive() {
        if isOpen {
            lastFrameMs = Int64(Date().timeIntervalSince1970 * 1000)
        }
    }

    private func writeFrames(_ frames: [Data], config: Config) {
        let nowMs = Int64(Date().timeIntervalSince1970 * 1000)

        // Gap finalize: a pause longer than gapMs starts a new file (so the
        // backend places resumed audio as a separate conversation).
        if isOpen, lastFrameMs > 0, nowMs - lastFrameMs > gapMs {
            closeCurrentLocked("gap")
        }
        // Rotation: bound file size/duration (between packets, never mid-packet).
        if isOpen, currentBytes >= maxFileBytes || (nowMs / 1000 - currentStartSec) >= maxFileSeconds {
            closeCurrentLocked("rotate")
        }

        if !isOpen {
            let startSec = nowMs / 1000
            let frameSize = config.codec == "opus_fs320" ? 320 : 160
            // Tag the device segment as `omibatch` so the Dart scanner can tell batch
            // recordings apart from offline-sync WAL flushes, which share this directory
            // and the same audio_*.bin naming. The backend ignores this segment; keep it
            // in sync with Dart's `batchRecordingDevice`.
            let name = "audio_omibatch_\(config.codec)_\(config.sampleRate)_1_fs\(frameSize)_\(startSec).bin.\(partSuffix)"
            guard openLocked(dirPath: config.dir, fileName: name, startSec: startSec, nowMs: nowMs) else {
                return // storage full or open failed — drop packet
            }
        }

        guard writeFramesLocked(frames) else { return }

        lastFrameMs = nowMs
        maybeFsyncLocked(nowMs: nowMs)
    }

    override func onClosedLocked() {
        lastFrameMs = 0
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

    // MARK: - Config

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
}
