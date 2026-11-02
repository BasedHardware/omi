import Foundation

extension ConversationFinalizationService {
  static func compactSegmentsForBackendLimit(
    _ segments: [APIClient.UploadSegment],
    maxSegments: Int = 500
  ) -> [APIClient.UploadSegment] {
    guard maxSegments > 0, segments.count > maxSegments else { return segments }

    var compacted: [APIClient.UploadSegment] = []
    compacted.reserveCapacity(maxSegments)
    for index in 0..<maxSegments {
      let startIndex = index * segments.count / maxSegments
      let endIndex = (index + 1) * segments.count / maxSegments
      let group = Array(segments[startIndex..<endIndex])
      guard let first = group.first, let last = group.last else { continue }

      let sameSpeaker = group.allSatisfy { segment in
        segment.speaker == first.speaker
          && segment.speaker_id == first.speaker_id
          && segment.is_user == first.is_user
          && segment.person_id == first.person_id
      }
      compacted.append(
        APIClient.UploadSegment(
          text: group.map(\.text).joined(separator: " "),
          speaker: sameSpeaker ? first.speaker : "MIXED",
          speaker_id: sameSpeaker ? first.speaker_id : nil,
          is_user: sameSpeaker ? first.is_user : false,
          person_id: sameSpeaker ? first.person_id : nil,
          start: first.start,
          end: last.end
        )
      )
    }
    return compacted
  }

}
