import Foundation

enum OnboardingMemoryBatchImportService {
  static func save(
    _ memories: [MemoryBatchItem],
    logPrefix: String
  ) async -> (saved: Int, failed: Int) {
    guard !memories.isEmpty else { return (0, 0) }

    let chunks = memories.chunked(maxSize: APIClient.memoriesBatchMaxSize)
    var saved = 0
    var failed = 0

    for chunk in chunks {
      do {
        let response = try await APIClient.shared.createMemoriesBatch(chunk)
        saved += response.createdCount
        failed += max(0, chunk.count - response.createdCount)
      } catch {
        failed += chunk.count
        log("\(logPrefix): Failed saving memory batch (\(chunk.count) items): \(error)")
      }
    }

    return (saved, failed)
  }
}

extension Array {
  func chunked(maxSize: Int) -> [[Element]] {
    precondition(maxSize > 0, "chunk size must be positive")
    guard !isEmpty else { return [] }

    var chunks: [[Element]] = []
    var index = startIndex
    while index < endIndex {
      let chunkEnd = self.index(index, offsetBy: maxSize, limitedBy: endIndex) ?? endIndex
      chunks.append(Array(self[index..<chunkEnd]))
      index = chunkEnd
    }
    return chunks
  }
}
