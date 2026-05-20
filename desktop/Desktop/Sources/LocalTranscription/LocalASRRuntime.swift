import Foundation

enum LocalTranscriptionModel: String, CaseIterable, Codable, Equatable, Hashable {
  case tiny
  case base
  case small
  case medium
  case largeV3Turbo = "large_v3_turbo"
}

struct LocalTranscriptionPlan: Equatable {
  var engine: LocalTranscriptionEngine
  var model: LocalTranscriptionModel
  var quality: TranscriptionQualityPreset
}

struct LocalASRTranscriptionRequest: Codable, Equatable {
  var requestId: String
  var audioPath: String
  var language: String
  var sampleRate: Int
  var channels: Int
  var engine: LocalTranscriptionEngine
  var model: LocalTranscriptionModel
  var fixtureSegments: [LocalASRTranscriptSegment]?

  enum CodingKeys: String, CodingKey {
    case requestId = "request_id"
    case audioPath = "audio_path"
    case language
    case sampleRate = "sample_rate"
    case channels
    case engine
    case model
    case fixtureSegments = "fixture_segments"
  }
}

struct LocalASRTranscriptionResponse: Codable, Equatable {
  var requestId: String
  var engine: LocalTranscriptionEngine
  var model: LocalTranscriptionModel
  var language: String
  var segments: [LocalASRTranscriptSegment]
  var fixture: Bool

  enum CodingKeys: String, CodingKey {
    case requestId = "request_id"
    case engine
    case model
    case language
    case segments
    case fixture
  }
}

struct LocalASRTranscriptSegment: Codable, Equatable {
  var id: String?
  var speaker: Int?
  var text: String
  var start: Double
  var end: Double

  func normalized(defaultSpeaker: Int = 0) -> NormalizedTranscriptSegment {
    NormalizedTranscriptSegment(
      segmentId: id,
      speaker: speaker ?? defaultSpeaker,
      speakerLabel: nil,
      text: text,
      start: start,
      end: end,
      isUser: true,
      personId: nil,
      translations: []
    )
  }
}

struct LocalASRHelperClient {
  var executableURL: URL
  var timeoutSeconds: TimeInterval = 60

  func transcribe(_ request: LocalASRTranscriptionRequest) async throws
    -> LocalASRTranscriptionResponse
  {
    let process = Process()
    process.executableURL = executableURL

    let input = Pipe()
    let output = Pipe()
    let errors = Pipe()
    process.standardInput = input
    process.standardOutput = output
    process.standardError = errors

    try process.run()
    let requestData = try JSONEncoder.localASR.encode(request)
    input.fileHandleForWriting.write(requestData)
    try? input.fileHandleForWriting.close()

    return try await withTimeout(seconds: timeoutSeconds) {
      process.waitUntilExit()
      let outputData = output.fileHandleForReading.readDataToEndOfFile()
      if process.terminationStatus != 0 {
        let errorText =
          String(data: errors.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        throw TranscriptionService.TranscriptionError.webSocketError(
          "Local ASR helper exited with status \(process.terminationStatus): \(errorText)"
        )
      }
      return try JSONDecoder.localASR.decode(LocalASRTranscriptionResponse.self, from: outputData)
    }
  }

  private func withTimeout<T: Sendable>(
    seconds: TimeInterval,
    operation: @escaping @Sendable () throws -> T
  ) async throws -> T {
    try await withThrowingTaskGroup(of: T.self) { group in
      group.addTask {
        try operation()
      }
      group.addTask {
        try await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
        throw CancellationError()
      }
      guard let result = try await group.next() else {
        throw CancellationError()
      }
      group.cancelAll()
      return result
    }
  }
}

struct LocalTranscriptMerger {
  private(set) var segments: [NormalizedTranscriptSegment] = []
  private let duplicateOverlapThreshold: Double

  init(duplicateOverlapThreshold: Double = 0.8) {
    self.duplicateOverlapThreshold = duplicateOverlapThreshold
  }

  mutating func merge(_ incomingSegments: [NormalizedTranscriptSegment])
    -> [NormalizedTranscriptSegment]
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

  private mutating func upsert(_ incoming: NormalizedTranscriptSegment) {
    if let segmentId = incoming.segmentId,
      let index = segments.firstIndex(where: { $0.segmentId == segmentId })
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
    _ existing: NormalizedTranscriptSegment, _ incoming: NormalizedTranscriptSegment
  ) -> Bool {
    guard normalizedText(existing.text) == normalizedText(incoming.text) else { return false }
    let intersection = max(0, min(existing.end, incoming.end) - max(existing.start, incoming.start))
    let shorterDuration = max(
      0.001, min(existing.end - existing.start, incoming.end - incoming.start))
    return intersection / shorterDuration >= duplicateOverlapThreshold
  }

  private func canMergeOverlap(
    _ existing: NormalizedTranscriptSegment,
    _ incoming: NormalizedTranscriptSegment
  ) -> Bool {
    guard existing.speaker == incoming.speaker else { return false }
    guard min(existing.end, incoming.end) > max(existing.start, incoming.start) else {
      return false
    }
    return edgeTokenOverlap(existing.text, incoming.text) > 0
  }

  private func mergedOverlap(
    _ existing: NormalizedTranscriptSegment,
    _ incoming: NormalizedTranscriptSegment
  ) -> NormalizedTranscriptSegment {
    let existingFirst = existing.start <= incoming.start
    let first = existingFirst ? existing : incoming
    let second = existingFirst ? incoming : existing
    let overlap = edgeTokenOverlap(first.text, second.text)
    let suffix = tokenized(second.text).dropFirst(overlap).joined(separator: " ")

    var merged = first
    merged.segmentId = first.segmentId ?? second.segmentId
    merged.start = min(first.start, second.start)
    merged.end = max(first.end, second.end)
    merged.text = suffix.isEmpty ? first.text : "\(first.text) \(suffix)"
    return merged
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

  private func preferredSegment(
    existing: NormalizedTranscriptSegment,
    incoming: NormalizedTranscriptSegment
  ) -> NormalizedTranscriptSegment {
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
}

extension JSONEncoder {
  fileprivate static var localASR: JSONEncoder {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    return encoder
  }
}

extension JSONDecoder {
  fileprivate static var localASR: JSONDecoder {
    JSONDecoder()
  }
}
