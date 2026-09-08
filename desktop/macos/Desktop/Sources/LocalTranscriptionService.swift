@preconcurrency import AVFoundation
import FluidAudio
import Foundation
import SoundAnalysis

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

  private struct DrainSnapshot {
    let manager: AsrManager
    let window: [Float]
    let startSec: Double
    let durSec: Double
  }

  private let language: String
  /// Source-based diarization: mic = the user ("You"), system audio = another speaker.
  private let isUser: Bool
  private let speakerLabel: String
  private let speakerId: Int
  private let sampleRate = 16000
  /// Longest stretch transcribed at once. A window also closes early when the speaker
  /// pauses — see `silenceTailSeconds` — so this is the ceiling, not the cadence.
  private let windowSeconds = 10.0
  private var windowSamples: Int { Int(Double(sampleRate) * windowSeconds) }
  /// Trailing quiet that ends a window early. Without it a window only closes on the fixed
  /// 10 s boundary, so a short spoken command waits for wherever it happens to land in that
  /// window — measured live at 1.1 s / 6.2 s / 7.7 s for three identical utterances, i.e. ~5 s
  /// expected and ~10 s worst case. That is the whole of the wake word's latency on Apple
  /// Silicon, where `STTSessionState.resolveMode` picks this on-device path by default.
  private let silenceTailSeconds = 0.6
  /// Speech must be at least this long before a pause can close the window, so ordinary
  /// room noise blips don't emit fragments. Also keeps every emitted window ≥ 1 s, which the
  /// system-audio music classifier needs for a stable verdict.
  private let minUtteranceSeconds = 1.0
  /// Noise floor shared with `drain`'s own silence check.
  private static let speechFloor: Float = 0.004

  private var asrManager: AsrManager?
  private var onSegments: SegmentsHandler?
  /// Fired (on the main actor) if the Parakeet model fails to download/load. Lets AppState
  /// fall back to cloud STT instead of silently producing a blank transcript.
  private var onModelLoadFailed: (@MainActor () -> Void)?

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
  /// `onModelLoadFailed` fires once if the model can't load, so the caller can fall back
  /// to cloud transcription instead of recording into a void.
  func start(onSegments: @escaping SegmentsHandler, onModelLoadFailed: (@MainActor () -> Void)? = nil) {
    self.onSegments = onSegments
    self.onModelLoadFailed = onModelLoadFailed

    Task { [weak self] in
      guard let self else { return }
      do {
        // Test hook: force a model-load failure to exercise the cloud fallback path.
        // Toggle with env OMI_FORCE_PARAKEET_FAIL=1 or `defaults write <bundle> forceParakeetFail -bool true`.
        if ProcessInfo.processInfo.environment["OMI_FORCE_PARAKEET_FAIL"] == "1"
          || UserDefaults.standard.bool(forKey: "forceParakeetFail")
        {
          throw NSError(
            domain: "LocalTranscriptionService", code: -1,
            userInfo: [NSLocalizedDescriptionKey: "forced model-load failure (OMI_FORCE_PARAKEET_FAIL)"])
        }
        // v2 = English-only (better recall); v3 = 25 European languages.
        let version: AsrModelVersion = self.language.hasPrefix("en") ? .v2 : .v3
        let started = Date()
        let models = try await AsrModels.downloadAndLoad(version: version)
        let manager = AsrManager()
        try await manager.loadModels(models)
        self.lock.withLock {
          self.asrManager = manager
          self.isReady = true
        }
        log(
          "LocalTranscriptionService: Parakeet \(version) ready in \(String(format: "%.1f", Date().timeIntervalSince(started)))s"
        )
      } catch {
        logError("LocalTranscriptionService: model load failed", error: error)
        if self.onModelLoadFailed != nil {
          await MainActor.run { self.onModelLoadFailed?() }
        }
      }
    }

    pumpTask = Task { [weak self] in
      while !Task.isCancelled {
        // 0.5 s, not 1 s: with pause-closed windows the tick is now the floor on how
        // soon a finished utterance can be transcribed, not just a poll for a full window.
        try? await Task.sleep(nanoseconds: 500_000_000)
        await self?.drain(force: false)
      }
    }
  }

  /// Feed 16 kHz mono Int16 little-endian PCM — the same `Data` the WebSocket path sends.
  func appendAudio(_ data: Data) {
    let floats = Self.int16ToFloat32(data)
    guard !floats.isEmpty else { return }
    lock.withLock {
      if acceptingAudio {
        buffer.append(contentsOf: floats)
      }
    }
  }

  /// Fire-and-forget stop. Prefer `await finish()` whenever the session lifecycle allows it —
  /// `finish()` guarantees the final tail is persisted before the caller rotates/clears the
  /// session. `stop()` only drains on a detached Task, so a caller that mutates session state
  /// right after (e.g. the 4-hour restart path) can still race; it exists for teardown sites
  /// that don't have an async context.
  func stop() {
    pumpTask?.cancel()
    pumpTask = nil
    lock.withLock { acceptingAudio = false }
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
    lock.withLock { acceptingAudio = false }
    await drainAll()
  }

  /// Flush every remaining buffered sample (called on stop). Waits out any in-flight window
  /// flush first, then transcribes the sub-window tail so the last words aren't dropped.
  private func drainAll() async {
    for _ in 0..<50 {
      let busy = lock.withLock { isFlushing }
      if !busy { break }
      try? await Task.sleep(nanoseconds: 100_000_000)
    }
    await drain(force: true)
  }

  /// Transcribe one window (or whatever remains, when `force`) and emit a segment.
  private func drain(force: Bool) async {
    guard
      let snapshot = lock.withLock({
        guard isReady, let manager = asrManager, !isFlushing else { return nil as DrainSnapshot? }
        // Drop silence sitting ahead of the first speech, advancing the cursor over it so
        // absolute timestamps stay exact. Otherwise quiet counts against the 10 s cap and
        // the window fills partway through the next sentence — observed live cutting
        // "Omi, what time is it now" down to "Now". Now the cap can only be reached by
        // 10 s of continuous talking, where a cut is unavoidable anyway.
        let lead = Self.leadingSilenceSamples(buffer, chunk: sampleRate / 10, keep: 2)
        if lead > 0 {
          buffer.removeFirst(lead)
          emittedSeconds += Double(lead) / Double(sampleRate)
        }
        let available = buffer.count
        // Three ways a window closes: it filled, the speaker paused, or the session is
        // stopping. On force (stop/finish) flush whatever is left, even a sub-window tail.
        let endpointed = Self.isEndpointed(
          buffer,
          tailSamples: Int(Double(sampleRate) * silenceTailSeconds),
          minSamples: Int(Double(sampleRate) * minUtteranceSeconds)
        )
        let ready = available >= windowSamples || endpointed || (force && available > 0)
        guard ready else { return nil }
        // A pause-closed window takes the whole buffer: the boundary is the silence itself,
        // so leaving a remainder would just split the next utterance at an arbitrary point.
        let take = (force || endpointed) ? available : windowSamples
        let window = Array(buffer.prefix(take))
        buffer.removeFirst(take)
        let startSec = emittedSeconds
        let durSec = Double(take) / Double(sampleRate)
        emittedSeconds += durSec
        isFlushing = true
        return DrainSnapshot(manager: manager, window: window, startSec: startSec, durSec: durSec)
      })
    else { return }

    defer {
      lock.withLock { isFlushing = false }
    }

    // Only skip DEAD silence (noise floor). The previous 0.012 threshold was tuned on loud
    // speaker playback and ate real (quieter) microphone speech — users saw "nothing
    // transcribed". A low floor lets normal mic speech through; hallucinations on near-silence
    // are filtered below by the model's own confidence score instead.
    let rms = Self.rms(snapshot.window)
    guard rms > Self.speechFloor else { return }

    // Music/video gate: don't turn songs, TV, or videos playing through *system audio* into
    // "conversations" — only real conversations/calls should be transcribed. Applied to the
    // system channel only; the mic channel (the user's own voice) is never gated. Runs Apple's
    // on-device SoundAnalysis classifier *before* Parakeet, so music also costs us no transcription.
    if !isUser, Self.windowIsMusic(snapshot.window, sampleRate: sampleRate) {
      log(
        String(
          format: "LocalTranscriptionService[sys]: skipped %.1fs music/video window (rms=%.4f)", snapshot.durSec, rms))
      return
    }

    do {
      // Fresh decoder state per window. Persisting TdtDecoderState across arbitrary 10 s
      // windows makes the transducer decoder drift — it starts looping ("...AND AND AND"),
      // Title-Casing every word, and emitting gibberish. Independent per-window decode is stable.
      var ds = try TdtDecoderState()
      let result = try await snapshot.manager.transcribe(snapshot.window, decoderState: &ds, language: nil)

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
        start: snapshot.startSec,
        end: snapshot.startSec + snapshot.durSec,
        translations: nil
      )
      // Deliver synchronously on the main actor so an awaited finish() guarantees the
      // segment is persisted (to the current session) before the caller rotates state.
      if self.onSegments != nil {
        let segs = [segment]
        await MainActor.run { self.onSegments?(segs) }
      }
      log(
        String(
          format: "LocalTranscriptionService[%@]: %.1fs rms=%.4f conf=%.2f rtfx=%.0fx → %@",
          isUser ? "mic" : "sys", snapshot.durSec, rms, result.confidence, result.rtfx, text))
    } catch {
      logError("LocalTranscriptionService: transcribe failed", error: error)
    }
  }

  static func rms(_ samples: ArraySlice<Float>) -> Float {
    guard !samples.isEmpty else { return 0 }
    return (samples.reduce(Float(0)) { $0 + $1 * $1 } / Float(samples.count)).squareRoot()
  }

  static func rms(_ samples: [Float]) -> Float { rms(samples[...]) }

  /// True when the buffer holds a real utterance followed by `tailSamples` of quiet — the
  /// speaker finished, so the window can close now instead of at the next fixed boundary.
  ///
  /// `minSamples` is measured in *voiced* audio, not buffer length. Whole-buffer RMS would
  /// admit a window that is mostly quiet with one blip in it, and Parakeet answers those with
  /// a hallucinated word: a 1.1 s window at rms 0.0067 decoded to "Yeah." live. Requiring a
  /// second of actual speech separates that cleanly — real commands carried 2.4–2.9 s of it.
  static func isEndpointed(_ buffer: [Float], tailSamples: Int, minSamples: Int) -> Bool {
    guard tailSamples > 0, buffer.count > tailSamples else { return false }
    let split = buffer.count - tailSamples
    guard rms(buffer[split...]) <= speechFloor else { return false }
    return voicedSamples(buffer[..<split], chunk: max(1, tailSamples / 6)) >= minSamples
  }

  /// Total audio above the noise floor, counted in `chunk`-sized steps.
  static func voicedSamples(_ samples: ArraySlice<Float>, chunk: Int) -> Int {
    guard chunk > 0 else { return 0 }
    var voiced = 0
    var index = samples.startIndex
    while index + chunk <= samples.endIndex {
      if rms(samples[index..<(index + chunk)]) > speechFloor { voiced += chunk }
      index += chunk
    }
    return voiced
  }

  /// Samples of silence at the head of the buffer, scanned in `chunk`-sized steps, leaving
  /// `keep` chunks of lead-in so the window never starts flush against the first phoneme.
  /// Returns 0 when the buffer opens with speech, and stops at the first speech chunk — a
  /// pause *between* utterances is never trimmed, only quiet before any of them.
  static func leadingSilenceSamples(_ buffer: [Float], chunk: Int, keep: Int) -> Int {
    guard chunk > 0 else { return 0 }
    var silent = 0
    var index = 0
    while index + chunk <= buffer.count {
      if rms(buffer[index..<(index + chunk)]) > speechFloor { break }
      silent += 1
      index += chunk
    }
    return max(0, silent - keep) * chunk
  }

  /// Classify a 16 kHz mono window as music/singing (vs speech) using Apple's on-device
  /// SoundAnalysis. Returns true → caller skips transcribing it. Fails *open* (returns false) on
  /// any error or on macOS < 12, so audio is never silently dropped when classification is unsure.
  private static func windowIsMusic(_ window: [Float], sampleRate: Int) -> Bool {
    guard #available(macOS 12.0, *) else { return false }
    guard window.count >= sampleRate,  // need ~1s+ for a stable classification
      let format = AVAudioFormat(
        commonFormat: .pcmFormatFloat32,
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
