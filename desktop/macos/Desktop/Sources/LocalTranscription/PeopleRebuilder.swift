import AVFoundation
import Foundation

/// One stretch of a conversation's audio that belongs to a known voice.
struct PeopleRebuildCut: Equatable, Sendable {
  /// nil is the user.
  let personId: String?
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

  /// The transcript segments of a conversation that name a person (or the user), mapped onto
  /// the aggregate artifact's media time. Segments across a gap in captured audio are skipped
  /// rather than guessed at.
  static func cuts(
    segments: [TranscriptSegment],
    artifact: CapturePlaybackArtifact
  ) -> [PeopleRebuildCut] {
    segments.compactMap { segment in
      guard segment.isUser || segment.personId != nil else { return nil }
      let wallEnd = min(segment.end, segment.start + maxCutSeconds)
      guard wallEnd - segment.start >= minCutSeconds,
        let start = artifact.artifactOffset(forWallOffset: segment.start),
        let end = artifact.artifactOffset(forWallOffset: wallEnd - 0.001)
      else { return nil }
      guard end - start >= minCutSeconds else { return nil }
      return PeopleRebuildCut(
        personId: segment.isUser ? nil : segment.personId, artifactStart: start, artifactEnd: end)
    }
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
  var activity: [String: PersonActivity] = [:]
  var failure: String?

  var message: String {
    if let failure { return failure }
    var parts = ["\(conversations) conversation\(conversations == 1 ? "" : "s") checked"]
    if withAudio > 0 { parts.append("\(withAudio) with audio") }
    parts.append(
      voicesRebuilt == 0 ? "no voices rebuilt" : "\(voicesRebuilt) voice\(voicesRebuilt == 1 ? "" : "s") rebuilt")
    if clipsSaved > 0 { parts.append("\(clipsSaved) clip\(clipsSaved == 1 ? "" : "s") saved") }
    return parts.joined(separator: " · ")
  }
}

/// The People page's Refresh: walks recent conversations on the backend, re-listens to every
/// stretch labeled as a known person or as the user, and rebuilds the remembered voices and
/// clips from that. Conversations without cached audio still count toward who was talked to.
actor PeopleRebuilder {
  static let shared = PeopleRebuilder()

  static let conversationLimit = 100
  static let clipsPerVoice = 3

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

    let conversations: [ServerConversation]
    do {
      conversations = try await APIClient.shared.getConversations(limit: Self.conversationLimit)
    } catch {
      logError("PeopleRebuilder: could not load conversations", error: error)
      summary.failure = "Couldn't load conversations"
      return summary
    }
    state.total = conversations.count
    summary.conversations = conversations.count

    await diarizer.prepare()
    let canEmbed = await diarizer.isAvailable
    var voices: [String: RebuiltVoice] = [:]
    var seen: [(segments: [TranscriptSegment], date: Date)] = []

    for conversation in conversations {
      state.scanned += 1
      state.message = "Checking \(state.scanned) of \(state.total)…"
      progress(state)

      let segments = await transcriptSegments(of: conversation)
      seen.append((segments, conversation.startedAt ?? conversation.createdAt))

      guard canEmbed, !conversation.isLocked,
        !conversation.audioFiles.isEmpty || conversation.conversationAudio != nil,
        segments.contains(where: { $0.isUser || $0.personId != nil })
      else { continue }
      guard case .readyAggregate(let artifact) = await LiveCapturePlaybackProvider().resolvePlayback(for: conversation)
      else { continue }
      let cuts = PeopleRebuildPlanner.cuts(segments: segments, artifact: artifact)
      guard !cuts.isEmpty else { continue }
      state.withAudio += 1
      state.message = "Listening to \(state.scanned) of \(state.total)…"
      progress(state)

      guard let audio = await Self.downloadAndDecode(artifact.signedURL) else { continue }
      let rate = Double(LocalVoiceprintStore.sampleRate)
      var touched: Set<String> = []
      for cut in cuts {
        let from = max(0, Int(cut.artifactStart * rate))
        let to = min(audio.count, Int(cut.artifactEnd * rate))
        guard to - from >= Int(PeopleRebuildPlanner.minCutSeconds * rate) else { continue }
        let samples = Array(audio[from..<to])
        guard let embedding = await diarizer.embedding(for: samples) else { continue }
        let key = LocalVoiceprintStore.sampleOwner(cut.personId)
        var voice = voices[key] ?? RebuiltVoice(personId: cut.personId)
        voice.embeddings.append(embedding)
        voice.speechSeconds += cut.length
        voice.clips.append(samples)
        voice.clips.sort { $0.count > $1.count }
        if voice.clips.count > Self.clipsPerVoice { voice.clips.removeLast(voice.clips.count - Self.clipsPerVoice) }
        if !touched.contains(key) {
          touched.insert(key)
          voice.conversationCount += 1
          let date = conversation.startedAt ?? conversation.createdAt
          voice.lastHeardAt = [voice.lastHeardAt, date].compactMap { $0 }.max()
        }
        voices[key] = voice
        state.cutsEmbedded += 1
      }
    }

    summary.withAudio = state.withAudio
    summary.activity = PeopleRebuildPlanner.activity(in: seen)
    let rebuilt = Array(voices.values).filter { !$0.embeddings.isEmpty }
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

  private func transcriptSegments(of conversation: ServerConversation) async -> [TranscriptSegment] {
    if conversation.transcriptSegmentsIncluded || !conversation.transcriptSegments.isEmpty {
      return conversation.transcriptSegments
    }
    guard let detail = try? await APIClient.shared.getConversation(id: conversation.id) else { return [] }
    return detail.transcriptSegments
  }

  /// Fetch a signed audio URL to a temp file and decode it to 16 kHz mono. The file is deleted
  /// afterwards; the URL is never logged.
  private static func downloadAndDecode(_ url: URL) async -> [Float]? {
    do {
      let (temp, _) = try await URLSession.shared.download(from: url)
      let ext = url.pathExtension.isEmpty ? "wav" : url.pathExtension
      let local = FileManager.default.temporaryDirectory
        .appendingPathComponent("people-rebuild-\(UUID().uuidString)").appendingPathExtension(ext)
      try FileManager.default.moveItem(at: temp, to: local)
      defer { try? FileManager.default.removeItem(at: local) }
      return try AudioClipDecoder.decode16kMono(url: local)
    } catch {
      logError("PeopleRebuilder: audio download/decode failed", error: error)
      return nil
    }
  }
}

/// Reads any AVFoundation-decodable audio file into 16 kHz mono Float32 samples.
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

  static func decode16kMono(url: URL) throws -> [Float] {
    let file = try AVAudioFile(forReading: url)
    let source = file.processingFormat
    guard
      let target = AVAudioFormat(
        commonFormat: .pcmFormatFloat32, sampleRate: Double(LocalVoiceprintStore.sampleRate), channels: 1,
        interleaved: false),
      let converter = AVAudioConverter(from: source, to: target)
    else { throw CocoaError(.fileReadCorruptFile) }

    var output: [Float] = []
    let chunkFrames: AVAudioFrameCount = 65_536
    let ratio = target.sampleRate / source.sampleRate
    while file.framePosition < file.length {
      guard let input = AVAudioPCMBuffer(pcmFormat: source, frameCapacity: chunkFrames) else { break }
      try file.read(into: input, frameCount: chunkFrames)
      if input.frameLength == 0 { break }
      let capacity = AVAudioFrameCount(Double(input.frameLength) * ratio) + 1024
      guard let converted = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: capacity) else { break }
      let feed = SingleBufferFeed(input)
      var conversionError: NSError?
      converter.convert(to: converted, error: &conversionError) { _, status in feed.next(status) }
      if let conversionError { throw conversionError }
      if let channel = converted.floatChannelData {
        output.append(contentsOf: UnsafeBufferPointer(start: channel[0], count: Int(converted.frameLength)))
      }
    }
    return output
  }
}
