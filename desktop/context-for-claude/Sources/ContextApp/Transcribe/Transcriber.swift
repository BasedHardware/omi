@preconcurrency import AVFoundation
import ContextCore
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

    /// The one pool shared by onboarding's warm-up and every first capture.
    ///
    /// The generic pool is deliberately injectable so its lifecycle contract can be tested with a
    /// small value instead of downloading or loading CoreML models.
    private static let modelPool = ModelPool<AsrModels> { version, progress in
        try await obtainModels(version: version, progress: progress)
    }

    // MARK: - Tuning

    /// The wire format every capture source produces. Not configurable — the model wants 16 kHz.
    private static let sampleRate = 16_000

    /// How much audio is decoded at a time: exactly one encoder input.
    ///
    /// Deliberately *equal* to `ASRConstants.maxModelSamples` (240 000 samples — 15 s, since
    /// `ASRConstants.sampleRate` is 16 kHz too) rather than merely under it, because the Parakeet
    /// encoder is a fixed-shape CoreML graph: `Encoder.mlmodelc` declares `mel [1, 128, 1501]` with
    /// `hasShapeFlexibility = 0` and always emits 188 frames, and on v3 even the preprocessor is
    /// pinned to `audio_signal [1, 240000]`. FluidAudio zero-pads whatever it is handed up to that
    /// length before inference (`AsrManager+Transcription`), so a 10 s window and a 15 s window are
    /// the *same* encoder pass at the same cost — the short one merely discards a third of it, and
    /// discards it unread, since `TdtFrameNavigation` clamps the decode to `min(encoderSequenceLength,
    /// actualAudioFrames)` precisely "to avoid processing padding".
    ///
    /// Filling the window is therefore free coverage rather than extra work: 50 % more audio per
    /// pass, and at full duty 240 passes an hour per source instead of 360.
    ///
    /// Sitting *at* the limit and never over it is what keeps it one pass. One sample more and
    /// `transcribeWithState` routes to `ChunkProcessor`, which splits the window and pays two passes
    /// for it; at exactly 240 000 both `frameAlignedAudio` and `padAudioIfNeeded` are no-ops, so the
    /// tensor handed to the ANE is all real audio and nothing else.
    ///
    /// What it costs is latency — a line lands ~15 s after it was spoken, plus a pump tick. Nothing
    /// in Context for Claude cares (there is no live caption UI; the transcript is read minutes to
    /// months later), and the decoder seeing whole clauses instead of fragments is exactly why the
    /// text comes out punctuated and cased like written English rather than like a live caption.
    /// Fewer, longer windows also mean fewer seams, and every seam costs the words that straddle it
    /// — see the fresh-decoder-state note in ``drain(force:)``.
    private static let windowSamples = ASRConstants.maxModelSamples

    /// The pump interval. Shorter than a window on purpose: a window becomes complete at an
    /// arbitrary moment, and polling at 1 s means it waits at most a second to be decoded.
    private static let pumpInterval: Duration = .seconds(1)

    /// How far the sample clock may disagree with the wall clock before it is re-anchored.
    ///
    /// Ten seconds. Capture latency is milliseconds, so anything approaching this is a real stall
    /// (device rebuild, system sleep, a tap that stopped delivering), not jitter.
    ///
    /// Held at ten deliberately, rather than following the window length as it once did. The two
    /// were equal by coincidence, not by construction: this measures how late audio *arrived*, which
    /// `reanchorClockIfDrifted` reads from the total samples ever received and is therefore
    /// independent of how much audio is decoded per pass. Letting it grow with the window would only
    /// widen the band in which a stalled tap goes unnoticed and timestamps stay wrong.
    private static let driftTolerance = 10.0

    /// Ceiling on undecoded audio.
    ///
    /// Only reachable while the model is still loading — once it is up the pump drains many times
    /// faster than real time. Five minutes covers a first-run download without letting a daemon
    /// that will run for weeks grow a buffer nobody bounded.
    private static let maxBufferedSeconds = 300.0

    private static var windowBytes: Int { windowSamples * 2 }
    private static var maxBufferedBytes: Int { Int(maxBufferedSeconds * Double(sampleRate)) * 2 }

    // MARK: - Model selection

    /// The language the model is chosen for.
    ///
    /// Context for Claude has no settings screen, so this follows the system language. `CONTEXT_LANG`
    /// overrides it, which is how a non-English decode gets exercised on an English machine.
    static var language: String {
        if let override = ProcessInfo.processInfo.environment["CONTEXT_LANG"], !override.isEmpty {
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
    static var isModelReady: Bool { isModelOnDisk(modelVersion) }

    /// The same question for an explicit version, which is what the airgap gate needs: the decision
    /// is "may these particular weights be fetched", and the answer turns on whether they are here.
    static func isModelOnDisk(_ version: AsrModelVersion) -> Bool {
        AsrModels.modelsExist(at: AsrModels.defaultCacheDirectory(for: version), version: version)
    }

    /// Downloads and compiles the model, reporting progress in 0...1.
    ///
    /// This exists purely so onboarding can own the ~600 MB first run. Without it the download
    /// happens inside the first `start()`, where it is invisible: the app says it is listening, the
    /// user has a conversation, and the audio spends the whole call queued behind a download. Doing
    /// it up front, with a progress bar, is the difference between a slow step and a silent failure.
    ///
    /// It loads as well as downloads, deliberately. Compiling the `.mlmodelc` files the first time
    /// is itself slow, and paying that here warms the compile cache. The loaded models go through
    /// ``ModelPool`` so the first capture reuses them instead of loading a second CoreML copy.
    ///
    /// Throws under Airgap Mode with nothing on disk — see ``SpeechModelAccess``.
    static func prepareModels(progress: (@Sendable (Double) -> Void)? = nil) async throws {
        let version = modelVersion
        if isModelReady {
            progress?(1)
            return
        }

        let started = Date()
        _ = try await modelPool.models(version: version, progress: progress)
        progress?(1)
        ContextLog.info(
            "Parakeet \(version) downloaded in \(String(format: "%.0f", Date().timeIntervalSince(started)))s", "stt")
    }

    /// The **only** call in this app that may put the Parakeet weights on disk.
    ///
    /// Both paths that need the model funnel through here — onboarding's warm-up above and
    /// ``ModelPool``, which is where the first `start()` lands — so Airgap Mode is asked once,
    /// in one place, rather than being re-derived at two call sites that can drift apart.
    ///
    /// `fileprivate` so `ModelPool`, below, can reach it and nothing outside this file can.
    fileprivate static func obtainModels(
        version: AsrModelVersion, progress: (@Sendable (Double) -> Void)? = nil
    ) async throws -> AsrModels {
        // Read once and used for both decisions below. Two reads could straddle a flip of the switch
        // and leave FluidAudio's offline flag disagreeing with the branch we then took.
        let airgapMode = NetworkEgress.isSuppressed(.speechModelDownload)

        // FluidAudio has its own offline switch, and ours is pushed into it on every call rather
        // than once at launch. It is not the guard — ``SpeechModelAccess`` is — it is what closes
        // the path the guard cannot see: `AsrModels.load` reaches `ModelHub.loadModels`, which on a
        // load failure purges the cache and re-downloads the whole repo unprompted. A load we
        // deliberately allowed because the weights were on disk could otherwise turn into the exact
        // 600 MB fetch we just refused, on a machine whose user asked for silence.
        ModelHub.offlineMode = airgapMode

        // FluidAudio reports a real fraction plus a phase (listing / downloading / compiling); only
        // the fraction is surfaced, because a progress bar that also changes its label mid-download
        // reads as an error to most people.
        let report: ProgressHandler = { update in progress?(update.fractionCompleted) }

        return try await SpeechModelAccess.obtain(
            airgapMode: airgapMode,
            isOnDisk: { isModelOnDisk(version) },
            loadFromDisk: {
                try await AsrModels.load(
                    from: AsrModels.defaultCacheDirectory(for: version),
                    version: version,
                    progressHandler: report)
            },
            fetch: {
                try await AsrModels.downloadAndLoad(version: version, progressHandler: report)
            })
    }

    // MARK: - State

    /// Which side of the conversation this instance transcribes. Mic is the user; the system tap is
    /// everyone else. That is the whole of Context for Claude's diarization, and it is the only kind that
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
            let models = try await Self.modelPool.models(version: version)
            let loaded = AsrManager()
            try await loaded.loadModels(models)
            manager = loaded
            ContextLog.info(
                "Parakeet \(version) ready for \(source.rawValue) in "
                    + "\(String(format: "%.1f", Date().timeIntervalSince(started)))s", "stt")
        } catch {
            // Tear the pump back down rather than leave it spinning over a buffer nothing will ever
            // decode — otherwise the buffer fills to its ceiling and the app looks alive.
            pump?.cancel()
            pump = nil
            acceptingAudio = false
            buffer.removeAll(keepingCapacity: false)
            ContextLog.error("Parakeet load failed for \(source.rawValue): \(error.localizedDescription)", "stt")
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
            anchorEpoch = ContextTime.now - Double(bufferedSamples) / Double(Self.sampleRate)
            return
        }

        let projectedNow = anchor + Double(samplesConsumed + bufferedSamples) / Double(Self.sampleRate)
        let drift = ContextTime.now - projectedNow
        guard abs(drift) > Self.driftTolerance else { return }

        anchorEpoch = anchor + drift
        ContextLog.info(
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
        ContextLog.error(
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
        //
        // Dropped rather than held back to be batched with the next window: this is only reachable
        // on the forced final drain, because the pump takes nothing but whole windows, so it is a
        // once-per-`finish()` event and not a per-hour cost. There is nothing to batch it with
        // either — the model takes one buffer per call, and the only other buffer in flight belongs
        // to the other channel, which is a different speaker and a different `AsrManager`.
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

        // Songs, TV and videos come through the system tap exactly like a call does — and a speaker
        // in the room reaches the mic exactly like the user does. Apple's on-device classifier is
        // the only thing that tells them apart, and it runs before Parakeet so music also costs no
        // transcription.
        //
        // Both channels are gated. The mic used to be exempt, on the reasoning that the user's own
        // voice is always worth keeping including when they sing, and that exemption is what let a
        // stereo in the room be transcribed and filed under `speaker == "me"`. That is the one
        // failure this app cannot absorb: a lyric stored as first-person speech is indistinguishable
        // from something the user actually said, `recall` hands it to Claude as evidence about their
        // life, and the product's own framing ("empty inside the coverage window means it did not
        // happen") makes it *more* credible rather than less. Losing the user's own singing is the
        // price of that, and it is the right way round — a sung line dropped is a gap in a
        // transcript, a sung line kept is a sentence they never said.
        //
        // The thresholds differ per channel and both are biased hard towards keeping: see
        // ``minimumMusicShare`` and ``MusicTally``.
        //
        // Skipping is safe for the timeline because `samplesConsumed` was advanced above, before any
        // gate could return — the clock counts audio that *left the buffer*, decoded or not, so a
        // dropped window leaves a hole rather than shifting every later timestamp.
        let verdict = await Self.windowIsMusic(samples, minimumMusicShare: minimumMusicShare)
        if verdict.isMusic {
            // Metrics only, and the tally counts specifically so a future retune has something to
            // read: this gate spent its whole life returning `false` for a mechanical reason (see
            // ``classifyAsMusic``) and a log line that only said "skipped" could never have shown it.
            ContextLog.info(
                String(
                    format: "%@ window skipped as music (rms %.4f, music %d/%d frames, "
                        + "speech %d frames, peak speech %.2f)",
                    source.rawValue, rms, verdict.musicFrames, verdict.frames, verdict.speechFrames,
                    verdict.peakSpeechConfidence), "stt")
            return
        }

        do {
            // A fresh decoder state for EVERY window. This is the least obvious line in the file
            // and the most expensive one to get wrong. `TdtDecoderState` is designed to carry
            // context across *contiguous* streaming chunks; carried across arbitrary 15 s windows —
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
            ContextLog.info(
                String(
                    format: "%@ %.0fs → %d chars (rms %.4f, conf %.2f, %.0fx realtime)",
                    source.rawValue, Double(take / 2) / Double(Self.sampleRate), line.count, rms,
                    result.confidence, result.rtfx), "stt")
        } catch {
            ContextLog.error("\(source.rawValue) transcribe failed: \(error.localizedDescription)", "stt")
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

    /// How much of a window must come back as music before it is dropped, per channel.
    ///
    /// The two channels hear music over different paths, and one number does not fit both. System
    /// audio *is* the recording: full level, no room, no noise. The mic hears a speaker across a
    /// room — reverberant, low-passed, mixed with room tone, then levelled by the mic's own AGC.
    ///
    /// Measured, that path does the opposite of what it sounds like it should. Rendering seven
    /// tracks through a room impulse plus room tone recorded on this machine's own mic raised the
    /// average music-classified frames from 5.2 of 9 (played clean) to 8.2 of 9. Reverb and HF
    /// rolloff smear a signal towards "music"; they do not hide it. What the room path *does* hide
    /// is speech — which makes the system channel's one-third bar dangerous here, not conservative.
    /// Reusing it on the mic dropped 88 of 96 windows that contained a real 1.5–4 s utterance spoken
    /// over room music: it would have deleted nearly every short thing the user said with a speaker
    /// on.
    ///
    /// Two-thirds is close to free on real music (65 of 84 room-music windows still drop, against 66
    /// at one-third) and is much harder to clear by accident, so the mic pays the higher bar.
    private var minimumMusicShare: Double {
        switch source {
        case .system: 1.0 / 3.0
        case .mic: 2.0 / 3.0
        }
    }

    /// Classifies one window as music/singing rather than speech.
    ///
    /// Runs off the actor: `SNAudioFileAnalyzer.analyze()` is synchronous and would otherwise block
    /// every `append` for its duration. Fails *open* — any error means "not music", because a
    /// misclassification that drops real speech is unrecoverable and one that transcribes a song is
    /// merely untidy.
    ///
    /// Cost, measured on this machine over 25 warm runs of a full 240 000-sample window: 0.7 ms to
    /// write the WAV and 112 ms to analyse it, median 112.5 ms end to end. At the 15 s window cadence
    /// that is 240 windows an hour per channel, so gating both channels costs 54 s of CPU an hour at
    /// full duty — 1.5 % of one core, on `.utility` QoS, which is to say the efficiency cores. It is
    /// also self-limiting: the RMS gate above has already removed the silent windows, and every
    /// window this *does* catch skips a Parakeet pass that costs more than the classification did.
    ///
    /// So it is left running on every window, and deliberately not sampled or made conditional.
    /// Sampling every Nth window would let (N−1)/N of the lyrics through, which does not fix the
    /// defect — the harm here is per-line, one fabricated first-person sentence at a time. Gating on
    /// low transducer confidence would be worse than useless: it would have to run Parakeet first,
    /// forfeiting the "music costs no transcription" saving, and music does not decode with low
    /// confidence — the lyrics that prompted this fix came through as fluent, well-formed,
    /// high-confidence sentences.
    private static func windowIsMusic(_ samples: [Float], minimumMusicShare: Double) async
        -> MusicVerdict
    {
        await Task.detached(priority: .utility) {
            Transcriber.classifyAsMusic(samples, minimumMusicShare: minimumMusicShare)
        }.value
    }

    private static func classifyAsMusic(_ samples: [Float], minimumMusicShare: Double)
        -> MusicVerdict
    {
        guard samples.count >= sampleRate,  // under ~1 s the classifier is a coin flip
            let format = AVAudioFormat(
                commonFormat: .pcmFormatFloat32, sampleRate: Double(sampleRate), channels: 1, interleaved: false),
            let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(samples.count)),
            let channel = buffer.floatChannelData
        else { return .inconclusive }

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
            // Scoped so the writer is closed before the analyzer opens the file, and this is load
            // bearing. `AVAudioFile` finalises the WAV header — the data-chunk length above all — in
            // its deinit, so a file still held open reads back as zero-length audio: `analyze()`
            // returns having produced no results at all, the tally sees `frames == 0`, and the gate
            // answers "not music" for every window ever handed to it. That is why music was reaching
            // the transcript on *both* channels rather than only the ungated one, and why the gate
            // had never once fired since it was written. Verified directly: same window, same
            // analyzer, 0 frames with the writer alive and 9 with it closed.
            do {
                let file = try AVAudioFile(forWriting: url, settings: settings)
                try file.write(from: buffer)
            }

            let analyzer = try SNAudioFileAnalyzer(url: url)
            let request = try SNClassifySoundRequest(classifierIdentifier: .version1)
            let tally = MusicTally()
            try analyzer.add(request, withObserver: tally)
            analyzer.analyze()  // synchronous: the tally is complete before this returns
            return tally.verdict(minimumMusicShare: minimumMusicShare)
        } catch {
            return .inconclusive
        }
    }
}

/// What the classifier made of one window. Counts only — no audio, nothing quotable, safe to log.
private struct MusicVerdict: Sendable {
    let isMusic: Bool
    let frames: Int
    let musicFrames: Int
    let speechFrames: Int
    let peakSpeechConfidence: Double

    /// The fail-open answer: the classifier could not be run, so nothing is suppressed.
    static let inconclusive = MusicVerdict(
        isMusic: false, frames: 0, musicFrames: 0, speechFrames: 0, peakSpeechConfidence: 0)
}

/// Tallies SoundAnalysis frames across one window to decide music/singing vs speech.
///
/// Only reachable from `Transcriber.classifyAsMusic`, which drives it with the *synchronous*
/// analyzer, so every mutation happens before `analyze()` returns and there is no concurrent access
/// to guard.
private final class MusicTally: NSObject, SNResultsObserving {
    /// Any single frame this sure it heard speech keeps the whole window, whatever else is in it.
    ///
    /// Picked from the wrong side deliberately. Across 299 windows built to contain real speech — a
    /// person talking across the room, someone talking over a song, a single 1.5 s sentence dropped
    /// into 15 s of room music — the lowest peak speech confidence any of them reached was 0.48.
    /// Sitting at 0.4 clears every one of them with margin to spare, and buys that margin for three
    /// points of recall on real music (65 of 84 room-music windows still drop, against 67 at 0.45).
    ///
    /// The asymmetry is the point. A window wrongly kept is a stray lyric in a transcript, visible
    /// and ignorable. A window wrongly dropped is a sentence the user really said that now exists
    /// nowhere, and `recall` will report the silence as evidence it never happened.
    private static let speechVetoConfidence = 0.4

    private var frames = 0
    private var musicFrames = 0
    private var speechFrames = 0
    private var peakSpeechConfidence = 0.0

    func request(_ request: SNRequest, didProduce result: SNResult) {
        guard let classification = result as? SNClassificationResult else { return }
        frames += 1

        // Read speech confidence *before* the top-1 test rather than after. SoundAnalysis scores
        // every class independently instead of splitting one budget between them, so a frame can be
        // 0.9 music and 0.7 speech at the same time. Counting speech only when it wins the frame
        // throws away precisely the evidence that matters here — someone talking *over* the music,
        // where music wins nearly every frame and the speech never surfaces as top-1 at all.
        if let speech = classification.classification(forIdentifier: "speech") {
            peakSpeechConfidence = max(peakSpeechConfidence, speech.confidence)
        }

        guard let top = classification.classifications.first, top.confidence > 0.3 else { return }

        let identifier = top.identifier.lowercased()
        if identifier == "speech" {
            speechFrames += 1
        } else if identifier == "music" || identifier == "singing" || identifier.contains("music") {
            musicFrames += 1
        }
    }

    /// Music has to hold a real share of the window *and* the window has to hold no speech at all.
    ///
    /// Three conditions, and only the last is about music. The first two are the ones that keep a
    /// conversation: any frame where speech won outright, or any frame merely confident that speech
    /// was present, and the window survives regardless of how musical the rest of it looked. That is
    /// what makes "when a window contains both music and speech, keep it" a property of the rule
    /// rather than a hope about the thresholds.
    ///
    /// Measured over 299 speech-bearing windows it suppresses 0, including 0 of the 96 holding only
    /// a brief utterance over room music. The previous rule — music merely outvoting speech and
    /// holding a third of the window — suppressed 163 of those 299 when pointed at a microphone.
    ///
    /// `frames > 0` is the fail-open case: no frames means the classifier told us nothing, and a
    /// gate that knows nothing must not delete anything.
    func verdict(minimumMusicShare: Double) -> MusicVerdict {
        let musical = Double(musicFrames) >= Double(frames) * minimumMusicShare
        let heardSpeech = speechFrames > 0 || peakSpeechConfidence >= Self.speechVetoConfidence
        return MusicVerdict(
            isMusic: frames > 0 && !heardSpeech && musical,
            frames: frames,
            musicFrames: musicFrames,
            speechFrames: speechFrames,
            peakSpeechConfidence: peakSpeechConfidence)
    }
}


// MARK: - Airgap

/// Whether the ~600 MB Parakeet weights may be fetched, and what to do when they may not.
///
/// This is the largest single thing this app ever pulls over the network, it goes to a third party
/// (HuggingFace) rather than to the user's own account, and it used to be the one remote client with
/// no entry in `NetworkEgress.Client` — so Airgap Mode did not cover it. `exclusions.json` outlives
/// an app reinstall, which is the case that made it matter: a user who had turned the switch on,
/// reinstalled, and launched would have watched 600 MB leave the machine on first run with no
/// suppression, no record, and nothing on screen to connect it to a setting they had set.
///
/// The rule has three outcomes rather than two, and the middle one is the point:
///
/// - Weights **already on disk** load regardless of the switch. Loading a local file is not egress,
///   and on-device transcription is what Airgap Mode exists to protect — a version of it that broke
///   the offline transcriber would be enforcing the opposite of its promise.
/// - Weights **missing with the switch off** are fetched, as before.
/// - Weights **missing with the switch on** are refused, loudly. There is no third option: the model
///   cannot be conjured, so transcription is simply off until the user turns the switch off, and
///   saying that is better than a progress bar that never moves.
///
/// Generic over the model type so the rule can be driven end to end in a test. CoreML weights are
/// precisely the thing a hermetic test cannot have, and a guard nobody can execute is a guard that
/// quietly stops working — see `AirgapEgressTests`.
enum SpeechModelAccess {

    /// What the weights are allowed to cost right now.
    enum Decision: Equatable {
        /// Not on this Mac, and nothing forbids fetching them.
        case fetch
        /// Already here. Local work, so Airgap Mode has no say.
        case loadWhatIsAlreadyHere
        /// Airgap Mode is on and there is nothing on disk to fall back to.
        case refuse
    }

    /// The decision, as a pure function of the two facts it turns on — so all four combinations are
    /// drivable without a network, a disk, or a 600 MB download.
    ///
    /// `isOnDisk` is read first deliberately: Airgap Mode only ever governs the *fetch*, so a
    /// present model short-circuits the question entirely.
    static func decide(airgapMode: Bool, isOnDisk: Bool) -> Decision {
        if isOnDisk { return .loadWhatIsAlreadyHere }
        return airgapMode ? .refuse : .fetch
    }

    /// Applies ``decide(airgapMode:isOnDisk:)``, and records the refusal where every other Airgap
    /// suppression in this app is recorded.
    static func obtain<Model>(
        airgapMode: Bool,
        isOnDisk: () -> Bool,
        loadFromDisk: () async throws -> Model,
        fetch: () async throws -> Model
    ) async throws -> Model {
        switch decide(airgapMode: airgapMode, isOnDisk: isOnDisk()) {
        case .loadWhatIsAlreadyHere:
            return try await loadFromDisk()
        case .fetch:
            return try await fetch()
        case .refuse:
            // Degraded rather than dropped: nothing of the user's is destroyed and nothing is
            // queued to be lost — the weights are still there to fetch the moment the switch goes
            // off. What *is* gone is the transcript of whatever is said while it stays on, and the
            // app cannot defer that: there is no model to decode it with, now or later, so holding
            // the audio would only trade an honest gap for an unbounded buffer.
            NetworkEgress.recordSuppression(.speechModelDownload, outcome: .degraded)
            ContextLog.error(
                "Airgap Mode on and the speech model is not on this Mac — nothing will be "
                    + "transcribed until it is turned off", "stt")
            throw SpeechModelError.airgapped
        }
    }
}

/// Why the speech model could not be obtained.
///
/// A `LocalizedError` because the sentence is the whole of the fix: `Engine.startAudio` turns a
/// throw from `Transcriber.start()` into the paused reason shown against that capture source, so
/// this text is what the user actually reads when transcription does not come up. It is
/// `NetworkEgress.explanation` verbatim rather than a second wording of it — one refusal, one
/// sentence, wherever it surfaces.
enum SpeechModelError: LocalizedError {
    case airgapped

    var errorDescription: String? {
        switch self {
        case .airgapped: return NetworkEgress.explanation(.speechModelDownload)
        }
    }
}

// MARK: - Model pool

/// One download-and-compile of a model value, shared by every caller for a version.
///
/// `AsrManager` instances stay separate — each channel needs its own decoder state — but the
/// weights behind them do not, and compiling them twice is pure cost paid at the worst moment. The
/// loader is injected so this task/result-sharing contract can be tested without CoreML hardware.
actor ModelPool<Value: Sendable> {
    typealias Loader = @Sendable (
        AsrModelVersion,
        (@Sendable (Double) -> Void)?
    ) async throws -> Value

    private let loader: Loader
    private var loaded: [AsrModelVersion: Value] = [:]
    private var inFlight: [AsrModelVersion: Task<Value, Error>] = [:]

    init(loader: @escaping Loader) {
        self.loader = loader
    }

    func models(
        version: AsrModelVersion,
        progress: (@Sendable (Double) -> Void)? = nil
    ) async throws -> Value {
        if let models = loaded[version] { return models }
        if let task = inFlight[version] { return try await task.value }

        // The production loader is `Transcriber.obtainModels`, not `AsrModels.downloadAndLoad` —
        // this was the second of the two unguarded entry points, and the one a real user hits:
        // onboarding's warm-up is skippable, but every first `Transcriber.start()` arrives here.
        //
        // Only a *success* is cached, so a refusal is re-decided on the next start rather than
        // remembered. That is what lets transcription come up on its own the moment Airgap Mode goes
        // off, and it costs nothing to re-ask: a refused decision is one `FileManager` existence
        // check and never touches the network.
        let loader = self.loader
        let task = Task { try await loader(version, progress) }
        inFlight[version] = task
        defer { inFlight[version] = nil }
        let models = try await task.value
        loaded[version] = models
        return models
    }
}
