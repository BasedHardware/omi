import AVFoundation
import Foundation

/// One stretch of a conversation's audio worth listening to again.
struct PeopleRebuildCut: Equatable, Sendable {
  /// The person the transcript names for it, if any.
  let personId: String?
  /// What the backend's diarization said. Treated as a hint: "You" is decided by who is
  /// heard in the most conversations, not by this flag.
  let labeledAsUser: Bool
  let artifactStart: TimeInterval
  let artifactEnd: TimeInterval

  var length: TimeInterval { artifactEnd - artifactStart }
}

/// Pure planning for a People refresh: which parts of which conversations to listen to again.
enum PeopleRebuildPlanner {
  /// Shortest cut worth embedding; the WeSpeaker front end needs about half a second and
  /// anything shorter is mostly a breath.
  static let minCutSeconds: TimeInterval = 1.0
  /// Longest cut kept: enough voice for a stable embedding and a listenable clip.
  static let maxCutSeconds: TimeInterval = 12.0

  /// Cuts embedded per conversation at most, longest first, so a long history stays a bounded job.
  static let maxCutsPerConversation = 40

  /// Every transcript segment long enough to carry a voice, mapped onto the artifact's media
  /// time. Segments across a gap in captured audio are skipped rather than guessed at.
  static func cuts(
    segments: [TranscriptSegment],
    artifact: CapturePlaybackArtifact
  ) -> [PeopleRebuildCut] {
    let all: [PeopleRebuildCut] = segments.compactMap { segment in
      let wallEnd = min(segment.end, segment.start + maxCutSeconds)
      guard wallEnd - segment.start >= minCutSeconds,
        let start = artifact.artifactOffset(forWallOffset: segment.start),
        let end = artifact.artifactOffset(forWallOffset: wallEnd - 0.001)
      else { return nil }
      guard end - start >= minCutSeconds else { return nil }
      return PeopleRebuildCut(
        personId: segment.isUser ? nil : segment.personId, labeledAsUser: segment.isUser,
        artifactStart: start, artifactEnd: end)
    }
    return Array(all.sorted { $0.length > $1.length }.prefix(maxCutsPerConversation))
  }

  /// How often, and how recently, each named person appears across conversations.
  static func activity(in conversations: [(segments: [TranscriptSegment], date: Date)]) -> [String: PersonActivity] {
    var result: [String: PersonActivity] = [:]
    for conversation in conversations {
      let people = Set(conversation.segments.compactMap { $0.isUser ? nil : $0.personId })
      for personId in people {
        let existing = result[personId]
        result[personId] = PersonActivity(
          conversationCount: (existing?.conversationCount ?? 0) + 1,
          lastTalkedAt: [existing?.lastTalkedAt, conversation.date].compactMap { $0 }.max())
      }
    }
    return result
  }

  /// A single cached part placed on the conversation's wall clock: it begins at its first chunk,
  /// which lands 30–60 s after `startedAt` on real captures, so treating media time as
  /// transcript time would cut the wrong moments.
  static func singlePartArtifact(
    file: CapturePlaybackFile,
    firstChunkTimestamp: TimeInterval?,
    conversationStartedAt: Date?
  ) -> CapturePlaybackArtifact? {
    guard let firstChunkTimestamp, let conversationStartedAt else { return nil }
    let wallOffset = firstChunkTimestamp - conversationStartedAt.timeIntervalSince1970
    guard wallOffset >= -1, file.duration > 0 else { return nil }
    return CapturePlaybackArtifact(
      signedURL: file.signedURL,
      duration: file.duration,
      spans: [
        CaptureAudioURLSpan(fileID: file.id, wallOffset: max(0, wallOffset), artifactOffset: 0, length: file.duration)
      ])
  }

  static func merge(_ local: [String: PersonActivity], _ remote: [String: PersonActivity]) -> [String: PersonActivity] {
    var merged = local
    for (personId, activity) in remote {
      let existing = merged[personId]
      merged[personId] = PersonActivity(
        conversationCount: max(existing?.conversationCount ?? 0, activity.conversationCount),
        lastTalkedAt: [existing?.lastTalkedAt, activity.lastTalkedAt].compactMap { $0 }.max())
    }
    return merged
  }
}

/// Greedy cosine clustering of every cut heard across conversations, so the user can be found
/// as the voice present in the most conversations. Pure, so the choice is testable.
struct VoiceClusterer {
  struct Cluster {
    /// Duration-weighted running mean of every embedding folded in — the voiceprint itself, so
    /// the individual embeddings never have to be kept.
    var centroid: [Float]
    var weight: Double = 0
    var speechSeconds: Double = 0
    var conversationIds: Set<String> = []
    var lastHeardAt: Date?
    /// Longest clips first, at most `clipsToKeep`, stored as 16-bit so a long history with
    /// dozens of voices stays tens of megabytes rather than hundreds.
    var compactClips: [[Int16]] = []
    var labeledAsUserSeconds: Double = 0

    var clips: [[Float]] { compactClips.map { $0.map { Float($0) / 32768 } } }
  }

  var matchThreshold: Float = 0.60
  var clipsToKeep = 3
  /// Only the most-present voices keep audio: a long history can hold dozens of one-off voices,
  /// and three 12 s clips each would be hundreds of megabytes of samples for voices that can
  /// never be chosen as the user.
  var clipHoldingClusters = 5
  private(set) var clusters: [Cluster] = []

  init(matchThreshold: Float = 0.60) {
    self.matchThreshold = matchThreshold
  }

  mutating func add(
    embedding: [Float], seconds: Double, conversationId: String, date: Date?, clip: [Float]?, labeledAsUser: Bool
  ) {
    guard let normalized = LocalSpeakerRegistry.normalized(embedding) else { return }
    var best: (index: Int, distance: Float)?
    for (index, cluster) in clusters.enumerated() {
      let distance = LocalSpeakerRegistry.cosineDistance(normalized, cluster.centroid)
      if distance < (best?.distance ?? .infinity) { best = (index, distance) }
    }
    let index: Int
    if let best, best.distance <= matchThreshold {
      index = best.index
      let total = clusters[index].weight + seconds
      var blended = clusters[index].centroid
      let keep = Float(clusters[index].weight / total)
      let add = Float(seconds / total)
      for i in blended.indices { blended[i] = blended[i] * keep + normalized[i] * add }
      clusters[index].centroid = LocalSpeakerRegistry.normalized(blended) ?? clusters[index].centroid
      clusters[index].weight = total
    } else {
      clusters.append(Cluster(centroid: normalized, weight: seconds))
      index = clusters.count - 1
    }
    clusters[index].speechSeconds += seconds
    clusters[index].conversationIds.insert(conversationId)
    clusters[index].lastHeardAt = [clusters[index].lastHeardAt, date].compactMap { $0 }.max()
    if labeledAsUser { clusters[index].labeledAsUserSeconds += seconds }
    if let clip {
      clusters[index].compactClips.append(clip.map { Int16(max(-1, min(1, $0)) * 32767) })
      clusters[index].compactClips.sort { $0.count > $1.count }
      if clusters[index].compactClips.count > clipsToKeep {
        clusters[index].compactClips.removeLast(clusters[index].compactClips.count - clipsToKeep)
      }
    }
    pruneClipsBeyondTopClusters()
  }

  /// Drop audio from every voice outside the leading `clipHoldingClusters`, so memory stays
  /// flat however many voices a history contains.
  private mutating func pruneClipsBeyondTopClusters() {
    let holders = clusters.indices.filter { !clusters[$0].compactClips.isEmpty }
    guard holders.count > clipHoldingClusters else { return }
    let ranked = holders.sorted { lhs, rhs in
      if clusters[lhs].conversationIds.count != clusters[rhs].conversationIds.count {
        return clusters[lhs].conversationIds.count > clusters[rhs].conversationIds.count
      }
      return clusters[lhs].speechSeconds > clusters[rhs].speechSeconds
    }
    for index in ranked.dropFirst(clipHoldingClusters) {
      clusters[index].compactClips.removeAll()
    }
  }

  /// The user: heard in the most conversations; on a tie, the most speech.
  var userCluster: Cluster? {
    clusters.max { lhs, rhs in
      if lhs.conversationIds.count != rhs.conversationIds.count {
        return lhs.conversationIds.count < rhs.conversationIds.count
      }
      return lhs.speechSeconds < rhs.speechSeconds
    }
  }
}

/// A voice rebuilt from conversation audio, ready for the diarizer to remember.
struct RebuiltVoice: Sendable {
  let personId: String?
  var embeddings: [[Float]] = []
  var speechSeconds: Double = 0
  /// Longest cuts first, at most a handful.
  var clips: [[Float]] = []
  var conversationCount = 0
  var lastHeardAt: Date?
}

struct PeopleRebuildProgress: Equatable, Sendable {
  var scanned = 0
  var total = 0
  var withAudio = 0
  var cutsEmbedded = 0
  var message = ""
}

struct PeopleRebuildSummary: Equatable, Sendable {
  var conversations = 0
  var withAudio = 0
  var voicesRebuilt = 0
  var clipsSaved = 0
  /// Conversations whose audio the backend is still preparing; a later Refresh picks them up.
  var audioPending = 0
  var audioLocked = 0
  /// Conversations the voice chosen as "You" was heard in.
  var userConversations: Int?
  var activity: [String: PersonActivity] = [:]
  var failure: String?

  var message: String {
    if let failure { return failure }
    var parts = ["\(conversations) conversation\(conversations == 1 ? "" : "s") checked"]
    if withAudio > 0 { parts.append("\(withAudio) with audio") }
    parts.append(
      voicesRebuilt == 0 ? "no voices rebuilt" : "\(voicesRebuilt) voice\(voicesRebuilt == 1 ? "" : "s") rebuilt")
    if clipsSaved > 0 { parts.append("\(clipsSaved) clip\(clipsSaved == 1 ? "" : "s") saved") }
    if let userConversations, userConversations > 0 {
      parts.append("you = the voice in \(userConversations) of them")
    }
    if audioPending > 0 { parts.append("\(audioPending) still preparing audio") }
    if audioLocked > 0 { parts.append("\(audioLocked) locked") }
    return parts.joined(separator: " · ")
  }
}

/// The People page's Refresh: walks recent conversations on the backend, re-listens to every
/// stretch labeled as a known person or as the user, and rebuilds the remembered voices and
/// clips from that. Conversations without cached audio still count toward who was talked to.
actor PeopleRebuilder {
  static let shared = PeopleRebuilder()

  /// Page size for the backend list; pages are walked until one comes back short.
  static let pageSize = 100
  /// Upper bound so a very long history stays a bounded job.
  static let maxConversations = 2000
  static let clipsPerVoice = 3
  /// Embeddings averaged per named person. More than this adds nothing to the mean and only
  /// costs memory on a long history.
  static let embeddingsPerPerson = 100

  private var isRunning = false

  func run(
    diarizer: LocalSpeakerDiarizer = .shared,
    progress: @escaping @Sendable (PeopleRebuildProgress) -> Void
  ) async -> PeopleRebuildSummary {
    guard !isRunning else { return PeopleRebuildSummary(failure: "A refresh is already running") }
    isRunning = true
    defer { isRunning = false }

    var summary = PeopleRebuildSummary()
    var state = PeopleRebuildProgress(message: "Loading conversations…")
    progress(state)

    var conversations: [ServerConversation] = []
    do {
      var offset = 0
      while conversations.count < Self.maxConversations {
        let page = try await APIClient.shared.getConversations(limit: Self.pageSize, offset: offset)
        conversations.append(contentsOf: page)
        offset += page.count
        state.total = conversations.count
        state.message = "Loading conversations… \(conversations.count)"
        progress(state)
        if page.count < Self.pageSize { break }
      }
    } catch {
      logError("PeopleRebuilder: could not load conversations", error: error)
      guard !conversations.isEmpty else {
        summary.failure = "Couldn't load conversations"
        return summary
      }
    }
    state.total = conversations.count
    summary.conversations = conversations.count

    await diarizer.prepare()
    let canEmbed = await diarizer.isAvailable
    var people: [String: RebuiltVoice] = [:]
    var clusterer = VoiceClusterer()
    var seen: [(segments: [TranscriptSegment], date: Date)] = []

    for listed in conversations {
      state.scanned += 1
      state.message = "Checking \(state.scanned) of \(state.total)…"
      progress(state)

      // The list omits audio metadata (and sometimes the transcript); the detail has both.
      let conversation = await detail(of: listed)
      let segments = conversation.transcriptSegments
      seen.append((segments, conversation.startedAt ?? conversation.createdAt))

      guard canEmbed, !segments.isEmpty else { continue }
      guard !conversation.isLocked else {
        summary.audioLocked += 1
        continue
      }
      guard !conversation.audioFiles.isEmpty || conversation.conversationAudio != nil else { continue }

      let artifact: CapturePlaybackArtifact
      switch await LiveCapturePlaybackProvider().resolvePlayback(for: conversation) {
      case .readyAggregate(let ready):
        artifact = ready
      case .fileFallback(let file):
        guard
          let placed = PeopleRebuildPlanner.singlePartArtifact(
            file: file,
            firstChunkTimestamp: conversation.audioFiles.first(where: { $0.id == file.id })?.firstChunkTimestamp,
            conversationStartedAt: conversation.startedAt)
        else { continue }
        artifact = placed
      case .pending:
        summary.audioPending += 1
        continue
      case .locked:
        summary.audioLocked += 1
        continue
      case .unavailable, .noAudio:
        continue
      }
      let cuts = PeopleRebuildPlanner.cuts(segments: segments, artifact: artifact)
      guard !cuts.isEmpty else { continue }
      state.withAudio += 1
      state.message = "Listening to \(state.scanned) of \(state.total)…"
      progress(state)

      guard let localAudio = await Self.download(artifact.signedURL) else { continue }
      defer { try? FileManager.default.removeItem(at: localAudio) }
      guard let reader = try? AudioClipDecoder.Reader(url: localAudio) else { continue }
      let rate = Double(LocalVoiceprintStore.sampleRate)
      let date = conversation.startedAt ?? conversation.createdAt
      var touched: Set<String> = []
      for cut in cuts {
        // Only the cut is decoded, never the whole file: a two-hour capture would otherwise be
        // hundreds of megabytes of floats.
        guard let samples = try? reader.read(fromSeconds: cut.artifactStart, toSeconds: cut.artifactEnd),
          samples.count >= Int(PeopleRebuildPlanner.minCutSeconds * rate)
        else { continue }
        guard let embedding = await diarizer.embedding(for: samples) else { continue }
        state.cutsEmbedded += 1
        // Every voice goes into the clustering; the biggest cluster across conversations is you.
        clusterer.add(
          embedding: embedding, seconds: cut.length, conversationId: conversation.id, date: date,
          clip: samples, labeledAsUser: cut.labeledAsUser)
        // Named people are rebuilt from exactly the segments that name them.
        guard let personId = cut.personId else { continue }
        var voice = people[personId] ?? RebuiltVoice(personId: personId)
        if voice.embeddings.count < Self.embeddingsPerPerson { voice.embeddings.append(embedding) }
        voice.speechSeconds += cut.length
        voice.clips.append(samples)
        voice.clips.sort { $0.count > $1.count }
        if voice.clips.count > Self.clipsPerVoice { voice.clips.removeLast(voice.clips.count - Self.clipsPerVoice) }
        if !touched.contains(personId) {
          touched.insert(personId)
          voice.conversationCount += 1
          voice.lastHeardAt = [voice.lastHeardAt, date].compactMap { $0 }.max()
        }
        people[personId] = voice
      }
    }

    summary.withAudio = state.withAudio
    summary.activity = PeopleRebuildPlanner.activity(in: seen)
    var rebuilt = Array(people.values).filter { !$0.embeddings.isEmpty }
    if let user = clusterer.userCluster {
      rebuilt.append(
        RebuiltVoice(
          personId: nil, embeddings: [user.centroid], speechSeconds: user.speechSeconds, clips: user.clips,
          conversationCount: user.conversationIds.count, lastHeardAt: user.lastHeardAt))
      summary.userConversations = user.conversationIds.count
      log(
        "PeopleRebuilder: you = cluster heard in \(user.conversationIds.count) conversations, \(Int(user.speechSeconds)) s (\(Int(user.labeledAsUserSeconds)) s labeled is_user); \(clusterer.clusters.count) voices in total"
      )
    }
    if !rebuilt.isEmpty {
      let saved = await diarizer.applyRebuild(rebuilt)
      summary.voicesRebuilt = rebuilt.count
      summary.clipsSaved = saved
    }
    state.message = summary.message
    progress(state)
    log("PeopleRebuilder: \(summary.message)")
    return summary
  }

  private func detail(of listed: ServerConversation) async -> ServerConversation {
    guard let detail = try? await APIClient.shared.getConversation(id: listed.id) else { return listed }
    return detail
  }

  /// Fetch a signed audio URL to a temp file the caller deletes. The URL is never logged.
  private static func download(_ url: URL) async -> URL? {
    do {
      let (temp, _) = try await URLSession.shared.download(from: url)
      let ext = url.pathExtension.isEmpty ? "wav" : url.pathExtension
      let local = FileManager.default.temporaryDirectory
        .appendingPathComponent("people-rebuild-\(UUID().uuidString)").appendingPathExtension(ext)
      try FileManager.default.moveItem(at: temp, to: local)
      return local
    } catch {
      logError("PeopleRebuilder: audio download failed", error: error)
      return nil
    }
  }
}

/// Reads ranges of any AVFoundation-decodable audio file as 16 kHz mono Float32 samples.
enum AudioClipDecoder {
  /// Hands one input buffer to the converter per call, then reports end of stream.
  private final class SingleBufferFeed: @unchecked Sendable {
    private var pending: AVAudioPCMBuffer?
    init(_ buffer: AVAudioPCMBuffer) { pending = buffer }
    func next(_ status: UnsafeMutablePointer<AVAudioConverterInputStatus>) -> AVAudioBuffer? {
      guard let buffer = pending else {
        status.pointee = .noDataNow
        return nil
      }
      pending = nil
      status.pointee = .haveData
      return buffer
    }
  }

  /// An open file that decodes one time range at a time, so a long capture never has to be
  /// held in memory whole.
  final class Reader {
    private let file: AVAudioFile
    private let target: AVAudioFormat
    private let converter: AVAudioConverter

    init(url: URL) throws {
      file = try AVAudioFile(forReading: url)
      guard
        let target = AVAudioFormat(
          commonFormat: .pcmFormatFloat32, sampleRate: Double(LocalVoiceprintStore.sampleRate), channels: 1,
          interleaved: false),
        let converter = AVAudioConverter(from: file.processingFormat, to: target)
      else { throw CocoaError(.fileReadCorruptFile) }
      self.target = target
      self.converter = converter
    }

    var durationSeconds: Double { Double(file.length) / file.processingFormat.sampleRate }

    func read(fromSeconds start: Double, toSeconds end: Double) throws -> [Float] {
      let sourceRate = file.processingFormat.sampleRate
      let firstFrame = max(0, AVAudioFramePosition(start * sourceRate))
      let lastFrame = min(file.length, AVAudioFramePosition(end * sourceRate))
      guard lastFrame > firstFrame else { return [] }
      file.framePosition = firstFrame
      let frames = AVAudioFrameCount(lastFrame - firstFrame)
      guard let input = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: frames) else { return [] }
      try file.read(into: input, frameCount: frames)
      guard input.frameLength > 0 else { return [] }
      let ratio = target.sampleRate / sourceRate
      let capacity = AVAudioFrameCount(Double(input.frameLength) * ratio) + 1024
      guard let converted = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: capacity) else { return [] }
      converter.reset()
      let feed = SingleBufferFeed(input)
      var conversionError: NSError?
      converter.convert(to: converted, error: &conversionError) { _, status in feed.next(status) }
      if let conversionError { throw conversionError }
      guard let channel = converted.floatChannelData else { return [] }
      return Array(UnsafeBufferPointer(start: channel[0], count: Int(converted.frameLength)))
    }
  }

  /// The whole file, for callers that know it is short.
  static func decode16kMono(url: URL) throws -> [Float] {
    let reader = try Reader(url: url)
    return try reader.read(fromSeconds: 0, toSeconds: reader.durationSeconds + 1)
  }
}
