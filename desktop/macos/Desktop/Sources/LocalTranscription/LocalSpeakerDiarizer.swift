import FluidAudio
import Foundation

/// On-device speaker identification for the local (Parakeet) transcription path.
///
/// Owns FluidAudio's diarization models (pyannote segmentation + WeSpeaker embeddings, CoreML
/// on the Neural Engine) and one `LocalSpeakerRegistry` shared by the mic and system-audio
/// `LocalTranscriptionService` instances, so speaker ids are consistent across both lanes and
/// across conversation rotations within an app run. The user's voiceprint persists in
/// `UserDefaults` so "You" is recognised from the first sentence of the next session.
///
/// Fails open: if the models can't load, `resolve` returns nil and the transcriber keeps the
/// old source-based labels (mic = "You", system = Speaker 1).
actor LocalSpeakerDiarizer {

  static let shared = LocalSpeakerDiarizer()

  private enum State {
    case idle
    case loading(Task<Void, Never>)
    case ready
    case unavailable
  }

  private var state: State = .idle
  private var manager: DiarizerManager?
  private var registry: LocalSpeakerRegistry
  private let defaults: UserDefaults
  private let loadModels: @Sendable () async throws -> DiarizerModels

  init(
    defaults: UserDefaults = .standard,
    loadModels: @escaping @Sendable () async throws -> DiarizerModels = { try await DiarizerModels.downloadIfNeeded() }
  ) {
    self.defaults = defaults
    self.loadModels = loadModels
    self.registry = LocalSpeakerRegistry(userVoiceprint: Self.loadVoiceprint(from: defaults))
  }

  var isAvailable: Bool {
    if case .ready = state { return true }
    return false
  }

  /// Load the models once per app run. Safe to call from both lanes; the second caller
  /// awaits the first load. Returns once the diarizer is ready or has given up.
  func prepare() async {
    switch state {
    case .ready, .unavailable:
      return
    case .loading(let task):
      await task.value
      return
    case .idle:
      break
    }
    let task = Task { await self.load() }
    state = .loading(task)
    await task.value
  }

  private func load() async {
    let started = Date()
    do {
      let models = try await loadModels()
      // Short windows are common (pause-closed utterances); default 1.0 s would drop them.
      var config = DiarizerConfig()
      config.minSpeechDuration = 0.5
      let manager = DiarizerManager(config: config)
      manager.initialize(models: models)
      self.manager = manager
      state = .ready
      log(
        "LocalSpeakerDiarizer: models ready in \(String(format: "%.1f", Date().timeIntervalSince(started)))s (voiceprint: \(registry.userVoiceprint == nil ? "none" : "stored"))"
      )
    } catch {
      state = .unavailable
      logError("LocalSpeakerDiarizer: model load failed; falling back to source-based speaker labels", error: error)
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "stt_selection",
        from: "on_device_diarization",
        to: "source_lanes",
        reason: "model_load_failed",
        outcome: .degraded
      )
    }
  }

  /// Identify the dominant voice in one transcribed window. Nil when the diarizer is not
  /// available or the window yields no usable embedding — the caller keeps its lane label.
  func resolve(
    window: [Float],
    durationSeconds: Double,
    rms: Float,
    lane: LocalTranscriptionLane
  ) -> LocalSpeakerRegistry.Outcome? {
    guard case .ready = state, let manager else { return nil }
    guard let embedding = dominantEmbedding(in: window, manager: manager) else { return nil }
    let outcome = registry.observe(
      LocalSpeakerRegistry.Observation(
        embedding: embedding, durationSeconds: durationSeconds, loudness: rms, lane: lane))
    if let voiceprint = outcome?.voiceprintToPersist {
      Self.storeVoiceprint(voiceprint, in: defaults)
      log("LocalSpeakerDiarizer: persisted user voiceprint")
    }
    return outcome
  }

  /// Embedding of whoever spoke most in the window. Segmentation masks out silence and the
  /// other voice in a two-speaker window, which an all-ones mask would blend in; if
  /// segmentation finds nothing (very short window), fall back to embedding the whole clip.
  private func dominantEmbedding(in window: [Float], manager: DiarizerManager) -> [Float]? {
    do {
      // Clustering is ours (LocalSpeakerRegistry); FluidAudio's per-manager speaker table would
      // otherwise grow for the whole app run.
      manager.speakerManager.reset()
      let result = try manager.performCompleteDiarization(window)
      var durationBySpeaker: [String: Float] = [:]
      var longestBySpeaker: [String: TimedSpeakerSegment] = [:]
      for segment in result.segments where manager.validateEmbedding(segment.embedding) {
        durationBySpeaker[segment.speakerId, default: 0] += segment.durationSeconds
        if let current = longestBySpeaker[segment.speakerId], current.durationSeconds >= segment.durationSeconds {
          continue
        }
        longestBySpeaker[segment.speakerId] = segment
      }
      if let dominant = durationBySpeaker.max(by: { $0.value < $1.value })?.key,
        let segment = longestBySpeaker[dominant]
      {
        return segment.embedding
      }
      let whole = try manager.extractSpeakerEmbedding(from: window)
      return manager.validateEmbedding(whole) ? whole : nil
    } catch {
      logError("LocalSpeakerDiarizer: embedding failed", error: error)
      return nil
    }
  }

  // MARK: - Voiceprint persistence

  private static func loadVoiceprint(from defaults: UserDefaults) -> [Float]? {
    guard let data = defaults.data(forKey: DefaultsKey.localSpeakerUserVoiceprint.rawValue),
      data.count % MemoryLayout<Float>.size == 0, !data.isEmpty
    else { return nil }
    return data.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
  }

  private static func storeVoiceprint(_ voiceprint: [Float], in defaults: UserDefaults) {
    let data = voiceprint.withUnsafeBufferPointer { Data(buffer: $0) }
    defaults.set(data, forKey: DefaultsKey.localSpeakerUserVoiceprint.rawValue)
  }
}
