import Foundation

/// Which capture lane an on-device transcription window came from.
enum LocalTranscriptionLane: String, Sendable, Equatable {
  case microphone
  case systemAudio
}

/// Session-stable speaker identities for on-device transcription, shared by the microphone
/// and system-audio lanes.
///
/// Before this, the mic lane stamped every window "You" and the system lane "Speaker 1", so a
/// second person in the room was transcribed as the user. The registry clusters per-window
/// speaker embeddings (cosine distance, running-mean centroids), names clusters that match a
/// remembered person, and decides which cluster is the user:
///
///  1. A remembered voice of the user (`KnownVoice` with `personId == nil`) wins: the first
///     mic-lane cluster within `knownVoiceMatchThreshold` of it becomes "You". An *enrolled*
///     print ("This is me", a push-to-talk turn) locks that for the session; a print the
///     bootstrap merely learned stays open to correction.
///  2. With no remembered voice — or when nothing has matched it after `voiceprintGraceSeconds`
///     of mic speech (new microphone, different room) — the dominant mic-lane voice, scored by
///     loudness-weighted speech time, is the provisional user. When a different mic voice
///     overtakes it by `bootstrapSwapMargin`, the two swap public ids and `Outcome.relabels`
///     tells the caller which already-emitted segments to rewrite.
///  3. `markAsUser` / `enrollUser` make the identity explicit; `assignPerson` teaches a named
///     person's voice so later sessions stamp their `personId` on arrival.
///
/// Public speaker ids: the user is always 0 (`VoiceBargeInPolicy` and
/// `EnvironmentalSpeakerContext` rely on that); everyone else counts up from 1 in order of
/// first appearance across both lanes, so a remote voice heard through the speakers and its
/// echo on the mic share one id. Pure value type — no CoreML — so the policy is unit-testable.
struct LocalSpeakerRegistry: Sendable {

  struct Resolution: Equatable, Hashable, Sendable {
    let speakerId: Int
    let isUser: Bool
    let personId: String?

    init(speakerId: Int, isUser: Bool, personId: String? = nil) {
      self.speakerId = speakerId
      self.isUser = isUser
      self.personId = isUser ? nil : personId
    }

    var speakerLabel: String { String(format: "SPEAKER_%02d", speakerId) }
  }

  struct Observation: Sendable {
    let embedding: [Float]
    let durationSeconds: Double
    /// Window RMS, used only to weight speech time when picking the provisional user.
    let loudness: Float
    let lane: LocalTranscriptionLane
  }

  /// A voice remembered from earlier sessions. `personId == nil` is the user.
  struct KnownVoice: Sendable {
    let personId: String?
    let embedding: [Float]
    let isEnrolled: Bool
  }

  struct Outcome: Equatable, Sendable {
    let resolution: Resolution
    /// Previous public speaker id → new resolution, for segments already emitted. Empty
    /// unless a cluster's identity changed.
    let relabels: [Int: Resolution]
    /// Voices the caller should remember now.
    let voiceprintsToPersist: [VoiceprintUpdate]
    /// Cosine distance to the closest cluster that existed before this window (infinity for
    /// the first one). Logged so the thresholds can be calibrated against real audio.
    let nearestDistance: Float
  }

  struct Config: Sendable {
    /// Max cosine distance for a window to join an existing cluster. WeSpeaker ResNet34
    /// distances measured live: same voice 0.06–0.26 (mixed windows ≈ 0.5), different voices
    /// 0.68–0.94. Matches the backend's `SPEAKER_CLUSTERING_THRESHOLD`.
    var matchThreshold: Float = 0.60
    /// Only confident matches move a centroid, so a borderline window can't drag a cluster
    /// toward another voice.
    var updateThreshold: Float = 0.45
    /// Distance to a remembered voice that identifies that person. Tighter than
    /// `matchThreshold`: a false "You" (or a false name) is worse than a late one.
    var knownVoiceMatchThreshold: Float = 0.50
    /// Mic speech tolerated without a match to the remembered user before falling back to
    /// bootstrap.
    var voiceprintGraceSeconds: Double = 30
    /// A rival mic voice must out-score the provisional user by this factor to take over.
    var bootstrapSwapMargin: Double = 1.5
    /// Speech a cluster needs before its voice is (re)remembered.
    var voiceprintPersistSeconds: Double = 20
    /// A voice is re-remembered every time its speech grows by this much.
    var voiceprintRepersistSeconds: Double = 60
    /// Hard cap on tracked voices; beyond it a window joins its nearest cluster.
    var maxClusters: Int = 16
    /// A window shorter than this never opens a new cluster — its embedding is too noisy
    /// (live: a 1.7 s echo fragment became a phantom "Speaker 4"). It joins the nearest voice.
    var minNewClusterSeconds: Double = 2.0
    /// Weight (in seconds) at which a centroid stops moving faster for new windows.
    var centroidWeightCapSeconds: Double = 90

    init() {}
  }

  struct Cluster: Sendable {
    let key: Int
    var speakerId: Int
    var centroid: [Float]
    var centroidWeightSeconds: Double
    var personId: String?
    var speechSeconds: Double = 0
    var micSeconds: Double = 0
    var systemSeconds: Double = 0
    /// Σ duration × RMS over mic-lane windows: louder-and-longer wins the bootstrap.
    var micEnergySeconds: Double = 0
    var secondsAtLastPersist: Double = 0

    /// A voice that is mostly heard through the speakers is a remote party, never the user —
    /// even when its echo also reaches the mic.
    var isMicVoice: Bool { micSeconds > 0 && micSeconds >= systemSeconds }
  }

  let config: Config
  private(set) var clusters: [Cluster] = []
  private(set) var userClusterKey: Int?
  /// Voices remembered from earlier sessions, plus anything enrolled this session.
  private(set) var knownVoices: [KnownVoice]
  /// True once the user cluster is beyond doubt: it matched an enrolled print, or the user
  /// confirmed it this session. Locks out bootstrap swaps for the rest of the session.
  private(set) var userIsConfirmed = false
  private var micSecondsSinceStart: Double = 0
  private var nextClusterKey = 0
  private var nextOtherSpeakerId = 1

  init(knownVoices: [KnownVoice] = [], config: Config = Config()) {
    self.config = config
    self.knownVoices = knownVoices.compactMap { voice in
      guard let normalized = Self.normalized(voice.embedding) else { return nil }
      return KnownVoice(personId: voice.personId, embedding: normalized, isEnrolled: voice.isEnrolled)
    }
  }

  /// Convenience for the common single-voiceprint case.
  init(userVoiceprint: [Float]?, userIsEnrolled: Bool = false, config: Config = Config()) {
    self.init(
      knownVoices: userVoiceprint.map { [KnownVoice(personId: nil, embedding: $0, isEnrolled: userIsEnrolled)] } ?? [],
      config: config)
  }

  var userSpeakerId: Int { 0 }

  var userCluster: Cluster? {
    guard let userClusterKey else { return nil }
    return clusters.first { $0.key == userClusterKey }
  }

  var knownUserVoice: KnownVoice? { knownVoices.first { $0.personId == nil } }

  func cluster(forSpeakerId speakerId: Int) -> Cluster? {
    clusters.first { $0.speakerId == speakerId }
  }

  private func resolution(for cluster: Cluster) -> Resolution {
    Resolution(speakerId: cluster.speakerId, isUser: cluster.key == userClusterKey, personId: cluster.personId)
  }

  // MARK: - Observing windows

  /// Fold one transcribed window into the registry and say who spoke.
  mutating func observe(_ observation: Observation) -> Outcome? {
    guard let embedding = Self.normalized(observation.embedding), observation.durationSeconds > 0 else {
      return nil
    }
    let duration = observation.durationSeconds
    if observation.lane == .microphone { micSecondsSinceStart += duration }

    let (index, created, nearestDistance) = assignCluster(embedding: embedding, duration: duration)
    let idBeforeReconsidering = clusters[index].speakerId
    accumulate(at: index, observation: observation, duration: duration)

    var relabels: [Int: Resolution] = [:]
    if let named = matchKnownPerson(at: index) { relabels.merge(named) { _, new in new } }
    if observation.lane == .microphone {
      relabels.merge(reconsiderUser(afterObserving: index)) { _, new in new }
    }
    if created {
      // No segment carries a brand-new cluster's provisional id yet; only the resolution
      // returned below needs it.
      relabels.removeValue(forKey: idBeforeReconsidering)
    }

    let cluster = clusters[index]
    return Outcome(
      resolution: resolution(for: cluster),
      relabels: relabels,
      voiceprintsToPersist: voiceprintsDue(),
      nearestDistance: nearestDistance
    )
  }

  // MARK: - Explicit identity

  /// "This is me": the cluster behind `speakerId` is the user, beyond doubt.
  /// Returns the relabels for its (and the previous user's) earlier segments and the print
  /// to remember; nil when no such speaker exists.
  mutating func markAsUser(speakerId: Int) -> (relabels: [Int: Resolution], persist: VoiceprintUpdate)? {
    guard let index = clusters.firstIndex(where: { $0.speakerId == speakerId }) else { return nil }
    clusters[index].personId = nil
    var relabels = promoteToUser(index)
    userIsConfirmed = true
    // Always report the cluster itself: when it was already the user, promote changed nothing,
    // but the caller may still hold segments that predate a name it carried.
    relabels[speakerId] = resolution(for: clusters[index])
    let update = VoiceprintUpdate(
      personId: nil, embedding: clusters[index].centroid,
      speechSeconds: clusters[index].speechSeconds, isEnrolled: true)
    rememberUserVoice(clusters[index].centroid, isEnrolled: true)
    clusters[index].secondsAtLastPersist = clusters[index].speechSeconds
    return (relabels, update)
  }

  /// Name (or un-name) the cluster behind `speakerId`. Naming teaches the person's voice.
  mutating func assignPerson(_ personId: String?, toSpeakerId speakerId: Int)
    -> (relabels: [Int: Resolution], persist: VoiceprintUpdate?)?
  {
    guard let index = clusters.firstIndex(where: { $0.speakerId == speakerId }),
      clusters[index].key != userClusterKey
    else { return nil }
    clusters[index].personId = personId
    let relabels = [speakerId: resolution(for: clusters[index])]
    guard let personId else { return (relabels, nil) }
    knownVoices.removeAll { $0.personId == personId }
    knownVoices.append(KnownVoice(personId: personId, embedding: clusters[index].centroid, isEnrolled: true))
    clusters[index].secondsAtLastPersist = clusters[index].speechSeconds
    let update = VoiceprintUpdate(
      personId: personId, embedding: clusters[index].centroid,
      speechSeconds: clusters[index].speechSeconds, isEnrolled: true)
    return (relabels, update)
  }

  /// A sample that is the user's voice beyond doubt (a push-to-talk turn). Remembers it and,
  /// if a mic cluster already matches, makes that cluster the user.
  mutating func enrollUser(embedding: [Float], speechSeconds: Double)
    -> (relabels: [Int: Resolution], persist: VoiceprintUpdate)?
  {
    guard let normalized = Self.normalized(embedding) else { return nil }
    rememberUserVoice(normalized, isEnrolled: true)
    var relabels: [Int: Resolution] = [:]
    if !userIsConfirmed,
      let index = nearestMicCluster(to: normalized, within: config.knownVoiceMatchThreshold)
    {
      relabels = promoteToUser(index)
      userIsConfirmed = true
    }
    return (
      relabels,
      VoiceprintUpdate(personId: nil, embedding: normalized, speechSeconds: speechSeconds, isEnrolled: true)
    )
  }

  /// Forget a remembered voice (the user's when `personId` is nil) for the rest of the session.
  mutating func forgetVoice(personId: String?) {
    knownVoices.removeAll { $0.personId == personId }
    if personId == nil {
      userIsConfirmed = false
    } else {
      for index in clusters.indices where clusters[index].personId == personId {
        clusters[index].personId = nil
      }
    }
  }

  /// Replace (or add) a remembered voice, e.g. after a rebuild from conversation audio.
  mutating func rememberKnownVoice(_ voice: KnownVoice) {
    guard let normalized = Self.normalized(voice.embedding) else { return }
    knownVoices.removeAll { $0.personId == voice.personId }
    knownVoices.append(KnownVoice(personId: voice.personId, embedding: normalized, isEnrolled: voice.isEnrolled))
  }

  private mutating func rememberUserVoice(_ embedding: [Float], isEnrolled: Bool) {
    knownVoices.removeAll { $0.personId == nil }
    knownVoices.append(KnownVoice(personId: nil, embedding: embedding, isEnrolled: isEnrolled))
  }

  // MARK: - Clustering

  private mutating func assignCluster(
    embedding: [Float], duration: Double
  ) -> (index: Int, created: Bool, nearestDistance: Float) {
    var best: (index: Int, distance: Float)?
    for (index, cluster) in clusters.enumerated() {
      let distance = Self.cosineDistance(embedding, cluster.centroid)
      if distance < (best?.distance ?? .infinity) {
        best = (index, distance)
      }
    }

    if let best,
      best.distance <= config.matchThreshold || clusters.count >= config.maxClusters
        || duration < config.minNewClusterSeconds
    {
      if best.distance <= config.updateThreshold {
        moveCentroid(at: best.index, toward: embedding, weight: duration)
      }
      return (best.index, false, best.distance)
    }

    let cluster = Cluster(
      key: nextClusterKey,
      speakerId: nextOtherSpeakerId,
      centroid: embedding,
      centroidWeightSeconds: duration
    )
    nextClusterKey += 1
    nextOtherSpeakerId += 1
    clusters.append(cluster)
    return (clusters.count - 1, true, best?.distance ?? .infinity)
  }

  private mutating func moveCentroid(at index: Int, toward embedding: [Float], weight: Double) {
    let existingWeight = min(clusters[index].centroidWeightSeconds, config.centroidWeightCapSeconds)
    let total = existingWeight + weight
    guard total > 0 else { return }
    let keep = Float(existingWeight / total)
    let add = Float(weight / total)
    var blended = clusters[index].centroid
    for i in blended.indices {
      blended[i] = blended[i] * keep + embedding[i] * add
    }
    if let normalized = Self.normalized(blended) {
      clusters[index].centroid = normalized
    }
    clusters[index].centroidWeightSeconds += weight
  }

  private mutating func accumulate(at index: Int, observation: Observation, duration: Double) {
    clusters[index].speechSeconds += duration
    switch observation.lane {
    case .microphone:
      clusters[index].micSeconds += duration
      clusters[index].micEnergySeconds += duration * Double(max(observation.loudness, 0))
    case .systemAudio:
      clusters[index].systemSeconds += duration
    }
  }

  private func nearestMicCluster(to embedding: [Float], within threshold: Float) -> Int? {
    var best: (index: Int, distance: Float)?
    for (index, cluster) in clusters.enumerated() where cluster.isMicVoice {
      let distance = Self.cosineDistance(embedding, cluster.centroid)
      if distance <= threshold, distance < (best?.distance ?? .infinity) {
        best = (index, distance)
      }
    }
    return best?.index
  }

  // MARK: - Who is this

  /// Stamp a remembered person on an unnamed cluster whose voice matches. Returns the relabel
  /// for that cluster's earlier segments when the match arrived after they were emitted.
  private mutating func matchKnownPerson(at index: Int) -> [Int: Resolution]? {
    guard clusters[index].personId == nil, clusters[index].key != userClusterKey else { return nil }
    let taken = Set(clusters.compactMap(\.personId))
    var best: (personId: String, distance: Float)?
    for voice in knownVoices {
      guard let personId = voice.personId, !taken.contains(personId) else { continue }
      let distance = Self.cosineDistance(clusters[index].centroid, voice.embedding)
      if distance <= config.knownVoiceMatchThreshold, distance < (best?.distance ?? .infinity) {
        best = (personId, distance)
      }
    }
    guard let best else { return nil }
    clusters[index].personId = best.personId
    return [clusters[index].speakerId: resolution(for: clusters[index])]
  }

  private mutating func reconsiderUser(afterObserving index: Int) -> [Int: Resolution] {
    if userIsConfirmed { return [:] }

    // Rule 1: the remembered voice of the user identifies them outright.
    if let known = knownUserVoice, clusters[index].isMicVoice, clusters[index].key != userClusterKey,
      Self.cosineDistance(clusters[index].centroid, known.embedding) <= config.knownVoiceMatchThreshold
    {
      userIsConfirmed = known.isEnrolled
      return promoteToUser(index)
    }

    // Rule 2: no remembered voice, or it has gone stale — the dominant mic voice is the user.
    if knownUserVoice != nil && userClusterKey == nil && micSecondsSinceStart < config.voiceprintGraceSeconds {
      return [:]
    }
    guard let dominant = dominantMicClusterIndex() else { return [:] }
    guard let currentKey = userClusterKey, let currentIndex = clusters.firstIndex(where: { $0.key == currentKey })
    else {
      return promoteToUser(dominant)
    }
    if dominant == currentIndex { return [:] }
    let challenger = clusters[dominant].micEnergySeconds
    let incumbent = clusters[currentIndex].micEnergySeconds
    guard challenger > incumbent * config.bootstrapSwapMargin else { return [:] }
    return promoteToUser(dominant)
  }

  private func dominantMicClusterIndex() -> Int? {
    var best: (index: Int, score: Double)?
    for (index, cluster) in clusters.enumerated() where cluster.isMicVoice && cluster.personId == nil {
      if cluster.micEnergySeconds > (best?.score ?? -1) {
        best = (index, cluster.micEnergySeconds)
      }
    }
    return best?.index
  }

  /// Make `index` the user (public id 0). A previous user cluster takes over the id the new
  /// one vacates, so the change is a pure swap and every earlier segment has a new home.
  private mutating func promoteToUser(_ index: Int) -> [Int: Resolution] {
    guard clusters[index].key != userClusterKey else { return [:] }
    let vacatedId = clusters[index].speakerId
    var relabels: [Int: Resolution] = [:]
    if let currentKey = userClusterKey, let currentIndex = clusters.firstIndex(where: { $0.key == currentKey }) {
      clusters[currentIndex].speakerId = vacatedId
      clusters[currentIndex].secondsAtLastPersist = 0
      relabels[userSpeakerId] = Resolution(
        speakerId: vacatedId, isUser: false, personId: clusters[currentIndex].personId)
    } else if vacatedId == nextOtherSpeakerId - 1 {
      // Nobody inherits the vacated id: give it back so the next other voice is "Speaker 1",
      // not "Speaker 2".
      nextOtherSpeakerId -= 1
    }
    clusters[index].speakerId = userSpeakerId
    clusters[index].personId = nil
    clusters[index].secondsAtLastPersist = 0
    userClusterKey = clusters[index].key
    if vacatedId != userSpeakerId {
      relabels[vacatedId] = Resolution(speakerId: userSpeakerId, isUser: true)
    }
    return relabels
  }

  // MARK: - Remembering voices

  /// Voices that have accumulated enough speech since they were last remembered: the user's
  /// (as a learned print unless already confirmed) and every named person's.
  private mutating func voiceprintsDue() -> [VoiceprintUpdate] {
    var updates: [VoiceprintUpdate] = []
    for index in clusters.indices {
      let cluster = clusters[index]
      let isUser = cluster.key == userClusterKey
      guard isUser || cluster.personId != nil else { continue }
      guard cluster.speechSeconds >= config.voiceprintPersistSeconds else { continue }
      let due =
        cluster.secondsAtLastPersist == 0
        || cluster.speechSeconds - cluster.secondsAtLastPersist >= config.voiceprintRepersistSeconds
      guard due else { continue }
      clusters[index].secondsAtLastPersist = cluster.speechSeconds
      updates.append(
        VoiceprintUpdate(
          personId: isUser ? nil : cluster.personId,
          embedding: cluster.centroid,
          speechSeconds: cluster.speechSeconds,
          isEnrolled: isUser ? userIsConfirmed : true
        ))
      if isUser {
        rememberUserVoice(cluster.centroid, isEnrolled: userIsConfirmed)
      }
    }
    return updates
  }

  // MARK: - Math

  static func cosineDistance(_ a: [Float], _ b: [Float]) -> Float {
    guard a.count == b.count, !a.isEmpty else { return .infinity }
    var dot: Float = 0
    var normA: Float = 0
    var normB: Float = 0
    for i in a.indices {
      dot += a[i] * b[i]
      normA += a[i] * a[i]
      normB += b[i] * b[i]
    }
    guard normA > 0, normB > 0 else { return .infinity }
    return 1 - dot / (normA.squareRoot() * normB.squareRoot())
  }

  /// L2-normalized copy, or nil for an empty / all-zero / non-finite vector.
  static func normalized(_ vector: [Float]) -> [Float]? {
    guard !vector.isEmpty else { return nil }
    var sumSquares: Float = 0
    for value in vector {
      guard value.isFinite else { return nil }
      sumSquares += value * value
    }
    guard sumSquares > 0 else { return nil }
    let scale = 1 / sumSquares.squareRoot()
    return vector.map { $0 * scale }
  }
}
