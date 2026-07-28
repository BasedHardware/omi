@preconcurrency import AVFoundation
import EarshotCore
import FluidAudio
import Foundation
import SoundAnalysis

/// On-device speech-to-text: NVIDIA Parakeet TDT 0.6B, CoreML, on the Apple Neural Engine.
///
/// Ported from Omi desktop's `LocalTranscriptionService`, which is the version that survived
/// contact with real always-on capture. Nothing here is novel and that is the point — every
/// constant and every ordering decision below was paid for by a transcript that came out wrong.
///
/// The shape: audio arrives as 16 kHz mono Int16 LE chunks from whatever `AudioSource` owns this
/// transcriber, accumulates into a `Data` buffer, and a pump task drains one fixed-size window per
/// second. Windows are decoded *independently*, not streamed — see ``drain(force:)``.
///
/// No network, no account, no cloud. Model weights (~600 MB) come from HuggingFace once and are
/// cached under Application Support; after that this runs with the machine offline.
actor Transcriber {

    // MARK: - Tuning

    /// The wire format every capture source produces. Not configurable — the model wants 16 kHz.
    private static let sampleRate = 16_000

    /// How much audio is decoded at a time.
    ///
    /// Ten seconds is a deliberate trade against streaming. It costs a ~10 s lag before a line
    /// appears, which nothing in Earshot cares about (there is no live caption UI — the transcript
    /// is read minutes to months later). In exchange the decoder sees whole clauses instead of
    /// fragments, so the text is punctuated and cased like written English rather than like a live
    /// caption. It also stays under `ASRConstants.maxModelSamples` (240 000 = 15 s), so one window
    /// is exactly one encoder pass with no internal chunking of its own.
    private static let windowSeconds = 10.0

    /// The pump interval. Shorter than a window on purpose: a window becomes complete at an
    /// arbitrary moment, and polling at 1 s means it waits at most a second to be decoded.
    private static let pumpInterval: Duration = .seconds(1)

    /// How far the sample clock may disagree with the wall clock before it is re-anchored.
    ///
    /// One window. Capture latency is milliseconds, so anything approaching this is a real stall
    /// (device rebuild, system sleep, a tap that stopped delivering), not jitter.
    private static let driftTolerance = windowSeconds

    /// Ceiling on undecoded audio.
    ///
    /// Only reachable while the model is still loading — once it is up the pump drains many times
    /// faster than real time. Five minutes covers a first-run download without letting a daemon
    /// that will run for weeks grow a buffer nobody bounded.
    private static let maxBufferedSeconds = 300.0

    private static var windowBytes: Int { Int(windowSeconds * Double(sampleRate)) * 2 }
    private static var maxBufferedBytes: Int { Int(maxBufferedSeconds * Double(sampleRate)) * 2 }

    // MARK: - Model selection

    /// The language the model is chosen for.
    ///
    /// Earshot has no settings screen, so this follows the system language. `EARSHOT_LANG`
    /// overrides it, which is how a non-English decode gets exercised on an English machine.
    static var language: String {
        if let override = ProcessInfo.processInfo.environment["EARSHOT_LANG"], !override.isEmpty {
            return override
        }
        return Locale.current.language.languageCode?.identifier ?? "en"
    }

    /// v2 is English-only and recalls noticeably better on English than v3 does; v3 covers 25
    /// European languages. English is worth the specialised model, everything else is not worth
    /// having no model at all.
    static var modelVersion: AsrModelVersion { language.hasPrefix("en") ? .v2 : .v3 }

    /// Whether the CoreML weights are already on disk.
    ///
    /// They live in `~/Library/Application Support/FluidAudio/Models/parakeet-tdt-0.6b-v2-coreml/`
    /// (`-v3-` for the multilingual model). Onboarding asks this before deciding whether it has to
    /// show a download step at all.
    static var isModelReady: Bool {
        let version = modelVersion
        return AsrModels.modelsExist(at: AsrModels.defaultCacheDirectory(for: version), version: version)
    }

    /// Downloads and compiles the model, reporting progress in 0...1.
    ///
    /// This exists purely so onboarding can own the ~600 MB first run. Without it the download
    /// happens inside the first `start()`, where it is invisible: the app says it is listening, the
    /// user has a conversation, and the audio spends the whole call queued behind a download. Doing
    /// it up front, with a progress bar, is the difference between a slow step and a silent failure.
    ///
    /// It loads as well as downloads, deliberately. Compiling the `.mlmodelc` files the first time
    /// is itself slow, and paying that here warms the compile cache; the loaded models are dropped
    /// because the second load from a warm cache is cheap.
    static func prepareModels(progress: (@Sendable (Double) -> Void)? = nil) async throws {
        let version = modelVersion
        if isModelReady {
            progress?(1)
            return
        }

        let started = Date()
        // FluidAudio reports a real fraction plus a phase (listing / downloading / compiling); only
        // the fraction is surfaced, because a progress bar that also changes its label mid-download
        // reads as an error to most people.
        _ = try await AsrModels.downloadAndLoad(
            version: version,
            progressHandler: { update in progress?(update.fractionCompleted) }
        )
        progress?(1)
        EarshotLog.info(
            "Parakeet \(version) downloaded in \(String(format: "%.0f", Date().timeIntervalSince(started)))s", "stt")
    }

    // MARK: - State

    /// Which side of the conversation this instance transcribes. Mic is the user; the system tap is
    /// everyone else. That is the whole of Earshot's diarization, and it is the only kind that
    /// cannot mislabel a speaker.
    private let source: SegmentSource

    /// Called once per accepted line with `(text, startEpoch, endEpoch)`, both Unix epoch seconds.
    var onLine: (@Sendable (String, Double, Double) -> Void)?

    private var manager: AsrManager?
    private var pump: Task<Void, Never>?

    /// Undecoded audio, 16 kHz mono Int16 little-endian — the same bytes the sources hand over, kept
    /// in the wire format so `PCM.rms` can gate a window without decoding it to floats first.
    private var buffer = Data()

    /// False between `finish()` and the next `start()`, so audio captured while the final window is
    /// still draining cannot be appended past the drain's snapshot and silently lost.
    private var acceptingAudio = false

    /// True while a window is in the model. Guards against a second pump tick starting a decode on
    /// top of the first: the actor releases its executor at every `await` inside ``drain(force:)``.
    private var isFlushing = false

    /// Wall-clock time of sample 0 of this capture run, or nil until the first chunk arrives.
    private var anchorEpoch: Double?

    /// Samples that have left the buffer, whether decoded or dropped. With `anchorEpoch` this is the
    /// clock: see ``drain(force:)``.
    private var samplesConsumed = 0

    init(source: SegmentSource) {
        self.source = source
    }

    /// Cross-actor setter for ``onLine``. An actor's stored properties cannot be assigned from
    /// outside, so the wiring goes through a method.
    func setOnLine(_ handler: @escaping @Sendable (String, Double, Double) -> Void) {
        onLine = handler
    }

    // MARK: - Lifecycle

    /// Loads the model and starts the pump. Idempotent, and cheap to call again after `finish()` —
    /// the loaded model is kept, so pause/resume does not re-pay the load.
    ///
    /// Throws if the model cannot be downloaded or loaded, which the engine turns into a visible
    /// paused reason. Failing loudly matters more than degrading: a transcriber that quietly never
    /// produces a line looks exactly like a quiet room.
    func start() async throws {
        guard pump == nil else { return }

        acceptingAudio = true
        anchorEpoch = nil
        samplesConsumed = 0

        // The pump starts before the model is ready so audio accumulates during a first-run
        // download instead of being dropped. `drain` no-ops until `manager` exists.
        pump = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: Self.pumpInterval)
                await self?.drain(force: false)
            }
        }

        guard manager == nil else { return }

        do {
            let version = Self.modelVersion
            let started = Date()
            // Shared across both transcribers. Two independent `downloadAndLoad` calls compile the
            // same ~600 MB of CoreML twice, concurrently, competing for the same ANE — which is why
            // a cold start used to take minutes per channel instead of once for both.
            let models = try await ModelPool.shared.models(version: version)
            let loaded = AsrManager()
            try await loaded.loadModels(models)
            manager = loaded
            EarshotLog.info(
                "Parakeet \(version) ready for \(source.rawValue) in "
                    + "\(String(format: "%.1f", Date().timeIntervalSince(started)))s", "stt")
        } catch {
            // Tear the pump back down rather than leave it spinning over a buffer nothing will ever
            // decode — otherwise the buffer fills to its ceiling and the app looks alive.
            pump?.cancel()
            pump = nil
            acceptingAudio = false
            buffer.removeAll(keepingCapacity: false)
            EarshotLog.error("Parakeet load failed for \(source.rawValue): \(error.localizedDescription)", "stt")
            throw error
        }
    }

    /// Feed 16 kHz mono Int16 little-endian PCM.
    func append(_ data: Data) {
        guard acceptingAudio, data.count >= 2 else { return }

        // An odd byte count means a chunk was split mid-sample upstream. Appending it would shift
        // every later sample by one byte and turn the rest of the stream into noise, so the stray
        // byte is dropped instead.
        let usable = data.count - (data.count % 2)
        buffer.append(usable == data.count ? data : data.prefix(usable))

        reanchorClockIfDrifted()
        trimBufferToCeiling()
    }

    /// Cancels the pump and decodes everything left, including a sub-window tail.
    ///
    /// Callers must await this before rotating or closing the session the lines belong to; the last
    /// words of a conversation are otherwise written after the session that contained them has been
    /// replaced.
    func finish() async {
        pump?.cancel()
        pump = nil
        // Stop buffering first so the drain below sees the complete tail: capture can still be
        // running (the engine stops sources independently) and would otherwise append past it.
        acceptingAudio = false

        // Wait out a window already in the model. Sleeping yields the actor, which is what lets the
        // in-flight `drain` resume and clear the flag.
        for _ in 0..<50 {
            if !isFlushing { break }
            try? await Task.sleep(for: .milliseconds(100))
        }
        await drain(force: true)
    }

    // MARK: - Timeline

    /// Keeps the sample clock honest against the wall clock.
    ///
    /// Segment times are derived from samples consumed, not from `now` — that is what makes a
    /// transcript line up with the screen timeline, because every line's start is the moment that
    /// audio was *spoken* rather than the moment the decoder happened to finish with it. The
    /// weakness of a pure sample count is that it assumes audio never stops arriving: one stalled
    /// tap or one sleep/wake and the clock runs permanently behind, silently, forever. So the
    /// anchor is corrected whenever the newest buffered sample no longer lands near `now`.
    private func reanchorClockIfDrifted() {
        let bufferedSamples = buffer.count / 2

        guard let anchor = anchorEpoch else {
            // This chunk is already `bufferedSamples` old by the time it reaches us.
            anchorEpoch = EarshotTime.now - Double(bufferedSamples) / Double(Self.sampleRate)
            return
        }

        let projectedNow = anchor + Double(samplesConsumed + bufferedSamples) / Double(Self.sampleRate)
        let drift = EarshotTime.now - projectedNow
        guard abs(drift) > Self.driftTolerance else { return }

        anchorEpoch = anchor + drift
        EarshotLog.info(
            "\(source.rawValue) audio clock re-anchored by \(String(format: "%.1f", drift))s "
                + "(capture stalled or the machine slept)", "stt")
    }

    /// Drops the oldest audio once the backlog passes its ceiling.
    ///
    /// Oldest rather than newest: if the model is minutes behind, the recent minutes are the ones
    /// still worth having. `samplesConsumed` advances by exactly what was dropped so the clock stays
    /// aligned — a gap in the transcript is recoverable, a permanently shifted timeline is not.
    private func trimBufferToCeiling() {
        guard buffer.count > Self.maxBufferedBytes else { return }

        let overflow = buffer.count - Self.maxBufferedBytes
        dropLeadingBytes(overflow)
        samplesConsumed += overflow / 2
        EarshotLog.error(
            "\(source.rawValue) dropped \(String(format: "%.0f", Double(overflow / 2) / Double(Self.sampleRate)))s "
                + "of audio: transcription is behind capture", "stt")
    }

    // MARK: - Decode

    /// Decodes one window (or whatever is left, when `force`) and emits at most one line.
    private func drain(force: Bool) async {
        guard !isFlushing, let manager, let anchor = anchorEpoch else { return }

        let take = force ? buffer.count : (buffer.count >= Self.windowBytes ? Self.windowBytes : 0)
        guard take > 0 else { return }

        // FluidAudio rejects anything under 0.3 s outright. A tail that short holds no word worth
        // storing, so it is dropped here rather than thrown from inside the model.
        guard take / 2 >= ASRConstants.minimumRequiredSamples(forSampleRate: Self.sampleRate) else {
            dropLeadingBytes(take)
            samplesConsumed += take / 2
            return
        }

        // Rebuild as its own `Data`: a slice keeps the parent's indices, and this value travels into
        // helpers that have no reason to know it was ever part of a larger buffer.
        let window = Data(buffer.prefix(take))
        dropLeadingBytes(take)

        let startEpoch = anchor + Double(samplesConsumed) / Double(Self.sampleRate)
        samplesConsumed += take / 2
        let endEpoch = anchor + Double(samplesConsumed) / Double(Self.sampleRate)

        isFlushing = true
        defer { isFlushing = false }

        // Gate on level before the model, not after. An inference on a silent window is pure
        // battery, and Parakeet answers a window of room tone with a confident hallucination.
        let rms = PCM.rms(int16LE: window)
        guard !TranscriptFilter.isSilent(rms: rms) else { return }

        let samples = PCM.floatSamples(int16LE: window)

        // Songs, TV and videos come through the system tap exactly like a call does. Apple's
        // on-device classifier is the only thing that tells them apart, and it runs before Parakeet
        // so music also costs no transcription. Never applied to the mic: the user's own voice is
        // always worth keeping, including when they sing.
        if source == .system, await Self.windowIsMusic(samples) {
            EarshotLog.info("system window skipped as music/video (rms \(String(format: "%.4f", rms)))", "stt")
            return
        }

        do {
            // A fresh decoder state for EVERY window. This is the least obvious line in the file
            // and the most expensive one to get wrong. `TdtDecoderState` is designed to carry
            // context across *contiguous* streaming chunks; carried across arbitrary 10 s windows —
            // which are not contiguous here, because silent and music windows are skipped — the
            // transducer drifts, starts looping on its own last token ("AND AND AND AND"),
            // Title-Cases every word, and eventually emits nothing but gibberish. Independent
            // per-window decoding is stable and costs only the words that straddle a seam.
            var state = try TdtDecoderState()
            let result = try await manager.transcribe(samples, decoderState: &state)

            // The decoder prepends seam punctuation ("...", ". so then"). Strip it before the filter
            // so a good line is not judged on an artifact of where the window happened to start.
            var text = result.text.trimmingCharacters(in: .whitespacesAndNewlines)
            while let first = text.first, !first.isLetter, !first.isNumber {
                text.removeFirst()
            }

            guard let line = TranscriptFilter.clean(text) else { return }

            onLine?(line, startEpoch, endEpoch)

            // Metrics only, never the words. Transcript text is the most sensitive thing this app
            // holds and os_log is readable by anything with the machine.
            EarshotLog.info(
                String(
                    format: "%@ %.0fs → %d chars (rms %.4f, conf %.2f, %.0fx realtime)",
                    source.rawValue, Double(take / 2) / Double(Self.sampleRate), line.count, rms,
                    result.confidence, result.rtfx), "stt")
        } catch {
            EarshotLog.error("\(source.rawValue) transcribe failed: \(error.localizedDescription)", "stt")
        }
    }

    private func dropLeadingBytes(_ count: Int) {
        guard count > 0 else { return }
        guard count < buffer.count else {
            buffer.removeAll(keepingCapacity: true)
            return
        }
        buffer = Data(buffer.dropFirst(count))
    }

    // MARK: - Music gate

    /// True when a window is music or singing rather than speech.
    ///
    /// Runs off the actor: `SNAudioFileAnalyzer.analyze()` is synchronous and would otherwise block
    /// every `append` for its duration. Fails *open* — any error means "not music", because a
    /// misclassification that drops real speech is unrecoverable and one that transcribes a song is
    /// merely untidy.
    private static func windowIsMusic(_ samples: [Float]) async -> Bool {
        await Task.detached(priority: .utility) {
            Transcriber.classifyAsMusic(samples)
        }.value
    }

    private static func classifyAsMusic(_ samples: [Float]) -> Bool {
        guard samples.count >= sampleRate,  // under ~1 s the classifier is a coin flip
            let format = AVAudioFormat(
                commonFormat: .pcmFormatFloat32, sampleRate: Double(sampleRate), channels: 1, interleaved: false),
            let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(samples.count)),
            let channel = buffer.floatChannelData
        else { return false }

        buffer.frameLength = AVAudioFrameCount(samples.count)
        samples.withUnsafeBufferPointer { channel[0].update(from: $0.baseAddress!, count: samples.count) }

        // SoundAnalysis ships a stream analyzer and a file analyzer. The file analyzer's `analyze()`
        // blocks until the observer has every result, which is the only variant that can answer a
        // yes/no question about a finished window — hence the temp WAV.
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("ambient-music-\(UUID().uuidString).wav")
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
            analyzer.analyze()  // synchronous: the tally is complete before this returns
            return tally.isMusic
        } catch {
            return false
        }
    }
}

/// Tallies SoundAnalysis frames across one window to decide music/singing vs speech.
///
/// Only reachable from `Transcriber.classifyAsMusic`, which drives it with the *synchronous*
/// analyzer, so every mutation happens before `analyze()` returns and there is no concurrent access
/// to guard.
private final class MusicTally: NSObject, SNResultsObserving {
    private var frames = 0
    private var musicFrames = 0
    private var speechFrames = 0

    func request(_ request: SNRequest, didProduce result: SNResult) {
        guard let classification = result as? SNClassificationResult,
            let top = classification.classifications.first
        else { return }

        frames += 1
        guard top.confidence > 0.3 else { return }

        let identifier = top.identifier.lowercased()
        if identifier == "speech" {
            speechFrames += 1
        } else if identifier == "music" || identifier == "singing" || identifier.contains("music") {
            musicFrames += 1
        }
    }

    /// Music has to both beat speech *and* hold a real share of the window.
    ///
    /// The second half of that is what keeps a call: the other party's voice through the system tap
    /// picks up stray music frames from hold music, notification chimes and background noise, and
    /// requiring a third of the window to be music means those never outvote a conversation. A song
    /// clears it easily.
    var isMusic: Bool { frames > 0 && musicFrames > speechFrames && musicFrames * 3 >= frames }
}


// MARK: - Model pool

/// One download-and-compile of the Parakeet weights, shared by every transcriber.
///
/// `AsrManager` instances stay separate — each channel needs its own decoder state — but the
/// weights behind them do not, and compiling them twice is pure cost paid at the worst moment.
private actor ModelPool {
    static let shared = ModelPool()

    private var loaded: [AsrModelVersion: AsrModels] = [:]
    private var inFlight: [AsrModelVersion: Task<AsrModels, Error>] = [:]

    func models(version: AsrModelVersion) async throws -> AsrModels {
        if let models = loaded[version] { return models }
        if let task = inFlight[version] { return try await task.value }

        let task = Task { try await AsrModels.downloadAndLoad(version: version) }
        inFlight[version] = task
        defer { inFlight[version] = nil }
        let models = try await task.value
        loaded[version] = models
        return models
    }
}
