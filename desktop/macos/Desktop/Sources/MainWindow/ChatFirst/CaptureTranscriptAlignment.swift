import Foundation

/// One recognized word on the audio's own clock (seconds into the media).
struct RecognizedWord: Equatable, Sendable {
  let text: String
  let start: TimeInterval
}

/// A transcript segment that was located in the audio: where the transcript
/// says it is versus where the words were actually heard.
struct CaptureTranscriptMatch: Equatable, Sendable {
  let segmentIndex: Int
  let transcriptTime: TimeInterval
  let audioTime: TimeInterval

  var offset: TimeInterval { audioTime - transcriptTime }
}

/// A piecewise-linear "transcript time → audio time" correction anchored on
/// matched segments. Between anchors the shift interpolates; outside them it
/// holds the nearest anchor's shift, so a capture whose delivery gaps sit in
/// the middle is corrected on both sides of the gap.
struct CaptureTranscriptOffsetCurve: Equatable, Sendable {
  struct Anchor: Equatable, Sendable {
    let transcriptTime: TimeInterval
    let offset: TimeInterval
  }

  let anchors: [Anchor]

  func offset(at transcriptTime: TimeInterval) -> TimeInterval {
    guard let first = anchors.first, let last = anchors.last else { return 0 }
    if transcriptTime <= first.transcriptTime { return first.offset }
    if transcriptTime >= last.transcriptTime { return last.offset }
    var lower = first
    for anchor in anchors {
      if anchor.transcriptTime <= transcriptTime {
        lower = anchor
        continue
      }
      let span = anchor.transcriptTime - lower.transcriptTime
      guard span > 0 else { return anchor.offset }
      let fraction = (transcriptTime - lower.transcriptTime) / span
      return lower.offset + fraction * (anchor.offset - lower.offset)
    }
    return last.offset
  }
}

/// What a resync did, for the status line and the log.
struct CaptureTranscriptSyncReport: Equatable, Sendable {
  let matchedSegments: Int
  let alignableSegments: Int
  let shiftAtStart: TimeInterval
  let shiftAtEnd: TimeInterval
}

/// Word-level alignment of a capture's transcript against speech recognized
/// from its stored audio. The transcript keeps every speaker, name, and edit;
/// only `start`/`end` move onto the audio's clock.
///
/// Why this exists: the backend stamps segment times on the speech provider's
/// stream clock, which falls behind wall time whenever device audio drops out,
/// while the stored audio keeps real receive times. The two drift apart over a
/// session, so no fixed formula can line them up; listening to the audio can.
enum CaptureTranscriptAlignmentPolicy {
  /// Minimum consecutive words that must agree before a segment is trusted.
  static let gramSize = 3
  /// How far from the transcript's claim the words may be found. Drift on real
  /// captures reached ~95 s; the window leaves room without inviting false
  /// matches from repeated phrases far away.
  static let searchWindow: TimeInterval = 300
  /// A match this far from the local consensus is a coincidence, not evidence.
  static let outlierTolerance: TimeInterval = 4
  static let minimumMatches = 3

  static func normalizedTokens(_ text: String) -> [String] {
    text.lowercased()
      .split(whereSeparator: { !$0.isLetter && !$0.isNumber && $0 != "'" })
      .map { String($0).replacingOccurrences(of: "'", with: "") }
      .filter { !$0.isEmpty }
  }

  /// Locates each segment with at least `gramSize` words in the recognized
  /// stream. Every n-gram of the segment votes with its own offset; the
  /// segment's offset is the median vote, so one mis-heard word cannot drag it.
  static func matches(
    segments: [TranscriptSegment],
    words: [RecognizedWord]
  ) -> [CaptureTranscriptMatch] {
    let wordTokens = words.map { normalizedTokens($0.text).first ?? "" }
    var index: [String: [Int]] = [:]
    if wordTokens.count >= gramSize {
      for position in 0...(wordTokens.count - gramSize) {
        let key = wordTokens[position..<(position + gramSize)].joined(separator: " ")
        index[key, default: []].append(position)
      }
    }

    var result: [CaptureTranscriptMatch] = []
    for (segmentIndex, segment) in segments.enumerated() {
      let tokens = normalizedTokens(segment.text)
      guard tokens.count >= gramSize else { continue }
      let duration = max(0, segment.end - segment.start)
      var votes: [(transcriptTime: TimeInterval, audioTime: TimeInterval)] = []
      for position in 0...(tokens.count - gramSize) {
        let key = tokens[position..<(position + gramSize)].joined(separator: " ")
        guard let candidates = index[key] else { continue }
        // Where this gram's first word sits inside the segment, on the
        // transcript's clock, taking the words as evenly spread.
        let fraction = tokens.count > 1 ? Double(position) / Double(tokens.count - 1) : 0
        let transcriptTime = segment.start + fraction * duration
        let nearest =
          candidates
          .map { words[$0].start }
          .filter { abs($0 - transcriptTime) <= searchWindow }
          .min(by: { abs($0 - transcriptTime) < abs($1 - transcriptTime) })
        if let nearest {
          votes.append((transcriptTime, nearest))
        }
      }
      let offsets = votes.map { $0.audioTime - $0.transcriptTime }
      let medianOffset = median(offsets)
      // Report the vote closest to the median so the anchor is a real word time.
      guard
        let representative = votes.min(by: {
          abs(($0.audioTime - $0.transcriptTime) - medianOffset)
            < abs(($1.audioTime - $1.transcriptTime) - medianOffset)
        })
      else { continue }
      result.append(
        CaptureTranscriptMatch(
          segmentIndex: segmentIndex,
          transcriptTime: representative.transcriptTime,
          audioTime: representative.audioTime
        ))
    }
    return result
  }

  /// Turns matches into a correction curve, or nil when the evidence is too
  /// thin or too contradictory to move anything. A match counts only when at
  /// least one adjacent match agrees with it: drift steps at a delivery gap
  /// are shared by everything after the gap, while a repeated phrase heard
  /// somewhere else agrees with nothing around it and is dropped.
  static func offsetCurve(from matches: [CaptureTranscriptMatch]) -> CaptureTranscriptOffsetCurve? {
    let sorted = matches.sorted { $0.transcriptTime < $1.transcriptTime }
    guard sorted.count >= minimumMatches else { return nil }
    var inliers: [CaptureTranscriptMatch] = []
    for (position, match) in sorted.enumerated() {
      let neighbours = [position - 1, position + 1]
        .filter { $0 >= 0 && $0 < sorted.count }
        .map { sorted[$0].offset }
      if neighbours.contains(where: { abs($0 - match.offset) <= outlierTolerance }) {
        inliers.append(match)
      }
    }
    guard inliers.count >= minimumMatches else { return nil }
    // Merge anchors that share a transcript time so interpolation never divides by zero.
    var anchors: [CaptureTranscriptOffsetCurve.Anchor] = []
    for match in inliers {
      if let last = anchors.last, abs(last.transcriptTime - match.transcriptTime) < 0.001 {
        anchors[anchors.count - 1] = .init(
          transcriptTime: last.transcriptTime, offset: (last.offset + match.offset) / 2)
      } else {
        anchors.append(.init(transcriptTime: match.transcriptTime, offset: match.offset))
      }
    }
    return CaptureTranscriptOffsetCurve(anchors: anchors)
  }

  /// Moves every segment onto the audio's clock. Speaker, person, text, ids,
  /// and translations are untouched; a segment can never end before it starts
  /// or start before the audio does.
  static func rebase(
    segments: [TranscriptSegment],
    curve: CaptureTranscriptOffsetCurve
  ) -> [TranscriptSegment] {
    segments.map { segment in
      let start = max(0, segment.start + curve.offset(at: segment.start))
      let end = max(start, segment.end + curve.offset(at: segment.end))
      return TranscriptSegment(
        id: segment.id,
        backendId: segment.backendId,
        text: segment.text,
        speaker: segment.speaker,
        isUser: segment.isUser,
        personId: segment.personId,
        start: start,
        end: end,
        translations: segment.translations
      )
    }
  }

  static func report(
    segments: [TranscriptSegment],
    matches: [CaptureTranscriptMatch],
    curve: CaptureTranscriptOffsetCurve
  ) -> CaptureTranscriptSyncReport {
    let alignable = segments.filter { normalizedTokens($0.text).count >= gramSize }.count
    // Read at the transcript's ends, not the last segment's start: with drift
    // through the final sentence the two differ, and the status names the shift
    // the listener meets at the end.
    let first = segments.first?.start ?? 0
    let last = segments.last?.end ?? 0
    return CaptureTranscriptSyncReport(
      matchedSegments: matches.count,
      alignableSegments: alignable,
      shiftAtStart: curve.offset(at: first),
      shiftAtEnd: curve.offset(at: last)
    )
  }

  static func median(_ values: [TimeInterval]) -> TimeInterval {
    guard !values.isEmpty else { return 0 }
    let sorted = values.sorted()
    let middle = sorted.count / 2
    return sorted.count.isMultiple(of: 2) ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle]
  }
}
