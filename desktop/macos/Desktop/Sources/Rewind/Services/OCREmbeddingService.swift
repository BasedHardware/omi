import CryptoKit
import Foundation

/// Actor-based service for embedding screenshot OCR text using Gemini embeddings
/// and performing disk-based vector search (no in-memory index).
/// Embeds per-screenshot concatenated OCR text with app context prefix.
/// Uses batched embedding with a 60-second flush window and content-hash
/// deduplication to reduce Gemini API costs (~20x fewer API calls).
actor OCREmbeddingService {
  static let shared = OCREmbeddingService()

  enum SearchError: Error {
    case unavailable
  }

  private let minTextLength = 20

  // MARK: - Batch Embedding Buffer

  /// Pending screenshots waiting to be embedded in the next batch flush
  private struct PendingItem {
    let id: Int64
    let formattedText: String
    let contentHash: String
  }

  private var pendingItems: [PendingItem] = []
  private var flushTask: Task<Void, Never>?

  /// Monotonic owner generation. `reset()` bumps it at the account-transition
  /// boundary; an in-flight `flushPendingEmbeddings()` captures the value it
  /// started under and re-checks it after every `await` before writing, so a
  /// flush that was already mid-flight when the pool retargeted discards its
  /// stale batch instead of writing the previous owner's embeddings into the
  /// next owner's database. Actors are re-entrant, so cancelling `flushTask`
  /// and clearing `pendingItems` alone does not stop a running flush.
  private var ownerGeneration = 0

  /// Content hashes of recently embedded texts to skip duplicates
  private var recentHashes: Set<String> = []
  private let maxRecentHashes = 5000

  /// Flush interval: accumulate screenshots for this long before batch-embedding
  private let flushIntervalNanos: UInt64 = 60_000_000_000  // 60s

  /// Max pending items before force-flushing (Gemini batch limit is 100)
  private let maxPendingItems = 100

  /// Injectable dependencies for the flush path. Production wires these to the
  /// live Gemini embedder and the Rewind database; tests inject a gated embedder
  /// so the owner-reset re-entrancy window can be driven deterministically.
  typealias BatchEmbedder = @Sendable (_ texts: [String], _ taskType: String?) async throws -> [[Float]]
  typealias EmbeddingWriter = @Sendable (_ screenshotId: Int64, _ embedding: Data) async throws -> Void
  private let batchEmbedder: BatchEmbedder
  private let embeddingWriter: EmbeddingWriter

  private init() {
    self.batchEmbedder = { _, _ in [] }
    self.embeddingWriter = { screenshotId, embedding in
      try await RewindDatabase.shared.updateScreenshotEmbedding(id: screenshotId, embedding: embedding)
    }
  }

  /// Test-only initializer that injects the flush path's embedder and writer so
  /// the owner-reset re-entrancy fence can be exercised without live services.
  init(batchEmbedderForTesting: @escaping BatchEmbedder, embeddingWriterForTesting: @escaping EmbeddingWriter) {
    self.batchEmbedder = batchEmbedderForTesting
    self.embeddingWriter = embeddingWriterForTesting
  }

  /// Number of screenshots queued for the next batch flush (test introspection).
  var pendingCount: Int { pendingItems.count }

  /// Drop all owner-bound queued state. Called at the account-transition
  /// boundary: queued items carry the previous owner's DB rowids and OCR
  /// text, and flushing them after the pool retargets would write the
  /// previous owner's embeddings into the next owner's database.
  func reset() {
    ownerGeneration &+= 1
    flushTask?.cancel()
    flushTask = nil
    pendingItems = []
    recentHashes = []
  }

  // MARK: - Text Formatting

  /// Format screenshot text for embedding: prepend app context for better retrieval
  static func formatForEmbedding(ocrText: String, appName: String, windowTitle: String?) -> String {
    var result = "[\(appName)]"
    if let title = windowTitle, !title.isEmpty {
      result += " \(title)"
    }
    result += "\n\(ocrText)"
    return result
  }

  /// Compute a content hash for deduplication
  private static func contentHash(_ text: String) -> String {
    let digest = SHA256.hash(data: Data(text.utf8))
    // Use first 16 bytes (32 hex chars) — enough for dedup
    return digest.prefix(16).map { String(format: "%02x", $0) }.joined()
  }

  // MARK: - Batched Embedding (for new screenshots in pipeline)

  /// Queue a screenshot for batched embedding instead of embedding immediately.
  /// Screenshots are accumulated and flushed every 60 seconds or when the
  /// buffer reaches 100 items, whichever comes first.
  func embedScreenshot(id: Int64, ocrText: String, appName: String, windowTitle: String?) async {
    guard ocrText.count >= minTextLength else { return }

    let formatted = Self.formatForEmbedding(ocrText: ocrText, appName: appName, windowTitle: windowTitle)
    let hash = Self.contentHash(formatted)

    // Skip if we recently embedded identical content
    if recentHashes.contains(hash) {
      return
    }

    pendingItems.append(PendingItem(id: id, formattedText: formatted, contentHash: hash))

    // Force flush if we hit the batch limit
    if pendingItems.count >= maxPendingItems {
      await flushPendingEmbeddings()
    } else {
      startFlushTimerIfNeeded()
    }
  }

  /// Start a timer to flush pending embeddings after the flush interval
  private func startFlushTimerIfNeeded() {
    guard flushTask == nil else { return }
    flushTask = Task {
      try? await Task.sleep(nanoseconds: flushIntervalNanos)
      guard !Task.isCancelled else { return }
      await self.flushPendingEmbeddings()
    }
  }

  /// Flush all pending screenshots: deduplicate, batch-embed, store results
  func flushPendingEmbeddings() async {
    flushTask?.cancel()
    flushTask = nil

    guard !pendingItems.isEmpty else { return }

    // Snapshot the owner generation this flush started under. If `reset()` runs
    // during any await below (actors are re-entrant), the captured value goes
    // stale and we abandon the batch rather than writing the previous owner's
    // embeddings into the next owner's database.
    let generation = ownerGeneration

    // Take the current batch and clear the buffer
    let batch = pendingItems
    pendingItems = []

    // Deduplicate within the batch by content hash
    var seen = Set<String>()
    var uniqueItems: [PendingItem] = []
    var duplicateGroups: [String: [Int64]] = [:]  // hash -> [ids that share this hash]

    for item in batch {
      if seen.insert(item.contentHash).inserted {
        uniqueItems.append(item)
      }
      duplicateGroups[item.contentHash, default: []].append(item.id)
    }

    let skippedCount = batch.count - uniqueItems.count
    if skippedCount > 0 {
      log(
        "OCREmbeddingService: Batch dedup — \(batch.count) items → \(uniqueItems.count) unique (\(skippedCount) duplicates)"
      )
    }

    // Process in chunks of 100 (Gemini batch limit)
    for chunkStart in stride(from: 0, to: uniqueItems.count, by: 100) {
      let chunkEnd = min(chunkStart + 100, uniqueItems.count)
      let chunk = Array(uniqueItems[chunkStart..<chunkEnd])

      let texts = chunk.map { $0.formattedText }
      do {
        let embeddings = try await batchEmbedder(texts, "RETRIEVAL_DOCUMENT")

        // The embed call above suspended; if the owner retargeted while it was
        // in flight, these rowids belong to the previous owner's database.
        // Abandon the rest of the batch instead of cross-writing.
        guard generation == ownerGeneration else {
          log("OCREmbeddingService: Owner changed mid-flush — dropping \(chunk.count) stale items")
          return
        }

        for (i, embedding) in embeddings.enumerated() where i < chunk.count {
          let item = chunk[i]
          let data = await EmbeddingService.shared.floatsToData(embedding)

          // Apply embedding to all IDs that share this content hash
          let allIds = duplicateGroups[item.contentHash] ?? [item.id]
          for screenshotId in allIds {
            try await embeddingWriter(screenshotId, data)
          }

          // Track hash to skip future duplicates
          recentHashes.insert(item.contentHash)
        }

        log(
          "OCREmbeddingService: Batch embedded \(chunk.count) unique items (applied to \(chunk.reduce(0) { $0 + (duplicateGroups[$1.contentHash]?.count ?? 1) }) screenshots)"
        )
      } catch let error as EmbeddingService.EmbeddingError where error.isExpectedBackendState {
        // Expected product-gating/limit (e.g. trial expired, rate limited): drop this
        // batch instead of re-queueing. Re-queueing here tight-loops the 60s flush
        // forever while gated, flooding Sentry; missing screenshots get re-embedded
        // via backfill once the user is un-gated.
        log(
          "OCREmbeddingService: Skipping batch of \(chunk.count) items — backend gating/limit: \(error.localizedDescription)"
        )
      } catch {
        logError("OCREmbeddingService: Batch embed failed for \(chunk.count) items", error: error)
        // Re-queue failed items for next flush — but only if we are still the
        // same owner. Re-queueing across a retarget would seed the next owner's
        // buffer with the previous owner's rowids.
        guard generation == ownerGeneration else {
          log("OCREmbeddingService: Owner changed mid-flush — not re-queueing \(chunk.count) stale items")
          return
        }
        pendingItems.append(contentsOf: chunk)
        startFlushTimerIfNeeded()
      }
    }

    // Evict old hashes if the set grows too large
    if recentHashes.count > maxRecentHashes {
      recentHashes.removeAll()
    }
  }

  // MARK: - Backfill

  func backfillIfNeeded() async {
    return
  }

  // MARK: - Disk-Based Semantic Search

  /// Search for screenshots similar to a query using disk-based vector search.
  /// Reads screenshot embedding BLOBs in batches, computes cosine similarity via vDSP.
  func searchSimilar(
    query: String,
    startDate: Date,
    endDate: Date,
    appFilter: String? = nil,
    topK: Int = 50
  ) async throws -> [(screenshotId: Int64, similarity: Float)] {
    // Flush any pending embeddings before searching so recent screenshots are findable
    await flushPendingEmbeddings()

    throw SearchError.unavailable
  }
}
