import Foundation

/// A Sendable snapshot of one ambient transcript segment, extracted from
/// `SpeakerSegment` on the main actor so the engine actor never crosses an
/// isolation boundary with the live object.
struct TranscriptSpeechSlice: Equatable, Sendable {
  let segmentID: String?
  let speaker: Int
  let text: String
  let isUser: Bool
  let start: Double
  let end: Double
}

extension SpeakerSegment {
  /// Value copy for the speech proactivity decide loop; the engine actor never
  /// touches the mutable `SpeakerSegment` it is extracted from.
  var speechProactivitySlice: TranscriptSpeechSlice {
    TranscriptSpeechSlice(
      segmentID: segmentId,
      speaker: speaker,
      text: text,
      isUser: isUser,
      start: start,
      end: end)
  }
}

/// Bounded rolling window of recent ambient speech. Pure value type: the
/// coordinator owns the mutation and the engine reads a Sendable snapshot.
/// Recency is measured by when each slice was *seen* (`seenAt`), never by the
/// transcript's own `start`/`end`, whose scale is backend-defined and not
/// comparable to a wall clock.
struct SpeechProactivityWindow: Equatable, Sendable {
  static let maximumSliceCount = 12
  static let retentionSeconds: TimeInterval = 180

  private struct DatedSlice: Equatable, Sendable {
    let slice: TranscriptSpeechSlice
    let seenAt: Date
  }

  private var datedSlices: [DatedSlice] = []

  var latestUserSlice: TranscriptSpeechSlice? {
    datedSlices.last { $0.slice.isUser }?.slice
  }

  mutating func append(_ slice: TranscriptSpeechSlice, seenAt: Date) {
    if let segmentID = slice.segmentID,
      let index = datedSlices.firstIndex(where: { $0.slice.segmentID == segmentID })
    {
      // A later transcript event for the same backend segment carries the
      // authoritative (longer) text; replace in place so the window keeps one
      // copy of the utterance.
      datedSlices[index] = DatedSlice(slice: slice, seenAt: seenAt)
    } else {
      datedSlices.append(DatedSlice(slice: slice, seenAt: seenAt))
    }
    prune(now: seenAt)
  }

  func snapshot() -> [TranscriptSpeechSlice] {
    datedSlices.map(\.slice)
  }

  private mutating func prune(now: Date) {
    let cutoff = now.addingTimeInterval(-Self.retentionSeconds)
    datedSlices.removeAll { $0.seenAt < cutoff }
    if datedSlices.count > Self.maximumSliceCount {
      datedSlices.removeFirst(datedSlices.count - Self.maximumSliceCount)
    }
  }
}
