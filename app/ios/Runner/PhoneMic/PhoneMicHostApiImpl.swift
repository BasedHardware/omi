import Foundation

/// Pigeon adapter: forwards host-API calls to the controller. No logic lives
/// here — the controller hops to its own queue and dispatches completions back
/// to the main thread itself.
final class PhoneMicHostApiImpl: PhoneMicHostApi {
    private let controller: PhoneMicController

    init(controller: PhoneMicController) {
        self.controller = controller
    }

    func start(mode: PhoneMicCaptureMode, completion: @escaping (Result<Void, Error>) -> Void) {
        controller.start(mode: mode, completion: completion)
    }

    func stop(completion: @escaping (Result<Void, Error>) -> Void) {
        controller.stop {
            completion(.success(()))
        }
    }

    func isRecording() throws -> Bool {
        return controller.isRecording
    }

    /// DEBUG VERIFICATION ONLY (removed before merge). Standalone of the live
    /// session: a fresh encoder + writer, so it validates the encode+WAL round-trip
    /// without touching capture. Real work is compiled only into DEBUG builds.
    func debugEncodeWavToBin(wavPath: String, marker: String, completion: @escaping (Result<String, Error>) -> Void) {
        #if DEBUG
            PhoneMicHostApiImpl.debugQueue.async {
                completion(PhoneMicHostApiImpl.runDebugEncode(wavPath: wavPath, marker: marker))
            }
        #else
            completion(.failure(PhoneMicPigeonError(
                code: "debug_disabled", message: "debugEncodeWavToBin is DEBUG-only", details: nil)))
        #endif
    }

    #if DEBUG
        private static let debugQueue = DispatchQueue(label: "com.omi.phonemic.debugEncode")

        /// Synchronous on debugQueue (== the writer's queue): parse a canonical 16kHz
        /// mono PCM16 WAV, encode its samples, write one finalized .bin, return its path.
        private static func runDebugEncode(wavPath: String, marker: String) -> Result<String, Error> {
            guard let wav = FileManager.default.contents(atPath: wavPath), wav.count > 44 else {
                return .failure(PhoneMicPigeonError(
                    code: "debug_bad_wav", message: "missing or too small to be a WAV: \(wavPath)", details: nil))
            }
            func u16(_ off: Int) -> UInt16 { UInt16(wav[off]) | (UInt16(wav[off + 1]) << 8) }
            func u32(_ off: Int) -> UInt32 {
                UInt32(wav[off]) | (UInt32(wav[off + 1]) << 8) | (UInt32(wav[off + 2]) << 16) | (UInt32(wav[off + 3]) << 24)
            }
            let tag = { (r: Range<Int>) in String(bytes: wav[r], encoding: .ascii) }
            guard tag(0 ..< 4) == "RIFF", tag(8 ..< 12) == "WAVE", tag(12 ..< 16) == "fmt ", tag(36 ..< 40) == "data",
                u16(20) == 1, u16(22) == 1, u32(24) == 16000, u16(34) == 16
            else {
                return .failure(PhoneMicPigeonError(
                    code: "debug_bad_wav", message: "expected a canonical 16kHz mono PCM16 WAV", details: nil))
            }

            guard let dir = resolveDebugDir(wavPath: wavPath) else {
                return .failure(PhoneMicPigeonError(
                    code: "batch_dir_unavailable", message: "no flutter.batchAudioDir and WAV has no directory", details: nil))
            }
            guard let encoder = PhoneMicOpusEncoder() else {
                return .failure(PhoneMicPigeonError(code: "opus_init_failed", message: "encoder create failed", details: nil))
            }

            let writer = PhoneMicBatchAudioWriter(dir: dir, queue: debugQueue)
            writer.append(opusPackets: encoder.encode(wav.subdata(in: 44 ..< wav.count)), marker: marker)
            writer.closeNowLocked("debug")

            if let produced = newestBin(dir: dir, marker: marker) {
                return .success(produced)
            }
            return .failure(PhoneMicPigeonError(
                code: "debug_no_output", message: "no .bin produced (empty input or muted?)", details: nil))
        }

        private static func resolveDebugDir(wavPath: String) -> String? {
            if let d = UserDefaults.standard.string(forKey: "flutter.batchAudioDir"), !d.isEmpty { return d }
            let dir = (wavPath as NSString).deletingLastPathComponent
            return dir.isEmpty ? nil : dir
        }

        private static func newestBin(dir: String, marker: String) -> String? {
            let url = URL(fileURLWithPath: dir, isDirectory: true)
            guard let items = try? FileManager.default.contentsOfDirectory(
                at: url, includingPropertiesForKeys: [.contentModificationDateKey]) else { return nil }
            let prefix = "audio_\(marker)_"
            return items
                .filter { $0.lastPathComponent.hasPrefix(prefix) && $0.lastPathComponent.hasSuffix(".bin") }
                .max { a, b in
                    let da = (try? a.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
                    let db = (try? b.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
                    return da < db
                }?.path
        }
    #endif
}
