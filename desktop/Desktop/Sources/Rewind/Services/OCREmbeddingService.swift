import Foundation
import Accelerate
import CryptoKit

/// Actor-based service for embedding screenshot OCR text using Gemini embeddings
/// and performing disk-based vector search (no in-memory index).
/// Embeds per-screenshot concatenated OCR text with app context prefix.
/// Uses batched embedding with a 60-second flush window and content-hash
/// deduplication to reduce Gemini API costs (~20x fewer API calls).
actor OCREmbeddingService {
    static let shared = OCREmbeddingService()

    private let embeddingDimension = EmbeddingService.embeddingDimension
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

    /// Content hashes of recently embedded texts to skip duplicates
    private var recentHashes: Set<String> = []
    private let maxRecentHashes = 5000

    /// Flush interval: accumulate screenshots for this long before batch-embedding
    private let flushIntervalNanos: UInt64 = 60_000_000_000 // 60s

    /// Max pending items before force-flushing (Gemini batch limit is 100)
    private let maxPendingItems = 100

    private init() {}

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

        // Take the current batch and clear the buffer
        let batch = pendingItems
        pendingItems = []

        // Deduplicate within the batch by content hash
        var seen = Set<String>()
        var uniqueItems: [PendingItem] = []
        var duplicateGroups: [String: [Int64]] = [:] // hash -> [ids that share this hash]

        for item in batch {
            if seen.insert(item.contentHash).inserted {
                uniqueItems.append(item)
            }
            duplicateGroups[item.contentHash, default: []].append(item.id)
        }

        let skippedCount = batch.count - uniqueItems.count
        if skippedCount > 0 {
            log("OCREmbeddingService: Batch dedup — \(batch.count) items → \(uniqueItems.count) unique (\(skippedCount) duplicates)")
        }

        // Process in chunks of 100 (Gemini batch limit)
        for chunkStart in stride(from: 0, to: uniqueItems.count, by: 100) {
            let chunkEnd = min(chunkStart + 100, uniqueItems.count)
            let chunk = Array(uniqueItems[chunkStart..<chunkEnd])

            let texts = chunk.map { $0.formattedText }
            do {
                let embeddings = try await EmbeddingService.shared.embedBatch(texts: texts, taskType: "RETRIEVAL_DOCUMENT")

                for (i, embedding) in embeddings.enumerated() where i < chunk.count {
                    let item = chunk[i]
                    let data = await EmbeddingService.shared.floatsToData(embedding)

                    // Apply embedding to all IDs that share this content hash
                    let allIds = duplicateGroups[item.contentHash] ?? [item.id]
                    for screenshotId in allIds {
                        try await RewindDatabase.shared.updateScreenshotEmbedding(id: screenshotId, embedding: data)
                    }

                    // Track hash to skip future duplicates
                    recentHashes.insert(item.contentHash)
                }

                log("OCREmbeddingService: Batch embedded \(chunk.count) unique items (applied to \(chunk.reduce(0) { $0 + (duplicateGroups[$1.contentHash]?.count ?? 1) }) screenshots)")
            } catch {
                logError("OCREmbeddingService: Batch embed failed for \(chunk.count) items", error: error)
                // Re-queue failed items for next flush
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

    /// Backfill embeddings for existing screenshots that have OCR text but no embedding.
    /// Capped at 5000 items per launch to prevent cost spikes.
    func backfillIfNeeded() async {
        do {
            let status = try await RewindDatabase.shared.getScreenshotEmbeddingBackfillStatus()
            if status.completed {
                log("OCREmbeddingService: Backfill already complete, skipping")
                return
            }

            log("OCREmbeddingService: Starting backfill (previously processed: \(status.processedCount))")

            let batchSize = 100
            let maxItemsPerLaunch = 5000
            var totalProcessed = status.processedCount
            var processedThisLaunch = 0
            var hitError = false

            while processedThisLaunch < maxItemsPerLaunch {
                let items = try await RewindDatabase.shared.getScreenshotsMissingEmbeddings(limit: batchSize)
                if items.isEmpty { break }

                let itemsToProcess = items

                let texts = itemsToProcess.map { Self.formatForEmbedding(ocrText: $0.ocrText, appName: $0.appName, windowTitle: $0.windowTitle) }
                let embeddings: [[Float]]
                do {
                    embeddings = try await EmbeddingService.shared.embedBatch(texts: texts, taskType: "RETRIEVAL_DOCUMENT")
                } catch {
                    logError("OCREmbeddingService: Batch embed failed at \(totalProcessed) items, will retry on next launch", error: error)
                    hitError = true
                    break
                }

                for (i, embedding) in embeddings.enumerated() where i < itemsToProcess.count {
                    let item = itemsToProcess[i]
                    let data = await EmbeddingService.shared.floatsToData(embedding)
                    try await RewindDatabase.shared.updateScreenshotEmbedding(id: item.id, embedding: data)
                }

                totalProcessed += itemsToProcess.count
                processedThisLaunch += itemsToProcess.count

                // Update progress every 1000 items
                if totalProcessed % 1000 < batchSize {
                    try await RewindDatabase.shared.updateScreenshotEmbeddingBackfillStatus(completed: false, processedCount: totalProcessed)
                    log("OCREmbeddingService: Backfill progress: \(totalProcessed) items (\(processedThisLaunch)/\(maxItemsPerLaunch) this launch)")
                }

                // Rate limiting delay between batches
                try await Task.sleep(nanoseconds: 200_000_000) // 200ms
            }

            if processedThisLaunch >= maxItemsPerLaunch {
                try await RewindDatabase.shared.updateScreenshotEmbeddingBackfillStatus(completed: false, processedCount: totalProcessed)
                log("OCREmbeddingService: Backfill paused at \(totalProcessed) items (cap of \(maxItemsPerLaunch)/launch reached), will continue on next launch")
            } else if hitError {
                try await RewindDatabase.shared.updateScreenshotEmbeddingBackfillStatus(completed: false, processedCount: totalProcessed)
                log("OCREmbeddingService: Backfill paused at \(totalProcessed) items due to error, will resume on next launch")
            } else {
                try await RewindDatabase.shared.updateScreenshotEmbeddingBackfillStatus(completed: true, processedCount: totalProcessed)
                log("OCREmbeddingService: Backfill complete — \(totalProcessed) items embedded")
            }

        } catch {
            logError("OCREmbeddingService: Backfill failed", error: error)
        }
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

        // Embed the query with RETRIEVAL_QUERY task type for asymmetric search
        let queryEmbedding = try await EmbeddingService.shared.embed(text: query, taskType: "RETRIEVAL_QUERY")

        let batchSize = 5000
        var offset = 0
        var topResults: [(screenshotId: Int64, similarity: Float)] = []

        while true {
            let batch = try await RewindDatabase.shared.readEmbeddingBatch(
                startDate: startDate,
                endDate: endDate,
                appFilter: appFilter,
                limit: batchSize,
                offset: offset
            )

            if batch.isEmpty { break }

            for (screenshotId, embeddingData) in batch {
                guard let storedEmbedding = dataToFloats(embeddingData) else { continue }
                let sim = cosineSimilarity(queryEmbedding, storedEmbedding)
                topResults.append((screenshotId: screenshotId, similarity: sim))
            }

            // Compact top results periodically to keep memory bounded
            if topResults.count > topK * 2 {
                topResults.sort { $0.similarity > $1.similarity }
                topResults = Array(topResults.prefix(topK))
            }

            offset += batchSize
        }

        // Final sort and trim
        topResults.sort { $0.similarity > $1.similarity }
        return Array(topResults.prefix(topK))
    }

    // MARK: - Helpers

    /// Cosine similarity using Accelerate vDSP
    private func cosineSimilarity(_ a: [Float], _ b: [Float]) -> Float {
        guard a.count == b.count, !a.isEmpty else { return 0 }
        var dot: Float = 0
        vDSP_dotpr(a, 1, b, 1, &dot, vDSP_Length(a.count))
        // Vectors are pre-normalized, so dot product = cosine similarity
        return dot
    }

    /// Convert Data (BLOB) back to [Float]
    private func dataToFloats(_ data: Data) -> [Float]? {
        guard data.count == embeddingDimension * MemoryLayout<Float>.size else { return nil }
        return data.withUnsafeBytes { raw in
            Array(raw.bindMemory(to: Float.self))
        }
    }
}
