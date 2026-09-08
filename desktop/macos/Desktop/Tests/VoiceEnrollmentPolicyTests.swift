import XCTest

@testable import Omi_Computer

/// Aged frequency with favorites pinned: who stays remembered when the store is full.
final class VoiceEnrollmentPolicyTests: XCTestCase {
  private let policy = VoiceEnrollmentPolicy()
  private let day: TimeInterval = 86_400

  private func voice(_ id: String?, score: Double, lastUsed: Date?, favorite: Bool = false) -> StoredVoiceprint {
    StoredVoiceprint(
      personId: id, embedding: [1, 0], speechSeconds: 10, updatedAt: lastUsed ?? .distantPast, isEnrolled: true,
      isFavorite: favorite, useScore: score, lastUsedAt: lastUsed)
  }

  func testScoreHalvesEveryHalfLife() {
    let now = Date()
    XCTAssertEqual(policy.decayedScore(8, lastUsedAt: now.addingTimeInterval(-14 * day), now: now), 4, accuracy: 1e-9)
    XCTAssertEqual(policy.decayedScore(8, lastUsedAt: now.addingTimeInterval(-28 * day), now: now), 2, accuracy: 1e-9)
    XCTAssertEqual(policy.decayedScore(8, lastUsedAt: nil, now: now), 0)
  }

  func testAUseBumpsTheDecayedScoreByOne() {
    let now = Date()
    let stale = voice("a", score: 4, lastUsed: now.addingTimeInterval(-14 * day))
    let used = policy.recordingUse(of: stale, now: now)
    XCTAssertEqual(used.useScore, 3, accuracy: 1e-9)
    XCTAssertEqual(used.lastUsedAt, now)
  }

  /// Weekly regular beats yesterday's one-off (LRU would get this wrong); a voice heard a lot
  /// long ago fades (LFU would get this wrong).
  func testEvictionDropsTheLeastValuableNonFavorites() {
    var policy = VoiceEnrollmentPolicy()
    policy.capacity = 2
    let now = Date()
    let prints = [
      voice(nil, score: 100, lastUsed: now),
      voice("weekly", score: 6, lastUsed: now.addingTimeInterval(-7 * day)),
      voice("one-off", score: 1, lastUsed: now.addingTimeInterval(-1 * day)),
      voice("last-year", score: 40, lastUsed: now.addingTimeInterval(-365 * day)),
      voice("pinned", score: 0, lastUsed: nil, favorite: true),
    ]

    let evicted = policy.evictions(from: prints, now: now)

    XCTAssertEqual(Set(evicted), ["one-off", "last-year"], "the user and the favorite are untouchable")
    XCTAssertEqual(policy.evictions(from: prints.filter { !evicted.contains($0.personId ?? "") }, now: now), [])
  }

  func testNothingIsEvictedUnderCapacity() {
    let prints = [voice("a", score: 0, lastUsed: nil), voice("b", score: 0, lastUsed: nil)]
    XCTAssertEqual(policy.evictions(from: prints, now: Date()), [])
  }
}
