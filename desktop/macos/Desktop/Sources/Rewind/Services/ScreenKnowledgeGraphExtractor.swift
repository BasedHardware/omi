import CryptoKit
import Foundation

/// Extracts entity nodes and edges from screenshot OCR text into `local_kg_*`.
///
/// Runs asynchronously after Rewind capture. Uses OCR text only — never images.
/// Prefers on-device Foundation Models when available; falls back to Gemini proxy.
actor ScreenKnowledgeGraphExtractor {
  static let shared = ScreenKnowledgeGraphExtractor()

  private struct PendingItem {
    let id: Int64
    let input: ScreenKGExtractionInput
    let contentHash: String
  }

  private let minTextLength = 20
  private let flushIntervalNanos: UInt64 = 60_000_000_000
  private let maxPendingItems = 20
  private let maxItemsPerFlush = 5
  private let backfillBatchSize = 50
  private let maxBackfillItemsPerLaunch = 5_000

  private var pendingItems: [PendingItem] = []
  private var flushTask: Task<Void, Never>?
  private var ownerGeneration = 0
  private var recentHashes: Set<String> = []
  private let maxRecentHashes = 2_000
  private var backfillScheduled = false
  private var pausedForProductGate = false

  typealias ExtractionBackend = @Sendable (ScreenKGExtractionInput) async throws -> String
  typealias KGMarkedWriter = @Sendable (_ ids: [Int64]) async throws -> Void
  typealias PendingFetcher =
    @Sendable (_ limit: Int) async throws -> [(
      id: Int64, ocrText: String, appName: String, windowTitle: String?
    )]

  private let extractEntities: ExtractionBackend
  private let markExtracted: KGMarkedWriter
  private let fetchPending: PendingFetcher

  private init() {
    self.extractEntities = { input in
      let backend = ScreenKGExtractionBackendSelector.preferredBackend()
      return try await backend.extractEntities(from: input)
    }
    self.markExtracted = { ids in
      try await RewindDatabase.shared.markScreenshotsKGExtracted(ids: ids)
    }
    self.fetchPending = { limit in
      try await RewindDatabase.shared.getScreenshotsPendingKGExtraction(limit: limit)
    }
  }

  init(
    extractEntitiesForTesting: @escaping ExtractionBackend,
    markExtractedForTesting: @escaping KGMarkedWriter,
    fetchPendingForTesting: PendingFetcher? = nil
  ) {
    self.extractEntities = extractEntitiesForTesting
    self.markExtracted = markExtractedForTesting
    self.fetchPending =
      fetchPendingForTesting ?? { limit in
        try await RewindDatabase.shared.getScreenshotsPendingKGExtraction(limit: limit)
      }
  }

  var pendingCount: Int { pendingItems.count }

  func reset() {
    ownerGeneration &+= 1
    flushTask?.cancel()
    flushTask = nil
    pendingItems = []
    recentHashes = []
    backfillScheduled = false
    pausedForProductGate = false
  }

  /// Queue a newly captured screenshot for extraction.
  func queueScreenshot(id: Int64, ocrText: String, appName: String, windowTitle: String?) async {
    guard !pausedForProductGate else { return }
    guard ocrText.count >= minTextLength else { return }

    let input = Self.makeInput(ocrText: ocrText, appName: appName, windowTitle: windowTitle)
    let hash = Self.contentHash(ocrText: ocrText, appName: appName, windowTitle: windowTitle)

    if recentHashes.contains(hash) {
      try? await markExtracted([id])
      return
    }

    pendingItems.append(PendingItem(id: id, input: input, contentHash: hash))

    if pendingItems.count >= maxPendingItems {
      await flushPendingExtractions()
    } else {
      startFlushTimerIfNeeded()
    }
  }

  /// Backfill screenshots captured before the extractor shipped (capped per launch).
  func scheduleBackfillIfNeeded() async {
    guard !backfillScheduled else { return }
    backfillScheduled = true
    await runBackfillBatch()
  }

  func flushPendingExtractions() async {
    flushTask?.cancel()
    flushTask = nil
    guard !pendingItems.isEmpty else { return }
    guard !pausedForProductGate else {
      pendingItems.removeAll()
      return
    }

    let generation = ownerGeneration
    let batch = Array(pendingItems.prefix(maxItemsPerFlush))
    pendingItems.removeFirst(min(maxItemsPerFlush, pendingItems.count))

    for item in batch {
      guard generation == ownerGeneration else {
        return
      }
      guard !pausedForProductGate else {
        return
      }
      await processItem(item, generation: generation)
    }

    if !pendingItems.isEmpty && !pausedForProductGate {
      startFlushTimerIfNeeded()
    }
  }

  // MARK: - Formatting

  static func makeInput(ocrText: String, appName: String, windowTitle: String?) -> ScreenKGExtractionInput {
    let truncated =
      ocrText.count > 6_000 ? String(ocrText.prefix(6_000)) + "…" : ocrText
    return ScreenKGExtractionInput(ocrText: truncated, appName: appName, windowTitle: windowTitle)
  }

  static func contentHash(ocrText: String, appName: String, windowTitle: String?) -> String {
    let key = "[\(appName)]\(windowTitle ?? "")\n\(ocrText)"
    let digest = SHA256.hash(data: Data(key.utf8))
    return digest.prefix(16).map { String(format: "%02x", $0) }.joined()
  }

  static func contentHash(_ input: ScreenKGExtractionInput) -> String {
    contentHash(ocrText: input.ocrText, appName: input.appName, windowTitle: input.windowTitle)
  }

  // MARK: - Private

  private func startFlushTimerIfNeeded() {
    guard flushTask == nil else { return }
    guard !pausedForProductGate else { return }
    flushTask = Task {
      try? await Task.sleep(nanoseconds: flushIntervalNanos)
      guard !Task.isCancelled else { return }
      await self.flushPendingExtractions()
    }
  }

  private func runBackfillBatch() async {
    var processedThisLaunch = 0

    do {
      while processedThisLaunch < maxBackfillItemsPerLaunch {
        if pausedForProductGate { break }

        let rows = try await fetchPending(backfillBatchSize)
        if rows.isEmpty { break }

        for row in rows {
          await queueScreenshot(
            id: row.id, ocrText: row.ocrText, appName: row.appName, windowTitle: row.windowTitle)
        }

        while !pendingItems.isEmpty {
          if pausedForProductGate { break }
          let before = pendingItems.count
          await flushPendingExtractions()
          if pendingItems.count >= before { break }
        }

        if pausedForProductGate { break }

        processedThisLaunch += rows.count
        if processedThisLaunch < maxBackfillItemsPerLaunch {
          try? await Task.sleep(nanoseconds: 200_000_000)
        }
      }
    } catch {
      log("ScreenKnowledgeGraphExtractor: backfill fetch failed: \(error.localizedDescription)")
    }
  }

  private func processItem(_ item: PendingItem, generation: Int) async {
    do {
      let jsonText = try await extractEntities(item.input)
      guard generation == ownerGeneration else { return }

      guard let parsed = KnowledgeGraphRecordBuilder.parseExtractionJSON(jsonText) else {
        log(
          "ScreenKnowledgeGraphExtractor: invalid extraction JSON for screenshot \(item.id) — will retry"
        )
        pendingItems.append(item)
        return
      }

      let records = KnowledgeGraphRecordBuilder.buildRecords(nodes: parsed.nodes, edges: parsed.edges)
      if !records.nodes.isEmpty || !records.edges.isEmpty {
        try await mergeGraph(nodes: records.nodes, edges: records.edges)
      }

      guard generation == ownerGeneration else { return }
      recentHashes.insert(item.contentHash)
      if recentHashes.count > maxRecentHashes {
        recentHashes.removeAll(keepingCapacity: true)
      }
      try await markExtracted([item.id])
      log(
        "ScreenKnowledgeGraphExtractor: extracted from screenshot \(item.id) via \(backendName())")
    } catch {
      guard generation == ownerGeneration else { return }
      if let geminiError = error as? GeminiClient.GeminiClientError, geminiError.isExpectedProductState {
        pausedForProductGate = true
        pendingItems.removeAll()
        log(
          "ScreenKnowledgeGraphExtractor: pausing — expected product state for screenshot \(item.id): \(error.localizedDescription)"
        )
        return
      }
      log("ScreenKnowledgeGraphExtractor: extraction failed for screenshot \(item.id): \(error.localizedDescription)")
      pendingItems.append(item)
    }
  }

  private func mergeGraph(nodes: [LocalKGNodeRecord], edges: [LocalKGEdgeRecord]) async throws {
    guard RuntimeOwnerIdentity.currentOwnerId() != nil,
      !RuntimeOwnerIdentity.effectiveOwnerTransitionInProgress
    else {
      throw LocalMutationAuthorizationError.revoked
    }

    try await KnowledgeGraphStorage.shared.mergeGraph(
      nodes: nodes,
      edges: edges,
      authorization: LocalMutationAuthorization {
        RuntimeOwnerIdentity.currentOwnerId() != nil
          && !RuntimeOwnerIdentity.effectiveOwnerTransitionInProgress
      })
  }

  private func backendName() -> String {
    ScreenKGExtractionBackendSelector.preferredBackend().name
  }
}
