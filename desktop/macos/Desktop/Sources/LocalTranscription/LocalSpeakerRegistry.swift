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
/// speaker embeddings (cosine distance, running-mean centroids) and decides which cluster is
/// the user:
///
///  1. A persisted voiceprint (`userVoiceprint`) wins: the first mic-lane cluster within
///     `userMatchThreshold` of it becomes "You" and stays "You".
///  2. With no voiceprint — or when nothing has matched it after `voiceprintGraceSeconds` of
///     mic speech (new microphone, different room) — the dominant mic-lane voice, scored by
///     loudness-weighted speech time, is the provisional user. The Mac's owner sits closest
///     to its microphone and is present in every session, so this converges quickly. When a
///     different mic voice overtakes the provisional user by `bootstrapSwapMargin`, the two
///     swap public ids and `Outcome.relabels` tells the caller which already-emitted
///     segments to rewrite.
///  3. Once the user cluster has `voiceprintPersistSeconds` of speech the registry hands
///     back a voiceprint to persist, so later sessions start with rule 1.
///
/// Public speaker ids: the user is always 0 (`VoiceBargeInPolicy` and
/// `EnvironmentalSpeakerContext` rely on that); everyone else counts up from 1 in order of
/// first appearance across both lanes, so a remote voice heard through the speakers and its
/// echo on the mic share one id. Pure value type — no CoreML — so the policy is unit-testable.
struct LocalSpeakerRegistry: Sendable {

  struct Resolution: Equatable, Hashable, Sendable {
    let speakerId: Int
    let isUser: Bool

    var speakerLabel: String { String(format: "SPEAKER_%02d", speakerId) }
  }

  struct Observation: Sendable {
    let embedding: [Float]
    let durationSeconds: Double
    /// Window RMS, used only to weight speech time when picking the provisional user.
    let loudness: Float
    let lane: LocalTranscriptionLane
  }

  struct Outcome: Equatable, Sendable {
    let resolution: Resolution
    /// Previous public speaker id → new resolution, for segments already emitted. Empty
    /// unless the user cluster changed.
    let relabels: [Int: Resolution]
    /// Non-nil when the caller should persist this as the user's voiceprint.
    let voiceprintToPersist: [Float]?
    /// Cosine distance to the closest cluster that existed before this window (infinity for
    /// the first one). Logged so the thresholds can be calibrated against real audio.
    let nearestDistance: Float
  }

  struct Config: Sendable {
    /// Max cosine distance for a window to join an existing cluster. WeSpeaker ResNet34
    /// distances: same voice ≈ 0.2–0.45, different voices ≈ 0.7+. Matches the backend's
    /// `SPEAKER_CLUSTERING_THRESHOLD`.
    var matchThreshold: Float = 0.60
    /// Only confident matches move a centroid, so a borderline window can't drag a cluster
    /// toward another voice.
    var updateThreshold: Float = 0.45
    /// Distance to the persisted voiceprint that identifies the user. Tighter than
    /// `matchThreshold`: a false "You" is worse than a late one.
    var userMatchThreshold: Float = 0.50
    /// Mic speech tolerated without a voiceprint match before falling back to bootstrap.
    var voiceprintGraceSeconds: Double = 30
    /// A rival mic voice must out-score the provisional user by this factor to take over.
    var bootstrapSwapMargin: Double = 1.5
    /// User speech needed before the voiceprint is (re)persisted.
    var voiceprintPersistSeconds: Double = 20
    /// Voiceprint is re-persisted every time user speech grows by this much.
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
    var speechSeconds: Double = 0
    var micSeconds: Double = 0
    var systemSeconds: Double = 0
    /// Σ duration × RMS over mic-lane windows: louder-and-longer wins the bootstrap.
    var micEnergySeconds: Double = 0

    /// A voice that is mostly heard through the speakers is a remote party, never the user —
    /// even when its echo also reaches the mic.
    var isMicVoice: Bool { micSeconds > 0 && micSeconds >= systemSeconds }
  }

  let config: Config
  private(set) var clusters: [Cluster] = []
  private(set) var userClusterKey: Int?
  /// Voiceprint carried over from earlier sessions — the only one that identifies the user
  /// outright (rule 1). One learned this session is provisional until it survives a restart.
  private let storedVoiceprint: [Float]?
  /// Latest voiceprint handed back for persistence (starts as `storedVoiceprint`).
  private(set) var userVoiceprint: [Float]?
  /// True once the user cluster was chosen by matching the persisted voiceprint (rule 1).
  /// Locks out bootstrap swaps for the rest of the session.
  private(set) var userIsConfirmed = false
  private var micSecondsSinceStart: Double = 0
  private var nextClusterKey = 0
  private var nextOtherSpeakerId = 1
  private var userSecondsAtLastPersist: Double = 0

  init(userVoiceprint: [Float]? = nil, config: Config = Config()) {
    self.config = config
    let normalized = userVoiceprint.flatMap(Self.normalized)
    self.storedVoiceprint = normalized
    self.userVoiceprint = normalized
  }

  var userSpeakerId: Int { 0 }

  var userCluster: Cluster? {
    guard let userClusterKey else { return nil }
    return clusters.first { $0.key == userClusterKey }
  }

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
    if observation.lane == .microphone {
      relabels = reconsiderUser(afterObserving: index)
      if created {
        // No segment carries a brand-new cluster's provisional id yet; only the resolution
        // returned below needs it.
        relabels.removeValue(forKey: idBeforeReconsidering)
      }
    }

    let voiceprint = voiceprintToPersistIfDue()
    let cluster = clusters[index]
    return Outcome(
      resolution: Resolution(speakerId: cluster.speakerId, isUser: cluster.key == userClusterKey),
      relabels: relabels,
      voiceprintToPersist: voiceprint,
      nearestDistance: nearestDistance
    )
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

  // MARK: - Who is the user

  private mutating func reconsiderUser(afterObserving index: Int) -> [Int: Resolution] {
    if userIsConfirmed { return [:] }

    // Rule 1: the persisted voiceprint identifies the user outright.
    if let storedVoiceprint, clusters[index].isMicVoice,
      Self.cosineDistance(clusters[index].centroid, storedVoiceprint) <= config.userMatchThreshold
    {
      userIsConfirmed = true
      return promoteToUser(index)
    }

    // Rule 2: no voiceprint, or it has gone stale — the dominant mic voice is the user.
    if storedVoiceprint != nil && micSecondsSinceStart < config.voiceprintGraceSeconds {
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
    for (index, cluster) in clusters.enumerated() where cluster.isMicVoice {
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
      relabels[userSpeakerId] = Resolution(speakerId: vacatedId, isUser: false)
    }
    if userClusterKey == nil, vacatedId == nextOtherSpeakerId - 1 {
      // Nobody inherits the vacated id: give it back so the next other voice is "Speaker 1",
      // not "Speaker 2".
      nextOtherSpeakerId -= 1
    }
    clusters[index].speakerId = userSpeakerId
    userClusterKey = clusters[index].key
    userSecondsAtLastPersist = 0
    if vacatedId != userSpeakerId {
      relabels[vacatedId] = Resolution(speakerId: userSpeakerId, isUser: true)
    }
    return relabels
  }

  // MARK: - Voiceprint persistence

  private mutating func voiceprintToPersistIfDue() -> [Float]? {
    guard let user = userCluster, user.speechSeconds >= config.voiceprintPersistSeconds else { return nil }
    let due =
      userSecondsAtLastPersist == 0
      || user.speechSeconds - userSecondsAtLastPersist >= config.voiceprintRepersistSeconds
    guard due else { return nil }
    userSecondsAtLastPersist = user.speechSeconds

    // Blend with the stored voiceprint so one odd session (a cold, a bad mic) cannot replace
    // the user's identity outright — but let it drift toward what this session heard. A
    // bootstrap pick (unconfirmed) overwrites instead: the stored print was stale or absent.
    var next = user.centroid
    if let previous = userVoiceprint, userIsConfirmed {
      for i in next.indices {
        next[i] = previous[i] * 0.5 + user.centroid[i] * 0.5
      }
    }
    guard let normalized = Self.normalized(next) else { return nil }
    userVoiceprint = normalized
    return normalized
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
