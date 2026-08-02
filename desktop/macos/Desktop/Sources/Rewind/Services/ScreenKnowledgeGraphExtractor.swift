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

  private var pendingItems: [PendingItem] = []
  private var flushTask: Task<Void, Never>?
  private var ownerGeneration = 0
  private var recentHashes: Set<String> = []
  private let maxRecentHashes = 2_000
  private var backfillScheduled = false

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
  }

  /// Queue a newly captured screenshot for extraction.
  func queueScreenshot(id: Int64, ocrText: String, appName: String, windowTitle: String?) async {
    guard ocrText.count >= minTextLength else { return }

    let input = Self.makeInput(ocrText: ocrText, appName: appName, windowTitle: windowTitle)
    let hash = Self.contentHash(input)

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

  /// One-shot backfill for screenshots captured before the extractor shipped.
  func scheduleBackfillIfNeeded() {
    guard !backfillScheduled else { return }
    backfillScheduled = true
    Task(priority: .utility) {
      await self.runBackfillBatch()
    }
  }

  func flushPendingExtractions() async {
    flushTask?.cancel()
    flushTask = nil
    guard !pendingItems.isEmpty else { return }

    let generation = ownerGeneration
    let batch = Array(pendingItems.prefix(maxItemsPerFlush))
    pendingItems.removeFirst(min(maxItemsPerFlush, pendingItems.count))

    for item in batch {
      guard generation == ownerGeneration else {
        return
      }
      await processItem(item, generation: generation)
    }

    if !pendingItems.isEmpty {
      startFlushTimerIfNeeded()
    }
  }

  // MARK: - Formatting

  static func makeInput(ocrText: String, appName: String, windowTitle: String?) -> ScreenKGExtractionInput {
    let truncated =
      ocrText.count > 6_000 ? String(ocrText.prefix(6_000)) + "…" : ocrText
    return ScreenKGExtractionInput(ocrText: truncated, appName: appName, windowTitle: windowTitle)
  }

  static func contentHash(_ input: ScreenKGExtractionInput) -> String {
    let key = "[\(input.appName)]\(input.windowTitle ?? "")\n\(input.ocrText)"
    let digest = SHA256.hash(data: Data(key.utf8))
    return digest.prefix(16).map { String(format: "%02x", $0) }.joined()
  }

  // MARK: - Private

  private func startFlushTimerIfNeeded() {
    guard flushTask == nil else { return }
    flushTask = Task {
      try? await Task.sleep(nanoseconds: flushIntervalNanos)
      guard !Task.isCancelled else { return }
      await self.flushPendingExtractions()
    }
  }

  private func runBackfillBatch() async {
    do {
      let rows = try await fetchPending(50)
      for row in rows {
        await queueScreenshot(
          id: row.id, ocrText: row.ocrText, appName: row.appName, windowTitle: row.windowTitle)
      }
      if !rows.isEmpty {
        await flushPendingExtractions()
      }
    } catch {
      log("ScreenKnowledgeGraphExtractor: backfill fetch failed: \(error.localizedDescription)")
    }
  }

  private func processItem(_ item: PendingItem, generation: Int) async {
    do {
      let jsonText = try await extractEntities(item.input)
      guard generation == ownerGeneration else { return }

      if let parsed = KnowledgeGraphRecordBuilder.parseExtractionJSON(jsonText) {
        let records = KnowledgeGraphRecordBuilder.buildRecords(nodes: parsed.nodes, edges: parsed.edges)
        if !records.nodes.isEmpty || !records.edges.isEmpty {
          try await mergeGraph(nodes: records.nodes, edges: records.edges)
        }
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
        log("ScreenKnowledgeGraphExtractor: skipping screenshot \(item.id) — \(error.localizedDescription)")
        try? await markExtracted([item.id])
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
