import Foundation
import Accelerate

/// Actor-based service for embedding screenshot OCR text using Gemini embeddings
/// and performing disk-based vector search (no in-memory index).
/// Embeds per-screenshot concatenated OCR text with app context prefix.
actor OCREmbeddingService {
    static let shared = OCREmbeddingService()

    private let embeddingDimension = EmbeddingService.embeddingDimension
    private let minTextLength = 20

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

    // MARK: - Single Embedding (for new screenshots in pipeline)

    /// Embed a single screenshot's OCR text and store the result
    func embedScreenshot(id: Int64, ocrText: String, appName: String, windowTitle: String?) async {
        guard ocrText.count >= minTextLength else { return }

        let formatted = Self.formatForEmbedding(ocrText: ocrText, appName: appName, windowTitle: windowTitle)

        do {
            let embedding = try await EmbeddingService.shared.embed(text: formatted, taskType: "RETRIEVAL_DOCUMENT")
            log("OCREmbeddingService: Created embedding for screenshot \(id) with \(embedding.count) dimensions")
            let data = await EmbeddingService.shared.floatsToData(embedding)
            try await RewindDatabase.shared.updateScreenshotEmbedding(id: id, embedding: data)
        } catch {
            logError("OCREmbeddingService: Failed to embed screenshot \(id)", error: error)
        }
    }

    // MARK: - Backfill

    /// Backfill embeddings for existing screenshots that have OCR text but no embedding
    func backfillIfNeeded() async {
        do {
            let status = try await RewindDatabase.shared.getScreenshotEmbeddingBackfillStatus()
            if status.completed {
                log("OCREmbeddingService: Backfill already complete, skipping")
                return
            }

            log("OCREmbeddingService: Starting backfill (previously processed: \(status.processedCount))")

            let batchSize = 100
            var totalProcessed = status.processedCount
            var hitError = false

            while true {
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

                // Update progress every 1000 items
                if totalProcessed % 1000 < batchSize {
                    try await RewindDatabase.shared.updateScreenshotEmbeddingBackfillStatus(completed: false, processedCount: totalProcessed)
                    log("OCREmbeddingService: Backfill progress: \(totalProcessed) items")
                }

                // Rate limiting delay between batches
                try await Task.sleep(nanoseconds: 200_000_000) // 200ms
            }

            // Only mark complete if we finished naturally (no API errors)
            if hitError {
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
