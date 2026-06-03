import Foundation
import AVFoundation
import SoundAnalysis
import FluidAudio

/// Tallies Apple SoundAnalysis frames over one window to decide if it's music/singing vs speech.
/// Used to keep songs / TV / videos playing through *system audio* from becoming "conversations".
@available(macOS 12.0, *)
private final class MusicTally: NSObject, SNResultsObserving {
    private(set) var frames = 0
    private(set) var musicFrames = 0
    private(set) var speechFrames = 0

    func request(_ request: SNRequest, didProduce result: SNResult) {
        guard let cr = result as? SNClassificationResult, let top = cr.classifications.first else { return }
        frames += 1
        guard top.confidence > 0.3 else { return }
        let id = top.identifier.lowercased()
        if id == "speech" {
            speechFrames += 1
        } else if id == "music" || id == "singing" || id.contains("music") {
            musicFrames += 1
        }
    }

    /// Music when music frames dominate speech *and* make up a meaningful share of the window —
    /// so a call (other party's speech through system audio) is kept, but a song is dropped.
    var isMusic: Bool { frames > 0 && musicFrames > speechFrames && musicFrames * 3 >= frames }
}

/// On-device speech-to-text via FluidAudio (NVIDIA Parakeet TDT, CoreML on the Apple Neural Engine).
///
/// Drop-in alternative to the cloud `TranscriptionService` for the desktop mono path: it accepts the
/// *same* 16 kHz mono Int16 little-endian PCM the WebSocket path receives, accumulates it into fixed
/// windows, transcribes each window locally, and emits `TranscriptionService.BackendSegment` so the
/// existing UI / DB pipeline (`handleBackendSegments`) is unchanged.
///
/// Enabled via `OMI_LOCAL_STT=1` (or `defaults write <bundle> useLocalSTT -bool true`). No network,
/// no Deepgram. Model weights (~600 MB–1.2 GB) download from HuggingFace on first run and are cached.
final class LocalTranscriptionService: @unchecked Sendable {

    typealias SegmentsHandler = @MainActor ([TranscriptionService.BackendSegment]) -> Void

    private let language: String
    /// Source-based diarization: mic = the user ("You"), system audio = another speaker.
    private let isUser: Bool
    private let speakerLabel: String
    private let speakerId: Int
    private let sampleRate = 16000
    /// Window length transcribed at a time. Not real-time — gives a ~10 s "lag" like the user wants.
    private let windowSeconds = 10.0
    private var windowSamples: Int { Int(Double(sampleRate) * windowSeconds) }

    private var asrManager: AsrManager?
    private var onSegments: SegmentsHandler?

    // 16 kHz mono Float32 sample buffer, guarded by `lock`.
    private let lock = NSLock()
    private var buffer: [Float] = []
    private var isReady = false
    private var isFlushing = false
    /// Set false when retiring the service (stop/finish) so no new samples enter the buffer while
    /// the final drain is in flight — otherwise audio captured during the ~100ms drain (capture is
    /// still running across a finishConversation rotation) would be appended past the snapshot and
    /// silently dropped.
    private var acceptingAudio = true
    private var emittedSeconds = 0.0  // absolute start offset of the next emitted segment

    private var pumpTask: Task<Void, Never>?

    init(language: String = "en", isUser: Bool = true) {
        self.language = language
        self.isUser = isUser
        self.speakerLabel = isUser ? "SPEAKER_00" : "SPEAKER_01"
        self.speakerId = isUser ? 0 : 1
    }

    /// Begin loading the model (async) and start the periodic flush loop.
    func start(onSegments: @escaping SegmentsHandler) {
        self.onSegments = onSegments

        Task { [weak self] in
            guard let self else { return }
            do {
                // v2 = English-only (better recall); v3 = 25 European languages.
                let version: AsrModelVersion = self.language.hasPrefix("en") ? .v2 : .v3
                let started = Date()
                let models = try await AsrModels.downloadAndLoad(version: version)
                let manager = AsrManager()
                try await manager.loadModels(models)
                self.lock.lock()
                self.asrManager = manager
                self.isReady = true
                self.lock.unlock()
                log("LocalTranscriptionService: Parakeet \(version) ready in \(String(format: "%.1f", Date().timeIntervalSince(started)))s")
            } catch {
                logError("LocalTranscriptionService: model load failed", error: error)
            }
        }

        pumpTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                await self?.drain(force: false)
            }
        }
    }

    /// Feed 16 kHz mono Int16 little-endian PCM — the same `Data` the WebSocket path sends.
    func appendAudio(_ data: Data) {
        let floats = Self.int16ToFloat32(data)
        guard !floats.isEmpty else { return }
        lock.lock()
        if acceptingAudio {
            buffer.append(contentsOf: floats)
        }
        lock.unlock()
    }

    /// Fire-and-forget stop. Prefer `await finish()` whenever the session lifecycle allows it —
    /// `finish()` guarantees the final tail is persisted before the caller rotates/clears the
    /// session. `stop()` only drains on a detached Task, so a caller that mutates session state
    /// right after (e.g. the 4-hour restart path) can still race; it exists for teardown sites
    /// that don't have an async context.
    func stop() {
        pumpTask?.cancel()
        pumpTask = nil
        lock.lock(); acceptingAudio = false; lock.unlock()
        // Strong `self` (not weak): the caller (AppState) nils its reference immediately after
        // stop(), so a weak capture could deallocate the service before the final tail is
        // transcribed. The strong reference keeps it alive until drainAll() finishes.
        Task { await self.drainAll() }
    }

    /// Awaitable flush. Cancels the pump and transcribes ALL remaining audio, delivering the
    /// final segments (synchronously on the main actor) before returning. Callers must `await`
    /// this before clearing/rotating the session so the last words persist to the right
    /// conversation instead of racing the async drain.
    func finish() async {
        pumpTask?.cancel()
        pumpTask = nil
        // Stop buffering new audio first so the single drain below captures the complete buffer —
        // capture can still be running (finishConversation rotation) and would otherwise append
        // past the drain snapshot.
        lock.lock(); acceptingAudio = false; lock.unlock()
        await drainAll()
    }

    /// Flush every remaining buffered sample (called on stop). Waits out any in-flight window
    /// flush first, then transcribes the sub-window tail so the last words aren't dropped.
    private func drainAll() async {
        for _ in 0..<50 {
            lock.lock(); let busy = isFlushing; lock.unlock()
            if !busy { break }
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
        await drain(force: true)
    }

    /// Transcribe one window (or whatever remains, when `force`) and emit a segment.
    private func drain(force: Bool) async {
        lock.lock()
        guard isReady, let manager = asrManager, !isFlushing else { lock.unlock(); return }
        let available = buffer.count
        // On force (stop/finish) flush whatever is left, even a sub-window tail; otherwise wait for a full window.
        let ready = available >= windowSamples || (force && available > 0)
        guard ready else { lock.unlock(); return }
        let take = force ? available : windowSamples
        let window = Array(buffer.prefix(take))
        buffer.removeFirst(take)
        let startSec = emittedSeconds
        let durSec = Double(take) / Double(sampleRate)
        emittedSeconds += durSec
        isFlushing = true
        lock.unlock()

        defer {
            lock.lock(); isFlushing = false; lock.unlock()
        }

        // Only skip DEAD silence (noise floor). The previous 0.012 threshold was tuned on loud
        // speaker playback and ate real (quieter) microphone speech — users saw "nothing
        // transcribed". A low floor lets normal mic speech through; hallucinations on near-silence
        // are filtered below by the model's own confidence score instead.
        let rms = (window.reduce(Float(0)) { $0 + $1 * $1 } / Float(window.count)).squareRoot()
        guard rms > 0.004 else { return }

        // Music/video gate: don't turn songs, TV, or videos playing through *system audio* into
        // "conversations" — only real conversations/calls should be transcribed. Applied to the
        // system channel only; the mic channel (the user's own voice) is never gated. Runs Apple's
        // on-device SoundAnalysis classifier *before* Parakeet, so music also costs us no transcription.
        if !isUser, Self.windowIsMusic(window, sampleRate: sampleRate) {
            log(String(format: "LocalTranscriptionService[sys]: skipped %.1fs music/video window (rms=%.4f)", durSec, rms))
            return
        }

        do {
            // Fresh decoder state per window. Persisting TdtDecoderState across arbitrary 10 s
            // windows makes the transducer decoder drift — it starts looping ("...AND AND AND"),
            // Title-Casing every word, and emitting gibberish. Independent per-window decode is stable.
            var ds = try TdtDecoderState()
            let result = try await manager.transcribe(window, decoderState: &ds, language: nil)

            var text = result.text.trimmingCharacters(in: .whitespacesAndNewlines)
            // Silence makes the TDT decoder emit just "." / "..." — drop windows with no real speech.
            guard text.contains(where: { $0.isLetter || $0.isNumber }) else { return }
            // NOTE: confidence is logged (below) but NOT yet used to gate — we don't know its scale
            // for real speech vs noise-hallucinations. Once the logs show the distribution we add a
            // confidence floor here to catch near-silence gibberish without dropping quiet speech.
            // Strip stray leading punctuation the streaming decoder prepends at window boundaries.
            while let first = text.first, !first.isLetter && !first.isNumber {
                text.removeFirst()
            }

            let segment = TranscriptionService.BackendSegment(
                id: UUID().uuidString,
                text: text,
                speaker: speakerLabel,
                speaker_id: speakerId,
                is_user: isUser,
                person_id: nil,
                start: startSec,
                end: startSec + durSec,
                translations: nil
            )
            // Deliver synchronously on the main actor so an awaited finish() guarantees the
            // segment is persisted (to the current session) before the caller rotates state.
            if let onSegments {
                let segs = [segment]
                await MainActor.run { onSegments(segs) }
            }
            log(String(format: "LocalTranscriptionService[%@]: %.1fs rms=%.4f conf=%.2f rtfx=%.0fx → %@",
                       isUser ? "mic" : "sys", durSec, rms, result.confidence, result.rtfx, text))
        } catch {
            logError("LocalTranscriptionService: transcribe failed", error: error)
        }
    }

    /// Classify a 16 kHz mono window as music/singing (vs speech) using Apple's on-device
    /// SoundAnalysis. Returns true → caller skips transcribing it. Fails *open* (returns false) on
    /// any error or on macOS < 12, so audio is never silently dropped when classification is unsure.
    private static func windowIsMusic(_ window: [Float], sampleRate: Int) -> Bool {
        guard #available(macOS 12.0, *) else { return false }
        guard window.count >= sampleRate,  // need ~1s+ for a stable classification
              let format = AVAudioFormat(commonFormat: .pcmFormatFloat32,
                                         sampleRate: Double(sampleRate), channels: 1, interleaved: false),
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(window.count)),
              let channel = buffer.floatChannelData
        else { return false }
        buffer.frameLength = AVAudioFrameCount(window.count)
        window.withUnsafeBufferPointer { channel[0].update(from: $0.baseAddress!, count: window.count) }

        // SoundAnalysis ships a file analyzer and a stream analyzer; the file analyzer's synchronous
        // analyze() blocks until the observer has all results, so we write the window to a temp WAV.
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("omi_music_\(UUID().uuidString).wav")
        defer { try? FileManager.default.removeItem(at: url) }

        do {
            let settings: [String: Any] = [
                AVFormatIDKey: kAudioFormatLinearPCM,
                AVSampleRateKey: Double(sampleRate),
                AVNumberOfChannelsKey: 1,
                AVLinearPCMBitDepthKey: 16,
                AVLinearPCMIsFloatKey: false,
                AVLinearPCMIsBigEndianKey: false,
            ]
            let file = try AVAudioFile(forWriting: url, settings: settings)
            try file.write(from: buffer)

            let analyzer = try SNAudioFileAnalyzer(url: url)
            let request = try SNClassifySoundRequest(classifierIdentifier: .version1)
            let tally = MusicTally()
            try analyzer.add(request, withObserver: tally)
            analyzer.analyze()  // synchronous: tally fully populated before this returns
            return tally.isMusic
        } catch {
            return false
        }
    }

    /// Convert 16-bit little-endian mono PCM to normalized Float32 [-1, 1].
    private static func int16ToFloat32(_ data: Data) -> [Float] {
        let count = data.count / 2
        guard count > 0 else { return [] }
        return data.withUnsafeBytes { raw -> [Float] in
            let samples = raw.bindMemory(to: Int16.self)
            var out = [Float](repeating: 0, count: count)
            for i in 0..<count {
                out[i] = Float(Int16(littleEndian: samples[i])) / 32768.0
            }
            return out
        }
    }
}
