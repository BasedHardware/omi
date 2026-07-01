import Foundation

protocol MemoryBatchCreating {
  func createMemoriesBatch(_ memories: [MemoryBatchItem]) async throws -> BatchMemoriesResponse
}

extension APIClient: MemoryBatchCreating {}

enum OnboardingMemoryBatchImportService {
  private static let retryBackoffSeconds: [UInt64] = [2, 5, 10]

  static func save(
    _ memories: [MemoryBatchItem],
    logPrefix: String,
    apiClient: MemoryBatchCreating = APIClient.shared,
    sleep: @escaping (UInt64) async -> Void = sleepSeconds
  ) async -> (saved: Int, failed: Int) {
    guard !memories.isEmpty else { return (0, 0) }

    let chunks = memories.chunked(maxSize: APIClient.memoriesBatchMaxSize)
    var saved = 0
    var failed = 0

    for chunk in chunks {
      do {
        let response = try await createChunkWithRetry(
          chunk,
          logPrefix: logPrefix,
          apiClient: apiClient,
          sleep: sleep
        )
        saved += response.createdCount
        failed += max(0, chunk.count - response.createdCount)
      } catch {
        failed += chunk.count
        log("\(logPrefix): Failed saving memory batch (\(chunk.count) items): \(error)")
      }
    }

    return (saved, failed)
  }

  private static func createChunkWithRetry(
    _ chunk: [MemoryBatchItem],
    logPrefix: String,
    apiClient: MemoryBatchCreating,
    sleep: @escaping (UInt64) async -> Void
  ) async throws -> BatchMemoriesResponse {
    var lastError: Error?

    for attempt in 0...retryBackoffSeconds.count {
      do {
        return try await apiClient.createMemoriesBatch(chunk)
      } catch {
        lastError = error
        guard shouldRetry(error), attempt < retryBackoffSeconds.count else {
          throw error
        }
        let delay = retryBackoffSeconds[attempt]
        log(
          "\(logPrefix): Retrying memory batch after \(delay)s " +
            "(\(chunk.count) items, attempt \(attempt + 2)): \(error)"
        )
        await sleep(delay)
      }
    }

    throw lastError ?? APIError.invalidResponse
  }

  private static func shouldRetry(_ error: Error) -> Bool {
    guard case let APIError.httpError(statusCode, _) = error else { return false }
    return statusCode == 429 || (500...599).contains(statusCode)
  }

  private static func sleepSeconds(_ seconds: UInt64) async {
    try? await Task.sleep(nanoseconds: seconds * 1_000_000_000)
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
