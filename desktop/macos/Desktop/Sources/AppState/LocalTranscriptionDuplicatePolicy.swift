import Foundation

/// Identifies a narrow class of duplicate local-STT segments caused by the same
/// playback being present in both the system-audio tap and the microphone input.
///
/// This deliberately requires exact normalized text and tight timing. Fuzzy text
/// matching would risk deleting legitimate speech where two people happen to say
/// similar words at the same time.
enum LocalTranscriptionDuplicateDecision: Equatable {
  case accept
  case suppressIncoming
  case replaceExisting(segmentId: String)
}

enum LocalTranscriptionDuplicatePolicy {
  /// Short acknowledgements such as "yes" or "okay" are too common to use as
  /// reliable evidence of playback bleed.
  static let minimumWordCount = 4

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
    guard lhs.isUser != rhs.isUser,
      normalizedWords(lhs.text).count >= minimumWordCount,
      normalizedWords(lhs.text) == normalizedWords(rhs.text)
    else {
      return false
    }

    return timestampRangesAreClose(lhs, rhs)
  }

  static func normalizedWords(_ text: String) -> [String] {
    text
      .lowercased()
      .split { !$0.isLetter && !$0.isNumber }
      .map(String.init)
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
