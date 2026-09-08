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
}

/// What the diarizer asks to remember after a window, a naming, or an enrollment.
struct VoiceprintUpdate: Equatable, Sendable {
  let personId: String?
  let embedding: [Float]
  let speechSeconds: Double
  let isEnrolled: Bool
}

/// Per-user JSON file of remembered voices, next to the user's other local data. Small (a few
/// KB per person) and rewritten whole on every change; reads fail soft to "no voices known".
final class LocalVoiceprintStore: @unchecked Sendable {
  static let fileName = "voiceprints.json"

  private let fileURL: URL
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

  /// Fold `update` into `voiceprints` and return the new list. A guessed (learned) update blends
  /// 50/50 with an existing print so one odd session cannot replace an identity outright; an
  /// enrolled update replaces a guessed print, and blends with an enrolled one.
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
      next[index] = StoredVoiceprint(
        personId: update.personId,
        embedding: LocalSpeakerRegistry.normalized(blended) ?? embedding,
        speechSeconds: replace ? update.speechSeconds : existing.speechSeconds + update.speechSeconds,
        updatedAt: now,
        isEnrolled: existing.isEnrolled || update.isEnrolled
      )
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
