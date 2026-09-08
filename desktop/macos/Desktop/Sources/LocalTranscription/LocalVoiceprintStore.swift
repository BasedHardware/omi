import AVFoundation
import Foundation
import OmiSupport

/// One remembered voice: the user's own (`personId == nil`) or a named person's.
struct StoredVoiceprint: Codable, Equatable, Sendable {
  var personId: String?
  /// L2-normalized WeSpeaker embedding (256 floats).
  var embedding: [Float]
  /// How much speech the print has been averaged over, across sessions.
  var speechSeconds: Double
  var updatedAt: Date
  /// True when a person confirmed the identity — "This is me", naming a speaker, or a
  /// push-to-talk turn — as opposed to a print the bootstrap merely guessed.
  var isEnrolled: Bool
  /// Pinned: never evicted, listed first.
  var isFavorite: Bool = false
  /// Aged use count (`VoiceEnrollmentPolicy`): one per session heard, halving over time.
  var useScore: Double = 0
  var lastUsedAt: Date?
  /// WAV clips of this voice, newest first, relative to the store's sample directory.
  var sampleFiles: [String] = []

  init(
    personId: String?, embedding: [Float], speechSeconds: Double, updatedAt: Date, isEnrolled: Bool,
    isFavorite: Bool = false, useScore: Double = 0, lastUsedAt: Date? = nil, sampleFiles: [String] = []
  ) {
    self.personId = personId
    self.embedding = embedding
    self.speechSeconds = speechSeconds
    self.updatedAt = updatedAt
    self.isEnrolled = isEnrolled
    self.isFavorite = isFavorite
    self.useScore = useScore
    self.lastUsedAt = lastUsedAt
    self.sampleFiles = sampleFiles
  }

  private enum CodingKeys: String, CodingKey {
    case personId, embedding, speechSeconds, updatedAt, isEnrolled, isFavorite, useScore, lastUsedAt, sampleFiles
  }

  /// Files written before favorites/usage/samples existed decode with their defaults.
  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    personId = try c.decodeIfPresent(String.self, forKey: .personId)
    embedding = try c.decode([Float].self, forKey: .embedding)
    speechSeconds = try c.decode(Double.self, forKey: .speechSeconds)
    updatedAt = try c.decode(Date.self, forKey: .updatedAt)
    isEnrolled = try c.decode(Bool.self, forKey: .isEnrolled)
    isFavorite = try c.decodeIfPresent(Bool.self, forKey: .isFavorite) ?? false
    useScore = try c.decodeIfPresent(Double.self, forKey: .useScore) ?? 0
    lastUsedAt = try c.decodeIfPresent(Date.self, forKey: .lastUsedAt)
    sampleFiles = try c.decodeIfPresent([String].self, forKey: .sampleFiles) ?? []
  }
}

/// What the diarizer asks to remember after a window, a naming, or an enrollment.
struct VoiceprintUpdate: Equatable, Sendable {
  let personId: String?
  let embedding: [Float]
  let speechSeconds: Double
  let isEnrolled: Bool
}

/// Per-user JSON file of remembered voices plus a directory of short WAV samples, next to the
/// user's other local data. The JSON is small (a few KB per person) and rewritten whole on
/// every change; reads fail soft to "no voices known".
final class LocalVoiceprintStore: @unchecked Sendable {
  static let fileName = "voiceprints.json"
  static let samplesDirectoryName = "voice-samples"
  static let sampleRate = 16_000

  let fileURL: URL
  private let lock = NSLock()

  init(fileURL: URL) {
    self.fileURL = fileURL
  }

  /// The store for the signed-in user's profile root.
  static func forCurrentUser(userId: String? = RewindDatabase.currentUserId) -> LocalVoiceprintStore {
    let root = DesktopLocalProfile.applicationSupportURL()
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(userId ?? "anonymous", isDirectory: true)
    return LocalVoiceprintStore(fileURL: root.appendingPathComponent(fileName))
  }

  var samplesDirectory: URL {
    fileURL.deletingLastPathComponent().appendingPathComponent(Self.samplesDirectoryName, isDirectory: true)
  }

  func load() -> [StoredVoiceprint] {
    lock.withLock {
      guard let data = try? Data(contentsOf: fileURL) else { return [] }
      let decoder = JSONDecoder()
      decoder.dateDecodingStrategy = .iso8601
      return (try? decoder.decode([StoredVoiceprint].self, from: data)) ?? []
    }
  }

  func save(_ voiceprints: [StoredVoiceprint]) {
    lock.withLock {
      do {
        try FileManager.default.createDirectory(
          at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        try encoder.encode(voiceprints).write(to: fileURL, options: .atomic)
      } catch {
        logError("LocalVoiceprintStore: save failed", error: error)
      }
    }
  }

  // MARK: - Audio samples

  static func sampleOwner(_ personId: String?) -> String { personId ?? "user" }

  func sampleURL(for file: String) -> URL {
    samplesDirectory.appendingPathComponent(file)
  }

  /// Write `samples` (16 kHz mono, -1…1) as a WAV clip for this voice. Returns the file name
  /// relative to the sample directory, or nil when nothing could be written.
  func addSample(personId: String?, samples: [Float], now: Date = Date()) -> String? {
    guard !samples.isEmpty else { return nil }
    let owner = Self.sampleOwner(personId)
    let file = "\(owner)/\(Int(now.timeIntervalSince1970 * 1000)).wav"
    let url = sampleURL(for: file)
    return lock.withLock {
      do {
        try FileManager.default.createDirectory(
          at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Self.writeWAV(samples, to: url)
        return file
      } catch {
        logError("LocalVoiceprintStore: sample write failed", error: error)
        return nil
      }
    }
  }

  func removeSamples(_ files: [String]) {
    lock.withLock {
      for file in files {
        try? FileManager.default.removeItem(at: sampleURL(for: file))
      }
    }
  }

  func removeAllSamples(personId: String?) {
    lock.withLock {
      try? FileManager.default.removeItem(
        at: samplesDirectory.appendingPathComponent(Self.sampleOwner(personId), isDirectory: true))
    }
  }

  private static func writeWAV(_ samples: [Float], to url: URL) throws {
    guard
      let format = AVAudioFormat(
        commonFormat: .pcmFormatFloat32, sampleRate: Double(sampleRate), channels: 1, interleaved: false),
      let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(samples.count)),
      let channel = buffer.floatChannelData
    else { throw CocoaError(.fileWriteUnknown) }
    buffer.frameLength = AVAudioFrameCount(samples.count)
    samples.withUnsafeBufferPointer { source in
      guard let base = source.baseAddress else { return }
      channel[0].update(from: base, count: samples.count)
    }
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
  }

  // MARK: - Merging

  /// Fold `update` into `voiceprints` and return the new list. A guessed (learned) update blends
  /// 50/50 with an existing print so one odd session cannot replace an identity outright; an
  /// enrolled update replaces a guessed print, and blends with an enrolled one. Favorites,
  /// usage and samples ride along untouched.
  static func applying(_ update: VoiceprintUpdate, to voiceprints: [StoredVoiceprint], now: Date = Date())
    -> [StoredVoiceprint]
  {
    guard let embedding = LocalSpeakerRegistry.normalized(update.embedding) else { return voiceprints }
    var next = voiceprints
    if let index = next.firstIndex(where: { $0.personId == update.personId }) {
      let existing = next[index]
      let replace = update.isEnrolled && !existing.isEnrolled
      var blended = embedding
      if !replace {
        for i in blended.indices {
          blended[i] = existing.embedding[i] * 0.5 + embedding[i] * 0.5
        }
      }
      var merged = existing
      merged.embedding = LocalSpeakerRegistry.normalized(blended) ?? embedding
      merged.speechSeconds = replace ? update.speechSeconds : existing.speechSeconds + update.speechSeconds
      merged.updatedAt = now
      merged.isEnrolled = existing.isEnrolled || update.isEnrolled
      next[index] = merged
    } else {
      next.append(
        StoredVoiceprint(
          personId: update.personId,
          embedding: embedding,
          speechSeconds: update.speechSeconds,
          updatedAt: now,
          isEnrolled: update.isEnrolled
        ))
    }
    return next
  }
}
