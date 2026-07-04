import Foundation

protocol ImportEvidenceBatchCreating {
  func createMemoryImportBatch(_ batch: ImportEvidenceBatch) async throws -> ImportEvidenceBatchResponse
}

protocol MemoryBatchCreating {
  func createMemoriesBatch(_ memories: [MemoryBatchItem]) async throws -> BatchMemoriesResponse
}

extension APIClient: ImportEvidenceBatchCreating {}
extension APIClient: MemoryBatchCreating {}

enum OnboardingImportEvidenceService {
  private static let retryBackoffSeconds: [UInt64] = [2, 5, 10]

  static func save(
    _ artifacts: [ImportEvidenceBatchItem],
    sourceType: String,
    logPrefix: String,
    importRunId: String? = nil,
    sourceAccountHash: String? = nil,
    legacyMemories: [MemoryBatchItem]? = nil,
    apiClient: ImportEvidenceBatchCreating = APIClient.shared,
    legacyApiClient: MemoryBatchCreating = APIClient.shared,
    sleep: @escaping (UInt64) async -> Void = sleepSeconds
  ) async -> (saved: Int, failed: Int) {
    guard !artifacts.isEmpty else { return (0, 0) }

    let importRunId = importRunId ?? Self.newImportRunId(sourceType: sourceType)
    let artifacts = withClientDeviceProvenance(artifacts)
    let chunks = artifacts.chunked(maxSize: APIClient.memoryImportBatchMaxSize)
    var saved = 0
    var failed = 0

    for chunk in chunks {
      do {
        let response = try await createChunkWithRetry(
          chunk,
          sourceType: sourceType,
          importRunId: importRunId,
          sourceAccountHash: sourceAccountHash,
          logPrefix: logPrefix,
          apiClient: apiClient,
          sleep: sleep
        )
        saved += response.artifactsCreated + response.artifactsDeduped
        failed += max(0, chunk.count - response.artifactsReceived)
      } catch {
        if Self.isLegacyMemorySystemError(error), let legacyMemories {
          log("\(logPrefix): Import evidence unavailable for legacy memory system; using legacy memory batch path")
          return await OnboardingMemoryBatchImportService.save(
            legacyMemories,
            logPrefix: logPrefix,
            apiClient: legacyApiClient,
            sleep: sleep
          )
        }
        failed += chunk.count
        log("\(logPrefix): Failed saving import evidence batch (\(chunk.count) items): \(error)")
      }
    }

    return (saved, failed)
  }

  private static func withClientDeviceProvenance(_ artifacts: [ImportEvidenceBatchItem]) -> [ImportEvidenceBatchItem] {
    let deviceId = ClientDeviceService.shared.clientDeviceId
    return artifacts.map { artifact in
      guard artifact.clientDeviceId == nil else { return artifact }
      return ImportEvidenceBatchItem(
        externalId: artifact.externalId,
        occurredAt: artifact.occurredAt,
        title: artifact.title,
        snippet: artifact.snippet,
        content: artifact.content,
        contentHash: artifact.contentHash,
        metadata: artifact.metadata,
        clientDeviceId: deviceId
      )
    }
  }

  private static func createChunkWithRetry(
    _ chunk: [ImportEvidenceBatchItem],
    sourceType: String,
    importRunId: String,
    sourceAccountHash: String?,
    logPrefix: String,
    apiClient: ImportEvidenceBatchCreating,
    sleep: @escaping (UInt64) async -> Void
  ) async throws -> ImportEvidenceBatchResponse {
    var lastError: Error?

    for attempt in 0...retryBackoffSeconds.count {
      do {
        return try await apiClient.createMemoryImportBatch(
          ImportEvidenceBatch(
            sourceType: sourceType,
            importRunId: importRunId,
            sourceAccountHash: sourceAccountHash,
            items: chunk
          )
        )
      } catch {
        lastError = error
        guard shouldRetry(error), attempt < retryBackoffSeconds.count else {
          throw error
        }
        let delay = retryBackoffSeconds[attempt]
        log(
          "\(logPrefix): Retrying import evidence batch after \(delay)s " +
            "(\(chunk.count) items, attempt \(attempt + 2)): \(error)"
        )
        await sleep(delay)
      }
    }

    throw lastError ?? APIError.invalidResponse
  }

  private static func shouldRetry(_ error: Error) -> Bool {
    if case let APIError.httpError(statusCode, _) = error {
      return statusCode == 429 || (500...599).contains(statusCode)
    }

    guard let urlError = error as? URLError else { return false }
    switch urlError.code {
    case .timedOut,
      .cannotFindHost,
      .cannotConnectToHost,
      .dnsLookupFailed,
      .networkConnectionLost,
      .notConnectedToInternet:
      return true
    default:
      return false
    }
  }

  private static func sleepSeconds(_ seconds: UInt64) async {
    try? await Task.sleep(nanoseconds: seconds * 1_000_000_000)
  }

  private static func isLegacyMemorySystemError(_ error: Error) -> Bool {
    guard case let APIError.httpError(statusCode, detail) = error else { return false }
    if statusCode == 403 && detail == "memory_import_requires_canonical" { return true }
    // Deployments without the canonical import router (prod today) 404 this
    // endpoint; without falling back the whole scan context is silently lost.
    return statusCode == 404
  }

  private static func newImportRunId(sourceType: String) -> String {
    let normalizedSource = sourceType
      .lowercased()
      .replacingOccurrences(of: #"[^a-z0-9_:-]+"#, with: "-", options: .regularExpression)
      .trimmingCharacters(in: CharacterSet(charactersIn: "-"))
    return "desktop-\(normalizedSource)-\(UUID().uuidString.lowercased())"
  }
}

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
        log("\(logPrefix): Failed saving legacy memory batch (\(chunk.count) items): \(error)")
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
          "\(logPrefix): Retrying legacy memory batch after \(delay)s " +
            "(\(chunk.count) items, attempt \(attempt + 2)): \(error)"
        )
        await sleep(delay)
      }
    }

    throw lastError ?? APIError.invalidResponse
  }

  private static func shouldRetry(_ error: Error) -> Bool {
    if case let APIError.httpError(statusCode, _) = error {
      return statusCode == 429 || (500...599).contains(statusCode)
    }

    guard let urlError = error as? URLError else { return false }
    switch urlError.code {
    case .timedOut,
      .cannotFindHost,
      .cannotConnectToHost,
      .dnsLookupFailed,
      .networkConnectionLost,
      .notConnectedToInternet:
      return true
    default:
      return false
    }
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
