import Foundation

/// Identifies a narrow class of duplicate STT segments caused by the same
/// playback being present in both the system-audio tap and the microphone input.
///
/// This deliberately requires exact normalized text, a contiguous containment of
/// sufficient length, and tight timing. Arbitrary fuzzy matching would risk
/// deleting legitimate speech where two people happen to say similar words at
/// the same time.
///
/// The containment rule exists because both recognizers run rolling windows
/// with different boundaries: the same playback re-transcribes as a *partial*
/// overlap (measured 2026-09-04: every spoken reply appeared 2-4× across the two
/// lanes, none of the duplicate pairs exactly equal). A short contained run of
/// words is still playback bleed when it crosses lanes inside overlapping
/// windows; it is not something a second human produces by coincidence while
/// the machine speech plays the same words.
enum LocalTranscriptionDuplicateDecision: Equatable {
  case accept
  case suppressIncoming
  case replaceExisting(segmentId: String)
}

enum LocalTranscriptionDuplicatePolicy {
  /// Short acknowledgements such as "yes" or "okay" are too common to use as
  /// reliable evidence of playback bleed.
  static let minimumWordCount = 4

  /// Containment matches need a longer run than exact matches: a few shared
  /// words inside dissimilar sentences is ordinary speech, while a contiguous
  /// echo of this length across lanes inside overlapping windows is not.
  static let minimumContainmentWordCount = 6

  /// The two local recognizers use independent capture clocks. Allow a small
  /// boundary difference while still requiring the windows to overlap or nearly
  /// touch.
  static let maximumTimestampGap: Double = 1.0

  static func decision(
    for incoming: SpeakerSegment,
    existing: [SpeakerSegment]
  ) -> LocalTranscriptionDuplicateDecision {
    guard let duplicate = existing.first(where: { isDuplicate($0, incoming) }),
      let segmentId = duplicate.segmentId,
      !segmentId.isEmpty
    else {
      return .accept
    }

    // Keep one canonical segment. If the mic copy arrived first, promote that
    // existing row to the system-audio source rather than deleting and reinserting
    // it. If the system copy arrived first, discard only the later mic copy.
    return incoming.isUser ? .suppressIncoming : .replaceExisting(segmentId: segmentId)
  }

  static func isDuplicate(_ lhs: SpeakerSegment, _ rhs: SpeakerSegment) -> Bool {
    guard lhs.isUser != rhs.isUser else { return false }
    let lhsWords = normalizedWords(lhs.text)
    let rhsWords = normalizedWords(rhs.text)
    guard min(lhsWords.count, rhsWords.count) >= minimumWordCount else { return false }

    if lhsWords == rhsWords {
      return timestampRangesAreClose(lhs, rhs)
    }

    guard min(lhsWords.count, rhsWords.count) >= minimumContainmentWordCount,
      containsContiguous(lhsWords, subsequence: rhsWords)
        || containsContiguous(rhsWords, subsequence: lhsWords)
    else { return false }

    return timestampRangesAreClose(lhs, rhs)
  }

  static func normalizedWords(_ text: String) -> [String] {
    text
      .lowercased()
      .split { !$0.isLetter && !$0.isNumber }
      .map(String.init)
  }

  private static func containsContiguous(_ words: [String], subsequence other: [String]) -> Bool {
    guard !other.isEmpty, other.count <= words.count else { return false }
    let windowCount = words.count - other.count + 1
    for offset in 0..<windowCount {
      let window = words[offset..<(offset + other.count)]
      if window.elementsEqual(other) {
        return true
      }
    }
    return false
  }

  private static func timestampRangesAreClose(_ lhs: SpeakerSegment, _ rhs: SpeakerSegment) -> Bool {
    let overlapStart = max(lhs.start, rhs.start)
    let overlapEnd = min(lhs.end, rhs.end)
    if overlapStart <= overlapEnd {
      return true
    }

    return min(abs(lhs.start - rhs.end), abs(rhs.start - lhs.end)) <= maximumTimestampGap
  }
}
