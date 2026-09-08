import FluidAudio
import Foundation

/// On-device speaker identification for the local (Parakeet) transcription path.
///
/// Owns FluidAudio's diarization models (pyannote segmentation + WeSpeaker embeddings, CoreML
/// on the Neural Engine) and one `LocalSpeakerRegistry` shared by the mic and system-audio
/// `LocalTranscriptionService` instances, so speaker ids are consistent across both lanes and
/// across conversation rotations within an app run. Remembered voices — the user's and every
/// named person's — live in `LocalVoiceprintStore`, so "You" and known people are recognised
/// from the first sentence of the next session.
///
/// Fails open: if the models can't load, `resolve` returns nil and the transcriber keeps the
/// old source-based labels (mic = "You", system = Speaker 1).
actor LocalSpeakerDiarizer {

  static let shared = LocalSpeakerDiarizer()

  /// What the People page shows about a remembered voice.
  struct VoiceSummary: Equatable, Sendable {
    let personId: String?
    let speechSeconds: Double
    let updatedAt: Date
    let isEnrolled: Bool
  }

  private enum State {
    case idle
    case loading(Task<Void, Never>)
    case ready
    case unavailable
  }

  /// Shortest push-to-talk sample worth learning the user's voice from.
  static let minEnrollmentSeconds = 2.0

  typealias RelabelSink = @MainActor ([Int: LocalSpeakerRegistry.Resolution]) -> Void

  private var state: State = .idle
  /// Where relabels go when they originate here rather than from a transcriber window (a
  /// push-to-talk enrollment that identifies a live speaker). Set by the app when the local
  /// transcription services start.
  private var relabelSink: RelabelSink?
  private var manager: DiarizerManager?
  private var registry: LocalSpeakerRegistry
  private var store: LocalVoiceprintStore
  private var voiceprints: [StoredVoiceprint]
  private let loadModels: @Sendable () async throws -> DiarizerModels

  init(
    store: LocalVoiceprintStore = .forCurrentUser(),
    loadModels: @escaping @Sendable () async throws -> DiarizerModels = { try await DiarizerModels.downloadIfNeeded() }
  ) {
    self.store = store
    self.loadModels = loadModels
    let voiceprints = store.load()
    self.voiceprints = voiceprints
    self.registry = LocalSpeakerRegistry(knownVoices: voiceprints.map(Self.knownVoice))
  }

  var isAvailable: Bool {
    if case .ready = state { return true }
    return false
  }

  func setRelabelSink(_ sink: RelabelSink?) {
    relabelSink = sink
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
      let known = voiceprints.filter { $0.personId != nil }.count
      log(
        "LocalSpeakerDiarizer: models ready in \(String(format: "%.1f", Date().timeIntervalSince(started)))s (user voice: \(userVoiceDescription), \(known) known people)"
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

  private var userVoiceDescription: String {
    guard let user = voiceprints.first(where: { $0.personId == nil }) else { return "none" }
    return user.isEnrolled ? "enrolled" : "learned"
  }

  // MARK: - Windows

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
    if let updates = outcome?.voiceprintsToPersist, !updates.isEmpty {
      remember(updates)
    }
    return outcome
  }

  // MARK: - Explicit identity

  /// "This is me" on a live bubble. Returns the relabels for segments already on screen.
  func markSpeakerAsUser(_ speakerId: Int) -> [Int: LocalSpeakerRegistry.Resolution] {
    guard let result = registry.markAsUser(speakerId: speakerId) else { return [:] }
    remember([result.persist])
    log("LocalSpeakerDiarizer: speaker \(speakerId) marked as the user")
    return result.relabels
  }

  /// A live speaker was named (or un-named). Teaches that person's voice.
  func assignPerson(_ personId: String?, toSpeaker speakerId: Int) -> [Int: LocalSpeakerRegistry.Resolution] {
    guard let result = registry.assignPerson(personId, toSpeakerId: speakerId) else { return [:] }
    if let update = result.persist { remember([update]) }
    return result.relabels
  }

  /// Learn the user's voice from a push-to-talk turn: whoever holds the shortcut and talks to
  /// Omi is the user beyond doubt. 16 kHz mono Int16 PCM. When a live mic speaker turns out
  /// to be the user, the relabels go to the sink the app registered.
  func enrollUserVoice(pcm16k: Data) async {
    guard case .ready = state, let manager else { return }
    let seconds = Double(pcm16k.count / 2) / 16000
    guard seconds >= Self.minEnrollmentSeconds else { return }
    let samples = Self.int16ToFloat32(pcm16k)
    guard let embedding = dominantEmbedding(in: samples, manager: manager),
      let result = registry.enrollUser(embedding: embedding, speechSeconds: seconds)
    else { return }
    remember([result.persist])
    log("LocalSpeakerDiarizer: learned the user's voice from a \(String(format: "%.1f", seconds))s push-to-talk turn")
    if !result.relabels.isEmpty, let relabelSink {
      let relabels = result.relabels
      await MainActor.run { relabelSink(relabels) }
    }
  }

  /// Forget a remembered voice (the user's when `personId` is nil).
  func forgetVoice(personId: String?) {
    registry.forgetVoice(personId: personId)
    voiceprints.removeAll { $0.personId == personId }
    store.save(voiceprints)
  }

  func voiceSummaries() -> [VoiceSummary] {
    voiceprints.map {
      VoiceSummary(personId: $0.personId, speechSeconds: $0.speechSeconds, updatedAt: $0.updatedAt, isEnrolled: $0.isEnrolled)
    }
  }

  private func remember(_ updates: [VoiceprintUpdate]) {
    for update in updates {
      voiceprints = LocalVoiceprintStore.applying(update, to: voiceprints)
    }
    store.save(voiceprints)
    let who = updates.map { $0.personId ?? "user" }.joined(separator: ", ")
    log("LocalSpeakerDiarizer: remembered voice for \(who)")
  }

  private static func knownVoice(_ stored: StoredVoiceprint) -> LocalSpeakerRegistry.KnownVoice {
    LocalSpeakerRegistry.KnownVoice(personId: stored.personId, embedding: stored.embedding, isEnrolled: stored.isEnrolled)
  }

  // MARK: - Embeddings

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

  private static func int16ToFloat32(_ data: Data) -> [Float] {
    let count = data.count / 2
    guard count > 0 else { return [] }
    return data.withUnsafeBytes { raw -> [Float] in
      let samples = raw.bindMemory(to: Int16.self)
      return (0..<count).map { Float(Int16(littleEndian: samples[$0])) / 32768.0 }
    }
  }
}
