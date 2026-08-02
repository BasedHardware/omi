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
    let ownerID: String
    let mergeCompleted: Bool
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
    @Sendable (_ limit: Int, _ afterID: Int64) async throws -> [(
      id: Int64, ocrText: String, appName: String, windowTitle: String?
    )]
  typealias OwnerIDProvider = @Sendable () async -> String?
  typealias GraphMerger =
    @Sendable (
      _ nodes: [LocalKGNodeRecord],
      _ edges: [LocalKGEdgeRecord],
      _ authorization: LocalMutationAuthorization
    ) async throws -> Void
  typealias OwnerMatchChecker = @Sendable (_ expectedOwnerID: String) -> Bool
  typealias ExtractionGate = @Sendable () -> Bool

  private let extractEntities: ExtractionBackend
  private let markExtracted: KGMarkedWriter
  private let fetchPending: PendingFetcher
  private let activeOwnerID: OwnerIDProvider
  private let mergeGraphImpl: GraphMerger
  private let ownerMatches: OwnerMatchChecker
  private let extractionEnabled: ExtractionGate
  private let backendAvailable: ExtractionGate

  private init() {
    self.extractEntities = { input in
      let allowCloudFallback = UserDefaults.standard.bool(forKey: .screenKnowledgeGraphCloudFallbackEnabled)
      guard let backend = ScreenKGExtractionBackendSelector.preferredBackend(allowCloudFallback: allowCloudFallback)
      else {
        throw ScreenKGExtractionError.onDeviceUnavailable
      }
      return try await backend.extractEntities(from: input)
    }
    self.markExtracted = { ids in
      try await RewindDatabase.shared.markScreenshotsKGExtracted(ids: ids)
    }
    self.fetchPending = { limit, afterID in
      try await RewindDatabase.shared.getScreenshotsPendingKGExtraction(limit: limit, afterID: afterID)
    }
    self.activeOwnerID = { RuntimeOwnerIdentity.currentOwnerId() }
    self.mergeGraphImpl = { nodes, edges, authorization in
      try await KnowledgeGraphStorage.shared.mergeGraph(
        nodes: nodes, edges: edges, authorization: authorization)
    }
    self.ownerMatches = { expectedOwnerID in
      RuntimeOwnerIdentity.currentOwnerId() == expectedOwnerID
        && !RuntimeOwnerIdentity.effectiveOwnerTransitionInProgress
    }
    self.extractionEnabled = {
      UserDefaults.standard.bool(forKey: .screenKnowledgeGraphExtractionEnabled)
    }
    self.backendAvailable = {
      let allowCloudFallback = UserDefaults.standard.bool(forKey: .screenKnowledgeGraphCloudFallbackEnabled)
      return ScreenKGExtractionBackendSelector.preferredBackend(allowCloudFallback: allowCloudFallback) != nil
    }
  }

  init(
    extractEntitiesForTesting: @escaping ExtractionBackend,
    markExtractedForTesting: @escaping KGMarkedWriter,
    fetchPendingForTesting: PendingFetcher? = nil,
    activeOwnerIDForTesting: @escaping OwnerIDProvider = { "test-owner" },
    mergeGraphForTesting: GraphMerger? = nil,
    ownerMatchesForTesting: OwnerMatchChecker? = nil,
    extractionEnabledForTesting: @escaping ExtractionGate = { true },
    backendAvailableForTesting: @escaping ExtractionGate = { true }
  ) {
    self.extractEntities = extractEntitiesForTesting
    self.markExtracted = markExtractedForTesting
    self.fetchPending =
      fetchPendingForTesting ?? { limit, afterID in
        try await RewindDatabase.shared.getScreenshotsPendingKGExtraction(
          limit: limit, afterID: afterID)
      }
    self.activeOwnerID = activeOwnerIDForTesting
    self.mergeGraphImpl =
      mergeGraphForTesting ?? { nodes, edges, authorization in
        try await KnowledgeGraphStorage.shared.mergeGraph(
          nodes: nodes, edges: edges, authorization: authorization)
      }
    self.ownerMatches =
      ownerMatchesForTesting ?? { expectedOwnerID in
        RuntimeOwnerIdentity.currentOwnerId() == expectedOwnerID
          && !RuntimeOwnerIdentity.effectiveOwnerTransitionInProgress
      }
    self.extractionEnabled = extractionEnabledForTesting
    self.backendAvailable = backendAvailableForTesting
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
  func queueScreenshot(
    id: Int64,
    ocrText: String,
    appName: String,
    windowTitle: String?,
    expectedOwnerID: String? = nil
  ) async {
    guard extractionEnabled(), backendAvailable() else { return }
    guard ocrText.count >= minTextLength else { return }
    guard let ownerID = await resolvedOwnerID(expectedOwnerID: expectedOwnerID) else { return }
    let generation = ownerGeneration

    let wasPausedForProductGate = pausedForProductGate
    if wasPausedForProductGate {
      pausedForProductGate = false
      backfillScheduled = false
    }

    let input = Self.makeInput(ocrText: ocrText, appName: appName, windowTitle: windowTitle)
    let hash = Self.contentHash(ocrText: ocrText, appName: appName, windowTitle: windowTitle)

    if recentHashes.contains(hash) {
      guard generation == ownerGeneration else { return }
      guard await resolvedOwnerID(expectedOwnerID: ownerID) != nil else { return }
      guard generation == ownerGeneration else { return }
      do {
        try await markExtracted([id])
      } catch {
        log(
          "ScreenKnowledgeGraphExtractor: failed to mark duplicate screenshot \(id): \(error.localizedDescription)"
        )
        if wasPausedForProductGate {
          await scheduleBackfillIfNeeded()
        }
        return
      }
      if wasPausedForProductGate {
        await scheduleBackfillIfNeeded()
      }
      return
    }

    guard generation == ownerGeneration else { return }
    pendingItems.append(
      PendingItem(
        id: id, input: input, contentHash: hash, ownerID: ownerID, mergeCompleted: false))

    if pendingItems.count >= maxPendingItems {
      await flushPendingExtractions()
    } else {
      startFlushTimerIfNeeded()
    }

    if wasPausedForProductGate {
      await scheduleBackfillIfNeeded()
    }
  }

  /// Backfill screenshots captured before the extractor shipped (capped per launch).
  func scheduleBackfillIfNeeded() async {
    guard extractionEnabled() else { return }
    guard backendAvailable() else {
      backfillScheduled = false
      return
    }
    guard !backfillScheduled else { return }
    backfillScheduled = true
    await runBackfillBatch()
  }

  func flushPendingExtractions() async {
    flushTask?.cancel()
    flushTask = nil
    guard extractionEnabled(), backendAvailable() else {
      pendingItems.removeAll()
      backfillScheduled = false
      return
    }
    guard !pendingItems.isEmpty else { return }
    guard !pausedForProductGate else { return }

    let generation = ownerGeneration
    let batch = Array(pendingItems.prefix(maxItemsPerFlush))
    pendingItems.removeFirst(min(maxItemsPerFlush, pendingItems.count))

    for item in batch {
      guard generation == ownerGeneration else {
        return
      }
      guard !pausedForProductGate else {
        pendingItems.removeAll()
        return
      }
      await processItem(item, generation: generation)
      if pausedForProductGate {
        pendingItems.removeAll()
        return
      }
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

  private func resolvedOwnerID(expectedOwnerID: String?) async -> String? {
    guard !RuntimeOwnerIdentity.effectiveOwnerTransitionInProgress else { return nil }
    guard let current = await activeOwnerID() else { return nil }
    if let expectedOwnerID {
      guard expectedOwnerID == current else { return nil }
      return expectedOwnerID
    }
    return current
  }

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
    var afterID: Int64 = 0
    let generation = ownerGeneration

    do {
      while processedThisLaunch < maxBackfillItemsPerLaunch {
        guard generation == ownerGeneration else { return }
        if pausedForProductGate { break }

        guard let ownerID = await resolvedOwnerID(expectedOwnerID: nil) else { return }
        guard generation == ownerGeneration else { return }

        let rows = try await fetchPending(backfillBatchSize, afterID)
        guard generation == ownerGeneration else { return }
        if rows.isEmpty { break }

        for row in rows {
          guard generation == ownerGeneration else { return }
          await queueScreenshot(
            id: row.id,
            ocrText: row.ocrText,
            appName: row.appName,
            windowTitle: row.windowTitle,
            expectedOwnerID: ownerID)
        }
        guard generation == ownerGeneration else { return }

        while !pendingItems.isEmpty {
          guard generation == ownerGeneration else { return }
          if pausedForProductGate { break }
          let before = pendingItems.count
          await flushPendingExtractions()
          if pendingItems.count >= before { break }
        }

        if let maxID = rows.map(\.id).max() {
          afterID = max(afterID, maxID)
        }
        processedThisLaunch += rows.count

        if pausedForProductGate { break }
        if !pendingItems.isEmpty {
          if !pausedForProductGate {
            startFlushTimerIfNeeded()
          }
          if processedThisLaunch >= maxBackfillItemsPerLaunch { break }
          try? await Task.sleep(nanoseconds: 200_000_000)
          continue
        }

        if processedThisLaunch < maxBackfillItemsPerLaunch {
          try? await Task.sleep(nanoseconds: 200_000_000)
        }
      }
    } catch {
      log("ScreenKnowledgeGraphExtractor: backfill fetch failed: \(error.localizedDescription)")
    }
  }

  private func processItem(_ item: PendingItem, generation: Int) async {
    guard await resolvedOwnerID(expectedOwnerID: item.ownerID) != nil else {
      requeueIfCurrentGeneration(item, mergeCompleted: item.mergeCompleted, generation: generation)
      return
    }

    var mergeCompleted = item.mergeCompleted
    do {
      if !mergeCompleted {
        let jsonText = try await extractEntities(item.input)
        guard generation == ownerGeneration else { return }
        guard await resolvedOwnerID(expectedOwnerID: item.ownerID) != nil else {
          requeueIfCurrentGeneration(item, mergeCompleted: false, generation: generation)
          return
        }

        guard let parsed = KnowledgeGraphRecordBuilder.parseExtractionJSON(jsonText) else {
          log(
            "ScreenKnowledgeGraphExtractor: invalid extraction JSON for screenshot \(item.id) — will retry"
          )
          requeueIfCurrentGeneration(item, mergeCompleted: false, generation: generation)
          return
        }

        let records = KnowledgeGraphRecordBuilder.buildRecords(nodes: parsed.nodes, edges: parsed.edges)
        if !records.nodes.isEmpty || !records.edges.isEmpty {
          try await mergeGraph(
            nodes: records.nodes,
            edges: records.edges,
            expectedOwnerID: item.ownerID,
            generation: generation)
          mergeCompleted = true
          guard generation == ownerGeneration else { return }
          guard await resolvedOwnerID(expectedOwnerID: item.ownerID) != nil else {
            requeueIfCurrentGeneration(item, mergeCompleted: true, generation: generation)
            return
          }
          await MainActor.run {
            ChatToolExecutor.onKnowledgeGraphUpdated?()
          }
        }
        mergeCompleted = true
      }

      guard generation == ownerGeneration else { return }
      guard await resolvedOwnerID(expectedOwnerID: item.ownerID) != nil else {
        requeueIfCurrentGeneration(item, mergeCompleted: mergeCompleted, generation: generation)
        return
      }
      try await markExtracted([item.id])
      guard generation == ownerGeneration else { return }
      recentHashes.insert(item.contentHash)
      if recentHashes.count > maxRecentHashes {
        recentHashes.removeAll(keepingCapacity: true)
      }
      log(
        "ScreenKnowledgeGraphExtractor: extracted from screenshot \(item.id) via \(backendName())")
    } catch {
      guard generation == ownerGeneration else { return }
      if let geminiError = error as? GeminiClient.GeminiClientError, geminiError.isExpectedProductState {
        pausedForProductGate = true
        log(
          "ScreenKnowledgeGraphExtractor: pausing — expected product state for screenshot \(item.id): \(error.localizedDescription)"
        )
        return
      }
      log("ScreenKnowledgeGraphExtractor: extraction failed for screenshot \(item.id): \(error.localizedDescription)")
      requeueIfCurrentGeneration(item, mergeCompleted: mergeCompleted, generation: generation)
    }
  }

  private func requeueIfCurrentGeneration(
    _ item: PendingItem,
    mergeCompleted: Bool,
    generation: Int
  ) {
    guard generation == ownerGeneration else { return }
    pendingItems.append(
      PendingItem(
        id: item.id,
        input: item.input,
        contentHash: item.contentHash,
        ownerID: item.ownerID,
        mergeCompleted: mergeCompleted))
  }

  private func mergeGraph(
    nodes: [LocalKGNodeRecord],
    edges: [LocalKGEdgeRecord],
    expectedOwnerID: String,
    generation: Int
  ) async throws {
    guard generation == ownerGeneration else {
      throw LocalMutationAuthorizationError.revoked
    }
    guard await resolvedOwnerID(expectedOwnerID: expectedOwnerID) != nil else {
      throw LocalMutationAuthorizationError.revoked
    }

    let expected = expectedOwnerID
    let matches = ownerMatches
    try await mergeGraphImpl(
      nodes,
      edges,
      LocalMutationAuthorization {
        matches(expected)
      })
  }

  private func backendName() -> String {
    let allowCloudFallback = UserDefaults.standard.bool(forKey: .screenKnowledgeGraphCloudFallbackEnabled)
    return ScreenKGExtractionBackendSelector.preferredBackend(allowCloudFallback: allowCloudFallback)?.name
      ?? "unavailable"
  }
}
