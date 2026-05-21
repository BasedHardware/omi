import Foundation

struct SpeakerSegmentReducer {
  struct ApplyResult: Equatable {
    var added: Int = 0
    var updated: Int = 0
    var totalSegmentCount: Int = 0
    var totalWordCount: Int = 0
  }

  private(set) var segments: [SpeakerSegment] = []
  private(set) var totalSegmentCount: Int = 0
  private(set) var totalWordCount: Int = 0
  var maxInMemorySegments: Int

  init(maxInMemorySegments: Int = 400) {
    self.maxInMemorySegments = maxInMemorySegments
  }

  mutating func reset() {
    segments = []
    totalSegmentCount = 0
    totalWordCount = 0
  }

  mutating func replaceSegments(_ replacement: [SpeakerSegment]) {
    segments = replacement
    totalSegmentCount = replacement.count
    totalWordCount = replacement.reduce(0) { $0 + wordCount($1.text) }
  }

  mutating func apply(_ incomingSegments: [TranscriptionService.BackendSegment]) -> ApplyResult {
    apply(incomingSegments.map(Self.speakerSegment(from:)))
  }

  mutating func apply(_ incomingSegments: [SpeakerSegment]) -> ApplyResult {
    var result = ApplyResult()

    for incoming in incomingSegments where !incoming.text.isEmpty {
      if let segId = incoming.segmentId,
        let existingIdx = segments.firstIndex(where: { $0.segmentId == segId })
      {
        let oldWords = wordCount(segments[existingIdx].text)
        var updated = incoming
        if updated.translations.isEmpty && !segments[existingIdx].translations.isEmpty {
          updated.translations = segments[existingIdx].translations
        }
        segments[existingIdx] = updated
        totalWordCount += wordCount(updated.text) - oldWords
        result.updated += 1
      } else {
        segments.append(incoming)
        totalSegmentCount += 1
        totalWordCount += wordCount(incoming.text)
        result.added += 1
      }
    }

    if segments.count > maxInMemorySegments {
      segments.removeFirst(segments.count - maxInMemorySegments)
    }

    result.totalSegmentCount = totalSegmentCount
    result.totalWordCount = totalWordCount
    return result
  }

  private static func speakerSegment(from segment: TranscriptionService.BackendSegment) -> SpeakerSegment {
    SpeakerSegment(
      segmentId: segment.id,
      speaker: segment.speaker_id ?? 0,
      text: segment.text,
      start: segment.start,
      end: segment.end,
      isUser: segment.is_user,
      personId: segment.person_id,
      translations: (segment.translations ?? []).map { SegmentTranslation(lang: $0.lang, text: $0.text) }
    )
  }

  private func wordCount(_ text: String) -> Int {
    text.split(separator: " ").count
  }
}
