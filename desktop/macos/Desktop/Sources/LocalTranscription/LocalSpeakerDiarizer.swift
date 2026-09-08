import FluidAudio
import Foundation

/// On-device speaker identification for the local (Parakeet) transcription path.
///
/// Owns FluidAudio's diarization models (pyannote segmentation + WeSpeaker embeddings, CoreML
/// on the Neural Engine) and one `LocalSpeakerRegistry` shared by the mic and system-audio
/// `LocalTranscriptionService` instances, so speaker ids are consistent across both lanes and
/// across conversation rotations within an app run. Remembered voices — the user's and every
/// named person's, each with a few short audio samples — live in `LocalVoiceprintStore`,
/// bounded by `VoiceEnrollmentPolicy` (aged frequency, favorites pinned), so "You" and known
/// people are recognised from the first sentence of the next session.
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
    let isFavorite: Bool
    let lastHeardAt: Date?
    let sampleURLs: [URL]
  }

  private enum State {
    case idle
    case loading(Task<Void, Never>)
    case ready
    case unavailable
  }

  typealias RelabelSink = @MainActor ([Int: LocalSpeakerRegistry.Resolution]) -> Void

  /// Shortest push-to-talk sample worth learning the user's voice from.
  static let minEnrollmentSeconds = 2.0
  /// Recent confident windows kept per live speaker, so naming them can save audio at once.
  private static let recentWindowsPerCluster = 3

  private var state: State = .idle
  /// Where relabels go when they originate here rather than from a transcriber window (a
  /// push-to-talk enrollment that identifies a live speaker). Set by the app when the local
  /// transcription services start.
  private var relabelSink: RelabelSink?
  private var manager: DiarizerManager?
  private var registry: LocalSpeakerRegistry
  private let store: LocalVoiceprintStore
  private let policy: VoiceEnrollmentPolicy
  private var voiceprints: [StoredVoiceprint]
  private let loadModels: @Sendable () async throws -> DiarizerModels
  private let now: @Sendable () -> Date
  /// Confident windows per registry cluster key, newest last.
  private var recentWindows: [Int: [[Float]]] = [:]
  /// Voices already counted as "heard" this app run (`VoiceEnrollmentPolicy` scores sessions).
  private var usedThisRun: Set<String> = []
  private var lastSampleAt: [String: Date] = [:]

  init(
    store: LocalVoiceprintStore = .forCurrentUser(),
    policy: VoiceEnrollmentPolicy = VoiceEnrollmentPolicy(),
    loadModels: @escaping @Sendable () async throws -> DiarizerModels = { try await DiarizerModels.downloadIfNeeded() },
    now: @escaping @Sendable () -> Date = { Date() }
  ) {
    self.store = store
    self.policy = policy
    self.loadModels = loadModels
    self.now = now
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
    guard
      let outcome = registry.observe(
        LocalSpeakerRegistry.Observation(
          embedding: embedding, durationSeconds: durationSeconds, loudness: rms, lane: lane))
    else { return nil }

    // A window that joined its cluster confidently (or opened it) is clean audio of one voice.
    let confident = outcome.nearestDistance == .infinity || outcome.nearestDistance <= registry.config.updateThreshold
    if confident, let key = registry.cluster(forSpeakerId: outcome.resolution.speakerId)?.key {
      var windows = recentWindows[key, default: []]
      windows.append(window)
      if windows.count > Self.recentWindowsPerCluster {
        windows.removeFirst(windows.count - Self.recentWindowsPerCluster)
      }
      recentWindows[key] = windows
    }

    // A remembered voice was heard: count the session and, now and then, keep a clip.
    let owner: String??
    if let personId = outcome.resolution.personId {
      owner = .some(personId)
    } else if outcome.resolution.isUser, registry.userIsConfirmed {
      owner = .some(nil)
    } else {
      owner = nil
    }
    if let owner, voiceprints.contains(where: { $0.personId == owner }) {
      var changed = touchUse(personId: owner)
      if confident, saveSampleIfDue(personId: owner, samples: window) { changed = true }
      if changed { persist() }
    }

    if !outcome.voiceprintsToPersist.isEmpty {
      remember(outcome.voiceprintsToPersist)
    }
    return outcome
  }

  // MARK: - Explicit identity

  /// "This is me" on a live bubble. Returns the relabels for segments already on screen.
  func markSpeakerAsUser(_ speakerId: Int) -> [Int: LocalSpeakerRegistry.Resolution] {
    let clusterKey = registry.cluster(forSpeakerId: speakerId)?.key
    guard let result = registry.markAsUser(speakerId: speakerId) else { return [:] }
    remember([result.persist])
    if let clusterKey { saveRecentWindows(of: clusterKey, as: nil) }
    _ = touchUse(personId: nil)
    persist()
    log("LocalSpeakerDiarizer: speaker \(speakerId) marked as the user")
    return result.relabels
  }

  /// A live speaker was named (or un-named). Teaches that person's voice and keeps a clip.
  func assignPerson(_ personId: String?, toSpeaker speakerId: Int) -> [Int: LocalSpeakerRegistry.Resolution] {
    let clusterKey = registry.cluster(forSpeakerId: speakerId)?.key
    guard let result = registry.assignPerson(personId, toSpeakerId: speakerId) else { return [:] }
    if let update = result.persist { remember([update]) }
    if let personId, let clusterKey {
      saveRecentWindows(of: clusterKey, as: personId)
      _ = touchUse(personId: personId)
      persist()
    }
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
    _ = saveSampleIfDue(personId: nil, samples: samples, force: true)
    _ = touchUse(personId: nil)
    persist()
    log("LocalSpeakerDiarizer: learned the user's voice from a \(String(format: "%.1f", seconds))s push-to-talk turn")
    if !result.relabels.isEmpty, let relabelSink {
      let relabels = result.relabels
      await MainActor.run { relabelSink(relabels) }
    }
  }

  /// Speaker embedding of a clip (16 kHz mono), for callers that rebuild voices from stored
  /// audio. Nil until the models are loaded.
  func embedding(for samples: [Float]) -> [Float]? {
    guard case .ready = state, let manager else { return nil }
    return dominantEmbedding(in: samples, manager: manager)
  }

  /// Replace remembered voices with ones rebuilt from conversation audio. Favorites and use
  /// scores survive; the embedding becomes the mean of the rebuilt cuts and the longest cuts
  /// become the voice's clips. Returns how many clips were saved.
  func applyRebuild(_ rebuilt: [RebuiltVoice]) -> Int {
    let now = now()
    var clipsSaved = 0
    for voice in rebuilt {
      guard let centroid = Self.meanEmbedding(voice.embeddings) else { continue }
      let update = VoiceprintUpdate(
        personId: voice.personId, embedding: centroid, speechSeconds: voice.speechSeconds, isEnrolled: true)
      // Replace rather than blend: the rebuild heard the whole history, not one session.
      voiceprints.removeAll { $0.personId == voice.personId }
      voiceprints = LocalVoiceprintStore.applying(update, to: voiceprints, now: now)
      if let index = voiceprints.firstIndex(where: { $0.personId == voice.personId }) {
        let previous = voiceprints[index]
        voiceprints[index].useScore = max(
          policy.decayedScore(previous.useScore, lastUsedAt: previous.lastUsedAt, now: now),
          Double(voice.conversationCount))
        voiceprints[index].lastUsedAt = [previous.lastUsedAt, voice.lastHeardAt].compactMap { $0 }.max()
        store.removeAllSamples(personId: voice.personId)
        voiceprints[index].sampleFiles = []
        for (offset, clip) in voice.clips.enumerated() {
          // Distinct names: clips share `now`, and the file name is the timestamp.
          let stamp = now.addingTimeInterval(-Double(offset))
          if let file = store.addSample(personId: voice.personId, samples: clip, now: stamp) {
            voiceprints[index].sampleFiles.append(file)
            clipsSaved += 1
          }
        }
      }
      registry.rememberKnownVoice(
        LocalSpeakerRegistry.KnownVoice(personId: voice.personId, embedding: centroid, isEnrolled: true))
    }
    evictIfOverCapacity()
    persist()
    return clipsSaved
  }

  private static func meanEmbedding(_ embeddings: [[Float]]) -> [Float]? {
    guard let first = embeddings.first else { return nil }
    var sum = [Float](repeating: 0, count: first.count)
    for embedding in embeddings where embedding.count == first.count {
      for i in sum.indices { sum[i] += embedding[i] }
    }
    return LocalSpeakerRegistry.normalized(sum)
  }

  /// Forget a remembered voice and its audio (the user's when `personId` is nil).
  func forgetVoice(personId: String?) {
    registry.forgetVoice(personId: personId)
    voiceprints.removeAll { $0.personId == personId }
    store.removeAllSamples(personId: personId)
    persist()
  }

  /// Pin (or unpin) a person so their voice is never evicted and they list first.
  func setFavorite(personId: String, _ isFavorite: Bool) {
    guard let index = voiceprints.firstIndex(where: { $0.personId == personId }) else { return }
    voiceprints[index].isFavorite = isFavorite
    persist()
  }

  func voiceSummaries() -> [VoiceSummary] {
    voiceprints.map { voiceprint in
      VoiceSummary(
        personId: voiceprint.personId,
        speechSeconds: voiceprint.speechSeconds,
        updatedAt: voiceprint.updatedAt,
        isEnrolled: voiceprint.isEnrolled,
        isFavorite: voiceprint.isFavorite,
        lastHeardAt: voiceprint.lastUsedAt,
        sampleURLs: voiceprint.sampleFiles.map { store.sampleURL(for: $0) }
      )
    }
  }

  // MARK: - Remembering

  private func remember(_ updates: [VoiceprintUpdate]) {
    let now = now()
    for update in updates {
      voiceprints = LocalVoiceprintStore.applying(update, to: voiceprints, now: now)
    }
    evictIfOverCapacity()
    persist()
    let who = updates.map { $0.personId ?? "user" }.joined(separator: ", ")
    log("LocalSpeakerDiarizer: remembered voice for \(who)")
  }

  /// Aged-frequency bookkeeping: one bump per voice per app run. Returns whether anything
  /// changed.
  private func touchUse(personId: String?) -> Bool {
    let key = LocalVoiceprintStore.sampleOwner(personId)
    guard !usedThisRun.contains(key), let index = voiceprints.firstIndex(where: { $0.personId == personId })
    else { return false }
    usedThisRun.insert(key)
    voiceprints[index] = policy.recordingUse(of: voiceprints[index], now: now())
    return true
  }

  private func evictIfOverCapacity() {
    let evicted = policy.evictions(from: voiceprints, now: now())
    guard !evicted.isEmpty else { return }
    for personId in evicted {
      registry.forgetVoice(personId: personId)
      store.removeAllSamples(personId: personId)
      voiceprints.removeAll { $0.personId == personId }
    }
    log("LocalSpeakerDiarizer: forgot \(evicted.count) rarely heard voice(s) to stay within \(policy.capacity)")
  }

  private func persist() {
    store.save(voiceprints)
  }

  private func saveRecentWindows(of clusterKey: Int, as personId: String?) {
    for window in recentWindows[clusterKey] ?? [] {
      _ = saveSampleIfDue(personId: personId, samples: window, force: true)
    }
  }

  /// Keep a clip of this voice unless one was kept recently. Trims to the freshest
  /// `maxSampleSeconds`; drops the oldest clip beyond `maxSamplesPerVoice`.
  @discardableResult
  private func saveSampleIfDue(personId: String?, samples: [Float], force: Bool = false) -> Bool {
    guard let index = voiceprints.firstIndex(where: { $0.personId == personId }) else { return false }
    let key = LocalVoiceprintStore.sampleOwner(personId)
    let now = now()
    if !force, let last = lastSampleAt[key], now.timeIntervalSince(last) < policy.sampleIntervalSeconds {
      return false
    }
    let maxSamples = Int(policy.maxSampleSeconds * Double(LocalVoiceprintStore.sampleRate))
    let clip = samples.count > maxSamples ? Array(samples.suffix(maxSamples)) : samples
    guard let file = store.addSample(personId: personId, samples: clip, now: now) else { return false }
    lastSampleAt[key] = now
    var files = voiceprints[index].sampleFiles
    files.insert(file, at: 0)
    if files.count > policy.maxSamplesPerVoice {
      store.removeSamples(Array(files[policy.maxSamplesPerVoice...]))
      files = Array(files.prefix(policy.maxSamplesPerVoice))
    }
    voiceprints[index].sampleFiles = files
    return true
  }

  private static func knownVoice(_ stored: StoredVoiceprint) -> LocalSpeakerRegistry.KnownVoice {
    LocalSpeakerRegistry.KnownVoice(
      personId: stored.personId, embedding: stored.embedding, isEnrolled: stored.isEnrolled)
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
