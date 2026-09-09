import Foundation

/// Which remembered voices to keep when there are more people than the store should hold.
///
/// **LFU with exponential aging**, favorites pinned. Every session a person is heard in bumps
/// their use score by one; the score halves every `halfLifeDays`. So someone heard weekly
/// outranks a one-off from yesterday (plain LRU would keep the one-off), and someone heard a
/// lot last year fades instead of squatting on a slot forever (plain LFU would keep them).
/// One number per person, decayed lazily, so it is cheap and deterministic to test.
struct VoiceEnrollmentPolicy: Sendable {
  /// Remembered people (the user's own voice is never counted or evicted).
  var capacity: Int = 30
  var halfLifeDays: Double = 14
  /// Audio kept per voice: the most recent clips, newest first.
  var maxSamplesPerVoice: Int = 5
  /// Longest clip kept; a longer window is trimmed to its end (the freshest speech).
  var maxSampleSeconds: Double = 12
  /// Minimum gap between two automatically saved clips of one voice.
  var sampleIntervalSeconds: Double = 60

  init() {}

  /// `score` as of `now`, given it was last touched at `lastUsedAt`.
  func decayedScore(_ score: Double, lastUsedAt: Date?, now: Date) -> Double {
    guard let lastUsedAt, score > 0 else { return 0 }
    let days = max(0, now.timeIntervalSince(lastUsedAt) / 86_400)
    return score * pow(0.5, days / halfLifeDays)
  }

  /// One more session this voice was heard in.
  func recordingUse(of voiceprint: StoredVoiceprint, now: Date) -> StoredVoiceprint {
    var next = voiceprint
    next.useScore = decayedScore(voiceprint.useScore, lastUsedAt: voiceprint.lastUsedAt, now: now) + 1
    next.lastUsedAt = now
    return next
  }

  /// Person ids to drop so that at most `capacity` non-favorite people remain: the lowest
  /// current scores go first, ties broken by the oldest last use. Favorites and the user are
  /// never returned.
  func evictions(from voiceprints: [StoredVoiceprint], now: Date) -> [String] {
    let people = voiceprints.filter { $0.personId != nil }
    let overflow = people.count - capacity
    guard overflow > 0 else { return [] }
    let candidates =
      people
      .filter { !$0.isFavorite }
      .map {
        (
          id: $0.personId ?? "", score: decayedScore($0.useScore, lastUsedAt: $0.lastUsedAt, now: now),
          last: $0.lastUsedAt ?? .distantPast
        )
      }
      .sorted { lhs, rhs in
        if lhs.score != rhs.score { return lhs.score < rhs.score }
        return lhs.last < rhs.last
      }
    return candidates.prefix(overflow).map(\.id)
  }
}
