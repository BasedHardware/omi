import Foundation

struct TranscriptChunkRecord: Sendable, Equatable {
  var id: Int64?
  let sessionId: Int64
  let chunkIndex: Int
  let text: String
  let textSha256: String
  let startedAt: Date
}

enum TranscriptChunker {
  static let window = 8
  static let stride = 6

  struct Segment: Sendable, Equatable {
    var text: String
    var order: Int
    var startedAt: Date
  }

  static func chunks(sessionId: Int64, segments: [Segment]) -> [TranscriptChunkRecord] {
    let ordered = segments.filter { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
      .sorted { $0.order == $1.order ? $0.startedAt < $1.startedAt : $0.order < $1.order }
    guard !ordered.isEmpty else { return [] }
    var result: [TranscriptChunkRecord] = []
    var start = 0
    var index = 0
    while start < ordered.count {
      let end = min(start + window, ordered.count)
      let slice = ordered[start..<end]
      let text = slice.map(\.text).joined(separator: "\n")
      result.append(
        TranscriptChunkRecord(
          id: nil,
          sessionId: sessionId,
          chunkIndex: index,
          text: text,
          textSha256: LocalEmbeddingStore.textHash(text),
          startedAt: slice.first?.startedAt ?? Date(timeIntervalSince1970: 0)))
      if end == ordered.count { break }
      start += stride
      index += 1
    }
    return result
  }
}
