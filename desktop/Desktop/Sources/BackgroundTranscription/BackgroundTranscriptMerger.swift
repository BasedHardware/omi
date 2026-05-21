import Foundation

struct BackgroundTranscriptMerger {
  private(set) var segments: [TranscriptionService.BackendSegment] = []
  private let duplicateOverlapThreshold: Double

  init(duplicateOverlapThreshold: Double = 0.8) {
    self.duplicateOverlapThreshold = duplicateOverlapThreshold
  }

  mutating func reset() {
    segments = []
  }

  mutating func merge(_ incomingSegments: [TranscriptionService.BackendSegment])
    -> [TranscriptionService.BackendSegment]
  {
    for incoming in incomingSegments
    where !incoming.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      upsert(incoming)
    }
    segments.sort { lhs, rhs in
      if lhs.start == rhs.start {
        return lhs.end < rhs.end
      }
      return lhs.start < rhs.start
    }
    return segments
  }

  private mutating func upsert(_ incoming: TranscriptionService.BackendSegment) {
    if let segmentId = incoming.id,
      let index = segments.firstIndex(where: { $0.id == segmentId })
    {
      segments[index] = preferredSegment(existing: segments[index], incoming: incoming)
      return
    }

    if let index = segments.firstIndex(where: { isDuplicate($0, incoming) }) {
      segments[index] = preferredSegment(existing: segments[index], incoming: incoming)
      return
    }

    if let index = segments.firstIndex(where: { canMergeOverlap($0, incoming) }) {
      segments[index] = mergedOverlap(segments[index], incoming)
      return
    }

    segments.append(incoming)
  }

  private func isDuplicate(
    _ existing: TranscriptionService.BackendSegment,
    _ incoming: TranscriptionService.BackendSegment
  ) -> Bool {
    guard normalizedText(existing.text) == normalizedText(incoming.text) else { return false }
    let intersection = max(0, min(existing.end, incoming.end) - max(existing.start, incoming.start))
    let shorterDuration = max(0.001, min(existing.end - existing.start, incoming.end - incoming.start))
    return intersection / shorterDuration >= duplicateOverlapThreshold
  }

  private func canMergeOverlap(
    _ existing: TranscriptionService.BackendSegment,
    _ incoming: TranscriptionService.BackendSegment
  ) -> Bool {
    guard (existing.speaker_id ?? 0) == (incoming.speaker_id ?? 0) else { return false }
    guard min(existing.end, incoming.end) > max(existing.start, incoming.start) else {
      return false
    }
    return edgeTokenOverlap(existing.text, incoming.text) > 0
  }

  private func mergedOverlap(
    _ existing: TranscriptionService.BackendSegment,
    _ incoming: TranscriptionService.BackendSegment
  ) -> TranscriptionService.BackendSegment {
    let existingFirst = existing.start <= incoming.start
    let first = existingFirst ? existing : incoming
    let second = existingFirst ? incoming : existing
    let overlap = edgeTokenOverlap(first.text, second.text)
    let suffix = tokenized(second.text).dropFirst(overlap).joined(separator: " ")
    let mergedText = suffix.isEmpty ? first.text : "\(first.text) \(suffix)"

    return TranscriptionService.BackendSegment(
      id: first.id ?? second.id,
      text: mergedText,
      speaker: first.speaker ?? second.speaker,
      speaker_id: first.speaker_id ?? second.speaker_id,
      is_user: first.is_user || second.is_user,
      person_id: first.person_id ?? second.person_id,
      start: min(first.start, second.start),
      end: max(first.end, second.end),
      translations: first.translations ?? second.translations,
      stt_provider: first.stt_provider ?? second.stt_provider,
      stt_model: first.stt_model ?? second.stt_model,
      provider_cluster_id: first.provider_cluster_id ?? second.provider_cluster_id,
      provider_speaker_label: first.provider_speaker_label ?? second.provider_speaker_label,
      speaker_identity_state: first.speaker_identity_state ?? second.speaker_identity_state,
      speaker_identity_confidence: first.speaker_identity_confidence ?? second.speaker_identity_confidence,
      speaker_identity_source: first.speaker_identity_source ?? second.speaker_identity_source,
      speaker_identity_version: first.speaker_identity_version ?? second.speaker_identity_version
    )
  }

  private func preferredSegment(
    existing: TranscriptionService.BackendSegment,
    incoming: TranscriptionService.BackendSegment
  ) -> TranscriptionService.BackendSegment {
    if normalizedText(existing.text) == normalizedText(incoming.text),
      existing.text.count <= incoming.text.count
    {
      return existing
    }
    if incoming.end - incoming.start > existing.end - existing.start {
      return incoming
    }
    if incoming.text.count > existing.text.count {
      return incoming
    }
    return existing
  }

  private func normalizedText(_ value: String) -> String {
    value.lowercased()
      .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
      .trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private func tokenized(_ value: String) -> [String] {
    normalizedText(value).split(separator: " ").map(String.init)
  }

  private func edgeTokenOverlap(_ first: String, _ second: String) -> Int {
    let left = tokenized(first)
    let right = tokenized(second)
    guard !left.isEmpty, !right.isEmpty else { return 0 }

    let maxOverlap = min(left.count, right.count)
    for count in stride(from: maxOverlap, through: 1, by: -1) {
      if Array(left.suffix(count)) == Array(right.prefix(count)) {
        return count
      }
    }
    return 0
  }
}
