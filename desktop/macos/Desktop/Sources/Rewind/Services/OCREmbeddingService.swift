import Accelerate
import CryptoKit
import Foundation

/// Actor-based service for embedding screenshot OCR text using Gemini embeddings
/// and performing disk-based vector search (no in-memory index).
/// Embeds per-screenshot concatenated OCR text with app context prefix.
/// Uses batched embedding with a 60-second flush window. The lossless sync rollout compacts
/// completed five-minute (app, window) buckets and embeds only their longest OCR row.
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
    let capturedAt: Date
    let appName: String
    let windowTitle: String
    let ocrLength: Int
  }

  private var pendingItems: [PendingItem] = []
  private var flushTask: Task<Void, Never>?
  private var flushTaskGeneration: UInt64 = 0

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
  private var isBackfillRunning = false
  /// Ceiling on the deferred buffer. The old code dropped a gated batch outright, which lost
  /// data; re-queueing it fixes that but reinstates an unbounded buffer for a user whose backend
  /// is gating every call — the buffer grows for as long as the gating lasts. Oldest deferred
  /// items are shed first so the buffer keeps the rows most likely to still be worth embedding.
  private let maxDeferredItems = 2_000

  /// Flush interval: accumulate screenshots for this long before batch-embedding
  private let flushIntervalNanos: UInt64 = 60_000_000_000  // 60s

  /// Max pending items before force-flushing (Gemini batch limit is 100)
  private let maxPendingItems = 100

  /// Injectable dependencies for the flush path. Production wires these to the
  /// live Gemini embedder and the Rewind database; tests inject a gated embedder
  /// so the owner-reset re-entrancy window can be driven deterministically.
  typealias BatchEmbedder = @Sendable (_ texts: [String], _ taskType: String?) async throws -> [[Float]]
  typealias EmbeddingWriter = @Sendable (_ screenshotId: Int64, _ embedding: Data) async throws -> Void
  typealias FlushSleeper = @Sendable (_ nanoseconds: UInt64) async throws -> Void
  private let batchEmbedder: BatchEmbedder
  private let embeddingWriter: EmbeddingWriter
  private let flushSleeper: FlushSleeper
  private let losslessSyncEnabled: @Sendable () async -> Bool
  private let now: @Sendable () -> Date

  private init() {
    self.batchEmbedder = { texts, taskType in
      try await EmbeddingService.shared.embedBatch(texts: texts, taskType: taskType)
    }
    self.embeddingWriter = { screenshotId, embedding in
      try await RewindDatabase.shared.updateScreenshotEmbedding(id: screenshotId, embedding: embedding)
    }
    self.flushSleeper = { nanoseconds in
      try await Task.sleep(nanoseconds: nanoseconds)
    }
    self.losslessSyncEnabled = {
      await MainActor.run { ScreenActivityLosslessSyncFeature.isEnabled }
    }
    self.now = Date.init
  }

  /// Test-only initializer that injects the flush path's embedder, writer, and
  /// optional sleeper so owner and timer races can be driven deterministically.
  init(
    batchEmbedderForTesting: @escaping BatchEmbedder,
    embeddingWriterForTesting: @escaping EmbeddingWriter,
    flushSleeperForTesting: FlushSleeper? = nil,
    losslessSyncEnabledForTesting: @escaping @Sendable () async -> Bool = { false },
    nowForTesting: @escaping @Sendable () -> Date = Date.init
  ) {
    self.batchEmbedder = batchEmbedderForTesting
    self.embeddingWriter = embeddingWriterForTesting
    self.flushSleeper =
      flushSleeperForTesting ?? { nanoseconds in
        try await Task.sleep(nanoseconds: nanoseconds)
      }
    self.losslessSyncEnabled = losslessSyncEnabledForTesting
    self.now = nowForTesting
  }

  /// Number of screenshots queued for the next batch flush (test introspection).
  var pendingCount: Int { pendingItems.count }

  /// Drop all owner-bound queued state. Called at the account-transition
  /// boundary: queued items carry the previous owner's DB rowids and OCR
  /// text, and flushing them after the pool retargets would write the
  /// previous owner's embeddings into the next owner's database.
  func reset() {
    ownerGeneration &+= 1
    cancelScheduledFlush()
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
  func embedScreenshot(
    id: Int64,
    timestamp: Date = Date(),
    ocrText: String,
    appName: String,
    windowTitle: String?,
    ownerSnapshot suppliedOwnerSnapshot: RewindCaptureOwnerSnapshot? = nil
  ) async {
    guard ocrText.count >= minTextLength else { return }
    guard let ownerSnapshot = suppliedOwnerSnapshot ?? RewindCaptureOwnerSnapshot.capture(),
      ownerSnapshot.isCurrent()
    else { return }

    let formatted = Self.formatForEmbedding(ocrText: ocrText, appName: appName, windowTitle: windowTitle)
    let hash = Self.contentHash(formatted)
    let usesLosslessCompaction = await losslessSyncEnabled()

    // The flag-off path preserves the old rollback behavior. Lossless mode never drops a row
    // because a prior batch happened to contain the same text.
    if !usesLosslessCompaction, recentHashes.contains(hash) {
      return
    }

    pendingItems.append(
      PendingItem(
        id: id,
        formattedText: formatted,
        contentHash: hash,
        capturedAt: timestamp,
        appName: appName,
        windowTitle: windowTitle ?? "",
        ocrLength: ocrText.count))

    // Force flush if we hit the batch limit
    if pendingItems.count >= maxPendingItems {
      await flushPendingEmbeddings()
    } else {
      startFlushTimerIfNeeded()
    }
  }

  /// Start a timer to flush pending embeddings after the flush interval
  private func startFlushTimerIfNeeded() {
    guard flushTask == nil, !pendingItems.isEmpty else { return }

    flushTaskGeneration &+= 1
    let generation = flushTaskGeneration
    let sleeper = flushSleeper
    let interval = flushIntervalNanos
    flushTask = Task { [weak self] in
      do {
        try await sleeper(interval)
      } catch {
        return
      }
      guard !Task.isCancelled else { return }
      await self?.runScheduledFlush(generation: generation)
    }
  }

  /// Cancel a scheduled or in-flight timer-owned flush. Bumping the generation
  /// prevents an old timer from clearing or replacing a newer timer after an
  /// actor re-entrancy hop.
  private func cancelScheduledFlush() {
    flushTaskGeneration &+= 1
    flushTask?.cancel()
    flushTask = nil
  }

  /// A timer-owned flush must keep its task registered while embedding so an
  /// external reset or explicit flush can still cancel it. It must not call the
  /// public entry point, because that would cancel the currently running task.
  private func runScheduledFlush(generation: UInt64) async {
    guard generation == flushTaskGeneration else { return }

    await performFlushPendingEmbeddings()

    guard generation == flushTaskGeneration else {
      // An external cancellation can race with the embed await. If the
      // cancelled embed re-queued its batch, make sure a replacement timer owns
      // it; reset() has already emptied the queue, so this is a no-op there.
      startFlushTimerIfNeeded()
      return
    }

    flushTask = nil
    startFlushTimerIfNeeded()
  }

  /// Explicitly flush all pending screenshots, cancelling any timer that owns
  /// the same queue first.
  func flushPendingEmbeddings() async {
    cancelScheduledFlush()
    await performFlushPendingEmbeddings()
    startFlushTimerIfNeeded()
  }

  /// Flush all pending screenshots: deduplicate, batch-embed, store results.
  private func performFlushPendingEmbeddings() async {
    guard !pendingItems.isEmpty,
      let ownerSnapshot = RewindCaptureOwnerSnapshot.capture(),
      ownerSnapshot.isCurrent()
    else { return }

    // Snapshot the owner generation this flush started under. If `reset()` runs
    // during any await below (actors are re-entrant), the captured value goes
    // stale and we abandon the batch rather than writing the previous owner's
    // embeddings into the next owner's database.
    let generation = ownerGeneration

    // Take the current batch and clear the buffer
    let batch = pendingItems
    pendingItems = []

    let usesLosslessCompaction = await losslessSyncEnabled()

    // Keep an open bucket buffered until its five-minute interval has closed. This makes the
    // longest-row decision stable without delaying capture or OCR.
    let itemsToProcess: [PendingItem]
    if usesLosslessCompaction {
      // Eligibility is per *bucket*, not per row: holding back only the rows younger than the
      // slack would rank an already-open bucket, embedding one winner now and another once its
      // later rows age in. Same alignment as ScreenActivitySyncService.bucketEligibilityCutoffEpoch.
      let cutoffEpoch = Int64((now().timeIntervalSince1970 - 5 * 60).rounded(.down))
      let isReady: (PendingItem) -> Bool = { (Self.bucketIndex(for: $0.capturedAt) + 1) * 300 <= cutoffEpoch }
      let ready = batch.filter(isReady)
      pendingItems.append(contentsOf: batch.filter { !isReady($0) })
      itemsToProcess = Self.compactByFiveMinuteBucket(ready)
    } else {
      itemsToProcess = batch
    }

    // Legacy rollback path: deduplicate within the batch by content hash.
    var seen = Set<String>()
    var uniqueItems: [PendingItem] = []
    var duplicateGroups: [String: [Int64]] = [:]  // hash -> [ids that share this hash]

    for item in itemsToProcess {
      if usesLosslessCompaction || seen.insert(item.contentHash).inserted {
        uniqueItems.append(item)
      }
      duplicateGroups[item.contentHash, default: []].append(item.id)
    }

    let skippedCount = itemsToProcess.count - uniqueItems.count
    if skippedCount > 0 {
      log(
        "OCREmbeddingService: Batch dedup — \(itemsToProcess.count) items → \(uniqueItems.count) unique (\(skippedCount) duplicates)"
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
        guard generation == ownerGeneration, ownerSnapshot.isCurrent() else {
          log("OCREmbeddingService: Owner changed mid-flush — dropping \(chunk.count) stale items")
          return
        }

        guard embeddings.count == chunk.count else {
          log(
            "OCREmbeddingService: Embedding count mismatch (requested=\(chunk.count), received=\(embeddings.count)); deferring batch"
          )
          pendingItems.append(contentsOf: chunk)
          continue
        }

        for (i, embedding) in embeddings.enumerated() where i < chunk.count {
          let item = chunk[i]
          let data = await EmbeddingService.shared.floatsToData(embedding)

          // Apply embedding to all IDs that share this content hash
          let allIds = usesLosslessCompaction ? [item.id] : (duplicateGroups[item.contentHash] ?? [item.id])
          for screenshotId in allIds {
            let authorization = LocalMutationAuthorization { ownerSnapshot.isCurrent() }
            try await authorization.withCommitLease {
              try await self.embeddingWriter(screenshotId, data)
            }
            guard generation == ownerGeneration, ownerSnapshot.isCurrent() else {
              log("OCREmbeddingService: Owner changed during writes — dropping stale batch")
              return
            }
          }

          if !usesLosslessCompaction {
            recentHashes.insert(item.contentHash)
          }
        }

        log(
          "OCREmbeddingService: Batch embedded \(chunk.count) unique items (applied to \(chunk.reduce(0) { $0 + (duplicateGroups[$1.contentHash]?.count ?? 1) }) screenshots)"
        )
      } catch let error as EmbeddingService.EmbeddingError where error.isExpectedBackendState {
        log(
          "OCREmbeddingService: Deferring batch of \(chunk.count) items — backend gating/limit: \(error.localizedDescription)"
        )
        guard generation == ownerGeneration else { return }
        deferItems(chunk)
      } catch {
        logError("OCREmbeddingService: Batch embed failed for \(chunk.count) items", error: error)
        // Re-queue failed items for next flush — but only if we are still the
        // same owner. Re-queueing across a retarget would seed the next owner's
        // buffer with the previous owner's rowids.
        guard generation == ownerGeneration else {
          log("OCREmbeddingService: Owner changed mid-flush — not re-queueing \(chunk.count) stale items")
          return
        }
        deferItems(chunk)
      }
    }

    // Evict old hashes if the set grows too large
    if recentHashes.count > maxRecentHashes {
      recentHashes.removeAll()
    }
  }

  static func bucketIndex(for date: Date) -> Int64 {
    Int64(date.timeIntervalSince1970.rounded(.down)) / 300
  }

  /// Re-queue a batch that could not be embedded, keeping the buffer bounded.
  private func deferItems(_ chunk: [PendingItem]) {
    pendingItems.append(contentsOf: chunk)
    guard pendingItems.count > maxDeferredItems else { return }
    let shed = pendingItems.count - maxDeferredItems
    pendingItems.removeFirst(shed)
    log("OCREmbeddingService: Deferred buffer at capacity — shed \(shed) oldest items")
  }

  private static func compactByFiveMinuteBucket(_ items: [PendingItem]) -> [PendingItem] {
    var winners: [String: PendingItem] = [:]
    for item in items {
      let bucket = bucketIndex(for: item.capturedAt)
      let key = "\(item.appName)\u{1f}\(item.windowTitle)\u{1f}\(bucket)"
      guard let current = winners[key] else {
        winners[key] = item
        continue
      }
      if item.ocrLength > current.ocrLength || (item.ocrLength == current.ocrLength && item.id > current.id) {
        winners[key] = item
      }
    }
    return winners.values.sorted { $0.id < $1.id }
  }

  // MARK: - Backfill

  /// Backfill embeddings for existing screenshots that have OCR text but no embedding.
  /// Lossless mode is capped at 500 compacted winners per launch; the flag-off legacy path keeps
  /// its existing 5000-row cap.
  func backfillIfNeeded() async {
    guard !isBackfillRunning else { return }
    isBackfillRunning = true
    defer { isBackfillRunning = false }

    guard let ownerSnapshot = RewindCaptureOwnerSnapshot.capture(),
      ownerSnapshot.isCurrent()
    else { return }
    let authorization = LocalMutationAuthorization { ownerSnapshot.isCurrent() }
    do {
      let usesLosslessCompaction = await losslessSyncEnabled()
      var status = try await RewindDatabase.shared.getScreenshotEmbeddingBackfillStatus()
      guard ownerSnapshot.isCurrent() else { return }
      if usesLosslessCompaction, status.completed {
        let rearmed = try await RewindDatabase.shared.rearmScreenshotEmbeddingBackfillIfNeeded(
          olderThan: now().addingTimeInterval(-5 * 60))
        if rearmed {
          status = (completed: false, processedCount: 0)
          log("OCREmbeddingService: Re-armed incomplete screenshot embedding backfill")
        }
      }
      if status.completed {
        log("OCREmbeddingService: Backfill already complete, skipping")
        return
      }

      log("OCREmbeddingService: Starting backfill (previously processed: \(status.processedCount))")

      let batchSize = 100
      let maxItemsPerLaunch = usesLosslessCompaction ? 500 : 5000
      var totalProcessed = status.processedCount
      var processedThisLaunch = 0
      var hitError = false

      while processedThisLaunch < maxItemsPerLaunch {
        let items =
          usesLosslessCompaction
          ? try await RewindDatabase.shared.getCompactedScreenshotsMissingEmbeddings(
            limit: batchSize, olderThan: now().addingTimeInterval(-5 * 60))
          : try await RewindDatabase.shared.getScreenshotsMissingEmbeddings(limit: batchSize)
        guard ownerSnapshot.isCurrent() else { return }
        if items.isEmpty { break }

        let itemsToProcess = items

        let texts = itemsToProcess.map {
          Self.formatForEmbedding(ocrText: $0.ocrText, appName: $0.appName, windowTitle: $0.windowTitle)
        }
        let embeddings: [[Float]]
        do {
          embeddings = try await EmbeddingService.shared.embedBatch(texts: texts, taskType: "RETRIEVAL_DOCUMENT")
          guard ownerSnapshot.isCurrent() else { return }
        } catch let error as EmbeddingService.EmbeddingError where error.isExpectedBackendState {
          log(
            "OCREmbeddingService: Backfill paused at \(totalProcessed) items — backend gating/limit: \(error.localizedDescription)"
          )
          hitError = true
          break
        } catch {
          logError(
            "OCREmbeddingService: Batch embed failed at \(totalProcessed) items, will retry on next launch",
            error: error)
          hitError = true
          break
        }

        guard embeddings.count == itemsToProcess.count else {
          log(
            "OCREmbeddingService: Backfill embedding count mismatch (requested=\(itemsToProcess.count), received=\(embeddings.count)); will retry on next launch"
          )
          hitError = true
          break
        }

        for (i, embedding) in embeddings.enumerated() where i < itemsToProcess.count {
          let item = itemsToProcess[i]
          let data = await EmbeddingService.shared.floatsToData(embedding)
          try await authorization.withCommitLease {
            try await RewindDatabase.shared.updateScreenshotEmbedding(
              id: item.id, embedding: data)
          }
        }

        totalProcessed += itemsToProcess.count
        processedThisLaunch += itemsToProcess.count

        // Update progress every 1000 items
        if totalProcessed % 1000 < batchSize {
          let progressCount = totalProcessed
          try await authorization.withCommitLease {
            try await RewindDatabase.shared.updateScreenshotEmbeddingBackfillStatus(
              completed: false, processedCount: progressCount)
          }
          log(
            "OCREmbeddingService: Backfill progress: \(totalProcessed) items (\(processedThisLaunch)/\(maxItemsPerLaunch) this launch)"
          )
        }

        // Rate limiting delay between batches
        try await Task.sleep(nanoseconds: 200_000_000)  // 200ms
      }

      let finalProcessedCount = totalProcessed
      if processedThisLaunch >= maxItemsPerLaunch {
        try await authorization.withCommitLease {
          try await RewindDatabase.shared.updateScreenshotEmbeddingBackfillStatus(
            completed: false, processedCount: finalProcessedCount)
        }
        log(
          "OCREmbeddingService: Backfill paused at \(totalProcessed) items (cap of \(maxItemsPerLaunch)/launch reached), will continue on next launch"
        )
      } else if hitError {
        try await authorization.withCommitLease {
          try await RewindDatabase.shared.updateScreenshotEmbeddingBackfillStatus(
            completed: false, processedCount: finalProcessedCount)
        }
        log("OCREmbeddingService: Backfill paused at \(totalProcessed) items due to error, will resume on next launch")
      } else {
        try await authorization.withCommitLease {
          try await RewindDatabase.shared.updateScreenshotEmbeddingBackfillStatus(
            completed: true, processedCount: finalProcessedCount)
        }
        log("OCREmbeddingService: Backfill complete — \(totalProcessed) items embedded")
      }

    } catch let error as EmbeddingService.EmbeddingError where error.isExpectedBackendState {
      log("OCREmbeddingService: Backfill stopped — backend gating/limit: \(error.localizedDescription)")
    } catch {
      logError("OCREmbeddingService: Backfill failed", error: error)
    }
  }

  // MARK: - Disk-Based Semantic Search

  /// Search for screenshots similar to a query using disk-based vector search.
  /// Reads screenshot embedding BLOBs in batches, computes cosine similarity via vDSP.
  /// How many stored embeddings one semantic search will compare against.
  ///
  /// The comparison is a linear scan — every blob is read and dotted with the query — so the cost
  /// of an unbounded range is the size of the capture history, which is now allowed to be
  /// unlimited. At 768 dimensions a blob is ~3 KB, so this budget is roughly 60 MB read and 20,000
  /// dot products: milliseconds of work and bounded memory, regardless of how many months the user
  /// has kept. `readEmbeddingBatch` returns newest-first, so spending the budget means comparing
  /// against the most recent frames rather than an arbitrary slice.
  static let defaultEmbeddingScanBudget = 20_000

  func searchSimilar(
    query: String,
    startDate: Date? = nil,
    endDate: Date? = nil,
    appFilter: String? = nil,
    topK: Int = 50,
    maxScannedEmbeddings: Int = defaultEmbeddingScanBudget
  ) async throws -> [(screenshotId: Int64, similarity: Float)] {
    guard let ownerSnapshot = RewindCaptureOwnerSnapshot.capture(),
      ownerSnapshot.isCurrent()
    else { throw LocalMutationAuthorizationError.revoked }
    // Flush any pending embeddings before searching so recent screenshots are findable
    await flushPendingEmbeddings()
    guard ownerSnapshot.isCurrent() else { throw LocalMutationAuthorizationError.revoked }

    // Embed the query with RETRIEVAL_QUERY task type for asymmetric search
    let queryEmbedding = try await EmbeddingService.shared.embed(text: query, taskType: "RETRIEVAL_QUERY")
    guard ownerSnapshot.isCurrent() else { throw LocalMutationAuthorizationError.revoked }

    let batchSize = 5000
    var offset = 0
    var scanned = 0
    var topResults: [(screenshotId: Int64, similarity: Float)] = []

    while scanned < maxScannedEmbeddings {
      let batch = try await RewindDatabase.shared.readEmbeddingBatch(
        startDate: startDate,
        endDate: endDate,
        appFilter: appFilter,
        limit: min(batchSize, maxScannedEmbeddings - scanned),
        offset: offset
      )
      guard ownerSnapshot.isCurrent() else { throw LocalMutationAuthorizationError.revoked }

      if batch.isEmpty { break }
      scanned += batch.count

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

      offset += batch.count
    }

    // Final sort and trim
    guard ownerSnapshot.isCurrent() else { throw LocalMutationAuthorizationError.revoked }
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
