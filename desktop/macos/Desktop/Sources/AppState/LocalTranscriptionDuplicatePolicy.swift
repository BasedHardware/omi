import Foundation

/// Identifies a narrow class of duplicate STT segments caused by the same
/// playback being present in both the system-audio tap and the microphone input.
///
/// This deliberately requires exact normalized text, or the mic segment's entire
/// normalized word run appearing contiguously inside a system-audio segment, plus
/// tight timing. Arbitrary fuzzy matching would risk deleting legitimate speech
/// where two people happen to say similar words at the same time.
///
/// The containment rule exists because both recognizers run rolling windows
/// with different boundaries: the same playback re-transcribes as a *partial*
/// overlap (measured 2026-09-04: every spoken reply appeared 2-4× across the two
/// lanes, none of the duplicate pairs exactly equal). Containment is strictly
/// one-directional — only a mic row that is *entirely* an echo fragment of a
/// system-audio row may be dropped. A mic row that mixes human speech with echo
/// (rolling windows routinely fuse "user question + reply onset" into one row)
/// is kept whole, because row-level suppression cannot separate the two; the
/// same measurement showed bidirectional containment deleting the user's own
/// questions from the ambient record.
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

    // Containment: only a mic row wholly contained in a system-audio row is an
    // echo fragment. The reverse (system ⊆ mic) means the mic row carries more
    // than the playback — human speech, a longer capture window, or both — and
    // must survive.
    guard min(lhsWords.count, rhsWords.count) >= minimumContainmentWordCount else { return false }
    let micWords = lhs.isUser ? lhsWords : rhsWords
    let systemWords = lhs.isUser ? rhsWords : lhsWords
    guard containsContiguous(systemWords, subsequence: micWords) else { return false }

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
